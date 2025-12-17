#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""CSFD scraper unit tests - Critical/Happy Path.

Tests web scraping, caching, dual-name handling with REAL CSFD.cz requests.

Usage:
    # All tests (with real network requests)
    python tests/test_csfd_scraper.py

    # Skip live network tests
    SKIP_LIVE_TESTS=1 python tests/test_csfd_scraper.py

    # Verbose mode
    python tests/test_csfd_scraper.py --verbose
"""

import os
import sys
import re
import sqlite3
import tempfile
import shutil
import unicodedata

# Unidecode fallback
def unidecode(text):
    """Normalize Unicode to ASCII - handles Czech characters."""
    normalized = unicodedata.normalize('NFKD', text)
    return ''.join([c for c in normalized if not unicodedata.combining(c)])

# Import csfd_scraper functions
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from csfd_scraper import (
    init_csfd_cache,
    search_csfd,
    get_csfd_titles,
    lookup_series_csfd,
    create_canonical_from_dual_names,
    format_display_name,
    _clean_for_canonical,
    REQUESTS_AVAILABLE
)


def should_skip_live_tests():
    """Check if live network tests should be skipped."""
    return os.environ.get('SKIP_LIVE_TESTS', '0') == '1'


class TestCacheInitialization:
    """Test CSFD cache database initialization."""

    def setUp(self):
        """Create temp directory for cache."""
        self.temp_dir = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.temp_dir)

    def tearDown(self):
        """Clean up temp directory."""
        os.chdir(self.old_cwd)
        shutil.rmtree(self.temp_dir)

    def test_cache_init_creates_database(self):
        """Cache initialization creates database file."""
        db = init_csfd_cache()
        assert db is not None, "init_csfd_cache() returned None"

        # Cache is created in csfd_scraper.py directory, not temp dir
        # Just verify db object is valid
        cursor = db.execute("SELECT 1")
        assert cursor.fetchone() == (1,), "Database not functional"
        db.close()

    def test_cache_init_creates_table(self):
        """Cache initialization creates csfd_cache table."""
        db = init_csfd_cache()
        assert db is not None

        cursor = db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        assert 'csfd_cache' in tables, f"csfd_cache table not found. Tables: {tables}"
        db.close()

    def test_cache_schema_columns(self):
        """Cache table has all required columns."""
        db = init_csfd_cache()
        assert db is not None

        cursor = db.execute("PRAGMA table_info(csfd_cache)")
        columns = [row[1] for row in cursor.fetchall()]

        required = ['search_name', 'canonical_key', 'display_name',
                   'original_title', 'czech_title', 'csfd_id', 'plot', 'cached_at']
        for col in required:
            assert col in columns, f"Missing column: {col}. Found: {columns}"
        db.close()

    def test_cache_init_idempotent(self):
        """Can call init_csfd_cache() multiple times."""
        db1 = init_csfd_cache()
        assert db1 is not None
        db1.close()

        db2 = init_csfd_cache()
        assert db2 is not None
        db2.close()


class TestCleanForCanonical:
    """Test name normalization for canonical keys."""

    def test_clean_basic_ascii(self):
        """Basic ASCII normalization to lowercase."""
        result = _clean_for_canonical("Suits")
        assert result == "suits", f"Expected 'suits', got '{result}'"

    def test_clean_czech_diacritics(self):
        """Czech diacritics normalized to ASCII."""
        result = _clean_for_canonical("Kravaťáci")
        assert result == "kravataci", f"Expected 'kravataci', got '{result}'"

    def test_clean_all_15_czech_chars(self):
        """All 15 Czech special characters normalized."""
        # á č ď é ě í ň ó ř š ť ú ů ý ž
        input_text = "áčďéěíňóřšťúůýž"
        # unidecode may handle ň as 'n' (single char) depending on implementation
        result = _clean_for_canonical(input_text)
        # Verify key characters are normalized
        assert 'a' in result  # á
        assert 'c' in result  # č
        assert 'e' in result  # é, ě
        assert 'i' in result  # í
        assert 'n' in result  # ň
        assert 'r' in result  # ř
        assert 's' in result  # š
        assert 't' in result  # ť
        assert 'u' in result  # ú, ů
        assert 'y' in result  # ý
        assert 'z' in result  # ž
        # No diacritics should remain
        assert not any(c in result for c in 'áčďéěíňóřšťúůýž')
        print(f"  Normalized: '{input_text}' -> '{result}'")

    def test_clean_whitespace_normalization(self):
        """Multiple spaces normalized to single space."""
        result = _clean_for_canonical("  Multiple   Spaces  ")
        assert result == "multiple spaces", f"Expected 'multiple spaces', got '{result}'"

    def test_clean_empty_string(self):
        """Empty string handled correctly."""
        result = _clean_for_canonical("")
        assert result == "", f"Expected empty string, got '{result}'"


class TestFormatDisplayName:
    """Test display name formatting."""

    def test_format_both_names_different(self):
        """Both names different -> 'Czech / Original'."""
        result = format_display_name("Suits", "Kravaťáci")
        assert result == "Kravaťáci / Suits", f"Expected 'Kravaťáci / Suits', got '{result}'"

    def test_format_both_names_same(self):
        """Same names (case-insensitive) -> single name."""
        result = format_display_name("Suits", "suits")
        assert result == "suits", f"Expected 'suits', got '{result}'"

    def test_format_only_original(self):
        """Only original title -> use it."""
        result = format_display_name("Suits", "")
        assert result == "Suits", f"Expected 'Suits', got '{result}'"

    def test_format_only_czech(self):
        """Only Czech title -> use it."""
        result = format_display_name("", "Kravaťáci")
        assert result == "Kravaťáci", f"Expected 'Kravaťáci', got '{result}'"


class TestCreateCanonicalFromDualNames:
    """Test canonical key creation from dual names."""

    def test_canonical_basic_dual(self):
        """Basic dual names -> sorted canonical key."""
        result = create_canonical_from_dual_names("Suits", "Kravaťáci")
        assert result is not None
        assert result['canonical_key'] == "kravataci|suits", \
            f"Expected 'kravataci|suits', got '{result['canonical_key']}'"
        # Display name keeps both for dual-name detection (not from merge)
        assert result['display_name'] == "Kravaťáci / Suits"

    def test_canonical_sorted_alphabetically(self):
        """Keys always sorted alphabetically."""
        result1 = create_canonical_from_dual_names("Suits", "Kravaťáci")
        result2 = create_canonical_from_dual_names("Kravaťáci", "Suits")

        assert result1['canonical_key'] == result2['canonical_key'], \
            f"Order matters: {result1['canonical_key']} != {result2['canonical_key']}"

    def test_canonical_substring_detection(self):
        """Substring detected -> use longer name only."""
        result = create_canonical_from_dual_names("South Park", "Městečko South Park")
        assert result is not None
        assert '|' not in result['canonical_key'], \
            f"Substring should not have pipe: {result['canonical_key']}"
        assert 'mestecko south park' in result['canonical_key']

    def test_canonical_empty_name(self):
        """Empty name -> None."""
        result = create_canonical_from_dual_names("", "Suits")
        assert result is None, f"Expected None for empty name, got {result}"

    def test_canonical_same_names(self):
        """Same names -> None."""
        result = create_canonical_from_dual_names("Suits", "Suits")
        assert result is None, f"Expected None for same names, got {result}"


class TestSearchCSFD:
    """Test CSFD search (LIVE NETWORK)."""

    def test_search_suits_finds_results(self):
        """Search 'suits' returns results with id/title/year."""
        if should_skip_live_tests():
            print("⊘ Skipped (SKIP_LIVE_TESTS=1)")
            return

        if not REQUESTS_AVAILABLE:
            print("⊘ Skipped (requests not available)")
            return

        print("Searching CSFD for 'suits'...")
        results = search_csfd("suits")

        assert results is not None, "search_csfd returned None"
        assert isinstance(results, list), f"Expected list, got {type(results)}"
        assert len(results) > 0, "No results found for 'suits'"

        first = results[0]
        assert 'id' in first, f"Missing 'id' in result: {first}"
        assert 'title' in first, f"Missing 'title' in result: {first}"
        assert 'year' in first, f"Missing 'year' in result: {first}"

        print(f"  Found {len(results)} results")
        print(f"  First result: {first['title']} ({first['year']}) [ID: {first['id']}]")

    def test_search_south_park_finds_results(self):
        """Search 'south park' finds popular series."""
        if should_skip_live_tests():
            print("⊘ Skipped (SKIP_LIVE_TESTS=1)")
            return

        if not REQUESTS_AVAILABLE:
            print("⊘ Skipped (requests not available)")
            return

        print("Searching CSFD for 'south park'...")
        results = search_csfd("south park")

        assert results is not None, "search_csfd returned None"
        assert len(results) > 0, "No results for 'south park'"

        print(f"  Found {len(results)} results")

    def test_search_result_structure(self):
        """Search results have proper structure."""
        if should_skip_live_tests():
            print("⊘ Skipped (SKIP_LIVE_TESTS=1)")
            return

        if not REQUESTS_AVAILABLE:
            print("⊘ Skipped (requests not available)")
            return

        results = search_csfd("suits")
        assert results is not None and len(results) > 0

        for result in results:
            assert isinstance(result['id'], str), f"ID should be string: {result['id']}"
            assert isinstance(result['title'], str), f"Title should be string: {result['title']}"
            assert isinstance(result['year'], str), f"Year should be string: {result['year']}"


class TestGetCSFDTitles:
    """Test CSFD title extraction (LIVE NETWORK)."""

    def test_get_titles_suits(self):
        """Extract titles for Suits (film_id=228986)."""
        if should_skip_live_tests():
            print("⊘ Skipped (SKIP_LIVE_TESTS=1)")
            return

        if not REQUESTS_AVAILABLE:
            print("⊘ Skipped (requests not available)")
            return

        print("Fetching CSFD titles for Suits (228986)...")
        titles = get_csfd_titles("228986")

        assert titles is not None, "get_csfd_titles returned None"
        assert 'local' in titles
        assert 'original' in titles
        assert 'czech' in titles
        assert 'is_series' in titles

        print(f"  Local: {titles.get('local')}")
        print(f"  Original: {titles.get('original')}")
        print(f"  Czech: {titles.get('czech')}")
        print(f"  Is Series: {titles['is_series']}")

        # Suits should be a series
        assert titles['is_series'] == True, "Suits should be detected as series"

    def test_get_titles_series_detection(self):
        """Series detection works for TV shows."""
        if should_skip_live_tests():
            print("⊘ Skipped (SKIP_LIVE_TESTS=1)")
            return

        if not REQUESTS_AVAILABLE:
            print("⊘ Skipped (requests not available)")
            return

        titles = get_csfd_titles("228986")  # Suits
        assert titles is not None
        assert titles['is_series'] == True

    def test_get_titles_plot_extraction(self):
        """Plot text extracted and cleaned."""
        if should_skip_live_tests():
            print("⊘ Skipped (SKIP_LIVE_TESTS=1)")
            return

        if not REQUESTS_AVAILABLE:
            print("⊘ Skipped (requests not available)")
            return

        titles = get_csfd_titles("228986")  # Suits
        assert titles is not None

        # Plot may or may not exist, but if it does, should be non-empty
        if 'plot' in titles:
            print(f"  Plot: {titles['plot'][:100]}...")
            assert len(titles['plot']) > 0


class TestLookupSeriesCSFD:
    """Test full CSFD lookup with caching (LIVE NETWORK)."""

    def setUp(self):
        """Create temp cache database."""
        self.temp_dir = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.temp_dir)
        self.cache_db = init_csfd_cache()

    def tearDown(self):
        """Clean up cache database."""
        if self.cache_db:
            self.cache_db.close()
        os.chdir(self.old_cwd)
        shutil.rmtree(self.temp_dir)

    def test_lookup_cache_miss_then_hit(self):
        """First call hits network, second from cache."""
        if should_skip_live_tests():
            print("⊘ Skipped (SKIP_LIVE_TESTS=1)")
            return

        if not REQUESTS_AVAILABLE:
            print("⊘ Skipped (requests not available)")
            return

        print("Testing cache miss then hit for 'suits'...")

        # First lookup - cache miss
        result1 = lookup_series_csfd("suits", self.cache_db)
        assert result1 is not None, "First lookup returned None"
        assert 'canonical_key' in result1
        assert 'display_name' in result1
        print(f"  Cache miss: {result1['canonical_key']}")

        # Second lookup - cache hit (no network request)
        result2 = lookup_series_csfd("suits", self.cache_db)
        assert result2 is not None, "Second lookup returned None"
        assert result2['canonical_key'] == result1['canonical_key']
        print(f"  Cache hit: {result2['canonical_key']}")

    def test_lookup_canonical_key_creation(self):
        """Canonical key created correctly."""
        if should_skip_live_tests():
            print("⊘ Skipped (SKIP_LIVE_TESTS=1)")
            return

        if not REQUESTS_AVAILABLE:
            print("⊘ Skipped (requests not available)")
            return

        result = lookup_series_csfd("suits", self.cache_db)
        assert result is not None

        canonical_key = result['canonical_key']
        print(f"  Canonical key: {canonical_key}")

        # Should contain normalized names
        assert canonical_key is not None
        assert len(canonical_key) > 0

    def test_lookup_cache_persistence(self):
        """Data actually stored in SQLite."""
        if should_skip_live_tests():
            print("⊘ Skipped (SKIP_LIVE_TESTS=1)")
            return

        if not REQUESTS_AVAILABLE:
            print("⊘ Skipped (requests not available)")
            return

        result = lookup_series_csfd("suits", self.cache_db)
        assert result is not None

        # Query cache directly
        cursor = self.cache_db.execute(
            "SELECT canonical_key, display_name FROM csfd_cache WHERE search_name = ?",
            ("suits",)
        )
        row = cursor.fetchone()

        assert row is not None, "Data not found in cache"
        assert row[0] == result['canonical_key']
        print(f"  Cached: search_name='suits' -> canonical_key='{row[0]}'")


class TestErrorResilience:
    """Test error handling."""

    def test_search_requests_unavailable(self):
        """Handle REQUESTS_AVAILABLE=False gracefully."""
        if REQUESTS_AVAILABLE:
            print("⊘ Skipped (requests is available)")
            return

        result = search_csfd("suits")
        assert result is None, "Should return None when requests unavailable"

    def test_clean_none_input(self):
        """Handle None input gracefully."""
        result = _clean_for_canonical(None)
        assert result == "", f"Expected empty string for None, got '{result}'"


# Test runner
if __name__ == '__main__':
    verbose = '--verbose' in sys.argv

    test_classes = [
        TestCacheInitialization,
        TestCleanForCanonical,
        TestFormatDisplayName,
        TestCreateCanonicalFromDualNames,
        TestSearchCSFD,  # Live network
        TestGetCSFDTitles,  # Live network
        TestLookupSeriesCSFD,  # Live network + cache
        TestErrorResilience,
    ]

    passed = 0
    failed = 0
    skipped = 0

    skip_live = should_skip_live_tests()
    if skip_live:
        print("=" * 60)
        print("SKIP_LIVE_TESTS=1 - Skipping live network tests")
        print("=" * 60)

    for test_class in test_classes:
        print(f"\n{'=' * 60}")
        print(f"{test_class.__name__}")
        print('=' * 60)

        test_obj = test_class()

        # Setup if exists
        if hasattr(test_obj, 'setUp'):
            try:
                test_obj.setUp()
            except Exception as e:
                print(f"✗ setUp failed: {e}")
                failed += 1
                continue

        # Run test methods
        for method_name in dir(test_obj):
            if method_name.startswith('test_'):
                try:
                    method = getattr(test_obj, method_name)
                    method()
                    print(f"✓ {method_name}")
                    passed += 1
                except AssertionError as e:
                    print(f"✗ {method_name}: {e}")
                    failed += 1
                except Exception as e:
                    print(f"✗ {method_name}: ERROR: {e}")
                    if verbose:
                        import traceback
                        traceback.print_exc()
                    failed += 1

        # Teardown if exists
        if hasattr(test_obj, 'tearDown'):
            try:
                test_obj.tearDown()
            except Exception as e:
                print(f"✗ tearDown failed: {e}")

    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed")
    print('=' * 60)

    sys.exit(0 if failed == 0 else 1)
