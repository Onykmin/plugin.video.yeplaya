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
        player._playback_done = True
        player.wait_for_playback(timeout=1)

    def test_on_playback_error_sets_flag(self):
        """onPlayBackError should set _error flag."""
        player = self._make_player({})
        assert player._playback_done is False
        player.onPlayBackError()
        assert player._playback_done is True

    def test_on_playback_stopped_sets_flag(self):
        player = self._make_player({})
        player.onPlayBackStopped()
        assert player._playback_done is True

    def test_on_playback_ended_sets_flag(self):
        player = self._make_player({})
        player.onPlayBackEnded()
        assert player._playback_done is True

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


# --- JSON-RPC subtitle metadata (v1.2.1 forced-subtitle fix) ---

class TestSubtitleMetadata:

    def _make_player(self, settings=None):
        return TestYePlayer()._make_player(settings)

    def test_metadata_none_when_executeJSONRPC_returns_non_str(self):
        """xbmc.executeJSONRPC on the bare MagicMock() auto-returns a
        MagicMock, not a JSON string — must be treated as unavailable."""
        player = self._make_player({})
        import lib.player as player_mod
        player_mod.xbmc.executeJSONRPC = MagicMock(return_value=MagicMock())
        result = player._get_subtitle_metadata(2)
        assert result is None

    def test_metadata_none_on_malformed_json(self):
        player = self._make_player({})
        import lib.player as player_mod
        player_mod.xbmc.executeJSONRPC = MagicMock(return_value="not valid json{{{")
        result = player._get_subtitle_metadata(2)
        assert result is None

    def test_metadata_none_on_missing_subtitles_key(self):
        player = self._make_player({})
        import json as _json
        import lib.player as player_mod

        def fake_rpc(payload_str):
            payload = _json.loads(payload_str)
            if payload['method'] == 'Player.GetActivePlayers':
                return _json.dumps({"id": 1, "jsonrpc": "2.0",
                                     "result": [{"playerid": 1, "type": "video"}]})
            return _json.dumps({"id": 1, "jsonrpc": "2.0", "result": {"currentsubtitle": {}}})

        player_mod.xbmc.executeJSONRPC = MagicMock(side_effect=fake_rpc)
        result = player._get_subtitle_metadata(2)
        assert result is None

    def test_metadata_none_on_length_mismatch(self):
        player = self._make_player({})
        import json as _json
        import lib.player as player_mod

        def fake_rpc(payload_str):
            payload = _json.loads(payload_str)
            if payload['method'] == 'Player.GetActivePlayers':
                return _json.dumps({"id": 1, "jsonrpc": "2.0",
                                     "result": [{"playerid": 1, "type": "video"}]})
            return _json.dumps({"id": 1, "jsonrpc": "2.0", "result": {
                "subtitles": [{"language": "eng", "name": "English"}],
            }})

        player_mod.xbmc.executeJSONRPC = MagicMock(side_effect=fake_rpc)
        result = player._get_subtitle_metadata(2)  # expected 2, got 1
        assert result is None

    def test_metadata_none_on_index_disagrees_with_position(self):
        player = self._make_player({})
        import json as _json
        import lib.player as player_mod

        def fake_rpc(payload_str):
            payload = _json.loads(payload_str)
            if payload['method'] == 'Player.GetActivePlayers':
                return _json.dumps({"id": 1, "jsonrpc": "2.0",
                                     "result": [{"playerid": 1, "type": "video"}]})
            return _json.dumps({"id": 1, "jsonrpc": "2.0", "result": {
                "subtitles": [
                    {"index": 5, "language": "eng", "name": "English [Forced]",
                     "isforced": True, "isdefault": False},
                    {"index": 1, "language": "eng", "name": "English",
                     "isforced": False, "isdefault": True},
                ],
            }})

        player_mod.xbmc.executeJSONRPC = MagicMock(side_effect=fake_rpc)
        result = player._get_subtitle_metadata(2)
        assert result is None

    def test_metadata_happy_path_selects_index_1(self):
        """Realistic 2-track payload: forced eng at 0, plain default eng at
        1 -> selection lands on index 1 and setSubtitleStream(1) is called."""
        player = self._make_player({'sub_lang': 'English', 'sub_auto': 'false'})
        import json as _json
        import lib.player as player_mod

        def fake_rpc(payload_str):
            payload = _json.loads(payload_str)
            if payload['method'] == 'Player.GetActivePlayers':
                return _json.dumps({"id": 1, "jsonrpc": "2.0",
                                     "result": [{"playerid": 1, "type": "video"}]})
            return _json.dumps({"id": 1, "jsonrpc": "2.0", "result": {
                "subtitles": [
                    {"index": 0, "language": "eng", "name": "English [Forced]",
                     "isforced": True, "isdefault": False},
                    {"index": 1, "language": "eng", "name": "English",
                     "isforced": False, "isdefault": True},
                ],
            }})

        player_mod.xbmc.executeJSONRPC = MagicMock(side_effect=fake_rpc)
        player.getAvailableAudioStreams = MagicMock(return_value=['Japanese'])
        player.getAvailableSubtitleStreams = MagicMock(return_value=['eng', 'eng'])
        player.setSubtitleStream = MagicMock()
        player.showSubtitles = MagicMock()
        player.onAVStarted()
        player.setSubtitleStream.assert_called_once_with(1)

    def test_metadata_no_lang_match_falls_back_to_label_only(self):
        """Well-formed metadata of correct length but with unresolvable
        language/name fields must fall back to label-only matching rather
        than being skipped entirely."""
        player = self._make_player({'sub_lang': 'English', 'sub_auto': 'false'})
        import json as _json
        import lib.player as player_mod

        def fake_rpc(payload_str):
            payload = _json.loads(payload_str)
            if payload['method'] == 'Player.GetActivePlayers':
                return _json.dumps({"id": 1, "jsonrpc": "2.0",
                                     "result": [{"playerid": 1, "type": "video"}]})
            return _json.dumps({"id": 1, "jsonrpc": "2.0", "result": {
                "subtitles": [
                    {"index": 0, "language": "", "name": "", "isforced": False, "isdefault": False},
                    {"index": 1, "language": "", "name": "", "isforced": False, "isdefault": False},
                ],
            }})

        player_mod.xbmc.executeJSONRPC = MagicMock(side_effect=fake_rpc)
        player.getAvailableAudioStreams = MagicMock(return_value=['Japanese'])
        player.getAvailableSubtitleStreams = MagicMock(return_value=['eng', 'eng'])
        player.setSubtitleStream = MagicMock()
        player.showSubtitles = MagicMock()
        player.onAVStarted()
        player.setSubtitleStream.assert_called_once_with(0)

    def test_metadata_jsonrpc_exception_does_not_propagate(self):
        """A raising executeJSONRPC must never break playback selection —
        falls back to label-only matching."""
        player = self._make_player({'sub_lang': 'English', 'sub_auto': 'false'})
        import lib.player as player_mod
        player_mod.xbmc.executeJSONRPC = MagicMock(side_effect=RuntimeError("boom"))
        player.getAvailableAudioStreams = MagicMock(return_value=['Japanese'])
        player.getAvailableSubtitleStreams = MagicMock(return_value=['Czech', 'English'])
        player.setSubtitleStream = MagicMock()
        player.showSubtitles = MagicMock()
        # Should not raise, and should still fall back to label-only match.
        player.onAVStarted()
        player.setSubtitleStream.assert_called_once_with(1)
