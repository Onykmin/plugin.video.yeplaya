# -*- coding: utf-8 -*-
# Module: parsing
# Author: onykmin
# License: AGPL v.3 https://www.gnu.org/licenses/agpl-3.0.html

import datetime
import re

_CURRENT_YEAR = datetime.datetime.now().year

# Max filename length fed to the lazy `(.+?)[sep]+` parsing regexes. Beyond
# this they backtrack quadratically; real Webshare filenames are < 260 chars.
_MAX_PARSE_LEN = 300

try:
    from unidecode import unidecode
except ImportError:
    import unicodedata
    def unidecode(text):
        """Normalize Unicode to ASCII - handles Czech characters."""
        normalized = unicodedata.normalize('NFKD', text)
        return ''.join([c for c in normalized if not unicodedata.combining(c)])

# Compiled regex patterns for performance
_PATTERN_S00E00 = re.compile(r'^(.+?)[\s_\.\-]+[\(\[]?[Ss](\d{1,2})[Ee](\d{1,3})[\)\]]?')
_PATTERN_S00E00_REVERSED = re.compile(r'^[Ss](\d{1,2})[Ee](\d{1,3})[\s_\.\-]+(.+?)$')  # Episode marker first
_PATTERN_0x00 = re.compile(r'^(.+?)[\s_\.\-]+[\(\[]?(\d{1,2})x(\d{1,3})[\)\]]?')
_PATTERN_MULTI_EP = re.compile(r'^(.+?)[\s_\.\-]+[\(\[]?[Ss](\d{1,2})[Ee](\d{1,3})(?:[\-\.]?[Ee]?(\d{1,3}))?[\)\]]?')
_PATTERN_ABSOLUTE_EP = re.compile(r'^(.+?)[\s\.\-]+(?:ep?\.?\s*)?(\d{1,3})(?!\d)', re.IGNORECASE)
_PATTERN_SEASON_TEXT = re.compile(r'(?:Season\s*(\d{1,2})|(\d{1,2})(?:st|nd|rd|th)\s*Season|(?:^|\s)S(?:eason)?\s+(\d{1,2})(?!\s*[Ee]))', re.IGNORECASE)
_PATTERN_QUALITY = re.compile(r'\b(1080p|720p|2160p|4K|BluRay|WEB-DL|HDTV|WEBRip|BRRip)\b', re.IGNORECASE)
_PATTERN_CODEC = re.compile(r'\b(x264|x265|H\.?264|H\.?265|HEVC|XviD)\b', re.IGNORECASE)
_PATTERN_AUDIO = re.compile(r'\b(DD5\.1|DTS|AC3|AAC)\b', re.IGNORECASE)
_PATTERN_YEAR = re.compile(r'\[?\d{4}\]?')
_PATTERN_LANG = re.compile(r'\b(CZ|EN|SK|DE|FR|ES|IT|PL|RU|JP|KR)\b|[\(\[](?:CZ|EN|SK|DE|FR|ES|IT|PL|RU|JP|KR)[\)\]]', re.IGNORECASE)
_PATTERN_SEPARATORS = re.compile(r'[\-_\.\,\:\;]+')
_PATTERN_EPISODE_MARKER = re.compile(r'\b[Ss]\d{1,2}[Ee]\d{1,3}\b')
_PATTERN_MOVIE_YEAR = re.compile(r'^(.+?)[\s_\.\-]*[\(\[]?((?:19|20)\d{2})(?!x\d{3,4})[\)\]]?')
_RE_RELEASE_GROUP = re.compile(r'[-\s]+(sparks|fgt|yify|yts|rarbg|etrg|ettv|fum|shitbox|ion10|fleet|cmrg|evo|geckos|playnow|demand|ntb|drones|strife|megusta|nogrp|mkvcage|galaxytv|stuttershit|lama|tbs|nhanc3|afg|qoq|wrd|joy|cinefile|fle|dr|lena)\s*$', re.IGNORECASE)


# ============================================================================
# Quality Parsing
# ============================================================================

def parse_quality_metadata(filename):
    """Extract quality metadata from filename for ranking duplicates.

    Returns dict with:
    {
        'quality': str,      # '2160p', '1080p', '720p', '480p', or None
        'source': str,       # 'BluRay', 'WEB-DL', 'HDTV', etc., or None
        'codec': str,        # 'x265', 'x264', 'HEVC', etc., or None
        'audio': str,        # 'DTS', 'DD5.1', 'AC3', 'AAC', or None
        'quality_score': int # 0-125 ranking (higher = better quality)
    }
    """
    result = {
        'quality': None,
        'source': None,
        'codec': None,
        'audio': None,
        'quality_score': 50
    }

    # Extract quality/resolution
    quality_match = re.search(r'\b(2160p|4K|1080p|720p|480p)\b', filename, re.IGNORECASE)
    if quality_match:
        quality = quality_match.group(1).lower()
        result['quality'] = quality

        if quality in ('2160p', '4k'):
            result['quality_score'] = 100
        elif quality == '1080p':
            result['quality_score'] = 80
        elif quality == '720p':
            result['quality_score'] = 60
        elif quality == '480p':
            result['quality_score'] = 40

    # Extract source type
    source_match = re.search(r'\b(BluRay|Blu-Ray|WEB-DL|WEBDL|HDTV|WEBRip|BRRip|DVDRip)\b', filename, re.IGNORECASE)
    if source_match:
        source = source_match.group(1).upper()
        if source in ('BLU-RAY', 'BLURAY'):
            source = 'BluRay'
        elif source in ('WEB-DL', 'WEBDL'):
            source = 'WEB-DL'
        elif source == 'WEBRIP':
            source = 'WEBRip'
        elif source == 'BRRIP':
            source = 'BRRip'
        elif source == 'DVDRIP':
            source = 'DVDRip'

        result['source'] = source

        if source == 'BluRay':
            result['quality_score'] += 15
        elif source == 'WEB-DL':
            result['quality_score'] += 10
        elif source == 'HDTV':
            result['quality_score'] += 5
        elif source == 'WEBRip':
            result['quality_score'] += 3

    # Extract codec
    codec_match = re.search(r'\b(x265|x264|H\.?265|H\.?264|HEVC|XviD)\b', filename, re.IGNORECASE)
    if codec_match:
        codec = codec_match.group(1).upper()
        if codec in ('X265', 'H.265', 'H265', 'HEVC'):
            codec = 'x265'
            result['quality_score'] += 5
        elif codec in ('X264', 'H.264', 'H264'):
            codec = 'x264'
        elif codec == 'XVID':
            codec = 'XviD'

        result['codec'] = codec

    # Extract audio
    audio_match = re.search(r'\b(DTS-HD|DTS|DD5\.1|DD5|AC3|AAC)\b', filename, re.IGNORECASE)
    if audio_match:
        audio = audio_match.group(1).upper()
        if audio in ('DD5.1', 'DD5'):
            audio = 'DD5.1'

        result['audio'] = audio

        if 'DTS' in audio:
            result['quality_score'] += 5
        elif audio == 'DD5.1':
            result['quality_score'] += 3
        elif audio == 'AC3':
            result['quality_score'] += 2
        elif audio == 'AAC':
            result['quality_score'] += 1

    return result


# ============================================================================
# Dual Name Detection
# ============================================================================

_RE_EP_TITLE_ARTICLE = re.compile(r'^(a|an|the)\s', re.IGNORECASE)


def _norm_title_eq(name1, name2):
    """True if two names are the same title written differently.

    Folds to ASCII lowercase AND strips punctuation + leading article so
    "Spider-Man"=="SpiderMan", "Batman"=="The Batman" register as equal and
    don't get treated as a bogus dual-name pair (audit finding #32).
    """
    from unicodedata import normalize

    def norm(s):
        s = normalize('NFKD', s.lower()).encode('ASCII', 'ignore').decode()
        s = re.sub(r'[^a-z0-9]+', '', _RE_EP_TITLE_ARTICLE.sub('', s))
        return s

    return norm(name1) == norm(name2)


def _looks_like_episode_title(name2):
    """Heuristic: is name2 a descriptive episode title rather than a CzSk alias?

    Dual-name aliases are short title-like phrases (1-2 words, e.g. "Tucnak",
    "The Penguin"); episode titles after " - " are wordy ("A Study in Pink",
    "The Blind Banker", "The Great Game"). Use word count (>=3) as the signal —
    NOT the leading article alone, since legit aliases like "The Penguin" are
    article-led too.
    """
    return len(name2.split()) >= 3


def _strip_episode_title_suffix(raw_name):
    """Drop a descriptive ' - <episode title>' suffix from a series name.

    "Sherlock - A Study in Pink" -> "Sherlock". Only fires when the suffix is a
    wordy episode title (>=3 words) AND the pair is NOT a dual-name alias, so
    legit dual names ("The Penguin - Tucnak") and short suffixes are untouched.
    Prevents one series fragmenting into one canonical key per episode (#16).
    """
    if ' - ' not in raw_name:
        return raw_name
    head, _, tail = raw_name.partition(' - ')
    if (head.strip() and _looks_like_episode_title(tail.strip())
            and not extract_dual_names(raw_name)):
        return head.strip()
    return raw_name


def _dual_name2_is_false_positive(name2):
    """True if the second half of a candidate dual-name pair is actually
    metadata (episode number/marker, quality/codec, year) or an episode title
    rather than a real alias."""
    if re.match(r'^\d{1,3}(\.\d)?(\s+[A-Z]{2})?(\s+\d+\.\s*serie)?$', name2, re.IGNORECASE):
        return True
    if re.match(r'^[Ss]\d{1,2}[Ee]\d{1,3}', name2):
        return True
    if re.match(r'^(?:19|20)\d{2}$', name2):
        return True
    quality_keywords = ['720p', '1080p', '2160p', '4k', 'x264', 'x265', 'hevc',
                        'h264', 'h265', 'bluray', 'webrip', 'webdl', 'hdtv',
                        'aac', 'dts', 'ac3']
    if any(kw in name2.lower() for kw in quality_keywords):
        return True
    return _looks_like_episode_title(name2)


def extract_dual_names(raw_name):
    """Detect and extract dual names from filename.

    Patterns detected:
    - "Original - Czech" (dash with spaces)
    - "Original-Czech" (dash without spaces)
    - "Original / Czech" (slash separator)
    - "Czech (Original)" (parentheses)
    - "Original (Czech)" (parentheses reverse)
    - "Czech [Original]" (brackets)
    - "Original [Czech]" (brackets reverse)
    - "Original  Czech" (multi-space separator 2+)

    Returns: (name1, name2) tuple or None if not dual-name format
    """
    # Try brackets format: "Name1 [Name2]"
    bracket_match = re.match(r'^(.+?)\s*\[([^\]]+)\]', raw_name)
    if bracket_match:
        name1 = bracket_match.group(1).strip()
        name2 = bracket_match.group(2).strip()

        quality_keywords = ['720p', '1080p', '2160p', '480p', '360p', 'hd', 'fps', 'x264', 'x265', 'hevc', 'aac', 'dts', 'bluray', 'webrip']
        is_quality = any(kw in name2.lower() for kw in quality_keywords)
        is_hex_hash = bool(re.match(r'^[0-9A-Fa-f]{6,8}$', name2))  # Release group hashes
        is_year = bool(re.match(r'^(?:19|20)\d{2}$', name2))  # Years like 2009, 2024

        # Apply the same shared false-positive guard as the dash/slash/multi-space
        # branches: an episode marker ("Show [S01E05]") or a wordy episode title
        # ("Sherlock [A Study in Pink]") in the brackets is not a dual-name alias.
        if (name1 and name2 and len(name1) > 1 and len(name2) > 1
                and not is_quality and not is_hex_hash and not is_year
                and not _dual_name2_is_false_positive(name2)):
            return (name1, name2)

    # Try parentheses format: "Name1 (Name2)"
    paren_match = re.match(r'^(.+?)\s*\(([^)]+)\)', raw_name)
    if paren_match:
        name1 = paren_match.group(1).strip()
        name2 = paren_match.group(2).strip()

        is_year = re.match(r'^\d{4}$', name2)
        quality_keywords = ['720p', '1080p', '2160p', '480p', '360p', 'hd', 'fps', 'x264', 'x265', 'hevc', 'aac', 'dts', 'bluray', 'webrip']
        is_quality = any(kw in name2.lower() for kw in quality_keywords)
        is_lang_only = re.match(r'^[A-Z]{2,3}$', name2)

        if name1 and name2 and len(name1) > 1 and len(name2) > 1 and not is_year and not is_quality and not is_lang_only:
            return (name1, name2)

    # Try dash separator with spaces: " - "
    if ' - ' in raw_name:
        parts = raw_name.split(' - ', 1)
        if len(parts) == 2:
            name1 = parts[0].strip()
            name2 = parts[1].strip()

            if re.search(r'[IVX]+\s*\(\d+\)', name1):
                return None

            if _norm_title_eq(name1, name2):
                return None

            # Reject name2 that is actually metadata (episode number/marker,
            # quality/codec, year) or a descriptive episode title rather than a
            # CzSk alias. Single source of truth: _dual_name2_is_false_positive
            # (audit round-2 #5/#10 — was duplicated inline here).
            if _dual_name2_is_false_positive(name2):
                return None

            if name1 and name2 and len(name1) > 1 and len(name2) > 1:
                return (name1, name2)

    # Try dash separator without spaces
    dash_match = re.match(r'^([A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ][^-]+)-([A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ].+)$', raw_name)
    if dash_match:
        name1 = dash_match.group(1).strip()
        name2 = dash_match.group(2).strip()

        if re.search(r'[IVX]+\s*\(\d+\)', name1):
            return None

        # Same-title-written-differently and metadata false positives must be
        # rejected here too — this branch previously had no metadata guard and
        # used a raw NFKD compare instead of the shared helpers (round-2 #5/#20).
        if _norm_title_eq(name1, name2) or _dual_name2_is_false_positive(name2):
            return None

        if (name1 and name2 and len(name1) > 1 and len(name2) > 1 and
            (' ' in name1 or ' ' in name2 or
             sum(1 for c in name1 if c.isupper()) > 1 or
             sum(1 for c in name2 if c.isupper()) > 1)):
            return (name1, name2)

    # Try slash separator
    if ' / ' in raw_name:
        parts = raw_name.split(' / ', 1)
        if len(parts) == 2:
            name1 = parts[0].strip()
            name2 = parts[1].strip()
            # Apply the same false-positive guards as the other branches: a
            # slash before metadata ("Inception / 1080p", "/ 2010", "/ S01E01")
            # or an episode title is not a dual-name pair (audit finding #33).
            if (name1 and name2 and len(name1) > 1 and len(name2) > 1
                    and not _norm_title_eq(name1, name2)
                    and not _dual_name2_is_false_positive(name2)):
                return (name1, name2)

    # Try multi-space separator (2+ spaces)
    multi_space_match = re.match(r'^(.+?)\s{2,}(.+)$', raw_name)
    if multi_space_match:
        name1 = multi_space_match.group(1).strip()
        name2 = multi_space_match.group(2).strip()

        if (name1 and name2 and len(name1) > 1 and len(name2) > 1 and
            any(c.isupper() for c in name1) and any(c.isupper() for c in name2)):

            # Reject same-title and metadata false positives via the shared
            # helpers (this branch had no metadata guard — round-2 #5/#20).
            if (not _norm_title_eq(name1, name2)
                    and not _dual_name2_is_false_positive(name2)):
                return (name1, name2)

    return None


# ============================================================================
# Name Cleaning
# ============================================================================

_ROMAN_MAP = {
    'ii': '2', 'iii': '3', 'iv': '4', 'v': '5',
    'vi': '6', 'vii': '7', 'viii': '8', 'ix': '9', 'x': '10',
    'xi': '11', 'xii': '12', 'xiii': '13',
}
# Only match ii+ (skip standalone "i" which conflicts with articles/pronouns)
_RE_ROMAN = re.compile(r'\b(xiii|xii|xi|ix|viii|vii|vi|iv|iii|ii)\b')


def _normalize_roman_numerals(name):
    """Convert Roman numerals (II+) to Arabic in canonical keys.

    "part iii" → "part 3", "season ii" → "season 2"
    Skips standalone "i" (too ambiguous — article/pronoun).
    """
    def replace_roman(m):
        roman = m.group(1).lower()
        return _ROMAN_MAP.get(roman, m.group(0))

    return _RE_ROMAN.sub(replace_roman, name)


def clean_series_name(name):
    """Aggressively normalize series name for grouping.

    Removes: quality, codec, audio, language tags, separators, year tags
    Handles: Czech special characters and other Unicode
    Returns: lowercase normalized name for consistent grouping
    """
    name = _PATTERN_EPISODE_MARKER.sub('', name)
    name = _PATTERN_QUALITY.sub('', name)
    name = _PATTERN_CODEC.sub('', name)
    name = _PATTERN_AUDIO.sub('', name)
    name = _PATTERN_LANG.sub('', name)
    # Strip years, but preserve if the name IS a year (e.g., series "1883")
    name_before_year_strip = name
    name = _PATTERN_YEAR.sub('', name)
    if not name.strip():
        name = name_before_year_strip  # Restore — name was entirely a year
    name = _PATTERN_SEPARATORS.sub(' ', name)
    name = ' '.join(name.split())
    # Strip bracket groups: "(...)" and "[...]" (release tags like [FLE], [YIFY])
    name = re.sub(r'[\(\[][^)\]]*[\)\]]', '', name)
    name = ' '.join(name.split())
    # Strip release group tags from end
    name = _RE_RELEASE_GROUP.sub('', name)
    name = unidecode(name)
    name = name.strip().lower()

    # Normalize Roman numerals to Arabic (only standalone: I, II, III, IV, V, etc.)
    name = _normalize_roman_numerals(name)

    # Strip a leading English article — but only if a non-trivial remainder is
    # left, so short titles aren't eaten ("A Team"->"team" yes; "A-ha"->"a ha"
    # kept because "ha" is too short; "A.I."->"a i" kept).
    for article, cut in (('the ', 4), ('a ', 2), ('an ', 3)):
        if name.startswith(article):
            remainder = name[cut:]
            if len(remainder.replace(' ', '')) >= 3:
                name = remainder
            break

    # Strip a trailing reordered 'the' ("Walking Dead The" / "Walking Dead,
    # The" -> reorder of "The Walking Dead"; the comma is already a space by
    # now via _PATTERN_SEPARATORS). Trailing 'a'/'an' are NOT stripped — a
    # title ending in "a" is common (esp. Czech) and rarely a reorder artifact.
    if name.endswith(' the'):
        name = name[:-4]

    # Remove inline ' the ' (rarely meaningful). Do NOT remove inline ' a '/
    # ' an ': in Czech/Slovak 'a' is the conjunction "and" ("Tom a Jerry"),
    # and English titles use 'a' meaningfully ("King a Queen").
    name = name.replace(' the ', ' ')
    name = ' '.join(name.split())

    return name.strip()


def get_word_set_key(name):
    """Get sorted word set for order-independent matching.

    Used in merge phase to detect series with same words but different order.
    Example: "south park" and "park south" both return "park south"
    """
    words = sorted(set(name.split()))
    return ' '.join(words)


def extract_language_tag(filename):
    """Extract language code from filename.

    Returns language code string ('CZ', 'EN', etc.) or None.
    """
    # Require a word boundary (or explicit brackets) around the code so codes
    # embedded in ordinary words don't false-match ("GENESIS"→ES, "SPIRIT"→IT,
    # "SEVEN"→EN). Mirrors _PATTERN_LANG. Bracketed group is captured separately.
    match = re.search(
        r'\b(CZ|EN|SK|DE|FR|ES|IT|PL|RU|JP|KR)\b'
        r'|[\(\[](CZ|EN|SK|DE|FR|ES|IT|PL|RU|JP|KR)[\)\]]',
        filename, re.IGNORECASE)
    if not match:
        return None
    return (match.group(1) or match.group(2)).upper()


def get_display_name(filename):
    """Extract display-friendly series name (preserves case)."""
    match = _PATTERN_S00E00.match(filename) or _PATTERN_0x00.match(filename)
    if match:
        raw_name = _strip_episode_title_suffix(match.group(1))
        name = raw_name.replace('.', ' ').replace('_', ' ')
        name = _PATTERN_QUALITY.sub('', name)
        name = _PATTERN_CODEC.sub('', name)
        name = _PATTERN_AUDIO.sub('', name)
        name = _PATTERN_LANG.sub('', name)
        name = ' '.join(name.split())
        return name.strip()
    return filename


# ============================================================================
# Season Text Extraction
# ============================================================================

def extract_season_from_text(filename):
    """Extract season number from text markers like "2nd Season", "Season 2".

    Returns:
        tuple: (season_number, cleaned_filename) or (None, filename) if no season text found

    Examples:
        "Mashle 2nd Season - 01.mkv" -> (2, "Mashle - 01.mkv")
        "Series Season 3 E05.mkv" -> (3, "Series E05.mkv")
        "Normal S01E01.mkv" -> (None, "Normal S01E01.mkv")
    """
    match = _PATTERN_SEASON_TEXT.search(filename)
    if not match:
        return None, filename

    # Extract season number from any of the three capture groups
    season = None
    for group in match.groups():
        if group:
            season = int(group)
            break

    if season is None:
        return None, filename

    # Remove the season text span, keeping the head (series name) and tail
    # (episode separator + number) intact. Tidy ONLY the seam left by the
    # removal — do NOT collapse separators across the whole string, which
    # corrupted the episode dash and re-inserted it at the wrong position (#34).
    head = filename[:match.start()].rstrip(' -_.')
    tail = filename[match.end():].lstrip(' _.')  # keep a leading '-' on the tail
    cleaned = '{} {}'.format(head, tail) if (head and tail) else (head or tail)
    cleaned = re.sub(r'\s{2,}', ' ', cleaned).strip()

    return season, cleaned


# ============================================================================
# Episode & Movie Parsing
# ============================================================================

def parse_episode_info(filename):
    """Parse TV series info from filename.

    Supports multiple episode numbering formats:
    - S##E## format: "Series S01E05.mkv", "(S01E05)", "[S01E05]"
    - ##x## format: "Series 1x05.mkv"
    - Absolute episode: "Series - 05.mkv", "Series 377.mkv"
    - Season text: "Series 2nd Season - 01.mkv"
    - Release groups: Strips leading tags like "[SubsPlease]" or "(Lena)"

    Returns dict or None:
    {
        'is_series': True,
        'series_name': 'the walking dead',
        'season': 1,
        'episode': 5,
        'original_name': filename
    }
    """
    # Cap length before regex work: the lazy `(.+?)[\s_.\-]+` patterns below
    # backtrack O(n^2) on pathological separator runs. Real filenames are well
    # under this; the cap keeps a crafted/decorative name from freezing the UI.
    if filename and len(filename) > _MAX_PARSE_LEN:
        filename = filename[:_MAX_PARSE_LEN]

    # Strip leading release group tags like "[SubsPlease] " or "(Lena) "
    # Only strips if at the very start of filename
    filename = re.sub(r'^[\(\[]([^)\]]+)[\)\]]\s*', '', filename)

    # Try S##E## format (normal: series name first)
    match = _PATTERN_S00E00.match(filename)
    if match:
        raw_name = match.group(1)
        try:
            season = int(match.group(2))
            episode = int(match.group(3))
        except (ValueError, TypeError):
            return None
        series_name = clean_series_name(_strip_episode_title_suffix(raw_name))
        return {
            'is_series': True,
            'series_name': series_name,
            'season': season,
            'episode': episode,
            'original_name': filename
        }

    # Try S##E## format (reversed: episode marker first, like "S01E02 Chainsaw Man")
    match = _PATTERN_S00E00_REVERSED.match(filename)
    if match:
        try:
            season = int(match.group(1))
            episode = int(match.group(2))
        except (ValueError, TypeError):
            return None
        raw_name = match.group(3)
        # Remove file extension
        raw_name = re.sub(r'\.(mkv|avi|mp4|m4v|wmv|flv|webm|mov)$', '', raw_name, flags=re.IGNORECASE)
        # Remove quality markers and everything after them
        raw_name = re.sub(r'[\s_\.\-]*(?:1080p|720p|2160p|4K|BluRay|WEB-DL|HDTV|WEBRip|BRRip|x264|x265|HEVC).*$', '', raw_name, flags=re.IGNORECASE)
        # Remove dash and anything after (often episode titles)
        raw_name = re.sub(r'[\s_]*-[\s_].*$', '', raw_name)
        raw_name = raw_name.strip(' .-_')
        # Guard against bare markers like "S01E01.mkv": after stripping the
        # extension and quality junk, nothing but a container extension remains,
        # which would otherwise yield a phantom series named "mkv"/"avi".
        if re.match(r'^(mkv|avi|mp4|m4v|wmv|flv|webm|mov)$', raw_name, re.IGNORECASE):
            raw_name = ''
        series_name = clean_series_name(raw_name)
        if series_name and len(series_name) >= 2:  # Make sure we got a valid series name
            return {
                'is_series': True,
                'series_name': series_name,
                'season': season,
                'episode': episode,
                'original_name': filename
            }

    # Try ##x## format
    match = _PATTERN_0x00.match(filename)
    if match:
        raw_name = match.group(1)
        try:
            season = int(match.group(2))
            episode = int(match.group(3))
        except (ValueError, TypeError):
            return None
        series_name = clean_series_name(_strip_episode_title_suffix(raw_name))
        return {
            'is_series': True,
            'series_name': series_name,
            'season': season,
            'episode': episode,
            'original_name': filename
        }

    # Try absolute episode number format (e.g., "Mashle - 01", "Series 12", "mashle ep9")
    # First check for season text markers
    season_from_text, cleaned_filename = extract_season_from_text(filename)

    match = _PATTERN_ABSOLUTE_EP.match(cleaned_filename)
    if match:
        raw_name = match.group(1)
        episode_str = match.group(2)

        # Check if this looks like a quality/codec/audio marker
        match_end = match.end()

        # Skip quality markers like "720p", "1080p"
        if match_end < len(cleaned_filename) and cleaned_filename[match_end:match_end+1].lower() == 'p':
            return None

        # Skip audio channel markers like "AAC5.1", "DD5.1", "AC3 5.1", "DD7.1"
        # Pattern: series name ends with audio codec, then our matched "episode" is a channel number
        if raw_name and raw_name[-1].isdigit():
            last_char = raw_name[-1]
            # Common audio: AC3 (3.x), 2.0, 2.1, 5.1, 7.1
            # If series ends with 2,3,5,7 and episode is 0,1, likely audio marker
            if last_char in ('2', '3', '5', '7') and episode_str in ('0', '1'):
                return None
            # Also skip if episode is 1,7 and series ends with 3 (AC3.7.1 pattern)
            if last_char == '3' and episode_str in ('1', '7'):
                return None

        # Skip if raw_name ends with known audio codec and episode is a channel number
        # Catches: "AC3 5.1", "DTS 5.1", "DD 5.1", "AAC 2.0"
        raw_name_upper = raw_name.rstrip(' .-_').upper() if raw_name else ''
        if raw_name_upper and episode_str in ('1', '2', '5', '7'):
            if any(raw_name_upper.endswith(codec) for codec in ('AC3', 'DTS', 'DD', 'AAC', 'EAC3', 'TRUEHD')):
                return None

        # Parse episode number (may have decimal like "6.5")
        try:
            if '.' in episode_str:
                episode = float(episode_str)
            else:
                episode = int(episode_str)
        except (ValueError, TypeError):
            return None

        # Validate episode number range (1-999)
        if episode < 1 or episode > 999:
            return None

        # Use extracted season or default to 1
        season = season_from_text if season_from_text else 1

        series_name = clean_series_name(raw_name)

        # Additional validation: series name should not be empty
        if not series_name or len(series_name) < 2:
            return None

        # For absolute episode numbers without explicit markers (ep, episode),
        # require series name to be reasonably long to avoid false positives
        # like "Blade 01" being mistaken for episode 1 instead of movie
        # Require a real "ep"/"episode" token, not any word containing the
        # letters "ep" ("Deep 2", "Steep 3", "Sleepers"), which would otherwise
        # bypass the sequel-number guard below and mis-parse a movie as a series.
        has_ep_marker = bool(re.search(r'\bep\b|\bep\.?\s*\d|\bepisode\b',
                                       cleaned_filename, re.IGNORECASE))
        if not has_ep_marker:
            # Require either multiple words OR longer single word (6+ chars)
            words = series_name.split()
            if len(words) == 1 and len(series_name) < 6:
                return None

            # Reject movie-sequel-like names ("Avatar 2", "Top Gun 2"): a single
            # non-zero digit with NO dash separator and NO ep marker is almost
            # always a sequel number, not an absolute episode (which are
            # zero-padded "01", multi-digit, dash-separated, or marker-tagged).
            gap = cleaned_filename[match.end(1):match.start(2)]
            if ('-' not in gap and len(episode_str) == 1 and episode_str != '0'):
                return None

        return {
            'is_series': True,
            'series_name': series_name,
            'season': season,
            'episode': int(episode) if isinstance(episode, float) and episode.is_integer() else episode,
            'original_name': filename
        }

    return None


# A 4-digit (19xx|20xx) token, with optional surrounding ()/[]; used to find
# the RELEASE year rather than a title-embedded number like "2049"/"2000".
# The `(?!x\d{3,4})` lookahead rejects a WIDTH that is part of a resolution
# ("1920x1080", "2020x1080") so the resolution width is never read as the
# release year (audit round-2 #2/#3).
_RE_YEAR_TOKEN_SCAN = re.compile(r'[\(\[]?((?:19|20)\d{2})(?!x\d{3,4})[\)\]]?')
_RE_BRACKETED_YEAR = re.compile(r'[\(\[]((?:19|20)\d{2})(?!x\d{3,4})[\)\]]')
# Known video/archive extensions only — used to strip a trailing extension from
# a "(year) Title.ext" title without eating dotted sequel suffixes ("Rocky.IV").
_RE_FILE_EXT_STRIP = re.compile(
    r'\.(mkv|mp4|avi|rar|zip|7z|ts|iso|m4v|flac|mp3|wmv|mov|mpg|mpeg)$',
    re.IGNORECASE)


def _select_movie_year(filename):
    """Pick the release year and the title text preceding it.

    Returns (raw_title, year) or None. Resolution order:
      1. A bracketed/parenthesized (19|20)\\d{2} = the release year (uploaders
         wrap the real year: "Death Race 2000 (1975)" -> 1975). The title is
         the text before the bracket, or — for the "(2010) Title" convention —
         the text AFTER it when nothing precedes it.
      2. Otherwise the LAST plausible (19|20)\\d{2} token that is <= current+2,
         with the title being everything before it.

    Limitation: a BARE trailing year is taken as the release year, so
    "Death Race 2000.mkv" yields year 2000 / title "Death Race". A bare title
    number and a real release year are indistinguishable by surface form; to
    keep an in-title number ("Death Race 2000", "Space 1999"), supply the real
    year in brackets ("Death Race 2000 (1975)") — rule 1 then wins. A leading
    implausible-future number ("2049") is left in the title via the plausibility
    cap.
    """
    # Strip leading release-group tags ("[FLE] ", "(Lena) ", "[FLE][YIFY] ")
    # so they don't leak into the title or get mistaken for the year token.
    # A bracket whose content is JUST a year ("(2010)") is NOT a release-group
    # tag — it is the release year for a "(2010) Title" name — so the lookahead
    # leaves it in place for rule 1 to consume (audit round-2 #5).
    filename = re.sub(
        r'^(?:[\(\[](?!(?:19|20)\d{2}[\)\]])[^)\]]*[\)\]]\s*)+', '', filename)

    # 1. bracketed year wins (it's an explicit release-year tag)
    bm = _RE_BRACKETED_YEAR.search(filename)
    if bm:
        year = int(bm.group(1))
        if year <= _CURRENT_YEAR + 2:
            raw_title = filename[:bm.start()].strip(' .-_([')
            if raw_title:
                return raw_title, year
            # "(2010) Title": nothing precedes the year — the title follows it.
            # Strip a trailing file extension here, which the normal
            # title-before-year path never carries (the year precedes it). Only
            # a KNOWN extension is stripped — a blanket ".<2-4 alnum>$" would
            # also eat dotted sequel suffixes ("Rocky.IV" -> "Rocky").
            after = filename[bm.end():].strip(' .-_)]')
            after = _RE_FILE_EXT_STRIP.sub('', after).strip(' .-_')
            if after:
                return after, year

    # 2. choose the rightmost plausible bare year token; everything before it
    #    is the title. This keeps in-title numbers in the title when a later
    #    real year exists, and avoids binding to an early title number.
    candidates = [(m.start(), int(m.group(1))) for m in _RE_YEAR_TOKEN_SCAN.finditer(filename)]
    plausible = [(pos, y) for pos, y in candidates if y <= _CURRENT_YEAR + 2]
    if plausible:
        pos, year = plausible[-1]
        raw_title = filename[:pos].strip(' .-_([')
        if raw_title:
            return raw_title, year
    return None


def parse_movie_info(filename):
    """Extract movie title and year from filename.

    Returns:
        {'is_movie': True, 'title': str, 'year': int, 'raw_title': str, 'dual_names': tuple|None}
        or None if not a movie pattern
    """
    if filename and len(filename) > _MAX_PARSE_LEN:
        filename = filename[:_MAX_PARSE_LEN]
    selected = _select_movie_year(filename)
    if selected:
        raw_title, year = selected

        # Validate title: must have at least 2 alphanumeric chars
        # Rejects malformed extractions like "(", "13-", "9|"
        alnum_chars = sum(1 for c in raw_title if c.isalnum())
        if alnum_chars < 2:
            return None

        clean_title = clean_series_name(raw_title)

        # Handle year-as-name edge case (e.g., movie "2012", series "1883")
        # If cleaning removed everything and raw title IS a 4-digit year, preserve it
        if len(clean_title) < 2:
            raw_stripped = raw_title.strip().replace('.', ' ').replace('-', ' ').strip()
            if re.match(r'^\d{4}$', raw_stripped):
                clean_title = raw_stripped
            else:
                return None

        dual_names = extract_dual_names(raw_title)

        return {
            'is_movie': True,
            'title': clean_title,
            'year': year,
            'raw_title': raw_title,
            'dual_names': dual_names
        }
    return None


# Export regex patterns for use in other modules
def get_s00e00_pattern():
    return _PATTERN_S00E00


def get_0x00_pattern():
    return _PATTERN_0x00
