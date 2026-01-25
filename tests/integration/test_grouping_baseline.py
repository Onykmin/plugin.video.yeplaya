#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Baseline Grouping Test Suite - Real Webshare API Integration

Captures grouping metrics for comparison before/after improvements.
Usage:
    python tests/integration/test_grouping_baseline.py
    python tests/integration/test_grouping_baseline.py --save-responses
    python tests/integration/test_grouping_baseline.py --verbose
"""

import os
import sys
import json
import time
import hashlib
import unicodedata
from xml.etree import ElementTree as ET
from datetime import datetime
from pathlib import Path

# === KODI MOCKS ===
class MockXBMC:
    LOGDEBUG = 0
    LOGINFO = 1
    LOGWARNING = 2
    LOGERROR = 3
    @staticmethod
    def log(msg, level=0):
        if '--verbose' in sys.argv or level >= 2:
            print(f"[LOG] {msg}")
    @staticmethod
    def translatePath(path):
        return path

class MockXBMCVFS:
    @staticmethod
    def translatePath(path):
        return path

import tempfile

class MockAddon:
    def getSetting(self, key):
        return 'false'
    def getSettingBool(self, key):
        return True  # Enable movie grouping
    def getAddonInfo(self, key):
        if key == 'profile':
            return tempfile.gettempdir()
        return ''

class MockXBMCAddon:
    @staticmethod
    def Addon():
        return MockAddon()

class MockXBMCGUI:
    NOTIFICATION_INFO = 'info'
    NOTIFICATION_WARNING = 'warning'
    NOTIFICATION_ERROR = 'error'

sys.modules['xbmc'] = MockXBMC
sys.modules['xbmcgui'] = MockXBMCGUI
sys.modules['xbmcplugin'] = type('obj', (object,), {})()
sys.modules['xbmcaddon'] = MockXBMCAddon
sys.modules['xbmcvfs'] = MockXBMCVFS

# Mock sys.argv for imports
old_argv = sys.argv[:]
sys.argv = ['plugin.video.yawsp', '0', '']

# Import from lib/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from lib.grouping import group_by_series
from lib.parsing import parse_episode_info, clean_series_name

# Restore argv
sys.argv = old_argv

# === CONSTANTS ===
CACHE_DIR = Path(__file__).parent / 'api_responses'
BASELINE_FILE = Path(__file__).parent / 'baseline_results.json'

# Test cases: query -> expected behavior
TEST_CASES = {
    # Series - Dual names (Czech/English)
    'penguin': {
        'type': 'series',
        'expected_groups': 1,
        'notes': 'The Penguin / Tučňák should merge into one',
    },
    'south park': {
        'type': 'series',
        'expected_groups': 1,
        'notes': 'South Park, Městečko South Park should merge',
    },
    'the office': {
        'type': 'series',
        'expected_groups': 2,  # US and UK are different shows
        'notes': 'Office US vs Office UK should stay separate',
    },
    'pokemon': {
        'type': 'series',
        'expected_groups': None,  # Multiple Pokemon series exist
        'notes': 'Pokemon has many spin-offs, complex case',
    },
    'chainsaw man': {
        'type': 'series',
        'expected_groups': 1,
        'notes': 'Anime with standard naming',
    },
    'mashle': {
        'type': 'series',
        'expected_groups': 1,
        'notes': 'Mashle, Mashle 2nd Season should merge',
    },
    'solo leveling': {
        'type': 'series',
        'expected_groups': 1,
        'notes': 'Korean webtoon anime adaptation',
    },
    'suits': {
        'type': 'series',
        'expected_groups': 1,
        'notes': 'Suits / Kravataci dual-name',
    },
    'breaking bad': {
        'type': 'series',
        'expected_groups': 1,
        'notes': 'Standard S##E## format',
    },
    'game of thrones': {
        'type': 'series',
        'expected_groups': 1,
        'notes': 'Multi-word title',
    },
    'attack on titan': {
        'type': 'series',
        'expected_groups': 1,
        'notes': 'Attack on Titan / Shingeki no Kyojin',
    },
    # Movies
    'inception 2010': {
        'type': 'movie',
        'expected_groups': 1,
        'notes': 'Single movie, multiple quality versions',
    },
    'avatar 2009': {
        'type': 'movie',
        'expected_groups': 1,
        'notes': 'First Avatar movie',
    },
}


def fetch_webshare_search(query, limit=200, category='video'):
    """Fetch search results from Webshare API (public, no auth needed)."""
    import requests

    try:
        response = requests.post(
            'https://webshare.cz/api/search/',
            data={
                'what': query,
                'category': category,
                'sort': '',
                'limit': limit,
                'offset': 0
            },
            timeout=30
        )
        response.raise_for_status()
        return response.content
    except Exception as e:
        print(f"✗ API error for '{query}': {e}")
        return None


def get_cache_path(query):
    """Get cache file path for a query."""
    safe_name = hashlib.md5(query.encode()).hexdigest()[:8] + '_' + query.replace(' ', '_')[:20]
    return CACHE_DIR / f'{safe_name}.xml'


def fetch_with_cache(query, limit=200, use_cache=True):
    """Fetch with optional caching."""
    cache_path = get_cache_path(query)

    if use_cache and cache_path.exists():
        print(f"  [CACHE] Loading: {query}")
        return cache_path.read_bytes()

    print(f"  [API] Fetching: {query}")
    content = fetch_webshare_search(query, limit)

    if content and '--save-responses' in sys.argv:
        CACHE_DIR.mkdir(exist_ok=True)
        cache_path.write_bytes(content)
        print(f"  [SAVED] {cache_path.name}")

    return content


def parse_files_from_xml(xml_content):
    """Parse files from Webshare XML response."""
    try:
        xml = ET.fromstring(xml_content)
    except ET.ParseError as e:
        print(f"✗ XML parse error: {e}")
        return []

    files = []
    for file_elem in xml.iter('file'):
        name = file_elem.find('name')
        size = file_elem.find('size')
        ident = file_elem.get('ident')

        if name is not None and name.text:
            files.append({
                'name': name.text,
                'size': size.text if size is not None else '0',
                'ident': ident or 'unknown'
            })

    return files


def calculate_metrics(query, files, grouped):
    """Calculate grouping quality metrics."""
    metrics = {
        'query': query,
        'total_files': len(files),
        'series_groups': len(grouped['series']),
        'movie_groups': len(grouped.get('movies', {})),
        'non_series': len(grouped['non_series']),
        'series_details': {},
        'movie_details': {},
        'potential_issues': [],
    }

    # Series details
    for key, data in grouped['series'].items():
        total_eps = data['total_episodes']
        seasons = len(data['seasons'])
        display = data.get('display_name', key)

        # Count total versions
        version_count = 0
        for s_data in data['seasons'].values():
            for ep_versions in s_data.values():
                version_count += len(ep_versions)

        metrics['series_details'][key] = {
            'display_name': display,
            'seasons': seasons,
            'episodes': total_eps,
            'versions': version_count,
        }

    # Movie details
    for key, data in grouped.get('movies', {}).items():
        metrics['movie_details'][key] = {
            'display_name': data.get('display_name', key),
            'year': data.get('year'),
            'versions': len(data.get('versions', [])),
        }

    # Detect potential issues
    series_keys = list(grouped['series'].keys())

    # Check for substring relationships that weren't merged
    for i, key1 in enumerate(series_keys):
        for key2 in series_keys[i+1:]:
            if key1 in key2 or key2 in key1:
                metrics['potential_issues'].append(
                    f"Substring not merged: '{key1}' vs '{key2}'"
                )

    # Check for single-episode "series" that might be movies
    for key, data in grouped['series'].items():
        if data['total_episodes'] == 1 and len(data['seasons']) == 1:
            metrics['potential_issues'].append(
                f"Single-ep series (might be movie?): '{key}'"
            )

    return metrics


def run_baseline_tests(use_cache=True):
    """Run all test cases and collect baseline metrics."""
    results = {
        'timestamp': datetime.now().isoformat(),
        'test_cases': {},
    }

    print("\n" + "="*70)
    print("BASELINE GROUPING TEST SUITE")
    print("="*70 + "\n")

    for query, expected in TEST_CASES.items():
        print(f"\n--- Testing: {query} ---")

        # Fetch data
        xml_content = fetch_with_cache(query, use_cache=use_cache)
        if not xml_content:
            results['test_cases'][query] = {'error': 'Failed to fetch'}
            continue

        # Parse files
        files = parse_files_from_xml(xml_content)
        print(f"  Files: {len(files)}")

        if not files:
            results['test_cases'][query] = {'error': 'No files found'}
            continue

        # Group
        grouped = group_by_series(files)

        # Calculate metrics
        metrics = calculate_metrics(query, files, grouped)
        metrics['expected'] = expected

        # Evaluate
        actual_groups = metrics['series_groups'] if expected['type'] == 'series' else metrics['movie_groups']
        expected_groups = expected.get('expected_groups')

        if expected_groups is not None:
            if actual_groups == expected_groups:
                status = "✓ PASS"
            elif actual_groups < expected_groups:
                status = "⚠ OVER-MERGED"
            else:
                status = "✗ UNDER-MERGED"
        else:
            status = "? (no expectation)"

        metrics['status'] = status
        results['test_cases'][query] = metrics

        # Print summary
        print(f"  Series groups: {metrics['series_groups']}")
        print(f"  Movie groups: {metrics['movie_groups']}")
        print(f"  Non-series: {metrics['non_series']}")
        print(f"  Status: {status}")

        if metrics['potential_issues']:
            print(f"  Issues: {len(metrics['potential_issues'])}")
            for issue in metrics['potential_issues'][:3]:
                print(f"    - {issue}")

        # Show series keys for debugging
        if '--verbose' in sys.argv:
            print(f"  Series keys:")
            for key in sorted(grouped['series'].keys()):
                data = grouped['series'][key]
                print(f"    '{key}': {data['total_episodes']} eps, display='{data.get('display_name', key)}'")

        # Rate limit
        time.sleep(0.5)

    return results


def print_summary(results):
    """Print summary of all tests."""
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70 + "\n")

    passed = 0
    failed = 0
    unknown = 0

    for query, metrics in results['test_cases'].items():
        if 'error' in metrics:
            print(f"  ERROR: {query} - {metrics['error']}")
            failed += 1
            continue

        status = metrics.get('status', '?')
        if '✓' in status:
            passed += 1
        elif '✗' in status or '⚠' in status:
            failed += 1
        else:
            unknown += 1

        print(f"  {status}: {query} ({metrics['series_groups']} series, {metrics['movie_groups']} movies)")

    print(f"\n  TOTAL: {passed} passed, {failed} failed, {unknown} unknown")
    print(f"  Timestamp: {results['timestamp']}")


def save_baseline(results):
    """Save baseline results to JSON."""
    with open(BASELINE_FILE, 'w') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n  Baseline saved to: {BASELINE_FILE}")


def main():
    """Main entry point."""
    use_cache = '--no-cache' not in sys.argv

    results = run_baseline_tests(use_cache=use_cache)
    print_summary(results)
    save_baseline(results)

    return 0 if all(
        '✓' in m.get('status', '')
        for m in results['test_cases'].values()
        if 'status' in m
    ) else 1


if __name__ == '__main__':
    sys.exit(main())
