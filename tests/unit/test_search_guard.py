# -*- coding: utf-8 -*-
"""Regression: search() stores history only on the first entry, not on pagination.

The series view paginates with 'page' (offset stays 0) and the flat view with
'offset'; either present means a later page and must NOT re-store history
(which would re-fsync and reorder the recent list on every page click).
"""
from unittest import mock

import pytest


@pytest.mark.parametrize('params, stored', [
    ({'what': 'office'}, ['office']),
    ({'what': 'office', 'offset': '0'}, ['office']),     # explicit first page
    ({'what': 'office', 'offset': '25'}, []),            # flat view, later page
    ({'what': 'office', 'page': '1'}, []),               # series view, later page
], ids=['first-entry', 'explicit-first-page', 'flat-pagination', 'series-pagination'])
def test_history_is_stored_only_on_first_entry(params, stored):
    import lib.search_ui as su
    calls = []
    with mock.patch.object(su, 'storesearch', calls.append), \
         mock.patch.object(su, 'revalidate', lambda: 'tok'), \
         mock.patch.object(su, 'dosearch', lambda *a, **k: None), \
         mock.patch.object(su.xbmcplugin, 'setContent', lambda *a, **k: None), \
         mock.patch.object(su.xbmcplugin, 'setPluginCategory', lambda *a, **k: None):
        su.search(params)
    assert calls == stored


def test_browse_sentinel_is_never_stored():
    import lib.search_ui as su
    calls = []
    with mock.patch.object(su, 'storesearch', calls.append), \
         mock.patch.object(su, 'revalidate', lambda: 'tok'), \
         mock.patch.object(su, 'dosearch', lambda *a, **k: None), \
         mock.patch.object(su.xbmcplugin, 'setContent', lambda *a, **k: None), \
         mock.patch.object(su.xbmcplugin, 'setPluginCategory', lambda *a, **k: None):
        su.search({'what': su.NONE_WHAT})
    assert calls == []
