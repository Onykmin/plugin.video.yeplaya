# -*- coding: utf-8 -*-
# Module: keys
# Author: onykmin
# License: AGPL v.3 https://www.gnu.org/licenses/agpl-3.0.html

"""Canonical key/identity helpers — the single source of truth for the
durable layers (playback state, favorites, drift resolution).

Dual-name detection in grouping.py produces canonical_keys whose pipe-
separated form depends on which alias appears in a given Webshare response
(e.g. "the penguin|tucnak" vs "tucnak"). Any layer that must recognise the
SAME content across separate fetches — state.py (watched/resume), favorites,
and the series_ui drift fallback — funnels through these functions so they
all agree on identity instead of each inventing its own match heuristic.

This module has no intra-package imports on purpose: it sits below state,
favorites, cache and ui so all of them can share it without import cycles.
"""

import re

# Browse sentinel for "no query" (Newest / Biggest) listings. The single
# definition; ui.NONE_WHAT and cache key normalization both alias this.
NONE_WHAT = '%#NONE#%'

_RE_SEASON_TOKEN = re.compile(r'(?:^| )se?(\d{1,2})(?: |$)')
# "peaky blinders 02": `Name NN - MM` used to bind the season number into the name.
_RE_BARE_SEASON_SUFFIX = re.compile(r' (\d{1,2})$')


def normalize_series_key(series):
    """Strip the dual-name prefix to stabilize a series identity across fetches.

    The user-visible "main" name is the segment AFTER the last "|"; using that
    alone makes "the penguin|tucnak" and "tucnak" resolve to the same identity.
    Returns the input unchanged when there is no pipe.
    """
    if not series or '|' not in series:
        return series
    return series.rsplit('|', 1)[-1]


def normalize_movie_key(canonical):
    """Strip the dual-name prefix in a movie canonical_key, preserve the year.

    Movie keys are "{name}|{year}" or "{dual_canonical}|{year}" where the
    dual_canonical itself contains "|". Split on the LAST "|" to peel off the
    year, strip the dual-name prefix from the name part, and re-join. The year
    is retained so different-year releases of the same title stay distinct.
    """
    if not canonical or '|' not in canonical:
        return canonical
    name_part, _, year = canonical.rpartition('|')
    return "{0}|{1}".format(normalize_series_key(name_part), year)


def alias_keys(own_key, merged_keys, normalize):
    """Sorted aliases of a merged group: every key it was merged from, plus each
    one's normalized form, minus the group's own key.

    Any of the merged keys could have been the (order-dependent) survivor under
    older code, so state rows / favorites stored under them must still resolve.
    """
    out = set()
    for k in merged_keys:
        out.add(k)
        out.add(normalize(k))
    out.discard(own_key)
    return sorted(k for k in out if k)


def identity_set(key, aliases, normalize):
    """Normalized identities a group answers to: its own and every alias's."""
    return {normalize(k) for k in (key, *(aliases or ())) if k}


def season_in_key(key):
    """Season of a season token a key still carries ("suits s03" -> 3), else None."""
    found = _RE_SEASON_TOKEN.search(key)
    return int(found.group(1)) if found else None


def legacy_row_seasons(alias, season, base=None):
    """Seasons an episode row stored under `alias` may carry for a file of `season`.

    The parser used to leave an unread season marker in the series name ("suits s03") or bind a
    season number before a dash into it ("peaky blinders 02") and file the episode under season 1,
    so a row under an alias that still names the file's season may be S01 as well as S03.
    An alias that is `base` plus a season token holds the rows of THAT season's files only: a file
    of another season (a genuine S01E05) never reads it, its episode number means other content.
    """
    try:
        season = int(season)
    except (TypeError, ValueError):
        return [season]
    suffix = _RE_BARE_SEASON_SUFFIX.search(alias)
    named = {season_in_key(alias), int(suffix.group(1)) if suffix else None} - {None}
    if base and named and season not in named and _season_alias_of(alias, base):
        return []
    return [season, 1] if season in named and season != 1 else [season]


def _season_alias_of(alias, base):
    """True when `alias` is `base` with a season token ("suits s03", "peaky blinders 02")."""
    stripped = _RE_BARE_SEASON_SUFFIX.sub('', _RE_SEASON_TOKEN.sub(' ', alias)).strip()
    return normalize_series_key(stripped) == normalize_series_key(base)
