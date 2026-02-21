# -*- coding: utf-8 -*-
# Module: language
# Author: onykmin
# License: AGPL v.3 https://www.gnu.org/licenses/agpl-3.0.html

"""Language code mapping and stream matching for audio/subtitle selection."""

import re

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


def match_stream(available_streams, primary_code, fallback_code=None):
    """Find best matching stream index for given language preference.

    Args:
        available_streams: list of stream label strings
        primary_code: ISO 639-1 code to prefer (or None)
        fallback_code: ISO 639-1 code as fallback (or None)

    Returns:
        0-based index or None if no match
    """
    if not available_streams or not primary_code:
        return None
    for code in [primary_code, fallback_code]:
        if not code:
            continue
        for i, label in enumerate(available_streams):
            if normalize_lang(label) == code:
                return i
    return None


def setting_to_code(setting_value):
    """Convert settings dropdown value to ISO 639-1 code.

    "Disabled" or empty → None, otherwise lookup in LANG_MAP.
    """
    if not setting_value or setting_value.lower() == 'disabled':
        return None
    return LANG_MAP.get(setting_value.lower())
