#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for lib.search_ui.dosearch's SEARCH_OK/EMPTY/FAILED signal.

Covers all five exits (brief §1.7 item 8, the highest-risk refactor):
  1. response is None -> SEARCH_FAILED
  2. empty files at offset 0 -> SEARCH_EMPTY
  3. is_ok(xml) False -> SEARCH_FAILED
  4. flat render -> SEARCH_OK
  5. series render -> SEARCH_OK

Plus the close_directory=False contract: endOfDirectory NOT called and the
30108 "no results" popinfo NOT fired on EMPTY/FAILED; the default
close_directory=True must still call endOfDirectory exactly as before
(backward-compat guard for the pre-existing test suite).
"""

import unittest
import unittest.mock as mock

import tests.conftest  # noqa: F401 — installs Kodi mocks

import lib.search_ui as search_ui
from lib.search_ui import SEARCH_OK, SEARCH_EMPTY, SEARCH_FAILED


def _make_response(xml_bytes):
    resp = mock.MagicMock()
    resp.content = xml_bytes
    return resp


_OK_EMPTY_XML = (
    b'<response><status>OK</status><total>0</total></response>'
)

_OK_ONE_FILE_XML = (
    b'<response><status>OK</status><total>1</total>'
    b'<file><ident>abc123</ident><name>Some.Movie.2020.1080p.mkv</name>'
    b'<size>123456</size></file>'
    b'</response>'
)

_NOT_OK_XML = (
    b'<response><status>FATAL</status></response>'
)


class DosearchSignalTestBase(unittest.TestCase):
    def setUp(self):
        self._saved_api = search_ui.api
        self._saved_display_series_list = search_ui.display_series_list
        self._saved_fetch_and_group_series = search_ui.fetch_and_group_series
        self._saved_popinfo = search_ui.popinfo
        self._saved_get_addon_setting = search_ui._addon.getSetting

        self.popinfo_calls = []
        search_ui.popinfo = lambda message, **kw: self.popinfo_calls.append(message)

        xbmcplugin_mod = search_ui.xbmcplugin
        self._saved_end_of_directory = xbmcplugin_mod.endOfDirectory
        self.end_of_directory_calls = []
        xbmcplugin_mod.endOfDirectory = lambda *a, **k: self.end_of_directory_calls.append((a, k))

        self._saved_add_directory_item = xbmcplugin_mod.addDirectoryItem
        xbmcplugin_mod.addDirectoryItem = lambda *a, **k: None

        # Force flat view by default so tests aren't tripped by the series
        # grouping path unless explicitly testing it. default_view='1' means
        # "Flat" per dosearch's own logic (prefer_series = default_view=='0').
        self._settings = {'default_view': '1'}
        search_ui._addon.getSetting = lambda key: self._settings.get(key, '')

    def tearDown(self):
        search_ui.api = self._saved_api
        search_ui.display_series_list = self._saved_display_series_list
        search_ui.fetch_and_group_series = self._saved_fetch_and_group_series
        search_ui.popinfo = self._saved_popinfo
        search_ui._addon.getSetting = self._saved_get_addon_setting
        search_ui.xbmcplugin.endOfDirectory = self._saved_end_of_directory
        search_ui.xbmcplugin.addDirectoryItem = self._saved_add_directory_item


# ---------------------------------------------------------------------------
# Exit 1: response is None -> SEARCH_FAILED
# ---------------------------------------------------------------------------

class TestResponseNone(DosearchSignalTestBase):
    def test_response_none_returns_failed(self):
        search_ui.api = lambda *a, **k: None
        result = search_ui.dosearch('tok', 'foo', '', '', 25, 0, 'search')
        self.assertEqual(result, SEARCH_FAILED)

    def test_response_none_pops_30107_and_closes_directory_by_default(self):
        search_ui.api = lambda *a, **k: None
        search_ui.dosearch('tok', 'foo', '', '', 25, 0, 'search')
        self.assertEqual(self.popinfo_calls, [search_ui._addon.getLocalizedString(30107)])
        self.assertEqual(len(self.end_of_directory_calls), 1)

    def test_response_none_close_directory_false_still_pops_30107_but_no_end(self):
        """The 30107 API-failure popinfo always fires, per the brief, even
        when close_directory=False; only endOfDirectory is suppressed."""
        search_ui.api = lambda *a, **k: None
        result = search_ui.dosearch('tok', 'foo', '', '', 25, 0, 'search',
                                     close_directory=False)
        self.assertEqual(result, SEARCH_FAILED)
        self.assertEqual(self.popinfo_calls, [search_ui._addon.getLocalizedString(30107)])
        self.assertEqual(self.end_of_directory_calls, [])


# ---------------------------------------------------------------------------
# Exit 2: empty files at offset 0 -> SEARCH_EMPTY
# ---------------------------------------------------------------------------

class TestEmptyResult(DosearchSignalTestBase):
    def test_empty_at_offset_zero_returns_empty(self):
        search_ui.api = lambda *a, **k: _make_response(_OK_EMPTY_XML)
        result = search_ui.dosearch('tok', 'foo', '', '', 25, 0, 'search')
        self.assertEqual(result, SEARCH_EMPTY)

    def test_empty_default_close_directory_pops_30108_and_ends(self):
        search_ui.api = lambda *a, **k: _make_response(_OK_EMPTY_XML)
        search_ui.dosearch('tok', 'foo', '', '', 25, 0, 'search')
        self.assertEqual(self.popinfo_calls, [search_ui._addon.getLocalizedString(30108)])
        self.assertEqual(len(self.end_of_directory_calls), 1)

    def test_empty_close_directory_false_no_popinfo_no_end(self):
        search_ui.api = lambda *a, **k: _make_response(_OK_EMPTY_XML)
        result = search_ui.dosearch('tok', 'foo', '', '', 25, 0, 'search',
                                     close_directory=False)
        self.assertEqual(result, SEARCH_EMPTY)
        self.assertEqual(self.popinfo_calls, [])
        self.assertEqual(self.end_of_directory_calls, [])


# ---------------------------------------------------------------------------
# Exit 3: is_ok(xml) False -> SEARCH_FAILED
# ---------------------------------------------------------------------------

class TestNotOkXml(DosearchSignalTestBase):
    def test_not_ok_returns_failed(self):
        search_ui.api = lambda *a, **k: _make_response(_NOT_OK_XML)
        result = search_ui.dosearch('tok', 'foo', '', '', 25, 0, 'search')
        self.assertEqual(result, SEARCH_FAILED)

    def test_not_ok_default_pops_30107_and_ends(self):
        search_ui.api = lambda *a, **k: _make_response(_NOT_OK_XML)
        search_ui.dosearch('tok', 'foo', '', '', 25, 0, 'search')
        self.assertEqual(self.popinfo_calls, [search_ui._addon.getLocalizedString(30107)])
        self.assertEqual(len(self.end_of_directory_calls), 1)

    def test_not_ok_close_directory_false_pops_30107_but_no_end(self):
        search_ui.api = lambda *a, **k: _make_response(_NOT_OK_XML)
        result = search_ui.dosearch('tok', 'foo', '', '', 25, 0, 'search',
                                     close_directory=False)
        self.assertEqual(result, SEARCH_FAILED)
        self.assertEqual(self.popinfo_calls, [search_ui._addon.getLocalizedString(30107)])
        self.assertEqual(self.end_of_directory_calls, [])


# ---------------------------------------------------------------------------
# Exit 4: flat render -> SEARCH_OK
# ---------------------------------------------------------------------------

class TestFlatRenderOk(DosearchSignalTestBase):
    def test_flat_render_returns_ok(self):
        search_ui.api = lambda *a, **k: _make_response(_OK_ONE_FILE_XML)
        result = search_ui.dosearch('tok', 'foo', '', '', 25, 0, 'search')
        self.assertEqual(result, SEARCH_OK)

    def test_flat_render_always_closes_directory_even_if_close_directory_false(self):
        """OK always closes — that caller is done, handle or no handle."""
        search_ui.api = lambda *a, **k: _make_response(_OK_ONE_FILE_XML)
        result = search_ui.dosearch('tok', 'foo', '', '', 25, 0, 'search',
                                     close_directory=False)
        self.assertEqual(result, SEARCH_OK)
        self.assertEqual(len(self.end_of_directory_calls), 1)

    def test_flat_render_no_failure_popinfo(self):
        search_ui.api = lambda *a, **k: _make_response(_OK_ONE_FILE_XML)
        search_ui.dosearch('tok', 'foo', '', '', 25, 0, 'search')
        self.assertEqual(self.popinfo_calls, [])


# ---------------------------------------------------------------------------
# Exit 5: series render -> SEARCH_OK
# ---------------------------------------------------------------------------

class TestSeriesRenderOk(DosearchSignalTestBase):
    def setUp(self):
        super(TestSeriesRenderOk, self).setUp()
        # Prefer series view: default_view='0' means prefer_series=True.
        self._settings['default_view'] = '0'
        self.display_calls = []
        search_ui.display_series_list = lambda *a, **k: self.display_calls.append((a, k))
        grouped = {
            'series': {'some show': {
                'display_name': 'Some Show',
                'seasons': {1: {1: [{'ident': 'abc123', 'name': 'file.mkv'}]}},
                'total_episodes': 1,
            }},
            'movies': {},
        }
        search_ui.fetch_and_group_series = lambda *a, **k: grouped

    def test_series_render_returns_ok(self):
        search_ui.api = lambda *a, **k: _make_response(_OK_ONE_FILE_XML)
        result = search_ui.dosearch('tok', 'foo', '', '', 25, 0, 'search')
        self.assertEqual(result, SEARCH_OK)
        self.assertEqual(len(self.display_calls), 1)

    def test_series_render_does_not_call_end_of_directory_directly(self):
        """display_series_list owns endOfDirectory for the series path; dosearch
        itself must not double-call it (display_series_list is stubbed here)."""
        search_ui.api = lambda *a, **k: _make_response(_OK_ONE_FILE_XML)
        search_ui.dosearch('tok', 'foo', '', '', 25, 0, 'search')
        self.assertEqual(self.end_of_directory_calls, [])

    def test_series_render_no_failure_popinfo(self):
        search_ui.api = lambda *a, **k: _make_response(_OK_ONE_FILE_XML)
        search_ui.dosearch('tok', 'foo', '', '', 25, 0, 'search')
        self.assertEqual(self.popinfo_calls, [])


if __name__ == '__main__':
    unittest.main()
