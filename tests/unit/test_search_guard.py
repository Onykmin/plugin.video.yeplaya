#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression: search() stores history only on first entry, not on pagination.

The series view paginates with 'page' (offset stays 0) and the flat view with
'offset'; either present means a later page and must NOT re-store history
(which would re-fsync and reorder the recent list on every page click).
"""

import unittest
import unittest.mock as mock

import tests.conftest  # noqa: F401 — installs Kodi mocks


class TestStoreSearchGuard(unittest.TestCase):
    def setUp(self):
        # Import inside setUp so the autouse mock-restore fixture (which may
        # purge lib.* after integration-test pollution) takes effect first.
        import lib.search_ui as su
        self.su = su

    def _run(self, params):
        su = self.su
        calls = []
        with mock.patch.object(su, 'storesearch', lambda w: calls.append(w)), \
             mock.patch.object(su, 'revalidate', lambda: 'tok'), \
             mock.patch.object(su, 'dosearch', lambda *a, **k: None), \
             mock.patch.object(su.xbmcplugin, 'setContent', lambda *a, **k: None), \
             mock.patch.object(su.xbmcplugin, 'setPluginCategory', lambda *a, **k: None):
            su.search(params)
        return calls

    def test_first_entry_stores(self):
        self.assertEqual(self._run({'what': 'office'}), ['office'])

    def test_flat_view_pagination_does_not_store(self):
        self.assertEqual(self._run({'what': 'office', 'offset': '25'}), [])

    def test_series_view_pagination_does_not_store(self):
        # 'page' present (offset implicitly 0) → later page, must not store.
        self.assertEqual(self._run({'what': 'office', 'page': '1'}), [])

    def test_browse_sentinel_does_not_store(self):
        self.assertEqual(self._run({'what': self.su.NONE_WHAT}), [])

    def test_explicit_first_page_stores(self):
        # offset=0 and no page param is still the first entry.
        self.assertEqual(self._run({'what': 'office', 'offset': '0'}), ['office'])


if __name__ == '__main__':
    unittest.main()
