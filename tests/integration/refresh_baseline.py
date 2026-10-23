# -*- coding: utf-8 -*-
"""Maintenance tool (not collected by pytest): re-record baseline_results.json.

    python3 tests/integration/refresh_baseline.py            # re-record from current code
    python3 tests/integration/refresh_baseline.py --fetch    # also re-download api_responses/*.xml

Run from the repo root. --fetch uses the public Webshare search endpoint
(no credentials) and needs network. Review the baseline diff before committing:
it is the record of what grouping is expected to output.

The query list is the one already in baseline_results.json; add a new query by
adding an entry there (``{"query": "x"}``) and, with --fetch, its fixture is recorded.
Each entry keeps its ``target`` (manual note about the ideal result), never auto-updated.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import tests.conftest  # noqa: E402,F401  (installs the Kodi mocks lib/ needs)
from tests.integration.test_baseline_regression import (  # noqa: E402
    BASELINE, HERE, fixture_path, observe, run_pipeline)


def fetch(query, limit=500):
    import requests
    response = requests.post(
        'https://webshare.cz/api/search/',
        data={'what': query, 'category': 'video', 'sort': '', 'limit': limit, 'offset': 0},
        timeout=30)
    response.raise_for_status()
    fixture_path(query).write_bytes(response.content)


def main():
    refetch = '--fetch' in sys.argv
    cases = {}
    for query, old in BASELINE.items():
        if refetch:
            fetch(query)
        grouped = run_pipeline(query)
        cases[query] = {
            'query': query,
            'target': old.get('target'),
            **observe(grouped),
        }
    out = HERE / 'baseline_results.json'
    out.write_text(json.dumps({'timestamp': datetime.now().isoformat(), 'test_cases': cases},
                              indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print('wrote %s (%d queries)' % (out, len(cases)))


if __name__ == '__main__':
    main()
