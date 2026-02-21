#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for language module — pure logic, no Kodi dependency."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from lib.language import normalize_lang, match_stream, setting_to_code


# --- normalize_lang ---

def test_normalize_iso1():
    assert normalize_lang('en') == 'en'
    assert normalize_lang('ja') == 'ja'
    assert normalize_lang('cs') == 'cs'

def test_normalize_iso2():
    assert normalize_lang('eng') == 'en'
    assert normalize_lang('jpn') == 'ja'
    assert normalize_lang('cze') == 'cs'

def test_normalize_full_name():
    assert normalize_lang('English') == 'en'
    assert normalize_lang('Japanese') == 'ja'
    assert normalize_lang('Czech') == 'cs'

def test_normalize_native_name():
    assert normalize_lang(u'日本語') == 'ja'
    assert normalize_lang(u'čeština') == 'cs'
    assert normalize_lang(u'русский') == 'ru'

def test_normalize_unknown():
    assert normalize_lang('Klingon') is None
    assert normalize_lang('xyz') is None

def test_normalize_case_insensitive():
    assert normalize_lang('ENGLISH') == 'en'
    assert normalize_lang('Japanese') == 'ja'
    assert normalize_lang('CZE') == 'cs'

def test_normalize_label_with_extras():
    assert normalize_lang('English (AC3 5.1)') == 'en'
    assert normalize_lang('Japanese (FLAC 2.0)') == 'ja'

def test_normalize_empty():
    assert normalize_lang('') is None
    assert normalize_lang(None) is None

def test_normalize_locale_tags():
    """Locale tags like en-US split on hyphen, first token matches."""
    assert normalize_lang('en-US') == 'en'
    assert normalize_lang('pt-BR') == 'pt'
    assert normalize_lang('cs-CZ') == 'cs'

def test_normalize_special_codes():
    assert normalize_lang('und') == 'und'
    assert normalize_lang('mul') is None
    assert normalize_lang('zxx') is None

def test_normalize_track_labels():
    """Labels like 'Track 1' have no recognized language."""
    assert normalize_lang('Track 1') is None
    assert normalize_lang('1') is None
    assert normalize_lang('Audio 2') is None

def test_normalize_whitespace():
    assert normalize_lang('   ') is None
    assert normalize_lang('  English  ') == 'en'

def test_normalize_non_standard_codes():
    """Common non-standard codes found in media metadata."""
    assert normalize_lang('cz') == 'cs'
    assert normalize_lang('jp') == 'ja'
    assert normalize_lang('nb') == 'no'
    assert normalize_lang('nob') == 'no'
    assert normalize_lang('nn') == 'no'
    assert normalize_lang('nno') == 'no'

def test_normalize_composite_arabic():
    assert normalize_lang(u'العربية (AC3 5.1)') == 'ar'

def test_normalize_composite_thai():
    assert normalize_lang(u'ไทย (AAC 2.0)') == 'th'

def test_normalize_composite_hindi():
    assert normalize_lang(u'हिन्दी (AC3 5.1)') == 'hi'

def test_normalize_composite_hebrew():
    assert normalize_lang(u'עברית (DTS)') == 'he'


# --- match_stream ---

def test_match_primary_found():
    streams = ['English', 'Japanese', 'Czech']
    assert match_stream(streams, 'ja') == 1

def test_match_fallback_used():
    streams = ['English', 'German', 'French']
    assert match_stream(streams, 'ja', 'de') == 1

def test_match_no_match():
    streams = ['English', 'German']
    assert match_stream(streams, 'ja', 'ko') is None

def test_match_empty_list():
    assert match_stream([], 'en') is None

def test_match_none_primary():
    assert match_stream(['English'], None) is None

def test_match_none_in_streams():
    """None entries in stream list should be skipped safely."""
    assert match_stream([None, 'English', ''], 'en') == 1

def test_match_primary_equals_fallback():
    streams = ['Japanese', 'English']
    assert match_stream(streams, 'en', 'en') == 1

def test_match_no_match_both_set():
    """Neither primary nor fallback found."""
    streams = ['English', 'German']
    assert match_stream(streams, 'ja', 'ko') is None


# --- setting_to_code ---

def test_setting_valid():
    assert setting_to_code('english') == 'en'
    assert setting_to_code('Japanese') == 'ja'

def test_setting_disabled():
    assert setting_to_code('Disabled') is None
    assert setting_to_code('disabled') is None

def test_setting_empty():
    assert setting_to_code('') is None
    assert setting_to_code(None) is None

def test_setting_unknown():
    assert setting_to_code('Esperanto') is None
    assert setting_to_code('Unknown') is None

def test_setting_all_dropdown_values():
    """Every value from settings.xml dropdown must resolve to a valid code."""
    dropdown = [
        'English', 'Czech', 'Slovak', 'German', 'French',
        'Spanish', 'Italian', 'Portuguese', 'Russian', 'Ukrainian',
        'Polish', 'Hungarian', 'Japanese', 'Korean', 'Chinese',
        'Arabic', 'Turkish', 'Dutch', 'Swedish', 'Norwegian',
        'Danish', 'Finnish', 'Greek', 'Romanian', 'Bulgarian',
        'Croatian', 'Serbian', 'Hindi', 'Thai',
    ]
    for name in dropdown:
        code = setting_to_code(name)
        assert code is not None, f"setting_to_code('{name}') returned None"
        assert len(code) == 2, f"setting_to_code('{name}') returned '{code}', expected 2-letter code"
