#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for lib.wdqs — the WDQS SPARQL client (offline, mocked HTTP).

Covers:
- Query construction (build_query): required clauses + regression guards
  against the measured failure modes in lib/wdqs.py evidence archive (bare DISTINCT,
  P577, SERVICE wikibase:label).
- Bindings parsing (_parse_bindings): cs+en, en-only (absent key, not null),
  cs-only, neither (dropped), missing film (skipped), Q-id extraction,
  malformed payload.
- HTTP behavior (_get / fetch_candidates): 200 success, non-200 checked
  before parsing, 403 no-retry, 429 Retry-After honored + bounded, timeout/
  RequestException swallowed, random offset bounds, User-Agent policy.
"""

import re
import sys
import unittest
import unittest.mock as mock

import tests.conftest  # noqa: F401 — installs Kodi mocks

import lib.wdqs as wdqs


def _real_requests_module():
    """Return the genuine `requests` library module, never a test double.

    tests/unit/test_filename_sanitization.py replaces sys.modules['requests']
    with a bare MockRequests (missing .Timeout/.RequestException/.get) at
    import time and never restores it — a cross-suite pollution bug in a
    file outside this brief's editing scope. Because other tests'
    reset_mock_addon() helper purges and later re-imports lib.* (including,
    transitively, lib.wdqs via lib.movie_pool), lib.wdqs.requests can end up
    bound to that mock depending on test execution order, well after this
    file's own imports ran. Detect that (a real requests module always has
    .Timeout) and force a fresh, genuine import back into sys.modules.
    """
    current = sys.modules.get('requests')
    if current is not None and hasattr(current, 'Timeout'):
        return current
    if 'requests' in sys.modules:
        del sys.modules['requests']
    import requests as fresh_requests
    return fresh_requests


def _ensure_wdqs_bound_to_real_requests():
    """Guarantee lib.wdqs.requests is the genuine module before each test."""
    real_requests = _real_requests_module()
    sys.modules['requests'] = real_requests
    if wdqs.requests is not real_requests:
        wdqs.requests = real_requests
    return real_requests


# ---------------------------------------------------------------------------
# 1. Query construction
# ---------------------------------------------------------------------------

class TestBuildQuery(unittest.TestCase):
    def test_contains_required_clauses(self):
        q = wdqs.build_query(100, 50)
        self.assertIn('wdt:P31 wd:Q11424', q)
        self.assertIn('wikibase:sitelinks', q)
        self.assertIn('FILTER(?sl >= 20)', q)
        self.assertIn('GROUP BY ?film', q)
        # Three OPTIONALs: cs label, en label, and (added) P577 date.
        self.assertEqual(q.count('OPTIONAL'), 3)
        self.assertIn('FILTER(LANG(?cs) = "cs")', q)
        self.assertIn('FILTER(LANG(?en) = "en")', q)
        # SAMPLE aggregates for both languages.
        self.assertIn('SAMPLE(?cs)', q)
        self.assertIn('SAMPLE(?en)', q)

    def test_contains_min_date_and_p577(self):
        """Year support: (MIN(?date) AS ?d) under the existing GROUP BY is
        what makes selecting wdt:P577 safe here (see build_query docstring
        and module docstring for the measured 100%-coverage, no-fan-out
        evidence) — this replaces the old test_no_p577 regression guard."""
        q = wdqs.build_query(10, 0)
        self.assertIn('MIN(?date)', q)
        self.assertIn('wdt:P577', q)

    def test_limit_and_offset_present(self):
        q = wdqs.build_query(123, 456)
        self.assertIn('LIMIT 123', q)
        self.assertIn('OFFSET 456', q)

    def test_limit_offset_coerced_to_int(self):
        q = wdqs.build_query('10', '20')
        self.assertIn('LIMIT 10', q)
        self.assertIn('OFFSET 20', q)

    def test_sitelinks_min_constant_used(self):
        q = wdqs.build_query(1, 0)
        self.assertIn('FILTER(?sl >= {})'.format(wdqs.SITELINKS_MIN), q)

    # -- Regression guards: measured failure modes, must never reappear. --

    def test_no_bare_distinct(self):
        """Bare DISTINCT dedupes the whole tuple, not the film — doc §1
        measured 10 rows all 'Barbarella' from a multi-valued property."""
        q = wdqs.build_query(10, 0)
        self.assertNotIn('DISTINCT', q)

    def test_p577_only_wrapped_in_min_never_bare(self):
        """P577 is now intentionally selected for year support (superseding
        the old test_no_p577 guard, which forbade it outright) — but ONLY
        ever as (MIN(?date) AS ?d) under GROUP BY ?film, the form measured
        safe from the doc §1 tuple fan-out. Guard against a bare/SAMPLE-less
        P577 creeping back into the projection."""
        q = wdqs.build_query(10, 0)
        self.assertIn('MIN(?date)', q)
        # No other aggregate/bare reference to ?date anywhere else in the
        # query — the only mention of it is inside MIN(...).
        self.assertEqual(q.count('?date'), 2)  # MIN(?date) + OPTIONAL {?film wdt:P577 ?date}

    def test_no_service_wikibase_label(self):
        """SERVICE wikibase:label + explicit OPTIONALs produced an HTTP 504
        at 65.2s (doc lines 56-61)."""
        q = wdqs.build_query(10, 0)
        self.assertNotIn('SERVICE', q)


# ---------------------------------------------------------------------------
# 2. Pool parse (_parse_bindings)
# ---------------------------------------------------------------------------

def _payload(bindings):
    return {'results': {'bindings': bindings}}


def _film(qid):
    return {'value': 'http://www.wikidata.org/entity/{}'.format(qid)}


class TestParseBindings(unittest.TestCase):
    def test_cs_and_en_row(self):
        rows = [{
            'film': _film('Q123'),
            'csL': {'value': 'Matrix'},
            'enL': {'value': 'The Matrix'},
        }]
        records = wdqs._parse_bindings(_payload(rows))
        self.assertEqual(records, [{'id': 'Q123', 'cs': 'Matrix', 'en': 'The Matrix'}])

    def test_en_only_row_key_absent(self):
        """Unmatched SPARQL OPTIONAL means the 'csL' key is ABSENT, not null."""
        rows = [{
            'film': _film('Q456'),
            'enL': {'value': 'Some Film'},
        }]
        records = wdqs._parse_bindings(_payload(rows))
        self.assertEqual(records, [{'id': 'Q456', 'cs': None, 'en': 'Some Film'}])

    def test_cs_only_row(self):
        rows = [{
            'film': _film('Q789'),
            'csL': {'value': 'Nejaky Film'},
        }]
        records = wdqs._parse_bindings(_payload(rows))
        self.assertEqual(records, [{'id': 'Q789', 'cs': 'Nejaky Film', 'en': None}])

    def test_row_with_neither_cs_nor_en_dropped(self):
        """Measured 0.15% of rows had neither — must be dropped, not crash."""
        rows = [{'film': _film('Q999')}]
        records = wdqs._parse_bindings(_payload(rows))
        self.assertEqual(records, [])

    def test_row_missing_film_key_skipped(self):
        rows = [{'csL': {'value': 'Orphan'}}]
        records = wdqs._parse_bindings(_payload(rows))
        self.assertEqual(records, [])

    def test_qid_extracted_from_full_entity_uri(self):
        rows = [{'film': _film('Q42'), 'enL': {'value': 'Hitchhiker'}}]
        records = wdqs._parse_bindings(_payload(rows))
        self.assertEqual(records[0]['id'], 'Q42')

    def test_mixed_rows(self):
        rows = [
            {'film': _film('Q1'), 'csL': {'value': 'a'}, 'enL': {'value': 'b'}},
            {'film': _film('Q2'), 'enL': {'value': 'c'}},
            {'film': _film('Q3')},  # dropped: neither
            {'enL': {'value': 'orphan'}},  # dropped: no film
        ]
        records = wdqs._parse_bindings(_payload(rows))
        ids = [r['id'] for r in records]
        self.assertEqual(ids, ['Q1', 'Q2'])

    def test_malformed_payload_missing_results_returns_empty(self):
        self.assertEqual(wdqs._parse_bindings({}), [])

    def test_malformed_payload_missing_bindings_returns_empty(self):
        self.assertEqual(wdqs._parse_bindings({'results': {}}), [])

    def test_malformed_payload_wrong_type_returns_empty(self):
        self.assertEqual(wdqs._parse_bindings({'results': None}), [])
        self.assertEqual(wdqs._parse_bindings(None), [])

    # -- Year ('d' -> 'y') parsing. --

    def test_year_parsed_from_date_binding(self):
        """Measured live format: 'd' is an xsd:dateTime string like
        '1998-05-18T00:00:00Z' — year is the first 4 chars, as an int."""
        rows = [{
            'film': _film('Q123'),
            'csL': {'value': 'Matrix'},
            'd': {'value': '1998-05-18T00:00:00Z'},
        }]
        records = wdqs._parse_bindings(_payload(rows))
        self.assertEqual(records, [{'id': 'Q123', 'cs': 'Matrix', 'en': None, 'y': 1998}])
        self.assertIsInstance(records[0]['y'], int)

    def test_year_key_absent_when_no_date_binding(self):
        """Unmatched OPTIONAL for P577 means 'd' is ABSENT, not null — the
        resulting record must have NO 'y' key at all (never 'y': None)."""
        rows = [{'film': _film('Q456'), 'enL': {'value': 'Some Film'}}]
        records = wdqs._parse_bindings(_payload(rows))
        self.assertNotIn('y', records[0])
        self.assertEqual(records, [{'id': 'Q456', 'cs': None, 'en': 'Some Film'}])

    def test_malformed_date_value_skipped_without_raising(self):
        """A non-date 'd' value must never crash parsing — just no 'y'."""
        rows = [{
            'film': _film('Q789'),
            'enL': {'value': 'Weird Film'},
            'd': {'value': 'unknown'},
        }]
        records = wdqs._parse_bindings(_payload(rows))
        self.assertNotIn('y', records[0])


# ---------------------------------------------------------------------------
# 3. HTTP behavior (_get / fetch_candidates)
# ---------------------------------------------------------------------------

class _FakeResponse(object):
    def __init__(self, status_code=200, json_data=None, json_raises=None, headers=None):
        self.status_code = status_code
        self._json_data = json_data
        self._json_raises = json_raises
        self.headers = headers or {}

    def json(self):
        if self._json_raises is not None:
            raise self._json_raises
        return self._json_data


class TestGetHttpBehavior(unittest.TestCase):
    def setUp(self):
        global requests
        # See _ensure_wdqs_bound_to_real_requests' docstring: guard against
        # cross-suite sys.modules['requests'] pollution on every test, not
        # just at file-import time, since another test file's fixture can
        # re-purge and re-import lib.* between tests in the same session.
        requests = _ensure_wdqs_bound_to_real_requests()
        self._sleep_patch = mock.patch('lib.wdqs.time.sleep', return_value=None)
        self._sleep_patch.start()

    def tearDown(self):
        self._sleep_patch.stop()

    def test_200_valid_json_returns_response(self):
        resp = _FakeResponse(200, json_data={'ok': True})
        with mock.patch('lib.wdqs.requests.get', return_value=resp) as m:
            result = wdqs._get({'query': 'x'})
        self.assertIs(result, resp)
        m.assert_called_once()

    def test_non_200_checked_before_parsing_502_json_raises(self):
        """A 502 whose .json() raises must still yield [] via fetch_candidates,
        never propagate — status is checked BEFORE any .json() call."""
        resp = _FakeResponse(502, json_raises=ValueError('not json'))
        with mock.patch('lib.wdqs.requests.get', return_value=resp):
            records = wdqs.fetch_candidates(10)
        self.assertEqual(records, [])

    def test_403_no_retry(self):
        resp = _FakeResponse(403)
        with mock.patch('lib.wdqs.requests.get', return_value=resp) as m:
            result = wdqs._get({'query': 'x'})
        self.assertIsNone(result)
        m.assert_called_once()

    def test_429_with_retry_after_honored_then_gives_up(self):
        resp1 = _FakeResponse(429, headers={'Retry-After': '3'})
        resp2 = _FakeResponse(429, headers={'Retry-After': '3'})
        with mock.patch('lib.wdqs.requests.get', side_effect=[resp1, resp2]) as m, \
             mock.patch('lib.wdqs.time.sleep') as sleep_mock:
            result = wdqs._get({'query': 'x'})
        self.assertIsNone(result)
        # MAX_RETRIES = 1 -> exactly one retry -> 2 total calls, bounded.
        self.assertEqual(m.call_count, 2)
        sleep_mock.assert_called_once_with(3.0)

    def test_429_without_retry_after_uses_backoff_constant(self):
        resp1 = _FakeResponse(429)
        resp2 = _FakeResponse(429)
        with mock.patch('lib.wdqs.requests.get', side_effect=[resp1, resp2]), \
             mock.patch('lib.wdqs.time.sleep') as sleep_mock:
            result = wdqs._get({'query': 'x'})
        self.assertIsNone(result)
        sleep_mock.assert_called_once_with(wdqs.RETRY_BACKOFF_SECONDS)

    def test_429_eventual_success_after_one_retry(self):
        resp1 = _FakeResponse(429, headers={'Retry-After': '1'})
        resp2 = _FakeResponse(200, json_data={'results': {'bindings': []}})
        with mock.patch('lib.wdqs.requests.get', side_effect=[resp1, resp2]) as m:
            result = wdqs._get({'query': 'x'})
        self.assertIs(result, resp2)
        self.assertEqual(m.call_count, 2)

    def test_other_5xx_bounded_retry_then_gives_up(self):
        resp1 = _FakeResponse(500)
        resp2 = _FakeResponse(500)
        with mock.patch('lib.wdqs.requests.get', side_effect=[resp1, resp2]) as m:
            result = wdqs._get({'query': 'x'})
        self.assertIsNone(result)
        self.assertEqual(m.call_count, 2)  # 1 initial + MAX_RETRIES(1)

    def test_timeout_returns_none_never_raises(self):
        with mock.patch('lib.wdqs.requests.get', side_effect=requests.Timeout('slow')):
            result = wdqs._get({'query': 'x'})
        self.assertIsNone(result)

    def test_request_exception_returns_none_never_raises(self):
        with mock.patch('lib.wdqs.requests.get',
                         side_effect=requests.RequestException('boom')):
            result = wdqs._get({'query': 'x'})
        self.assertIsNone(result)

    def test_fetch_candidates_timeout_returns_empty_list(self):
        with mock.patch('lib.wdqs.requests.get', side_effect=requests.Timeout('slow')):
            records = wdqs.fetch_candidates(50)
        self.assertEqual(records, [])

    def test_fetch_candidates_non_json_body_returns_empty(self):
        resp = _FakeResponse(200, json_raises=ValueError('bad body'))
        with mock.patch('lib.wdqs.requests.get', return_value=resp):
            records = wdqs.fetch_candidates(50)
        self.assertEqual(records, [])

    def test_fetch_candidates_zero_or_negative_count_returns_empty_no_call(self):
        with mock.patch('lib.wdqs.requests.get') as m:
            self.assertEqual(wdqs.fetch_candidates(0), [])
            self.assertEqual(wdqs.fetch_candidates(-5), [])
        m.assert_not_called()

    def test_fetch_candidates_success_parses_records(self):
        payload = {'results': {'bindings': [
            {'film': _film('Q1'), 'csL': {'value': 'a'}, 'enL': {'value': 'b'}},
        ]}}
        resp = _FakeResponse(200, json_data=payload)
        with mock.patch('lib.wdqs.requests.get', return_value=resp):
            records = wdqs.fetch_candidates(10)
        self.assertEqual(records, [{'id': 'Q1', 'cs': 'a', 'en': 'b'}])

    def test_random_offset_stays_within_bounds(self):
        with mock.patch('lib.wdqs.random.randint', return_value=0) as randint_mock, \
             mock.patch('lib.wdqs.requests.get',
                         return_value=_FakeResponse(200, json_data={'results': {'bindings': []}})):
            wdqs.fetch_candidates(100)
        args, _ = randint_mock.call_args
        self.assertEqual(args, (0, wdqs.POOL_TOTAL - 100))

    def test_random_offset_bounds_when_count_exceeds_pool_total(self):
        with mock.patch('lib.wdqs.random.randint', return_value=0) as randint_mock, \
             mock.patch('lib.wdqs.requests.get',
                         return_value=_FakeResponse(200, json_data={'results': {'bindings': []}})):
            wdqs.fetch_candidates(wdqs.POOL_TOTAL * 10)
        args, _ = randint_mock.call_args
        self.assertEqual(args, (0, 0))

    def test_random_offset_many_draws_within_range(self):
        """Statistical sanity check: fetch_candidates' internally-picked
        offset (visible via the query text passed to requests.get) always
        stays within 0..POOL_TOTAL-limit across many draws — overshooting
        the pool end measured a 28.50s worst case for 0 rows returned."""
        limit = 50
        max_offset = wdqs.POOL_TOTAL - limit
        captured_offsets = []

        def _fake_get(url, params=None, headers=None, timeout=None):
            match = re.search(r'OFFSET (\d+)', params['query'])
            captured_offsets.append(int(match.group(1)))
            return _FakeResponse(200, json_data={'results': {'bindings': []}})

        with mock.patch('lib.wdqs.requests.get', side_effect=_fake_get):
            for _ in range(200):
                wdqs.fetch_candidates(limit)

        self.assertEqual(len(captured_offsets), 200)
        for offset in captured_offsets:
            self.assertGreaterEqual(offset, 0)
            self.assertLessEqual(offset, max_offset)

    def test_user_agent_present_and_not_webshare_spoofed_ua(self):
        headers = wdqs._headers()
        ua = headers.get('User-Agent')
        self.assertTrue(ua)
        self.assertIsInstance(ua, str)
        # Policy requirement: must NOT be lib.api's spoofed Chrome UA.
        self.assertNotIn('Mozilla', ua)
        self.assertNotIn('Chrome', ua)

    def test_user_agent_falls_back_when_addon_unavailable(self):
        with mock.patch('lib.wdqs.xbmcaddon.Addon', side_effect=Exception('no addon')):
            ua = wdqs._addon_user_agent()
        self.assertTrue(ua)
        self.assertIn('plugin.video.yeplaya', ua)


if __name__ == '__main__':
    unittest.main()


class TestEffectivePoolTotal(unittest.TestCase):
    """POOL_TOTAL is a 2026 measurement (wdqs.py:71); lib/wdqs.py evidence archive; orig. doc:78
    warns a hardcoded bound that is too low makes the pool tail permanently
    unreachable as Wikidata grows. effective_pool_total() lets an observed
    floor raise it, without ever running the doc's 6-45s COUNT query."""

    def test_none_returns_static_measurement(self):
        self.assertEqual(wdqs.effective_pool_total(None), wdqs.POOL_TOTAL)

    def test_floor_below_static_is_ignored(self):
        self.assertEqual(wdqs.effective_pool_total(wdqs.POOL_TOTAL - 1000),
                         wdqs.POOL_TOTAL)

    def test_floor_above_static_raises_the_bound(self):
        self.assertEqual(wdqs.effective_pool_total(wdqs.POOL_TOTAL + 3000),
                         wdqs.POOL_TOTAL + 3000)

    def test_non_int_floor_is_ignored(self):
        for bad in ('junk', 1.5, [], {}, True):
            self.assertEqual(wdqs.effective_pool_total(bad), wdqs.POOL_TOTAL,
                             'bad floor {!r} must not change the bound'.format(bad))

    def test_full_page_records_a_floor_short_page_does_not(self):
        """A FULL page at `offset` proves offset+limit items exist; a short
        page proves nothing (it may be the pool end). Compares raw bindings,
        not filtered records — _parse_bindings drops title-less rows, so
        filtering here would under-count a genuinely full page."""
        full = {'results': {'bindings': [
            {'film': {'value': 'http://www.wikidata.org/entity/Q%d' % i},
             'enL': {'value': 'T%d' % i}} for i in range(5)]}}
        short = {'results': {'bindings': [
            {'film': {'value': 'http://www.wikidata.org/entity/Q1'},
             'enL': {'value': 'T1'}}]}}

        class _Resp(object):
            def __init__(self, payload):
                self.status_code = 200
                self._payload = payload

            def json(self):
                return self._payload

        with mock.patch.object(wdqs, '_get', return_value=_Resp(full)), \
             mock.patch.object(wdqs.random, 'randint', return_value=100):
            wdqs.fetch_candidates(5)
        self.assertEqual(wdqs.LAST_OBSERVED_FLOOR, 105)

        with mock.patch.object(wdqs, '_get', return_value=_Resp(short)), \
             mock.patch.object(wdqs.random, 'randint', return_value=100):
            wdqs.fetch_candidates(5)
        self.assertIsNone(wdqs.LAST_OBSERVED_FLOOR)
