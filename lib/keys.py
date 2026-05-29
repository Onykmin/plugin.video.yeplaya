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

# Browse sentinel for "no query" (Newest / Biggest) listings. The single
# definition; ui.NONE_WHAT and cache key normalization both alias this.
NONE_WHAT = '%#NONE#%'


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
