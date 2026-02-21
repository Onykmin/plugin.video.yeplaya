#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for player module — mocked Kodi."""
import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from tests.conftest import MockPlayer, MockMonitor, MockAddon


def _ensure_xbmc_mocks():
    """Ensure xbmc mock has proper Player and Monitor classes."""
    xbmc = sys.modules.get('xbmc')
    if xbmc is not None:
        try:
            if not isinstance(xbmc.Player, type) or not issubclass(xbmc.Player, MockPlayer):
                xbmc.Player = MockPlayer
        except (TypeError, AttributeError):
            xbmc.Player = MockPlayer
        try:
            if not isinstance(xbmc.Monitor, type) or not issubclass(xbmc.Monitor, MockMonitor):
                xbmc.Monitor = MockMonitor
        except (TypeError, AttributeError):
            xbmc.Monitor = MockMonitor


class TestYePlayer:

    def _make_player(self, settings=None):
        """Create YePlayer with given settings."""
        _ensure_xbmc_mocks()
        addon = MockAddon()
        addon._settings = settings or {}
        # Mock xbmcaddon.Addon() to return our test addon (fresh each call)
        xbmcaddon = sys.modules.get('xbmcaddon')
        if xbmcaddon is not None:
            xbmcaddon.Addon = MagicMock(return_value=addon)
        # Clear player module to force re-import
        if 'lib.player' in sys.modules:
            del sys.modules['lib.player']
        from lib.player import YePlayer
        player = YePlayer()
        return player

    def test_selects_audio(self):
        player = self._make_player({'audio_lang': 'Japanese', 'audio_lang2': 'English'})
        player.getAvailableAudioStreams = MagicMock(return_value=['English', 'Japanese', 'Czech'])
        player.getAvailableSubtitleStreams = MagicMock(return_value=[])
        player.setAudioStream = MagicMock()
        player.onAVStarted()
        player.setAudioStream.assert_called_once_with(1)

    def test_selects_subtitle(self):
        player = self._make_player({'sub_lang': 'English', 'sub_lang2': 'Czech', 'sub_auto': 'true'})
        player.getAvailableAudioStreams = MagicMock(return_value=['Japanese'])
        player.getAvailableSubtitleStreams = MagicMock(return_value=['Czech', 'English'])
        player.setSubtitleStream = MagicMock()
        player.showSubtitles = MagicMock()
        player.onAVStarted()
        player.setSubtitleStream.assert_called_once_with(1)
        player.showSubtitles.assert_called_once_with(True)

    def test_auto_subs_off(self):
        player = self._make_player({'sub_lang': 'English', 'sub_auto': 'false'})
        player.getAvailableAudioStreams = MagicMock(return_value=['Japanese'])
        player.getAvailableSubtitleStreams = MagicMock(return_value=['English'])
        player.setSubtitleStream = MagicMock()
        player.showSubtitles = MagicMock()
        player.onAVStarted()
        player.setSubtitleStream.assert_called_once_with(0)
        player.showSubtitles.assert_not_called()

    def test_noop_disabled(self):
        player = self._make_player({'audio_lang': 'Disabled', 'sub_lang': 'Disabled'})
        player.getAvailableAudioStreams = MagicMock(return_value=['English', 'Japanese'])
        player.getAvailableSubtitleStreams = MagicMock(return_value=['English'])
        player.setAudioStream = MagicMock()
        player.setSubtitleStream = MagicMock()
        player.onAVStarted()
        player.setAudioStream.assert_not_called()
        player.setSubtitleStream.assert_not_called()

    def test_noop_single_audio(self):
        player = self._make_player({'audio_lang': 'Japanese'})
        player.getAvailableAudioStreams = MagicMock(return_value=['Japanese'])
        player.getAvailableSubtitleStreams = MagicMock(return_value=[])
        player.setAudioStream = MagicMock()
        player.onAVStarted()
        player.setAudioStream.assert_not_called()

    def test_error_logged_not_raised(self):
        player = self._make_player({'audio_lang': 'Japanese'})
        player.getAvailableAudioStreams = MagicMock(side_effect=RuntimeError("boom"))
        player.getAvailableSubtitleStreams = MagicMock(return_value=[])
        # Should not raise
        player.onAVStarted()

    def test_fallback_audio(self):
        player = self._make_player({'audio_lang': 'Korean', 'audio_lang2': 'English'})
        player.getAvailableAudioStreams = MagicMock(return_value=['English', 'Japanese'])
        player.getAvailableSubtitleStreams = MagicMock(return_value=[])
        player.setAudioStream = MagicMock()
        player.onAVStarted()
        player.setAudioStream.assert_called_once_with(0)

    def test_settings_hot_reload(self):
        """Settings change between playbacks should be picked up."""
        _ensure_xbmc_mocks()
        addon = MockAddon()
        addon._settings = {'audio_lang': 'Japanese', 'audio_lang2': 'English'}
        xbmcaddon = sys.modules.get('xbmcaddon')
        xbmcaddon.Addon = MagicMock(return_value=addon)
        if 'lib.player' in sys.modules:
            del sys.modules['lib.player']
        from lib.player import YePlayer

        # First playback — Japanese selected
        player = YePlayer()
        player.getAvailableAudioStreams = MagicMock(return_value=['English', 'Japanese'])
        player.getAvailableSubtitleStreams = MagicMock(return_value=[])
        player.setAudioStream = MagicMock()
        player.onAVStarted()
        player.setAudioStream.assert_called_once_with(1)

        # User changes settings
        addon._settings = {'audio_lang': 'English', 'audio_lang2': 'English'}

        # Second playback — same player class, should pick up new settings
        player2 = YePlayer()
        player2.getAvailableAudioStreams = MagicMock(return_value=['English', 'Japanese'])
        player2.getAvailableSubtitleStreams = MagicMock(return_value=[])
        player2.setAudioStream = MagicMock()
        player2.onAVStarted()
        player2.setAudioStream.assert_called_once_with(0)

    def test_no_match_keeps_default(self):
        """No matching stream → no setAudioStream/setSubtitleStream call."""
        player = self._make_player({'audio_lang': 'Korean', 'sub_lang': 'Korean'})
        player.getAvailableAudioStreams = MagicMock(return_value=['English', 'Japanese'])
        player.getAvailableSubtitleStreams = MagicMock(return_value=['English'])
        player.setAudioStream = MagicMock()
        player.setSubtitleStream = MagicMock()
        player.onAVStarted()
        player.setAudioStream.assert_not_called()
        player.setSubtitleStream.assert_not_called()

    def test_missing_settings_graceful(self):
        """Old addon without language settings → no crash (getSetting returns '')."""
        player = self._make_player({})
        player.getAvailableAudioStreams = MagicMock(return_value=['English', 'Japanese'])
        player.getAvailableSubtitleStreams = MagicMock(return_value=['English'])
        player.setAudioStream = MagicMock()
        player.setSubtitleStream = MagicMock()
        player.onAVStarted()
        player.setAudioStream.assert_not_called()
        player.setSubtitleStream.assert_not_called()

    def test_set_audio_stream_throws(self):
        """Exception in setAudioStream should not crash."""
        player = self._make_player({'audio_lang': 'Japanese'})
        player.getAvailableAudioStreams = MagicMock(return_value=['English', 'Japanese'])
        player.getAvailableSubtitleStreams = MagicMock(return_value=[])
        player.setAudioStream = MagicMock(side_effect=RuntimeError("kodi internal error"))
        # Should not raise — caught by outer try/except in onAVStarted
        player.onAVStarted()

    def test_wait_for_playback_returns_on_av_started(self):
        """wait_for_playback exits immediately when _av_started is True."""
        player = self._make_player({})
        player._av_started = True
        # Should return immediately without looping
        player.wait_for_playback(timeout=1)

    def test_wait_for_playback_returns_on_error(self):
        """wait_for_playback exits on playback error."""
        player = self._make_player({})
        player._error = True
        player.wait_for_playback(timeout=1)

    def test_on_playback_error_sets_flag(self):
        """onPlayBackError should set _error flag."""
        player = self._make_player({})
        assert player._error is False
        player.onPlayBackError()
        assert player._error is True

    def test_on_playback_stopped_sets_flag(self):
        player = self._make_player({})
        player.onPlayBackStopped()
        assert player._error is True

    def test_on_playback_ended_sets_flag(self):
        player = self._make_player({})
        player.onPlayBackEnded()
        assert player._error is True

    def test_sub_auto_missing_defaults_off(self):
        """If sub_auto not in settings, subtitles found but not auto-enabled."""
        player = self._make_player({'sub_lang': 'English'})
        player.getAvailableAudioStreams = MagicMock(return_value=['Japanese'])
        player.getAvailableSubtitleStreams = MagicMock(return_value=['English'])
        player.setSubtitleStream = MagicMock()
        player.showSubtitles = MagicMock()
        player.onAVStarted()
        player.setSubtitleStream.assert_called_once_with(0)
        player.showSubtitles.assert_not_called()
