#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The pick-variant modals (episode + movie) must list versions largest-first.

Drives the real dialog builders and captures the order handed to
xbmcgui.Dialog().select(), which is the order the user sees and the index
`resolve_and_play` maps back through.
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


def test_episode_modal_sorted_by_size_desc():
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


def test_movie_modal_sorted_by_size_desc():
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
