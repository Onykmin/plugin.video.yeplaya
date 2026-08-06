#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for language module — pure logic, no Kodi dependency."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from lib.language import normalize_lang, match_stream, setting_to_code, is_forced_label


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

def test_match_fallback_only_when_primary_disabled():
    """Primary disabled (None) but fallback set → fallback still matches."""
    streams = ['English', 'German', 'French']
    assert match_stream(streams, None, 'de') == 1

def test_match_fallback_only_no_match():
    streams = ['English', 'German']
    assert match_stream(streams, None, 'ja') is None

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


# --- is_forced_label ---

def test_is_forced_label_variants():
    """Every documented forced-marker label form must be detected."""
    assert is_forced_label('Czech (Forced)') is True
    assert is_forced_label('cs (forced)') is True
    assert is_forced_label('Czech Forced') is True
    assert is_forced_label('forced-cze') is True

def test_is_forced_label_native_wording():
    """Czech/Slovak native forced wording (accent-insensitive)."""
    assert is_forced_label(u'nucené') is True
    assert is_forced_label(u'vynútené') is True
    assert is_forced_label(u'Czech (nucené)') is True
    assert is_forced_label(u'Slovak (vynútené)') is True

def test_is_forced_label_negative_false_positives():
    """Words that merely contain the substring must NOT be detected."""
    assert is_forced_label('Reinforced') is False
    assert is_forced_label('Enforced') is False

def test_is_forced_label_plain_language_false():
    assert is_forced_label('Czech') is False
    assert is_forced_label('English') is False

def test_is_forced_label_none_safe():
    """Must be None-safe, matching match_stream's tolerance of None/empty entries."""
    assert is_forced_label(None) is False
    assert is_forced_label('') is False


# --- match_stream: forced-marker detection does not break language detection (Fact A) ---

def test_forced_labels_still_resolve_language():
    """Forced marker must not swallow the language token normalize_lang needs."""
    assert normalize_lang('forced-cze') == 'cs'
    assert normalize_lang('Czech (Forced)') == 'cs'
    assert normalize_lang('cs (forced)') == 'cs'
    assert normalize_lang('Czech Forced') == 'cs'


# --- match_stream: deprioritize_forced=True (subtitle path) ---

def test_match_forced_deprioritized_behind_normal_same_lang():
    """Acceptance row 1: non-forced track of same language wins over forced."""
    streams = ['Czech (Forced)', 'Czech']
    assert match_stream(streams, 'cs', deprioritize_forced=True) == 1

def test_match_forced_used_when_only_track():
    """Acceptance row 2: forced is all there is → still selected."""
    streams = ['Czech (Forced)']
    assert match_stream(streams, 'cs', deprioritize_forced=True) == 0

def test_match_forced_primary_beats_nonforced_fallback():
    """Acceptance row 3: primary-language forced beats fallback-language non-forced."""
    streams = ['Czech (Forced)', 'English']
    assert match_stream(streams, 'cs', 'en', deprioritize_forced=True) == 0

def test_match_nonforced_primary_beats_forced_primary_when_fallback_present_first():
    """Acceptance row 4: non-forced primary wins even though an earlier fallback
    and an earlier forced-primary both precede it positionally."""
    streams = ['English', 'Czech (Forced)', 'Czech']
    assert match_stream(streams, 'cs', 'en', deprioritize_forced=True) == 2

def test_match_forced_deprioritized_all_label_variants():
    """Every forced-label variant must be deprioritized behind a plain same-language track."""
    variants = ['Czech (Forced)', 'cs (forced)', 'Czech Forced', 'forced-cze']
    for forced_label in variants:
        streams = [forced_label, 'Czech']
        assert match_stream(streams, 'cs', deprioritize_forced=True) == 1, (
            "variant %r was not deprioritized" % forced_label
        )

def test_match_forced_deprioritized_native_wording():
    """Native Czech/Slovak forced wording combined with a language token (Fact B)."""
    streams = [u'Czech (nucené)', 'Czech']
    assert match_stream(streams, 'cs', deprioritize_forced=True) == 1
    streams_sk = [u'Slovak (vynútené)', 'Slovak']
    assert match_stream(streams_sk, 'sk', deprioritize_forced=True) == 1

def test_match_forced_negative_not_deprioritized():
    """A label that merely contains 'forced' as a substring (Reinforced) must not
    be treated as a forced track — ranking is unaffected, first match wins."""
    streams = ['Reinforced', 'Czech']
    # 'Reinforced' carries no recognizable language token, so it is skipped by
    # normalize_lang regardless; the real assertion is the predicate itself
    # (see test_is_forced_label_negative_false_positives). Here we additionally
    # confirm a Reinforced-labelled *Czech* entry is NOT pushed behind a second
    # Czech entry, proving no false-positive forced ranking occurs.
    streams2 = ['Czech (Reinforced)', 'Czech']
    assert match_stream(streams2, 'cs', deprioritize_forced=True) == 0

def test_match_forced_single_track_language_no_change():
    """No behaviour change when only one track of a language is present (brief L85)."""
    streams = ['English', 'Czech (Forced)']
    assert match_stream(streams, 'cs', deprioritize_forced=True) == 1
    assert match_stream(streams, 'cs') == 1


# --- match_stream: audio non-regression (deprioritize_forced omitted, D1) ---

def test_match_audio_no_kwarg_ordering_unchanged():
    """Without the opt-in kwarg, first-match-wins ordering is exactly as before —
    the audio path (_select_audio) never passes deprioritize_forced."""
    streams = ['Czech (Forced)', 'Czech']
    assert match_stream(streams, 'cs') == 0

def test_match_audio_no_kwarg_forced_label_in_audio_context():
    """A 'forced' token in an audio-like label must not change existing
    first-match-wins semantics when the kwarg is not passed."""
    streams = ['English', 'Czech (Forced)', 'Czech']
    assert match_stream(streams, 'cs', 'en') == 1
