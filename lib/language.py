# -*- coding: utf-8 -*-
# Module: language
# Author: onykmin
# License: AGPL v.3 https://www.gnu.org/licenses/agpl-3.0.html

"""Language code mapping and stream matching for audio/subtitle selection."""

import re

try:
    from unidecode import unidecode
except ImportError:
    import unicodedata
    def unidecode(text):
        normalized = unicodedata.normalize('NFKD', text)
        return ''.join([c for c in normalized if not unicodedata.combining(c)])

# All known variants → 2-letter ISO 639-1 code
LANG_MAP = {
    # English
    'en': 'en', 'eng': 'en', 'english': 'en',
    # Czech
    'cs': 'cs', 'cz': 'cs', 'ces': 'cs', 'cze': 'cs', 'czech': 'cs', u'čeština': 'cs', u'česky': 'cs',
    # Slovak
    'sk': 'sk', 'slk': 'sk', 'slo': 'sk', 'slovak': 'sk', u'slovenčina': 'sk', u'slovensky': 'sk',
    # German
    'de': 'de', 'deu': 'de', 'ger': 'de', 'german': 'de', 'deutsch': 'de',
    # French
    'fr': 'fr', 'fra': 'fr', 'fre': 'fr', 'french': 'fr', u'français': 'fr',
    # Spanish
    'es': 'es', 'spa': 'es', 'spanish': 'es', u'español': 'es',
    # Italian
    'it': 'it', 'ita': 'it', 'italian': 'it', 'italiano': 'it',
    # Portuguese
    'pt': 'pt', 'por': 'pt', 'portuguese': 'pt', u'português': 'pt',
    # Russian
    'ru': 'ru', 'rus': 'ru', 'russian': 'ru', u'русский': 'ru',
    # Ukrainian
    'uk': 'uk', 'ukr': 'uk', 'ukrainian': 'uk', u'українська': 'uk',
    # Polish
    'pl': 'pl', 'pol': 'pl', 'polish': 'pl', 'polski': 'pl',
    # Hungarian
    'hu': 'hu', 'hun': 'hu', 'hungarian': 'hu', 'magyar': 'hu',
    # Japanese
    'ja': 'ja', 'jp': 'ja', 'jpn': 'ja', 'japanese': 'ja', u'日本語': 'ja',
    # Korean
    'ko': 'ko', 'kor': 'ko', 'korean': 'ko', u'한국어': 'ko',
    # Chinese
    'zh': 'zh', 'zho': 'zh', 'chi': 'zh', 'chinese': 'zh', u'中文': 'zh',
    # Arabic
    'ar': 'ar', 'ara': 'ar', 'arabic': 'ar', u'العربية': 'ar',
    # Turkish
    'tr': 'tr', 'tur': 'tr', 'turkish': 'tr', u'türkçe': 'tr',
    # Dutch
    'nl': 'nl', 'nld': 'nl', 'dut': 'nl', 'dutch': 'nl', 'nederlands': 'nl',
    # Swedish
    'sv': 'sv', 'swe': 'sv', 'swedish': 'sv', 'svenska': 'sv',
    # Norwegian
    'no': 'no', 'nor': 'no', 'nb': 'no', 'nob': 'no', 'nn': 'no', 'nno': 'no',
    'norwegian': 'no', 'norsk': 'no',
    # Danish
    'da': 'da', 'dan': 'da', 'danish': 'da', 'dansk': 'da',
    # Finnish
    'fi': 'fi', 'fin': 'fi', 'finnish': 'fi', 'suomi': 'fi',
    # Greek
    'el': 'el', 'ell': 'el', 'gre': 'el', 'greek': 'el', u'ελληνικά': 'el',
    # Romanian
    'ro': 'ro', 'ron': 'ro', 'rum': 'ro', 'romanian': 'ro', u'română': 'ro',
    # Bulgarian
    'bg': 'bg', 'bul': 'bg', 'bulgarian': 'bg', u'български': 'bg',
    # Croatian
    'hr': 'hr', 'hrv': 'hr', 'croatian': 'hr', 'hrvatski': 'hr',
    # Serbian
    'sr': 'sr', 'srp': 'sr', 'serbian': 'sr', u'српски': 'sr',
    # Hindi
    'hi': 'hi', 'hin': 'hi', 'hindi': 'hi', u'हिन्दी': 'hi',
    # Thai
    'th': 'th', 'tha': 'th', 'thai': 'th', u'ไทย': 'th',
    # Vietnamese
    'vi': 'vi', 'vie': 'vi', 'vietnamese': 'vi', u'tiếng việt': 'vi',
    # Indonesian
    'id': 'id', 'ind': 'id', 'indonesian': 'id',
    # Malay
    'ms': 'ms', 'msa': 'ms', 'may': 'ms', 'malay': 'ms',
    # Hebrew
    'he': 'he', 'heb': 'he', 'hebrew': 'he', u'עברית': 'he',
    # Persian
    'fa': 'fa', 'fas': 'fa', 'per': 'fa', 'persian': 'fa', u'فارسی': 'fa',
    # Latin (undetermined/misc)
    'la': 'la', 'lat': 'la', 'latin': 'la',
    # Undetermined
    'und': 'und', 'undetermined': 'und',
}

# Regex to extract language token from stream labels like "English (AC3 5.1)" or "Track 1 - Japanese"
_LABEL_RE = re.compile(
    r'[a-zA-Z\u00C0-\u024F\u1E00-\u1EFF'   # Latin + extended (Vietnamese etc.)
    r'\u0400-\u04FF'                          # Cyrillic
    r'\u0590-\u05FF'                          # Hebrew
    r'\u0600-\u06FF'                          # Arabic
    r'\u0900-\u097F'                          # Devanagari (Hindi)
    r'\u0E00-\u0E7F'                          # Thai
    r'\u3000-\u9FFF'                          # CJK
    r'\uAC00-\uD7AF]+'                        # Korean
)

# Detects a "forced" subtitle marker in a stream label (e.g. "Czech (Forced)",
# "forced-cze", native Czech/Slovak "nucen\u00E9"/"vyn\u00FAten\u00E9" after unidecode).
# Word-boundary alternation avoids false positives on words that merely
# contain the substring ("Reinforced", "Enforced"). Applied on top of
# normalize_lang, never in place of it \u2014 see match_stream's
# deprioritize_forced kwarg. SDH/hearing-impaired tracks are intentionally
# NOT covered here (out of scope; they are complete subtitles, not broken).
_FORCED_RE = re.compile(r'\b(?:forced|nucene|vynutene)\b')


def is_forced_label(stream_label):
    """Return True if a stream label carries a "forced" subtitle marker.

    Accent-insensitive (handles native Czech/Slovak wording) and None/empty
    safe. Detection only \u2014 never mutates or strips the label, so language
    detection via normalize_lang keeps working on the same string.
    """
    if not stream_label:
        return False
    normalized = unidecode(stream_label).lower()
    return bool(_FORCED_RE.search(normalized))


def normalize_lang(stream_label):
    """Normalize a stream label to ISO 639-1 code or None.

    Handles raw codes ('en', 'eng'), full names ('English'),
    native names ('日本語'), and labels like 'English (AC3 5.1)'.
    """
    if not stream_label:
        return None
    label = stream_label.strip().lower()
    # Direct lookup first
    if label in LANG_MAP:
        return LANG_MAP[label]
    # Try extracting first word/token from label
    for token in _LABEL_RE.findall(label):
        token_lower = token.lower()
        if token_lower in LANG_MAP:
            return LANG_MAP[token_lower]
    return None


def match_stream(available_streams, primary_code, fallback_code=None, deprioritize_forced=False):
    """Find best matching stream index for given language preference.

    Args:
        available_streams: list of stream label strings
        primary_code: ISO 639-1 code to prefer (or None)
        fallback_code: ISO 639-1 code as fallback (or None)
        deprioritize_forced: when True, within each language code prefer a
            non-forced track over a forced one, only falling back to a forced
            track when it is the only track in that language. Opt-in and
            defaulted to False so the audio path (_select_audio) is
            byte-for-byte unchanged; only _select_subtitles passes True.

    Returns:
        0-based index or None if no match
    """
    # Proceed if EITHER preference is set: a user may disable the primary
    # language yet still want the fallback matched (primary=None, fallback='en').
    if not available_streams or (not primary_code and not fallback_code):
        return None
    for code in [primary_code, fallback_code]:
        if not code:
            continue
        if not deprioritize_forced:
            for i, label in enumerate(available_streams):
                if normalize_lang(label) == code:
                    return i
            continue
        # Forced-ness inner: scan for a non-forced match of this language
        # first; only if none exists, fall back to a forced match of the
        # SAME language. Language precedence (outer loop) still outranks
        # forced-ness — a non-forced fallback-language track is never
        # reached before both passes of the primary language are exhausted.
        forced_idx = None
        for i, label in enumerate(available_streams):
            if normalize_lang(label) != code:
                continue
            if is_forced_label(label):
                if forced_idx is None:
                    forced_idx = i
                continue
            return i
        if forced_idx is not None:
            return forced_idx
    return None


def setting_to_code(setting_value):
    """Convert settings dropdown value to ISO 639-1 code.

    "Disabled" or empty → None, otherwise lookup in LANG_MAP.
    """
    if not setting_value or setting_value.lower() == 'disabled':
        return None
    return LANG_MAP.get(setting_value.lower())
