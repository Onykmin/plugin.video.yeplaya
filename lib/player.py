# -*- coding: utf-8 -*-
# Module: player
# Author: onykmin
# License: AGPL v.3 https://www.gnu.org/licenses/agpl-3.0.html

"""Custom player with automatic audio/subtitle language selection."""

import json

import xbmc
import xbmcaddon
from lib.language import (
    match_stream, match_stream_meta, normalize_lang, setting_to_code, is_forced_label,
)

_LOG = "yeplaya.player: "


class YePlayer(xbmc.Player):
    """Player subclass that selects preferred audio/subtitle streams on playback start."""

    def __init__(self, state_key=None, tracking_enabled=True):
        super(YePlayer, self).__init__()
        self._av_started = False
        self._playback_done = False
        self._had_error = False
        self._state_key = state_key
        self._tracking_enabled = tracking_enabled
        self._monitor = xbmc.Monitor()
        # Last position/total sampled while the player was demonstrably alive.
        # getTime()/getTotalTime() are unreliable once playback has stopped, so
        # we poll during playback and prefer these values at capture time.
        self._last_pos = 0.0
        self._last_total = 0.0

    def _poll_position(self):
        """Sample current position while playing; keep the last valid reading."""
        try:
            pos = self.getTime()
            total = self.getTotalTime()
        except Exception:
            return
        if total and total > 0:
            self._last_pos = float(pos or 0)
            self._last_total = float(total)

    def wait_for_playback(self, timeout=30):
        """Keep the plugin script alive across the whole playback session.

        Phase 1: wait up to `timeout` seconds for playback to actually start
        (onAVStarted), or for an early error/abort. Phase 2: once playing, loop
        — polling position so we have a reliable resume point — until playback
        stops/ends or Kodi aborts. Without phase 2 the script would return the
        instant playback started, the interpreter would tear down, and the
        onPlayBackStopped/Ended callbacks (hence resume/watched tracking) would
        never fire.
        """
        for _ in range(timeout * 10):
            if self._av_started or self._playback_done:
                break
            if self._monitor.waitForAbort(0.1):
                return
        else:
            xbmc.log(_LOG + "wait_for_playback: timeout after %ds" % timeout, xbmc.LOGWARNING)
            return
        if self._playback_done:
            return
        # Phase 2: stay alive while the media plays so stop/end callbacks fire.
        # isPlaying() is the primary exit signal; if it is unavailable or raises
        # we must NOT spin forever, so treat that as "stop waiting". waitForAbort
        # paces the loop and exits on Kodi shutdown.
        xbmc.log(_LOG + "wait_for_playback: entering keep-alive loop", xbmc.LOGDEBUG)
        elapsed = 0.0
        while not self._playback_done:
            self._poll_position()
            try:
                if not self.isPlaying():
                    xbmc.log(_LOG + "wait_for_playback: isPlaying() False, exiting",
                             xbmc.LOGDEBUG)
                    break
            except Exception:
                break
            # Safety backstop: never loop longer than the media's own duration
            # plus a wide margin. If isPlaying() somehow stays True with no
            # stop/end callback (stuck stream), this prevents an indefinite hang
            # WITHOUT truncating legitimate playback (the cap tracks total time).
            if self._last_total and self._last_total > 0:
                if elapsed > self._last_total + 900:  # +15 min margin
                    xbmc.log(_LOG + "wait_for_playback: backstop hit (%.0fs > "
                             "%.0fs+900), exiting" % (elapsed, self._last_total),
                             xbmc.LOGWARNING)
                    break
            if self._monitor.waitForAbort(1.0):
                break
            elapsed += 1.0

    def _capture_state(self, force_watched=False):
        """Persist resume/watched state while the player is still alive."""
        if not self._tracking_enabled or not self._state_key or self._had_error:
            return
        addon = xbmcaddon.Addon()
        resume_ok = addon.getSetting('track_resume') != 'false'
        watched_ok = addon.getSetting('track_watched') != 'false'
        if not (resume_ok or watched_ok):
            return
        # Prefer the last position sampled during playback: getTime() is
        # unreliable (may return 0 or raise) once playback has stopped.
        if self._last_total and self._last_total > 0:
            pos, total = self._last_pos, self._last_total
            src = "polled"
        else:
            try:
                pos = self.getTime()
                total = self.getTotalTime()
                src = "getTime"
            except Exception as e:
                xbmc.log(_LOG + "capture: getTime failed: %s" % e, xbmc.LOGWARNING)
                pos, total = 0.0, 0.0
                src = "failed"
        xbmc.log(_LOG + "capture(%s): key=%s pos=%.0f total=%.0f force_watched=%s"
                 % (src, self._state_key, pos or 0, total or 0, force_watched),
                 xbmc.LOGINFO)
        try:
            from lib import state
            if force_watched:
                if watched_ok:
                    state.mark_watched(self._state_key)
                return
            if total is None or total <= 0:
                return
            ratio = pos / total
            if ratio >= 0.90:
                if watched_ok:
                    state.mark_watched(self._state_key)
            else:
                if resume_ok:
                    state.record_playback(self._state_key, pos, total)
        except Exception as e:
            xbmc.log(_LOG + "capture: state write failed: %s" % e, xbmc.LOGERROR)

    def onPlayBackError(self):
        self._playback_done = True
        self._had_error = True
        xbmc.log(_LOG + "playback error", xbmc.LOGERROR)

    def onPlayBackStopped(self):
        self._capture_state()
        self._playback_done = True

    def onPlayBackEnded(self):
        self._capture_state(force_watched=True)
        self._playback_done = True

    def onAVStarted(self):
        self._av_started = True
        try:
            addon = xbmcaddon.Addon()
            raw_a = addon.getSetting('audio_lang')
            raw_a2 = addon.getSetting('audio_lang2')
            raw_s = addon.getSetting('sub_lang')
            raw_s2 = addon.getSetting('sub_lang2')
            raw_sa = addon.getSetting('sub_auto')
            xbmc.log(_LOG + "settings: audio=%s/%s sub=%s/%s auto=%s" % (raw_a, raw_a2, raw_s, raw_s2, raw_sa), xbmc.LOGINFO)
            self._select_audio(addon)
            self._select_subtitles(addon)
        except Exception as e:
            xbmc.log(_LOG + "error: " + str(e), xbmc.LOGERROR)

    def _select_audio(self, addon):
        primary = setting_to_code(addon.getSetting('audio_lang'))
        fallback = setting_to_code(addon.getSetting('audio_lang2'))
        if not primary and not fallback:
            xbmc.log(_LOG + "audio: SKIP (disabled)", xbmc.LOGINFO)
            return
        streams = self._get_audio_streams()
        xbmc.log(_LOG + "audio: streams=%s primary=%s fallback=%s" % (streams, primary, fallback), xbmc.LOGINFO)
        if len(streams) <= 1:
            xbmc.log(_LOG + "audio: SKIP (single stream)", xbmc.LOGINFO)
            return
        for i, s in enumerate(streams):
            xbmc.log(_LOG + "audio: [%d] '%s' → %s" % (i, s, normalize_lang(s)), xbmc.LOGINFO)
        idx = match_stream(streams, primary, fallback)
        if idx is not None:
            xbmc.log(_LOG + "audio: selecting index %d" % idx, xbmc.LOGINFO)
            self.setAudioStream(idx)
        else:
            xbmc.log(_LOG + "audio: no match, keeping default", xbmc.LOGINFO)

    def _select_subtitles(self, addon):
        primary = setting_to_code(addon.getSetting('sub_lang'))
        fallback = setting_to_code(addon.getSetting('sub_lang2'))
        if not primary and not fallback:
            xbmc.log(_LOG + "subs: SKIP (disabled)", xbmc.LOGINFO)
            return
        streams = self._get_subtitle_streams()
        xbmc.log(_LOG + "subs: streams=%s primary=%s fallback=%s" % (streams, primary, fallback), xbmc.LOGINFO)
        if not streams:
            xbmc.log(_LOG + "subs: SKIP (no streams)", xbmc.LOGINFO)
            return
        for i, s in enumerate(streams):
            xbmc.log(_LOG + "subs: [%d] '%s' → %s" % (i, s, normalize_lang(s)), xbmc.LOGINFO)

        idx = None
        meta = None
        try:
            meta = self._get_subtitle_metadata(len(streams))
            if meta is not None and not self._metadata_langs_agree(streams, meta):
                xbmc.log(_LOG + "subs: jsonrpc metadata language mismatch vs bare codes, "
                         "discarding", xbmc.LOGWARNING)
                meta = None
        except Exception as e:
            xbmc.log(_LOG + "subs: jsonrpc metadata lookup failed: %s" % e, xbmc.LOGWARNING)
            meta = None

        if meta is not None:
            idx, reason = match_stream_meta(meta, primary, fallback)
            if idx is not None:
                xbmc.log(_LOG + "subs: metadata source=jsonrpc selecting index %d (%s)"
                         % (idx, reason), xbmc.LOGINFO)
            else:
                xbmc.log(_LOG + "subs: jsonrpc metadata matched nothing (%s), "
                         "falling back to label-only" % reason, xbmc.LOGINFO)
        else:
            xbmc.log(_LOG + "subs: jsonrpc metadata unavailable, falling back to label-only",
                     xbmc.LOGINFO)

        if idx is None:
            idx = match_stream(streams, primary, fallback, deprioritize_forced=True)
            if idx is not None:
                chosen_forced = is_forced_label(streams[idx])
                xbmc.log(_LOG + "subs: selecting index %d (forced=%s, deprioritize_forced=True)"
                         % (idx, chosen_forced), xbmc.LOGINFO)

        if idx is not None:
            self.setSubtitleStream(idx)
            if addon.getSetting('sub_auto') == 'true':
                xbmc.log(_LOG + "subs: showSubtitles(True)", xbmc.LOGINFO)
                self.showSubtitles(True)
        else:
            xbmc.log(_LOG + "subs: no match, keeping default", xbmc.LOGINFO)

    def _jsonrpc(self, method, params):
        """Round-trip a Kodi JSON-RPC call. Returns the 'result' value, or
        None on ANY problem (never raises).

        Guards against the test-mock shape: xbmc.executeJSONRPC on a bare
        MagicMock() auto-returns a MagicMock object rather than a JSON
        string, which would blow up json.loads with a TypeError. Treat any
        non-str result as "JSON-RPC unavailable" rather than an error.
        """
        try:
            payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
            raw = xbmc.executeJSONRPC(json.dumps(payload))
            if not isinstance(raw, str):
                return None
            resp = json.loads(raw)
            return resp.get('result')
        except Exception:
            return None

    def _metadata_langs_agree(self, streams, tracks):
        """Cross-check jsonrpc track languages against the bare codes from
        getAvailableSubtitleStreams(). If both sides resolve a language for
        the same position and they disagree, the two lists are misaligned
        (or jsonrpc returned stale/wrong data) — refuse to use metadata.
        """
        try:
            for i, track in enumerate(tracks):
                if i >= len(streams):
                    break
                if not isinstance(track, dict):
                    continue
                bare_lang = normalize_lang(streams[i])
                meta_lang = normalize_lang(track.get('language'))
                if bare_lang is not None and meta_lang is not None and bare_lang != meta_lang:
                    xbmc.log(_LOG + "subs: index %d language mismatch bare=%s meta=%s"
                             % (i, bare_lang, meta_lang), xbmc.LOGWARNING)
                    return False
            return True
        except Exception:
            return False

    def _get_subtitle_metadata(self, expected_count):
        """Fetch real per-track subtitle metadata via JSON-RPC.

        Returns a list of track dicts (positionally ordered, same index
        space as getAvailableSubtitleStreams), or None if metadata is
        unavailable, malformed, or its ordering can't be trusted — in which
        case the caller must fall back to label-only matching.
        """
        try:
            players = self._jsonrpc("Player.GetActivePlayers", {})
            if not isinstance(players, list) or not players:
                xbmc.log(_LOG + "subs: jsonrpc no active players", xbmc.LOGINFO)
                return None
            pid = None
            for p in players:
                if isinstance(p, dict) and p.get('type') == 'video':
                    pid = p.get('playerid')
                    break
            if pid is None:
                first = players[0]
                pid = first.get('playerid') if isinstance(first, dict) else None
            if pid is None:
                xbmc.log(_LOG + "subs: jsonrpc no usable playerid", xbmc.LOGINFO)
                return None

            payload = {
                "jsonrpc": "2.0", "id": 1, "method": "Player.GetProperties",
                "params": {"playerid": pid, "properties": ["subtitles", "currentsubtitle"]},
            }
            raw = xbmc.executeJSONRPC(json.dumps(payload))
            raw_dump = raw if isinstance(raw, str) else str(raw)
            if len(raw_dump) > 4000:
                raw_dump = raw_dump[:4000] + "...(truncated)"
            xbmc.log(_LOG + "subs: jsonrpc raw=%s" % raw_dump, xbmc.LOGINFO)

            if not isinstance(raw, str):
                xbmc.log(_LOG + "subs: jsonrpc GetProperties returned no usable result",
                         xbmc.LOGWARNING)
                return None
            result = json.loads(raw).get('result')
            if not isinstance(result, dict):
                xbmc.log(_LOG + "subs: jsonrpc GetProperties returned no usable result",
                         xbmc.LOGWARNING)
                return None
            subs = result.get('subtitles')
            if not isinstance(subs, list):
                xbmc.log(_LOG + "subs: jsonrpc 'subtitles' missing or not a list", xbmc.LOGWARNING)
                return None
            if len(subs) != expected_count:
                xbmc.log(_LOG + "subs: jsonrpc count mismatch (got %d, expected %d)"
                         % (len(subs), expected_count), xbmc.LOGWARNING)
                return None
            for i, entry in enumerate(subs):
                if not isinstance(entry, dict):
                    xbmc.log(_LOG + "subs: jsonrpc entry %d not a dict" % i, xbmc.LOGWARNING)
                    return None
                if 'index' in entry and entry.get('index') != i:
                    xbmc.log(_LOG + "subs: jsonrpc index field %s disagrees with position %d"
                             % (entry.get('index'), i), xbmc.LOGWARNING)
                    return None
            return subs
        except Exception as e:
            xbmc.log(_LOG + "subs: jsonrpc metadata error: %s" % e, xbmc.LOGWARNING)
            return None

    def _get_audio_streams(self):
        """Return list of audio stream language labels."""
        try:
            count = self.getAvailableAudioStreams()
            return count if isinstance(count, list) else []
        except Exception:
            return []

    def _get_subtitle_streams(self):
        """Return list of subtitle stream language labels."""
        try:
            count = self.getAvailableSubtitleStreams()
            return count if isinstance(count, list) else []
        except Exception:
            return []
