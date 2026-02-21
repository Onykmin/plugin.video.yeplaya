# -*- coding: utf-8 -*-
"""Pytest configuration with Kodi module mocks."""
import sys
from unittest.mock import MagicMock, patch


class MockAddon:
    """Mock Kodi addon."""

    def __init__(self):
        self._settings = {}

    def getSetting(self, key):
        return self._settings.get(key, '')

    def setSetting(self, key, value):
        self._settings[key] = value

    def getAddonInfo(self, key):
        return 'TestAddon'

    def getLocalizedString(self, id):
        return f'String_{id}'


class MockListItem:
    """Mock Kodi ListItem."""

    def __init__(self, label=''):
        self.label = label
        self._art = {}
        self._info = {}
        self._properties = {}
        self._context = []

    def getVideoInfoTag(self):
        return MagicMock()

    def setArt(self, art):
        self._art.update(art)

    def setInfo(self, type, info):
        self._info.update(info)

    def setProperty(self, key, value):
        self._properties[key] = value

    def addContextMenuItems(self, items):
        self._context = items


class MockMonitor:
    """Mock Kodi Monitor."""

    def waitForAbort(self, timeout=None):
        return False


class MockPlayer:
    """Mock Kodi Player base class for subclassing."""

    def onAVStarted(self):
        pass

    def onPlayBackError(self):
        pass

    def onPlayBackStopped(self):
        pass

    def onPlayBackEnded(self):
        pass

    def getAvailableAudioStreams(self):
        return []

    def getAvailableSubtitleStreams(self):
        return []

    def setAudioStream(self, idx):
        pass

    def setSubtitleStream(self, idx):
        pass

    def showSubtitles(self, visible):
        pass


def setup_kodi_mocks():
    """Setup Kodi module mocks."""
    mock_addon = MockAddon()

    xbmc = MagicMock()
    xbmc.LOGINFO = 1
    xbmc.LOGWARNING = 2
    xbmc.LOGERROR = 3
    xbmc.Keyboard = MagicMock()
    xbmc.Player = MockPlayer
    xbmc.Monitor = MockMonitor

    xbmcaddon = MagicMock()
    xbmcaddon.Addon.return_value = mock_addon

    xbmcgui = MagicMock()
    xbmcgui.ListItem = MockListItem
    xbmcgui.NOTIFICATION_INFO = 1
    xbmcgui.NOTIFICATION_WARNING = 2
    xbmcgui.NOTIFICATION_ERROR = 3

    xbmcplugin = MagicMock()

    sys.modules['xbmc'] = xbmc
    sys.modules['xbmcaddon'] = xbmcaddon
    sys.modules['xbmcgui'] = xbmcgui
    sys.modules['xbmcplugin'] = xbmcplugin

    return mock_addon


# Setup mocks before any imports
_mock_addon = setup_kodi_mocks()


def get_mock_addon():
    """Return the mock addon instance."""
    return _mock_addon


def reset_mock_addon():
    """Reset mock addon settings and re-initialize lib modules that depend on it."""
    _mock_addon._settings = {}
    # Clear cached lib modules so they pick up fresh mock state
    for mod in list(sys.modules.keys()):
        if mod.startswith('lib.'):
            del sys.modules[mod]
    return _mock_addon
