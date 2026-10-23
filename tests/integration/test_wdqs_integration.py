#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Integration coverage for lib.wdqs against a cached WDQS response fixture.

Follows this directory's existing convention (see test_grouping_improvements.
py's TestRealAPIData / test_api_grouping.py's cached-response pattern):
cached fixture files under tests/integration/api_responses/, tests
pytest.mark.skipif-gated on the fixture's existence, NO live network calls
in the pytest-collected suite (the historical live-fetch helpers in this
directory, e.g. test_grouping_baseline.py's fetch_webshare_search, are
standalone-script-only and are not collected by pytest at all — confirmed
via `pytest --collect-only`).

tests/integration/api_responses/wdqs_sample.json is a hand-built fixture
matching the real WDQS SPARQL JSON results shape (doc'd in lib/wdqs.py's
_parse_bindings docstring): unmatched OPTIONALs are absent keys, not nulls.
It is NOT a live capture (no outbound HTTP is made to build or use it), but
mirrors the shape lib.wdqs must handle, including the two measured edge
cases: an en/cs byte-identical row (Yossi & Jagger) and a title-less row
that must be dropped.
"""

import json
from pathlib import Path

import pytest

import lib.wdqs as wdqs


FIXTURE_PATH = Path(__file__).parent / 'api_responses' / 'wdqs_sample.json'


@pytest.mark.skipif(not FIXTURE_PATH.exists(), reason="No cached WDQS fixture")
class TestWdqsParsesRealShapedFixture:
    def _load(self):
        with open(FIXTURE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)

    def test_row_with_neither_title_dropped(self):
        payload = self._load()
        records = wdqs._parse_bindings(payload)
        ids = [r['id'] for r in records]
        assert 'Q3' not in ids  # the title-less row

    def test_all_other_rows_kept(self):
        payload = self._load()
        records = wdqs._parse_bindings(payload)
        ids = sorted(r['id'] for r in records)
        assert ids == sorted(['Q1', 'Q2', 'Q83495', 'Q219776'])

    def test_byte_identical_cs_en_row_preserved_as_is(self):
        """_parse_bindings itself does not dedupe cs/en — that collapse is
        random_movie_ui._distinct_titles' job, tested separately."""
        payload = self._load()
        records = wdqs._parse_bindings(payload)
        by_id = {r['id']: r for r in records}
        yossi = by_id['Q219776']
        assert yossi['cs'] == yossi['en'] == 'Yossi & Jagger'

    def test_en_only_and_cs_only_rows_have_none_for_missing_side(self):
        payload = self._load()
        records = wdqs._parse_bindings(payload)
        by_id = {r['id']: r for r in records}
        assert by_id['Q1']['cs'] is None and by_id['Q1']['en'] == 'Germinal'
        assert by_id['Q2']['en'] is None and by_id['Q2']['cs'] == 'Tucnak'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
