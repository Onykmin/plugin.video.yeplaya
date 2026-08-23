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

import io
import os
import threading

import xbmc
import xbmcgui
import xbmcplugin

from lib.api import revalidate
from lib.utils import popinfo, get_handle, get_addon, get_url, set_video_info
from lib.logging import log_debug
from lib.movie_pool import pick_random, load_pool
from lib.search_ui import storesearch
from lib.ui import CATEGORIES, SORTS

try:
    from xbmcvfs import translatePath
except ImportError:
    from xbmc import translatePath

try:
    import fcntl as _fcntl
except ImportError:
    _fcntl = None  # Non-POSIX (Windows): no cross-process guard available.

_handle = get_handle()
_addon = get_addon()

_LOCK_FILENAME = 'yeplaya-randommovie.lock'

# Grace period for reaping the fetch worker when Kodi is shutting down.
# Covers wdqs's own request ceiling (wdqs.REQUEST_TIMEOUT) plus the short
# atomic pool write that follows it, so the thread is not abandoned
# mid-write; bounded so a hung socket can never wedge Kodi's exit.
_ABORT_JOIN_SECONDS = 5.0

# How long the degraded-path "preparing movie list" toast stays up when the
# progress dialog is unavailable. Sized to lib/wdqs.py evidence archive's measured
# worst-case cold fetch (~31s), not popinfo's 3s default.
_FALLBACK_NOTICE_MS = 31000


def _acquire_picker_lock():
    """Acquire an exclusive, cross-process lock guarding the picker dialog.

    Duplicated from lib.playback._acquire_cross_process_lock (module-private
    there) rather than imported, to avoid coupling this module to playback's
    internals for one helper — mirrors why _setting_int above is duplicated
    from lib.search_ui.

    Kodi spawns a fresh interpreter per plugin call: several rapid clicks on
    the cold path (WDQS prefetch can take 5-31s, see movie_pool.py) each
    start their own process, each blocks in pick_random(), and each then
    shows its own xbmcgui.Dialog().select() — closing one just pops the
    next. This is a single global feature (only one picker dialog should
    ever be in flight at a time), so a fixed lock filename is fine — no
    per-ident scoping needed.

    Returns an open file handle to keep for the dialog's duration (close to
    release), or None if the lock is already held (another picker is in
    flight). On non-POSIX platforms (no fcntl), or if the lock file can't be
    created, returns the string 'noflock' so the caller still proceeds —
    never wedge the feature on a path/platform problem, only a genuinely
    held lock means another picker is running.
    """
    if _fcntl is None:
        return 'noflock'
    lock_path = os.path.join(translatePath('special://temp/'), _LOCK_FILENAME)
    try:
        fh = io.open(lock_path, 'w')
    except (IOError, OSError) as e:
        xbmc.log("yeplaya: random-movie lock file unavailable, proceeding "
                 "without cross-process lock: " + str(e), xbmc.LOGWARNING)
        return 'noflock'
    try:
        _fcntl.flock(fh.fileno(), _fcntl.LOCK_EX | _fcntl.LOCK_NB)
        return fh
    except (IOError, OSError):
        try:
            fh.close()
        except Exception:
            pass
        return None


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


def _pick_with_progress(excluded, progress):
    """Run pick_random() on a worker thread while sweeping `progress`.

    Kodi's DialogProgressBG renders the percentage as text next to its own
    busy spinner. A percentage that never changes therefore reads as HUNG —
    the user reported exactly that with a fixed 50 (a stuck grey arc beside
    a spinning white one). WDQS exposes no progress events, so there is no
    honest percentage to show; the only honest signal is MOTION.

    So: do the blocking fetch off-thread and sweep the bar from this thread
    while it runs. The sweep is deliberately capped below 100 (a bar that
    hits 100 and keeps waiting is its own lie) and is NOT a time estimate —
    measured latency spans 5-31s with a 4.5x spread on the identical query
    (lib/wdqs.py evidence archive; orig. doc §2.1), so any ETA would be fiction.

    Falls back to a plain synchronous call if the thread can't be started,
    so the feature never depends on the animation.
    """
    result = {}

    def _worker():
        try:
            result['item'] = pick_random(excluded)
        except Exception as e:  # surface via result, never kill the thread silently
            result['error'] = e

    try:
        worker = threading.Thread(target=_worker)
        worker.daemon = True
        worker.start()
    except Exception as e:
        log_debug('progress worker unavailable, fetching inline: {}'.format(e))
        return pick_random(excluded)

    # Sweep 0->95 in ~1% steps. xbmc.Monitor().waitForAbort doubles as the
    # sleep AND the shutdown check, so a Kodi quit mid-fetch stops the sweep
    # instead of spinning until the daemon thread is killed.
    monitor = xbmc.Monitor()
    percent = 0
    aborted = False
    while worker.is_alive():
        if monitor.waitForAbort(0.3):
            aborted = True
            break
        percent = min(percent + 1, 95)
        if progress is not None:
            try:
                progress.update(percent)
            except Exception:
                pass

    # Join long enough to actually reap the worker, not just token-poll it.
    # The old worker.join(0.1) was far shorter than the 5-31s fetch it was
    # waiting on (lib/wdqs.py evidence archive; orig. doc §2.1), so on a Kodi quit mid-fetch this
    # function returned while the daemon thread was still inside
    # movie_pool._mutate — i.e. holding a cross-process file lock and
    # part-way through an atomic write, during interpreter shutdown. On the
    # normal path the loop above has already seen the thread finish, so this
    # join returns immediately; the timeout only matters on abort.
    #
    # Bounded, never indefinite: a hung socket must not wedge Kodi's exit.
    # REQUEST_TIMEOUT is wdqs's own ceiling, so the worker cannot legitimately
    # outlive it; a small grace covers the disk write that follows.
    worker.join(_ABORT_JOIN_SECONDS if aborted else 0.1)
    if worker.is_alive():
        # Nothing safe left to do — the write path is guarded by an flock and
        # an atomic rename (lib/movie_pool._save_envelope), so a torn pool
        # file is not possible; log it so the case is visible rather than
        # silent.
        log_debug('pick worker still running after join; abandoning wait')

    if 'error' in result:
        raise result['error']
    return result.get('item')


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

    lock = _acquire_picker_lock()
    if lock is None:
        # Another random-movie picker is already in flight (e.g. a stacked
        # click during the slow cold-pool fetch below) — do NOT show a
        # second dialog on top of it; just resolve this extra invocation
        # away. This is the fix for the reported "closing the dialog makes
        # another one appear" symptom.
        popinfo(_addon.getLocalizedString(30454), icon=xbmcgui.NOTIFICATION_INFO)
        xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())
        return

    # Bound BEFORE the try: the finally block below closes it, and
    # revalidate() can raise — an unbound name there would mask the real
    # error with an UnboundLocalError.
    progress = None

    try:
        revalidate()

        # A cold (never-fetched) pool triggers a synchronous WDQS prefetch
        # inside pick_random() below. Measured 5-31s, with a 4.5x spread on
        # the IDENTICAL query within a minute (lib/wdqs.py evidence archive; orig. doc §2.1), so
        # there is no wait we can promise — only one we must keep visible.
        #
        # A popinfo() toast is NOT enough here: it self-dismisses after 3s
        # and leaves up to ~28s of dead silence, which is exactly what makes
        # the user click again ("if I click and nothing happens in short
        # time I will click again and again"). DialogProgressBG persists for
        # the whole fetch, so there is never a moment without a visual clue.
        # BG (not DialogProgress) deliberately: it must not steal focus from
        # or sit modally in front of the picker dialog that follows, and
        # this fetch has no cancel semantics to offer — movie_pool writes
        # the pool atomically or not at all.
        #
        # The percentage must ANIMATE, not sit still. A fixed value (we tried
        # 50) renders as a frozen number beside Kodi's own busy spinner, and
        # a stuck arc next to a spinning one reads as HUNG, not working
        # (user-reported, with screenshot). WDQS emits no progress events, so
        # the fetch runs on a worker thread below and the bar is swept from
        # this thread purely to convey liveness — see _sweep_progress.
        cold = not load_pool()
        if cold:
            try:
                progress = xbmcgui.DialogProgressBG()
                progress.create(_addon.getAddonInfo('name'),
                                _addon.getLocalizedString(30455))
                progress.update(0)
            except Exception as e:
                # Never let a UI nicety break the feature — fall back to the
                # toast if the progress dialog is unavailable.
                log_debug('progress dialog unavailable: {}'.format(e))
                progress = None
                # Degraded path: no progress bar available, so this toast is
                # the ONLY feedback during a 5-31s fetch. popinfo's 3s default
                # (lib/utils.py:111) would leave ~28s of silence — the exact
                # "I clicked and nothing happened so I clicked again" symptom
                # the progress dialog exists to prevent. Hold it for the
                # measured worst case instead.
                popinfo(_addon.getLocalizedString(30455),
                        icon=xbmcgui.NOTIFICATION_INFO,
                        time=_FALLBACK_NOTICE_MS)

        excluded = set()

        first_pick = True
        while True:
            if first_pick and progress is not None:
                # Only the first pick can trigger the slow WDQS prefetch;
                # every later reroll reads the now-warm pool from disk.
                item = _pick_with_progress(excluded, progress)
            else:
                item = pick_random(excluded)
            first_pick = False
            # The slow part is over (pick_random returned, pool now on disk).
            # Close the progress bar BEFORE any dialog below so the two are
            # never on screen together.
            if progress is not None:
                try:
                    progress.close()
                except Exception:
                    pass
                progress = None
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
    finally:
        # Belt-and-braces: a DialogProgressBG left open would persist for the
        # whole Kodi session, so close it on every exit path (early return,
        # exception) — not just the happy one above.
        if progress is not None:
            try:
                progress.close()
            except Exception:
                pass
        if lock not in (None, 'noflock'):
            try:
                lock.close()
            except Exception:
                pass
