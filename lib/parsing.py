# -*- coding: utf-8 -*-
# Module: parsing
# Author: onykmin
# License: AGPL v.3 https://www.gnu.org/licenses/agpl-3.0.html

import re

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
_PATTERN_MOVIE_YEAR = re.compile(r'^(.+?)[\s_\.\-]*[\(\[]?((?:19|20)\d{2})[\)\]]?')


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

        quality_keywords = ['p', 'hd', 'fps', 'x264', 'x265', 'hevc', 'aac', 'dts', 'bluray', 'webrip']
        is_quality = any(kw in name2.lower() for kw in quality_keywords)

        if name1 and name2 and len(name1) > 1 and len(name2) > 1 and not is_quality:
            return (name1, name2)

    # Try parentheses format: "Name1 (Name2)"
    paren_match = re.match(r'^(.+?)\s*\(([^)]+)\)', raw_name)
    if paren_match:
        name1 = paren_match.group(1).strip()
        name2 = paren_match.group(2).strip()

        is_year = re.match(r'^\d{4}$', name2)
        quality_keywords = ['p', 'hd', 'fps', 'x264', 'x265', 'hevc', 'aac', 'dts', 'bluray', 'webrip']
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

            from unicodedata import normalize
            norm1 = normalize('NFKD', name1.lower()).encode('ASCII', 'ignore').decode()
            norm2 = normalize('NFKD', name2.lower()).encode('ASCII', 'ignore').decode()
            if norm1 == norm2:
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

        from unicodedata import normalize
        norm1 = normalize('NFKD', name1.lower()).encode('ASCII', 'ignore').decode()
        norm2 = normalize('NFKD', name2.lower()).encode('ASCII', 'ignore').decode()
        if norm1 == norm2:
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
            if name1 and name2 and len(name1) > 1 and len(name2) > 1:
                return (name1, name2)

    # Try multi-space separator (2+ spaces)
    multi_space_match = re.match(r'^(.+?)\s{2,}(.+)$', raw_name)
    if multi_space_match:
        name1 = multi_space_match.group(1).strip()
        name2 = multi_space_match.group(2).strip()

        if (name1 and name2 and len(name1) > 1 and len(name2) > 1 and
            any(c.isupper() for c in name1) and any(c.isupper() for c in name2)):

            from unicodedata import normalize
            norm1 = normalize('NFKD', name1.lower()).encode('ASCII', 'ignore').decode()
            norm2 = normalize('NFKD', name2.lower()).encode('ASCII', 'ignore').decode()
            if norm1 != norm2:
                return (name1, name2)

    return None


# ============================================================================
# Name Cleaning
# ============================================================================

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
    name = _PATTERN_YEAR.sub('', name)
    name = _PATTERN_SEPARATORS.sub(' ', name)
    name = ' '.join(name.split())
    name = re.sub(r'\([^)]*\)', '', name)
    name = ' '.join(name.split())
    name = unidecode(name)
    name = name.strip().lower()

    if name.startswith('the '):
        name = name[4:]
    elif name.startswith('a '):
        name = name[2:]
    elif name.startswith('an '):
        name = name[3:]

    name = name.replace(' the ', ' ').replace(' a ', ' ').replace(' an ', ' ')
    name = ' '.join(name.split())

    return name.strip()


def extract_language_tag(filename):
    """Extract language code from filename.

    Returns language code string ('CZ', 'EN', etc.) or None.
    """
    match = re.search(r'[\(\[]?(CZ|EN|SK|DE|FR|ES|IT|PL|RU|JP|KR)[\)\]]?', filename, re.IGNORECASE)
    return match.group(1).upper() if match else None


def get_display_name(filename):
    """Extract display-friendly series name (preserves case)."""
    match = _PATTERN_S00E00.match(filename) or _PATTERN_0x00.match(filename)
    if match:
        raw_name = match.group(1)
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

    # Remove the season text from filename for clean series name extraction
    cleaned = filename[:match.start()] + filename[match.end():]
    # Clean up any double separators left behind
    cleaned = re.sub(r'[\s\-]+', ' ', cleaned).strip()
    # Restore dash if it was the separator
    if ' - ' in filename:
        cleaned = re.sub(r'\s+', ' - ', cleaned, count=1)

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
    # Strip leading release group tags like "[SubsPlease] " or "(Lena) "
    # Only strips if at the very start of filename
    filename = re.sub(r'^[\(\[]([^)\]]+)[\)\]]\s*', '', filename)

    # Try S##E## format (normal: series name first)
    match = _PATTERN_S00E00.match(filename)
    if match:
        raw_name = match.group(1)
        season = int(match.group(2))
        episode = int(match.group(3))
        series_name = clean_series_name(raw_name)
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
        season = int(match.group(1))
        episode = int(match.group(2))
        raw_name = match.group(3)
        # Remove file extension
        raw_name = re.sub(r'\.(mkv|avi|mp4|m4v|wmv|flv|webm|mov)$', '', raw_name, flags=re.IGNORECASE)
        # Remove quality markers and everything after them
        raw_name = re.sub(r'[\s_\.\-]*(?:1080p|720p|2160p|4K|BluRay|WEB-DL|HDTV|WEBRip|BRRip|x264|x265|HEVC).*$', '', raw_name, flags=re.IGNORECASE)
        # Remove dash and anything after (often episode titles)
        raw_name = re.sub(r'[\s_]*-[\s_].*$', '', raw_name)
        raw_name = raw_name.strip(' .-_')
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
        season = int(match.group(2))
        episode = int(match.group(3))
        series_name = clean_series_name(raw_name)
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

        # Skip audio channel markers like "AAC5.1", "DD7.1", "AC3.2.0", "AC3.7.1"
        # Pattern: series name ends with digit, then separator, then our matched episode
        if raw_name and raw_name[-1].isdigit():
            last_char = raw_name[-1]
            # Common audio: AC3 (3.x), 2.0, 2.1, 5.1, 7.1
            # If series ends with 2,3,5,7 and episode is 0,1, likely audio marker
            if last_char in ('2', '3', '5', '7') and episode_str in ('0', '1'):
                return None
            # Also skip if episode is 1,7 and series ends with 3 (AC3.7.1 pattern)
            if last_char == '3' and episode_str in ('1', '7'):
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
        has_ep_marker = 'ep' in cleaned_filename.lower() or 'episode' in cleaned_filename.lower()
        if not has_ep_marker:
            # Require either multiple words OR longer single word (6+ chars)
            words = series_name.split()
            if len(words) == 1 and len(series_name) < 6:
                return None

        return {
            'is_series': True,
            'series_name': series_name,
            'season': season,
            'episode': int(episode) if isinstance(episode, float) and episode.is_integer() else episode,
            'original_name': filename
        }

    return None


def parse_movie_info(filename):
    """Extract movie title and year from filename.

    Returns:
        {'is_movie': True, 'title': str, 'year': int, 'raw_title': str, 'dual_names': tuple|None}
        or None if not a movie pattern
    """
    match = _PATTERN_MOVIE_YEAR.match(filename)
    if match:
        raw_title = match.group(1)
        year = int(match.group(2))
        clean_title = clean_series_name(raw_title)
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
