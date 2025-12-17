#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for deduplicate_versions() function."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Mock Kodi modules
sys.modules['xbmc'] = __import__('unittest.mock').mock.MagicMock()
sys.modules['xbmcaddon'] = __import__('unittest.mock').mock.MagicMock()
sys.modules['xbmcgui'] = __import__('unittest.mock').mock.MagicMock()
sys.modules['xbmcplugin'] = __import__('unittest.mock').mock.MagicMock()
sys.modules['xbmcvfs'] = __import__('unittest.mock').mock.MagicMock()

from lib.grouping import deduplicate_versions


def test_empty_list():
    """Empty list returns empty list."""
    result = deduplicate_versions([])
    assert result == []


def test_single_version():
    """Single version returns unchanged."""
    versions = [{'ident': 'abc', 'name': 'file.mkv', 'size': 1000}]
    result = deduplicate_versions(versions)
    assert len(result) == 1
    assert result[0]['ident'] == 'abc'


def test_duplicate_by_ident():
    """Duplicates detected by ident."""
    versions = [
        {'ident': 'abc', 'name': 'file1.mkv', 'size': 1000},
        {'ident': 'abc', 'name': 'file2.mkv', 'size': 2000},  # Same ident
    ]
    result = deduplicate_versions(versions)
    assert len(result) == 1
    assert result[0]['name'] == 'file1.mkv'  # First kept


def test_duplicate_by_name_size():
    """Duplicates detected by name+size."""
    versions = [
        {'ident': 'abc', 'name': 'file.mkv', 'size': 1000},
        {'ident': 'def', 'name': 'file.mkv', 'size': 1000},  # Same name+size
    ]
    result = deduplicate_versions(versions)
    assert len(result) == 1
    assert result[0]['ident'] == 'abc'  # First kept


def test_different_files_kept():
    """Different files are kept."""
    versions = [
        {'ident': 'abc', 'name': 'file1.mkv', 'size': 1000},
        {'ident': 'def', 'name': 'file2.mkv', 'size': 2000},
    ]
    result = deduplicate_versions(versions)
    assert len(result) == 2


def test_unknown_ident_uses_name_size():
    """'unknown' idents fall back to name+size."""
    versions = [
        {'ident': 'unknown', 'name': 'file.mkv', 'size': 1000},
        {'ident': 'unknown', 'name': 'file.mkv', 'size': 1000},
    ]
    result = deduplicate_versions(versions)
    assert len(result) == 1


def test_none_ident_uses_name_size():
    """None idents fall back to name+size."""
    versions = [
        {'ident': None, 'name': 'file.mkv', 'size': 1000},
        {'ident': None, 'name': 'file.mkv', 'size': 1000},
    ]
    result = deduplicate_versions(versions)
    assert len(result) == 1


def test_missing_size_keeps_both():
    """Files without size cannot be deduped by name+size."""
    versions = [
        {'ident': 'abc', 'name': 'file.mkv', 'size': None},
        {'ident': 'def', 'name': 'file.mkv', 'size': None},
    ]
    result = deduplicate_versions(versions)
    assert len(result) == 2  # Can't dedupe without size


def test_missing_name_keeps_both():
    """Files without name cannot be deduped by name+size."""
    versions = [
        {'ident': 'abc', 'name': None, 'size': 1000},
        {'ident': 'def', 'name': None, 'size': 1000},
    ]
    result = deduplicate_versions(versions)
    assert len(result) == 2  # Can't dedupe without name


def test_order_preserved():
    """First occurrence kept, order preserved."""
    versions = [
        {'ident': 'a', 'name': 'a.mkv', 'size': 100},
        {'ident': 'b', 'name': 'b.mkv', 'size': 200},
        {'ident': 'a', 'name': 'a.mkv', 'size': 100},  # Duplicate of first
        {'ident': 'c', 'name': 'c.mkv', 'size': 300},
    ]
    result = deduplicate_versions(versions)
    assert len(result) == 3
    assert result[0]['ident'] == 'a'
    assert result[1]['ident'] == 'b'
    assert result[2]['ident'] == 'c'


def test_mixed_duplicate_types():
    """Handle mix of ident-based and name+size duplicates."""
    versions = [
        {'ident': 'abc', 'name': 'file1.mkv', 'size': 1000},
        {'ident': 'abc', 'name': 'file2.mkv', 'size': 2000},  # Dup by ident
        {'ident': 'def', 'name': 'file1.mkv', 'size': 1000},  # Dup by name+size
        {'ident': 'ghi', 'name': 'file3.mkv', 'size': 3000},  # Unique
    ]
    result = deduplicate_versions(versions)
    assert len(result) == 2
    assert result[0]['ident'] == 'abc'
    assert result[1]['ident'] == 'ghi'


if __name__ == '__main__':
    tests = [
        ('Empty list', test_empty_list),
        ('Single version', test_single_version),
        ('Duplicate by ident', test_duplicate_by_ident),
        ('Duplicate by name+size', test_duplicate_by_name_size),
        ('Different files kept', test_different_files_kept),
        ('Unknown ident uses name+size', test_unknown_ident_uses_name_size),
        ('None ident uses name+size', test_none_ident_uses_name_size),
        ('Missing size keeps both', test_missing_size_keeps_both),
        ('Missing name keeps both', test_missing_name_keeps_both),
        ('Order preserved', test_order_preserved),
        ('Mixed duplicate types', test_mixed_duplicate_types),
    ]

    print('=== Testing deduplicate_versions() ===')
    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            test_func()
            print(f'✓ {name}')
            passed += 1
        except AssertionError as e:
            print(f'✗ {name}: {e}')
            failed += 1

    print(f'\n=== Results ===')
    print(f'Passed: {passed}')
    print(f'Failed: {failed}')

    sys.exit(0 if failed == 0 else 1)
