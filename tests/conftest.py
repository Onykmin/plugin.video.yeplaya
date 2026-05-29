# -*- coding: utf-8 -*-
"""Pytest configuration with Kodi module mocks."""
import sys
import pytest
from unittest.mock import MagicMock, patch


class MockAddon:
    """Mock Kodi addon."""

    def __init__(self):
        self._settings = {}

    def getSetting(self, key):
        return self._settings.get(key, '')

    def getSettingBool(self, key):
        val = self._settings.get(key, 'true')
        return val == 'true' or val is True

    def setSetting(self, key, value):
        self._settings[key] = value

    def getAddonInfo(self, key):
        return 'TestAddon'

    def getLocalizedString(self, id):
        return f'String_{id}'

    def openSettings(self):
        pass


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
    xbmc.LOGDEBUG = 0
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
    xbmcplugin.SORT_METHOD_NONE = 0
    xbmcplugin.SORT_METHOD_LABEL = 1

    xbmcvfs = MagicMock()
    xbmcvfs.translatePath = lambda x: x
    xbmcvfs.exists = MagicMock(return_value=True)

    # Sentinel so the autouse guard can detect if an integration test has
    # since replaced this module with its own bare mock.
    xbmc._yeplaya_canonical_mock = True

    sys.modules['xbmc'] = xbmc
    sys.modules['xbmcaddon'] = xbmcaddon
    sys.modules['xbmcgui'] = xbmcgui
    sys.modules['xbmcplugin'] = xbmcplugin
    sys.modules['xbmcvfs'] = xbmcvfs

    return mock_addon


# Setup mocks before any imports
_mock_addon = setup_kodi_mocks()

# Snapshot the canonical Kodi mock module objects so the autouse guard can
# restore the SAME objects (lib.* modules captured these at import time, so
# restoring the identical objects keeps their references valid).
_CANONICAL_KODI = {name: sys.modules[name] for name in
                   ('xbmc', 'xbmcaddon', 'xbmcgui', 'xbmcplugin', 'xbmcvfs')}


def _preimport_lib_modules():
    """Import lib.* under the canonical mocks NOW, before any integration test
    file (collected first, alphabetically) can swap in its bare mocks.

    lib modules capture Kodi handles at import time (``import xbmc``,
    ``_addon = get_addon()``). Caching them canonical-bound here means later
    integration-time ``sys.modules['xbmc'] = MockXBMC`` cannot rebind them,
    so unit tests always see canonical-bound lib modules — no per-test purge
    needed (which would split module identity for tests that patch by path).
    """
    for name in ('lib.utils', 'lib.cache', 'lib.keys', 'lib.state',
                 'lib.grouping', 'lib.playback', 'lib.favorites',
                 'lib.favorites_ui', 'lib.search_ui', 'lib.series_ui',
                 'lib.ui', 'lib.routing'):
        try:
            __import__(name)
        except Exception:
            pass  # best-effort; skip any module that can't import standalone


_preimport_lib_modules()


@pytest.fixture(autouse=True)
def _restore_canonical_kodi_mocks():
    """Guarantee every test sees the canonical Kodi mocks.

    Integration tests install their own bare ``MockXBMC`` into ``sys.modules``
    at import time and never restore it, which would leak into tests run in
    the same session. Before each test, if the canonical xbmc mock has been
    clobbered, restore the snapshot — the SAME objects the (pre-imported)
    lib.* modules already reference, so no module reload is needed.
    """
    if sys.modules.get('xbmc') is not _CANONICAL_KODI['xbmc']:
        sys.modules.update(_CANONICAL_KODI)
        # Re-point Addon in place WITHOUT purging lib.* (purging would split
        # module identity for tests that patch by dotted path).
        _mock_addon._settings = {}
        _CANONICAL_KODI['xbmcaddon'].Addon = MagicMock(return_value=_mock_addon)
    yield


def get_mock_addon():
    """Return the mock addon instance."""
    return _mock_addon


def reset_mock_addon():
    """Reset mock addon settings and re-initialize lib modules that depend on it."""
    _mock_addon._settings = {}
    # Restore the global mock: other tests (e.g. test_player_lang) replace
    # xbmcaddon.Addon with a MagicMock bound to a different addon instance.
    xbmcaddon = sys.modules.get('xbmcaddon')
    if xbmcaddon is not None:
        xbmcaddon.Addon = MagicMock(return_value=_mock_addon)
    # Clear cached lib modules so they pick up fresh mock state
    for mod in list(sys.modules.keys()):
        if mod.startswith('lib.'):
            del sys.modules[mod]
    return _mock_addon


def make_kodi_recorder(dialog_yesno=True):
    """Ordered call recorder spanning Kodi runtime entry points.

    Returns (events, dialog). `events` is a list of (kind, payload) tuples
    in invocation order. Useful for asserting Kodi contract invariants
    like "endOfDirectory must precede Container.Update" — pitfalls a
    plain MagicMock can't detect because it records each attribute
    independently with no cross-module ordering.

    Kinds:
      ('exec', cmd)     — xbmc.executebuiltin
      ('end', succeeded)— xbmcplugin.endOfDirectory
      ('resolved', ok)  — xbmcplugin.setResolvedUrl
      ('yesno', None)   — xbmcgui.Dialog().yesno
      ('ok', None)      — xbmcgui.Dialog().ok
      ('popinfo', msg)  — utils.popinfo

    Callers should call this in setUp and tear back to MagicMock in
    tearDown, since it mutates module-level globals.
    """
    import xbmc, xbmcgui, xbmcplugin
    events = []

    xbmc.executebuiltin = lambda cmd: events.append(('exec', cmd))

    def _end(handle, succeeded=True, updateListing=False, cacheToDisc=True):
        events.append(('end', succeeded))
    xbmcplugin.endOfDirectory = _end

    def _resolved(handle, succeeded, listitem):
        events.append(('resolved', succeeded))
    xbmcplugin.setResolvedUrl = _resolved

    dialog = MagicMock()
    def _yesno(*a, **kw):
        events.append(('yesno', None))
        return dialog_yesno
    def _ok(*a, **kw):
        events.append(('ok', None))
    dialog.yesno = _yesno
    dialog.ok = _ok
    xbmcgui.Dialog = lambda: dialog

    # popinfo is module-level in utils + sometimes re-imported elsewhere;
    # callers can patch additional sites if they pin to a stale binding.
    try:
        from lib import utils
        def _popinfo(message, heading=None, icon=None, time=3000, sound=False):
            events.append(('popinfo', message))
        utils.popinfo = _popinfo
    except ImportError:
        pass

    return events, dialog
