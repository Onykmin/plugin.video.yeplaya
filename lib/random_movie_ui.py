# -*- coding: utf-8 -*-
# Module: random_movie_ui
# Author: onykmin
# License: AGPL v.3 https://www.gnu.org/licenses/agpl-3.0.html

"""Random-movie picker: one-click search fill from the WDQS-backed pool.

Mirrors lib.series_ui's random-episode picker's idiom (commit d6723f3):
an in-process reroll loop over an in-memory `excluded` set of Q-ids, scoped
to this single Kodi action only (Kodi is one-process-per-action, so backing
out and re-entering deliberately starts fresh — same contract as episodes).
"""

import xbmc
import xbmcgui
import xbmcplugin

from lib.api import revalidate
from lib.utils import popinfo, get_handle, get_addon, get_url, set_video_info
from lib.logging import log_debug
from lib.movie_pool import pick_random, load_pool
from lib.search_ui import storesearch
from lib.ui import CATEGORIES, SORTS

_handle = get_handle()
_addon = get_addon()


def _setting_int(key, default):
    """Read int setting with fallback for empty/garbage values.

    Duplicated from lib.search_ui (module-private there) rather than
    imported, to avoid growing that module's public surface for one helper.
    """
    try:
        raw = _addon.getSetting(key)
        if raw is None or raw == '':
            return default
        return int(raw)
    except (ValueError, TypeError):
        return default


def _display_title(item):
    """Pick ONE title to show/search for this film — cs first, else en.

    How many language labels the underlying Wikidata record carries (one or
    two) is an internal data detail; the dialog and search behaviour must be
    byte-identical either way (user report: "I do not care if there is only
    one language?!; I should click and see random movie!"). cs is preferred
    over en because this addon is Czech/Slovak-facing (lib/language.py's
    audio/subtitle matching, and the cs/sk strings.po translations) — when a
    Czech title exists it is the more useful one to search Webshare with.
    Returns None only if the item has neither (structurally shouldn't happen,
    movie_pool guarantees at least one of cs/en is non-None).
    """
    return item.get('cs') or item.get('en')


def _build_dialog_rows(title, year=None):
    """Assemble the fixed 3-row dialog: film / Reroll / Cancel.

    Always exactly 3 rows, regardless of how many titles the drawn film's
    record actually has, and regardless of whether a year is known — no
    branching on title OR year count anywhere in this dialog's shape (the
    existing uniformity invariant: how many language labels a record
    carries must never be observable, and the same now holds for year
    presence — it can only ever change this one row's TEXT, never the row
    count). Mirrors this addon's existing picker idiom: both
    lib.series_ui's version-picker and the random-episode picker (commit
    d6723f3) show "the drawn item plus a reroll affordance"; this is the
    same shape, just for one drawn film instead of one drawn episode.

    `year`, when known, is DISPLAY-ONLY: it is folded into string 30450's
    row text as "Title (Year)" but never into `actions` — the search/store
    string must stay the bare title (appending "(1998)" would wreck
    Webshare search results). Reuses string 30450 for both cases (bare
    title vs "Title (Year)") rather than adding a new string id.

    Returns (listitems, actions) where actions[i] names what selecting row i
    does, so row order and dispatch can never drift apart — same contract as
    lib.series_ui._build_dialog_rows.
    """
    row_text = '{} ({})'.format(title, year) if year else title
    film_item = xbmcgui.ListItem(label=_addon.getLocalizedString(30450).format(row_text))
    if year:
        # Info-label only (Matrix-safe via set_video_info) — purely a Kodi
        # metadata annotation on this ListItem, never fed to search/store.
        set_video_info(film_item, {'year': year})
    listitems = [
        film_item,
        xbmcgui.ListItem(label=_addon.getLocalizedString(30448)),
        xbmcgui.ListItem(label=_addon.getLocalizedString(30449)),
    ]
    actions = [('search', title), ('reroll', None), ('cancel', None)]
    return listitems, actions


def _run_search(title):
    """Hand off `title` to a real search exactly as newsearch() does.

    `random_movie` is a resolve action (main.py's _RESOLVE_ACTIONS), invoked
    via PlayMedia — it is NOT a directory-listing context. dosearch() renders
    with addDirectoryItem/endOfDirectory into a handle Kodi never opened as a
    directory, so results are silently discarded (the reported bug: dialog
    closes, nothing renders). The fix is the same contract newsearch() uses:
    setResolvedUrl(False) to close out this resolve cleanly, then
    Container.Update to hand off to a NEW action that opens its own
    directory handle. storesearch() still runs here first so the picked
    title lands in history like a manual search ("like I would do").

    NOTE: because the search now happens in a separate, unobservable Kodi
    action, this function cannot know whether the search came back empty —
    do NOT re-add auto-reroll-on-empty here; that behaviour was removed
    precisely because it requires seeing dosearch()'s result in-process.
    """
    storesearch(title)
    category = CATEGORIES[_setting_int('scategory', 0)]
    sort = SORTS[_setting_int('ssort', 0)]
    limit = _setting_int('slimit', 25)
    url = get_url(action='search', what=title, category=category, sort=sort,
                  limit=limit, offset=0)
    xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())
    xbmc.executebuiltin("Container.Update({})".format(url))


def show_random_movie_dialog(params):
    """Pick a random movie from the WDQS pool and let the user confirm it.

    One click, one random movie, EVERY time — byte-identical dialog shape
    regardless of how many titles the drawn film's Wikidata record has (one
    or two). That title count is an internal data detail with zero
    observable effect: the dialog always has exactly 3 rows (film / Reroll
    / Cancel; see _build_dialog_rows), and _display_title always resolves
    to exactly one title to show and search. Two earlier designs are
    deliberately NOT used here: auto-searching straight through with no
    dialog when the film had only one title (silently skipped the
    confirmation step — the whole point of this feature — on the majority
    of picks, measured 58.7% of the live pool), and a dialog whose row
    count grew to two title rows for two-title films (let the user infer,
    from the UI, how many titles a record happened to carry). Both made the
    experience vary by data shape instead of being predictable.
    """
    log_debug('show_random_movie_dialog called with params: {}'.format(params))
    revalidate()

    excluded = set()

    while True:
        item = pick_random(excluded)
        if item is None:
            # pick_random() returning None conflates two different causes:
            # a genuine pool exhaustion (every pool item already excluded)
            # vs. the pool itself being empty because the WDQS fetch failed
            # (e.g. an outage). load_pool() is a pure disk read — safe to
            # call again here just to tell the two apart for the user.
            if load_pool():
                popinfo(_addon.getLocalizedString(30447), icon=xbmcgui.NOTIFICATION_WARNING)
            else:
                popinfo(_addon.getLocalizedString(30453), icon=xbmcgui.NOTIFICATION_WARNING)
            xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())
            return

        # Mark seen immediately so a reroll never re-offers the same film.
        excluded.add(item['id'])

        title = _display_title(item)
        if not title:
            # Structurally shouldn't happen (movie_pool guarantees at least
            # one of cs/en is non-None), but never search an empty string.
            continue

        listitems, actions = _build_dialog_rows(title, item.get('y'))
        selected = xbmcgui.Dialog().select(
            _addon.getLocalizedString(30446), listitems, useDetails=False)
        chosen_action, chosen_title = actions[selected] if 0 <= selected < len(actions) else ('cancel', None)

        if chosen_action == 'cancel':
            xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())
            return

        if chosen_action == 'reroll':
            continue

        # chosen_action == 'search': hand off to a real search action. This
        # ends the loop unconditionally — see _run_search's docstring for
        # why an empty-result reroll is no longer possible from here.
        _run_search(chosen_title)
        return
