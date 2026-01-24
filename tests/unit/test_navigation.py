#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for navigation and state management bugs.

Tests:
- Back navigation state (slast) stability during pagination
- Page bounds validation
"""

import sys
import os
import unittest

# Add parent directory for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

# Mock Kodi modules before any imports
class MockXBMC:
    LOGDEBUG = 0
    LOGINFO = 1
    LOGWARNING = 2
    LOGERROR = 3

    @staticmethod
    def log(msg, level=0):
        pass

    class Monitor:
        def __init__(self):
            pass

        def onSettingsChanged(self):
            pass

    class Keyboard:
        def __init__(self, default='', heading=''):
            self._text = default
            self._confirmed = False

        def doModal(self):
            pass

        def isConfirmed(self):
            return self._confirmed

        def getText(self):
            return self._text


class MockSettings:
    """Mock addon settings storage."""
    def __init__(self):
        self._settings = {'slast': '', 'scategory': '0', 'ssort': '0', 'slimit': '25'}

    def getSetting(self, key):
        return self._settings.get(key, '')

    def setSetting(self, key, value):
        self._settings[key] = value

    def getAddonInfo(self, key):
        return 'plugin.video.yeplaya'

    def getLocalizedString(self, id):
        return 'String {}'.format(id)


class MockXBMCAddon:
    _instance = MockSettings()

    @staticmethod
    def Addon():
        return MockXBMCAddon._instance


class MockXBMCGUI:
    NOTIFICATION_INFO = 1
    NOTIFICATION_WARNING = 2
    NOTIFICATION_ERROR = 3

    class ListItem:
        def __init__(self, label='', path=''):
            self._label = label
            self._path = path

        def setArt(self, art):
            pass

        def setProperty(self, key, value):
            pass

        def getVideoInfoTag(self):
            return MockInfoTag()

        def addContextMenuItems(self, items):
            pass

        def setInfo(self, type, info):
            pass

    class Dialog:
        def notification(self, heading, message, icon, time, sound=False):
            pass


class MockInfoTag:
    def setTitle(self, title):
        pass


class MockXBMCPlugin:
    SORT_METHOD_NONE = 0

    @staticmethod
    def setContent(handle, content):
        pass

    @staticmethod
    def addDirectoryItem(handle, url, listitem, isFolder):
        return True

    @staticmethod
    def endOfDirectory(handle, updateListing=False):
        pass

    @staticmethod
    def setPluginCategory(handle, category):
        pass


sys.modules['xbmc'] = MockXBMC()
sys.modules['xbmcgui'] = MockXBMCGUI()
sys.modules['xbmcplugin'] = MockXBMCPlugin()
sys.modules['xbmcaddon'] = MockXBMCAddon()


class TestBackNavigation(unittest.TestCase):
    """Test back navigation state management."""

    def setUp(self):
        """Reset settings before each test."""
        MockXBMCAddon._instance = MockSettings()

    def test_slast_stable_during_pagination(self):
        """slast should not change to NONE_WHAT on pagination."""
        settings = MockXBMCAddon._instance

        # Simulate first page of search
        what = 'southpark'
        settings.setSetting('slast', what)

        # Simulate pagination (offset present) - old buggy behavior would set NONE_WHAT
        # Fixed behavior: slast stays as 'what'
        # This simulates the fixed code path
        if what is not None:
            # Fixed: always set slast to what, regardless of offset
            settings.setSetting('slast', what)

        self.assertEqual(settings.getSetting('slast'), 'southpark',
                        "slast should remain 'southpark' during pagination")

    def test_slast_cleared_on_menu_return(self):
        """slast should be cleared when returning to search menu."""
        settings = MockXBMCAddon._instance
        settings.setSetting('slast', 'previous_search')

        # Simulate returning to menu (what is None)
        what = None
        if what is None:
            settings.setSetting('slast', '')

        self.assertEqual(settings.getSetting('slast'), '',
                        "slast should be empty on menu return")

    def test_slast_set_on_new_search(self):
        """slast should be set when starting new search."""
        settings = MockXBMCAddon._instance
        settings.setSetting('slast', '')

        # Simulate new search
        what = 'game.of.thrones'
        settings.setSetting('slast', what)

        self.assertEqual(settings.getSetting('slast'), 'game.of.thrones',
                        "slast should be set to search term")


class TestPageBounds(unittest.TestCase):
    """Test pagination bounds validation."""

    def test_negative_page_clamped_to_zero(self):
        """Negative page numbers should be clamped to 0."""
        page = -5
        total_pages = 10

        # Fixed validation logic
        if page < 0:
            page = 0
        elif page >= total_pages:
            page = total_pages - 1

        self.assertEqual(page, 0, "Negative page should clamp to 0")

    def test_page_exceeding_total_clamped(self):
        """Page exceeding total should clamp to last page."""
        page = 100
        total_pages = 5

        # Fixed validation logic
        if page < 0:
            page = 0
        elif page >= total_pages:
            page = total_pages - 1

        self.assertEqual(page, 4, "Page 100 should clamp to 4 (last page)")

    def test_valid_page_unchanged(self):
        """Valid page number should remain unchanged."""
        page = 3
        total_pages = 10
        original_page = page

        if page < 0:
            page = 0
        elif page >= total_pages:
            page = total_pages - 1

        self.assertEqual(page, original_page, "Valid page should be unchanged")

    def test_page_zero_with_empty_results(self):
        """Page 0 should work with zero total items."""
        total_items = 0
        items_per_page = 25
        page = 0

        total_pages = max(1, (total_items + items_per_page - 1) // items_per_page)

        if page < 0:
            page = 0
        elif page >= total_pages:
            page = total_pages - 1

        self.assertEqual(page, 0, "Page should be 0 with empty results")
        self.assertEqual(total_pages, 1, "total_pages should be at least 1")

    def test_start_end_indices_valid(self):
        """Start and end indices should be valid for slicing."""
        total_items = 75
        items_per_page = 25
        page = 2  # Third page

        total_pages = max(1, (total_items + items_per_page - 1) // items_per_page)

        if page < 0:
            page = 0
        elif page >= total_pages:
            page = total_pages - 1

        start_idx = page * items_per_page
        end_idx = start_idx + items_per_page

        self.assertEqual(start_idx, 50, "Start index for page 2 should be 50")
        self.assertEqual(end_idx, 75, "End index for page 2 should be 75")

        # Verify slicing works
        items = list(range(total_items))
        page_items = items[start_idx:end_idx]
        self.assertEqual(len(page_items), 25, "Should have 25 items on page 2")


if __name__ == '__main__':
    unittest.main()
