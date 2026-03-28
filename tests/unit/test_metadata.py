# -*- coding: utf-8 -*-
"""Tests for metadata extraction (pure functions, no Kodi mocks needed)."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from lib.metadata import extract_video_info, extract_audio_info, extract_subtitle_info


class TestExtractVideoInfo:
    def test_single_stream(self):
        info = {'video': {'stream': {'width': '1920', 'height': '1080', 'format': 'H.265'}}}
        result = extract_video_info(info)
        assert result['resolution'] == '1920x1080'
        assert result['video_codec'] == 'H.265'

    def test_multi_stream_uses_first(self):
        info = {'video': {'stream': [
            {'width': '1920', 'height': '1080', 'format': 'H.264'},
            {'width': '720', 'height': '480', 'format': 'MPEG2'}
        ]}}
        result = extract_video_info(info)
        assert result['resolution'] == '1920x1080'
        assert result['video_codec'] == 'H.264'

    def test_missing_dimensions(self):
        info = {'video': {'stream': {'format': 'VP9'}}}
        result = extract_video_info(info)
        assert 'resolution' not in result
        assert result['video_codec'] == 'VP9'

    def test_no_video_key(self):
        assert extract_video_info({}) == {}
        assert extract_video_info({'audio': {}}) == {}

    def test_no_stream_key(self):
        assert extract_video_info({'video': {}}) == {}

    def test_empty_stream_list(self):
        assert extract_video_info({'video': {'stream': []}}) == {}


class TestExtractAudioInfo:
    def test_single_stream(self):
        info = {'audio': {'stream': {'language': 'en', 'format': 'AAC', 'channels': '2'}}}
        result = extract_audio_info(info)
        assert 'EN AAC 2ch' in result['audio']

    def test_multi_stream(self):
        info = {'audio': {'stream': [
            {'language': 'en', 'format': 'AAC', 'channels': '6'},
            {'language': 'cz', 'format': 'AC3', 'channels': '2'}
        ]}}
        result = extract_audio_info(info)
        assert 'EN AAC 6ch' in result['audio']
        assert 'CZ AC3 2ch' in result['audio']

    def test_missing_language(self):
        info = {'audio': {'stream': {'format': 'DTS', 'channels': '6'}}}
        result = extract_audio_info(info)
        assert 'DTS 6ch' in result['audio']

    def test_no_audio_key(self):
        assert extract_audio_info({}) == {}

    def test_empty_stream(self):
        info = {'audio': {'stream': {}}}
        result = extract_audio_info(info)
        assert result == {}


class TestExtractSubtitleInfo:
    def test_single_subtitle(self):
        info = {'subtitle': {'stream': {'language': 'cz'}}}
        result = extract_subtitle_info(info)
        assert result['subtitles'] == 'CZ'

    def test_multi_subtitles(self):
        info = {'subtitle': {'stream': [
            {'language': 'en'},
            {'language': 'cz'},
            {'language': 'sk'}
        ]}}
        result = extract_subtitle_info(info)
        assert 'EN' in result['subtitles']
        assert 'CZ' in result['subtitles']
        assert 'SK' in result['subtitles']

    def test_no_language(self):
        info = {'subtitle': {'stream': [{'format': 'srt'}]}}
        result = extract_subtitle_info(info)
        assert result == {}

    def test_no_subtitle_key(self):
        assert extract_subtitle_info({}) == {}
