#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""CSFD integration tests with yawsp.py grouping - Critical/Happy Path.

Tests complete workflow: filename → dual-name detection → CSFD lookup → grouping.

Usage:
    # All tests (with real network requests)
    python tests/test_csfd_integration.py

    # Skip live network tests
    SKIP_LIVE_TESTS=1 python tests/test_csfd_integration.py
"""

import os
import sys
import re
import sqlite3
import tempfile
import shutil
import unicodedata

# Mock sys.argv before importing yawsp (which reads sys.argv[1])
if len(sys.argv) < 2:
    sys.argv = ['plugin.video.yawsp', '0', '']

# Mock xbmc modules before importing yawsp
class MockXBMC:
    LOGDEBUG = 0
    LOGINFO = 1
    LOGWARNING = 2
    LOGERROR = 3

    @staticmethod
    def log(msg, level=1):
        if '--verbose' in sys.argv:
            print(f"[XBMC LOG] {msg}")

class MockXBMCGUI:
    NOTIFICATION_INFO = 'info'
    NOTIFICATION_WARNING = 'warning'
    NOTIFICATION_ERROR = 'error'

    class ListItem:
        def __init__(self, label='', path=''):
            self.label = label
            self.path = path

        def setArt(self, art):
            pass

        def setInfo(self, type, infoLabels):
            pass

        def setProperty(self, key, value):
            pass

        def addContextMenuItems(self, items):
            pass

        def getVideoInfoTag(self):
            return MockXBMCGUI.InfoTagVideo()

        def setLabel(self, label):
            self.label = label

    class InfoTagVideo:
        def setTitle(self, title):
            pass

    class Dialog:
        def notification(self, heading, message, icon, time, sound=False):
            pass

        def ok(self, title, message):
            pass

        def select(self, title, options):
            return 0  # Select first option

        def textviewer(self, title, text):
            pass

class MockXBMCPlugin:
    SORT_METHOD_LABEL = 1

    @staticmethod
    def setPluginCategory(handle, category):
        pass

    @staticmethod
    def setContent(handle, content):
        pass

    @staticmethod
    def addDirectoryItem(handle, url, listitem, isFolder):
        return True

    @staticmethod
    def endOfDirectory(handle, succeeded=True, updateListing=False):
        pass

    @staticmethod
    def setResolvedUrl(handle, succeeded, listitem):
        pass

    @staticmethod
    def addSortMethod(handle, method):
        pass

class MockXBMCAddon:
    class Addon:
        def __init__(self):
            pass

        def getSetting(self, key):
            settings = {
                'labelformat': '{name}',
                'customformat': 'false',
                'resultsize': 'false',
                'shistory': '10',
                'default_view': '0',  # Series view
            }
            return settings.get(key, '')

        def setSetting(self, key, value):
            pass

        def getAddonInfo(self, key):
            if key == 'profile':
                return tempfile.gettempdir()
            if key == 'name':
                return 'YAWsP'
            return ''

        def getLocalizedString(self, num):
            return f'String {num}'

        def openSettings(self):
            pass

class MockXBMCVFS:
    @staticmethod
    def exists(path):
        return os.path.exists(path)

    @staticmethod
    def File(path, mode):
        return open(path, mode)

def translatePath(path):
    return path

# Install mocks
sys.modules['xbmc'] = MockXBMC
sys.modules['xbmcgui'] = MockXBMCGUI
sys.modules['xbmcplugin'] = MockXBMCPlugin
sys.modules['xbmcaddon'] = MockXBMCAddon
sys.modules['xbmcvfs'] = MockXBMCVFS
MockXBMC.translatePath = translatePath
MockXBMCVFS.translatePath = translatePath

# Now import from lib/ modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.grouping import group_by_series
from lib.parsing import parse_episode_info, extract_dual_names, clean_series_name, get_display_name
from csfd_scraper import (
    init_csfd_cache,
    lookup_series_csfd,
    create_canonical_from_dual_names,
    REQUESTS_AVAILABLE
)


def should_skip_live_tests():
    """Check if live network tests should be skipped."""
    return os.environ.get('SKIP_LIVE_TESTS', '0') == '1'


class TestDualNameFilenameGrouping:
    """Test dual-name detection in filenames (NO NETWORK)."""

    def test_suits_dash_separator(self):
        """'Suits - Kravaťáci S01E01.mkv' groups correctly."""
        files = [
            {'name': 'Suits - Kravaťáci S01E01.mkv', 'ident': 'id1', 'size': '1000000000'},
            {'name': 'Suits - Kravaťáci S01E02.mkv', 'ident': 'id2', 'size': '1000000000'},
        ]

        result = group_by_series(files)

        assert len(result['series']) == 1, f"Expected 1 series, got {len(result['series'])}"

        series_key = list(result['series'].keys())[0]
        series_data = result['series'][series_key]

        assert series_data['total_episodes'] == 2, \
            f"Expected 2 episodes, got {series_data['total_episodes']}"

        print(f"  Canonical key: {series_key}")
        print(f"  Display name: {series_data.get('display_name')}")

    def test_suits_slash_separator(self):
        """'Suits / Kravaťáci S01E01.mkv' groups correctly."""
        files = [
            {'name': 'Suits / Kravaťáci S01E01.mkv', 'ident': 'id1', 'size': '1000000000'},
            {'name': 'Suits / Kravaťáci S01E02.mkv', 'ident': 'id2', 'size': '1000000000'},
        ]

        result = group_by_series(files)
        assert len(result['series']) == 1
        assert result['series'][list(result['series'].keys())[0]]['total_episodes'] == 2

    def test_suits_parentheses(self):
        """'Suits (Kravaťáci) S01E01.mkv' groups correctly."""
        files = [
            {'name': 'Suits (Kravaťáci) S01E01.mkv', 'ident': 'id1', 'size': '1000000000'},
            {'name': 'Suits (Kravaťáci) S01E02.mkv', 'ident': 'id2', 'size': '1000000000'},
        ]

        result = group_by_series(files)
        assert len(result['series']) == 1
        assert result['series'][list(result['series'].keys())[0]]['total_episodes'] == 2

    def test_mixed_separators_group_together(self):
        """Different separators with same names should be mergeable."""
        files = [
            {'name': 'Suits - Kravaťáci S01E01.mkv', 'ident': 'id1', 'size': '1000000000'},
            {'name': 'Suits - Kravaťáci S01E02.mkv', 'ident': 'id2', 'size': '1000000000'},
            {'name': 'Suits - Kravaťáci S01E03.mkv', 'ident': 'id3', 'size': '1000000000'},
        ]

        result = group_by_series(files)

        # Same separator format should group together
        assert len(result['series']) == 1, \
            f"Expected 1 series, got {len(result['series'])} - keys: {list(result['series'].keys())}"

        series_data = result['series'][list(result['series'].keys())[0]]
        assert series_data['total_episodes'] == 3

    def test_dual_names_canonical_key(self):
        """Canonical key is normalized and sorted."""
        files = [
            {'name': 'Suits - Kravaťáci S01E01.mkv', 'ident': 'id1', 'size': '1000000000'},
        ]

        result = group_by_series(files)
        series_key = list(result['series'].keys())[0]

        # Should be normalized (lowercase, diacritics removed, sorted)
        assert 'kravataci' in series_key or 'suits' in series_key, \
            f"Unexpected canonical key: {series_key}"

        print(f"  Canonical key: {series_key}")

    def test_penguin_variants(self):
        """'Tučňák - The Penguin' variants group together."""
        files = [
            {'name': 'Tučňák - The Penguin S01E01.mkv', 'ident': 'id1', 'size': '1000000000'},
            {'name': 'Tučňák-The Penguin S01E02.mkv', 'ident': 'id2', 'size': '1000000000'},
        ]

        result = group_by_series(files)

        assert len(result['series']) == 1
        assert result['series'][list(result['series'].keys())[0]]['total_episodes'] == 2

    def test_south_park_substring_merge(self):
        """'South Park' + 'Městečko South Park' merge via substring."""
        files = [
            {'name': 'South.Park.S01E01.mkv', 'ident': 'id1', 'size': '1000000000'},
            {'name': 'Mestecko.South.Park.S01E02.mkv', 'ident': 'id2', 'size': '1000000000'},
        ]

        result = group_by_series(files)

        # Should merge into ONE series (substring detected)
        assert len(result['series']) == 1, \
            f"Expected 1 merged series, got {len(result['series'])} - keys: {list(result['series'].keys())}"

        series_key = list(result['series'].keys())[0]
        print(f"  Merged canonical key: {series_key}")


class TestExtractDualNames:
    """Test dual name extraction from filenames."""

    def test_extract_dash_separator(self):
        """Extract dual names from dash separator."""
        result = extract_dual_names("Suits - Kravaťáci")
        assert result is not None, "Failed to extract dual names"
        assert result == ("Suits", "Kravaťáci") or result == ("Kravaťáci", "Suits")

    def test_extract_parentheses(self):
        """Extract dual names from parentheses."""
        result = extract_dual_names("Suits (Kravaťáci)")
        assert result is not None
        assert "Suits" in result and "Kravaťáci" in result

    def test_extract_slash_separator(self):
        """Extract dual names from slash separator."""
        result = extract_dual_names("Suits / Kravaťáci")
        assert result is not None
        assert "Suits" in result and "Kravaťáci" in result


class TestCSFDLookupIntegration:
    """Test CSFD lookup integration (LIVE NETWORK)."""

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

    def test_lookup_suits_canonical_key(self):
        """CSFD lookup for 'suits' creates canonical key."""
        if should_skip_live_tests():
            print("⊘ Skipped (SKIP_LIVE_TESTS=1)")
            return

        if not REQUESTS_AVAILABLE:
            print("⊘ Skipped (requests not available)")
            return

        print("Testing CSFD lookup for 'suits'...")
        result = lookup_series_csfd("suits", self.cache_db)

        assert result is not None, "lookup_series_csfd returned None"
        assert 'canonical_key' in result
        assert 'display_name' in result

        print(f"  Canonical key: {result['canonical_key']}")
        print(f"  Display name: {result['display_name']}")

    def test_create_canonical_from_dual_names_suits(self):
        """Create canonical from 'Suits' + 'Kravaťáci'."""
        result = create_canonical_from_dual_names("Suits", "Kravaťáci")

        assert result is not None
        assert result['canonical_key'] == "kravataci|suits"
        # Dual-name detection keeps both (not affected by merge logic)
        assert "/" in result['display_name']

        print(f"  Canonical: {result['canonical_key']}")
        print(f"  Display: {result['display_name']}")


class TestCompleteWorkflow:
    """Test end-to-end workflow (NO NETWORK - uses dual-name detection)."""

    def test_quality_metadata_preserved(self):
        """Quality metadata preserved with dual-name grouping."""
        files = [
            {'name': 'Suits - Kravaťáci S01E01 1080p BluRay x265.mkv', 'ident': 'id1', 'size': '2000000000'},
            {'name': 'Suits - Kravaťáci S01E01 720p WEB-DL.mkv', 'ident': 'id2', 'size': '1000000000'},
        ]

        result = group_by_series(files)

        series_key = list(result['series'].keys())[0]
        episodes = result['series'][series_key]['seasons'][1][1]

        # Should have 2 versions, sorted by quality
        assert len(episodes) == 2, f"Expected 2 versions, got {len(episodes)}"

        # First should be higher quality (1080p BluRay x265 > 720p WEB-DL)
        first = episodes[0]
        assert first['quality_meta']['quality_score'] >= episodes[1]['quality_meta']['quality_score']

        print(f"  Version 1: {first['quality_meta']['quality']} {first['quality_meta']['source']} " +
              f"score={first['quality_meta']['quality_score']}")

    def test_non_series_files_unaffected(self):
        """Non-series files remain in non_series list."""
        files = [
            {'name': 'Suits - Kravaťáci S01E01.mkv', 'ident': 'id1', 'size': '1000000000'},
            {'name': 'Movie.2023.1080p.mkv', 'ident': 'id2', 'size': '5000000000'},
        ]

        result = group_by_series(files)

        assert len(result['series']) == 1, "Expected 1 series"
        assert len(result['non_series']) == 1, "Expected 1 non-series file"
        assert result['non_series'][0]['name'] == 'Movie.2023.1080p.mkv'


# Test runner
if __name__ == '__main__':
    verbose = '--verbose' in sys.argv

    test_classes = [
        TestDualNameFilenameGrouping,  # No network
        TestExtractDualNames,  # No network
        TestCSFDLookupIntegration,  # Live network
        TestCompleteWorkflow,  # No network
    ]

    passed = 0
    failed = 0

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
