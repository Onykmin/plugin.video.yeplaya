#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The pick-variant modals (episode + movie) rank versions SIZE-FIRST: the
biggest file wins, quality_score only breaks ties between equal-size
entries. Mirrors `series_ui._rank_versions`.

This deliberately differs from `grouping._version_sort_key`, which is
quality-first and feeds the grouping/merge passes, not the user-facing pick
lists.

Drives the real dialog builders and captures the order handed to
xbmcgui.Dialog().select(), which is the order the user sees and the index
`resolve_and_play` maps back through.

Renamed from test_modal_size_sort.py: not because the primary key changed
(it hasn't — size-first is unchanged and still asserted below), but because
this module now covers the whole version-ordering contract, primary key AND
tiebreak, rather than just the "largest-first" primary key alone.
"""
import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

import tests.conftest  # noqa: F401 — installs Kodi mocks

from lib import series_ui


def _capture_select_order(grouped, params, fn):
    """Run `fn(params)` with the grouping/enrichment seams stubbed and return
    the list of version dicts in the order passed to dialog.select()."""
    captured = {}

    class _Dlg:
        def select(self, heading, listitems, useDetails=False):
            # Record the labels shown, in order; -1 = user cancelled.
            captured['labels'] = [li.label for li in listitems]
            return -1

        def ok(self, *a, **k):
            pass

    # Patch Dialog on whatever xbmcgui object series_ui is currently bound to
    # (integration tests may have swapped sys.modules['xbmcgui'] for a bare
    # mock, so patch the live module rather than an import-time reference).
    xbmcgui_mod = sys.modules['xbmcgui']
    with patch.object(series_ui, 'revalidate', return_value='tok'), \
         patch.object(series_ui, 'get_or_fetch_grouped',
                      return_value=('ck', grouped)), \
         patch.object(series_ui, 'enrich_file_metadata', lambda *a, **k: None), \
         patch.object(xbmcgui_mod, 'Dialog', _Dlg):
        fn(params)
    return captured.get('labels', [])


def test_episode_modal_size_breaks_quality_ties():
    # All three names use underscore-separated resolutions
    # (e.g. 'small_720p.mkv'), so parse_quality_metadata's
    # \b(2160p|4K|1080p|720p|480p)\b regex finds no word boundary and every
    # fixture scores the default 50 by design — a genuine tie. That tie is
    # exactly what makes size the deciding factor here.
    versions = [
        {'ident': 'a', 'name': 'small_720p.mkv', 'size': '100'},
        {'ident': 'b', 'name': 'big_1080p.mkv', 'size': '900'},
        {'ident': 'c', 'name': 'mid_1080p.mkv', 'size': '500'},
    ]
    grouped = {'series': {'show': {'display_name': 'Show',
                                   'seasons': {1: {1: versions}}}}}
    params = {'series': 'show', 'season': '1', 'episode': '1', 'what': 'q'}
    labels = _capture_select_order(grouped, params, series_ui.show_version_dialog)
    assert labels == ['big_1080p.mkv', 'mid_1080p.mkv', 'small_720p.mkv'], labels


def test_movie_modal_size_breaks_quality_ties():
    # Same underscore-resolution trick as above: all three fixtures score
    # the default 50, so this is a tie-break test, not a primary-key test.
    versions = [
        {'ident': 'a', 'name': 'small.mkv', 'size': '200'},
        {'ident': 'b', 'name': 'huge.mkv', 'size': '5000'},
        {'ident': 'c', 'name': 'mid.mkv', 'size': '1500'},
    ]
    grouped = {'movies': {'inception|2010': {
        'display_name': 'Inception', 'year': 2010,
        'versions': versions, 'canonical_key': 'inception|2010'}}}
    params = {'movie_key': 'inception|2010', 'what': 'q'}
    labels = _capture_select_order(grouped, params, series_ui.select_movie_version)
    assert labels == ['huge.mkv', 'mid.mkv', 'small.mkv'], labels


def test_episode_modal_size_beats_quality():
    """Primary key is file size: the BIGGER file wins even when the smaller
    one scores higher on quality. Space/dot-separated names so the resolution
    regex matches and scores genuinely differ (1080p+WEB-DL=90 vs 720p=60)."""
    versions = [
        {'ident': 'small_hq', 'name': 'Show.S01E01.1080p.WEB-DL.x264.mkv', 'size': '100'},
        {'ident': 'big_lq', 'name': 'Show.S01E01.720p.x264.mkv', 'size': '9000'},
    ]
    grouped = {'series': {'show': {'display_name': 'Show',
                                   'seasons': {1: {1: versions}}}}}
    params = {'series': 'show', 'season': '1', 'episode': '1', 'what': 'q'}
    labels = _capture_select_order(grouped, params, series_ui.show_version_dialog)
    assert labels == [
        'Show.S01E01.720p.x264.mkv',
        'Show.S01E01.1080p.WEB-DL.x264.mkv',
    ], labels


def test_movie_modal_size_beats_quality():
    """Same primary-key proof for the movie version picker."""
    versions = [
        {'ident': 'small_hq', 'name': 'Movie.2020.1080p.WEB-DL.x264.mkv', 'size': '100'},
        {'ident': 'big_lq', 'name': 'Movie.2020.720p.x264.mkv', 'size': '9000'},
    ]
    grouped = {'movies': {'movie|2020': {
        'display_name': 'Movie', 'year': 2020,
        'versions': versions, 'canonical_key': 'movie|2020'}}}
    params = {'movie_key': 'movie|2020', 'what': 'q'}
    labels = _capture_select_order(grouped, params, series_ui.select_movie_version)
    assert labels == [
        'Movie.2020.720p.x264.mkv',
        'Movie.2020.1080p.WEB-DL.x264.mkv',
    ], labels


def test_movie_modal_enriches_top5_by_size_and_skips_already_enriched():
    """After FIX 1, select_movie_version shares _prepare_episode_versions
    with the episode picker: rank-then-enrich-top-5, not the old
    enrich-then-rank inline copy. This pins the resulting contract for the
    movie dialog specifically:

    (a) enrich_file_metadata is called at most 5 times (TOP_FILES_TO_ENRICH),
        even with >5 versions in play;
    (b) the enriched idents are (a subset of) the top-5 by the SIZE-FIRST
        ranking, never the first 5 of the input/API order — the fixture's
        input order is deliberately the REVERSE of size order, so "first 5
        of input" and "top 5 by size" are disjoint sets, leaving no overlap
        to mask a regression that swaps rank-then-enrich back to
        enrich-then-rank;
    (c) a version that already carries 'file_info' is NOT re-enriched (the
        guard inside _prepare_episode_versions' top-5 loop) — its rank slot
        is simply skipped, it does not roll over to the 6th-ranked entry.
    """
    # 7 versions, input order = ascending size (i.e. reverse of the size-
    # first rank, which is descending). Ranked order is v7,v6,v5,v4,v3,v2,v1.
    # v7 (rank #1) already carries file_info, so it is skipped by the guard;
    # the top-5 rank slots [v7,v6,v5,v4,v3] therefore yield enrich calls for
    # v6,v5,v4,v3 only (4 calls) — v2/v1 (ranks #6/#7) must never be touched.
    versions = [
        {'ident': 'v1', 'name': 'Movie.2020.v1.mkv', 'size': '100'},
        {'ident': 'v2', 'name': 'Movie.2020.v2.mkv', 'size': '200'},
        {'ident': 'v3', 'name': 'Movie.2020.v3.mkv', 'size': '300'},
        {'ident': 'v4', 'name': 'Movie.2020.v4.mkv', 'size': '400'},
        {'ident': 'v5', 'name': 'Movie.2020.v5.mkv', 'size': '500'},
        {'ident': 'v6', 'name': 'Movie.2020.v6.mkv', 'size': '600'},
        {'ident': 'v7', 'name': 'Movie.2020.v7.mkv', 'size': '700', 'file_info': {'audio': 'en'}},
    ]
    grouped = {'movies': {'movie|2020': {
        'display_name': 'Movie', 'year': 2020,
        'versions': versions, 'canonical_key': 'movie|2020'}}}
    params = {'movie_key': 'movie|2020', 'what': 'q'}

    def _fake_enrich(file_dict, ident, token):
        file_dict['file_info'] = {'audio': 'en'}
        return True

    enrich_spy = MagicMock(side_effect=_fake_enrich)

    class _Dlg:
        def select(self, heading, listitems, useDetails=False):
            return -1

        def ok(self, *a, **k):
            pass

    xbmcgui_mod = sys.modules['xbmcgui']
    with patch.object(series_ui, 'revalidate', return_value='tok'), \
         patch.object(series_ui, 'get_or_fetch_grouped', return_value=('ck', grouped)), \
         patch.object(series_ui, 'enrich_file_metadata', enrich_spy), \
         patch.object(xbmcgui_mod, 'Dialog', _Dlg):
        series_ui.select_movie_version(params)

    # (a) at most 5 enrichment calls (never more than TOP_FILES_TO_ENRICH).
    assert enrich_spy.call_count <= 5

    enriched_idents = {call.args[1] for call in enrich_spy.call_args_list}

    # (b) every enriched ident is among the top-5 by size-first rank
    # (v3..v7), never one of the bottom-2 (v1, v2) that "first 5 of
    # ascending input order" would have picked instead.
    assert enriched_idents.issubset({'v3', 'v4', 'v5', 'v6', 'v7'})
    assert not enriched_idents & {'v1', 'v2'}

    # (c) v7 already carried 'file_info' going in, so it must NOT be
    # re-enriched, and its rank-#1 slot is simply skipped rather than
    # rolling over to v2/v1 — exactly 4 calls, for v3..v6.
    assert 'v7' not in enriched_idents
    assert enriched_idents == {'v3', 'v4', 'v5', 'v6'}
    assert enrich_spy.call_count == 4
