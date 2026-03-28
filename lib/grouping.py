# -*- coding: utf-8 -*-
# Module: grouping
# Author: onykmin
# License: AGPL v.3 https://www.gnu.org/licenses/agpl-3.0.html

import xbmc
import xbmcaddon
from lib.logging import log_debug, log_error
from lib.parsing import (parse_episode_info, parse_movie_info,
                         extract_language_tag, extract_dual_names, get_display_name,
                         get_s00e00_pattern, get_0x00_pattern, get_word_set_key)
from lib.api import api, parse_xml, is_ok
from lib.utils import todict

# Import NONE_WHAT from ui to avoid duplication
# Note: Import at end to avoid circular dependency
def _get_none_what():
    from lib.ui import NONE_WHAT
    return NONE_WHAT

_addon = xbmcaddon.Addon()

# Check if dual names available
try:
    from csfd_scraper import create_canonical_from_dual_names
    DUAL_NAMES_AVAILABLE = True
except ImportError:
    DUAL_NAMES_AVAILABLE = False

_PATTERN_S00E00 = get_s00e00_pattern()
_PATTERN_0x00 = get_0x00_pattern()

# Pattern to detect S##E## markers for movie vs series disambiguation
# Use [\b_] boundaries to also match underscore-separated markers like _S01E06_
import re
_PATTERN_EPISODE_MARKER = re.compile(r'(?:^|[\b_\s.\-,])[Ss]\d{1,2}[Ee]\d{1,3}(?:[\b_\s.\-,]|$)')

# Compiled patterns for display name cleaning (used in pick_best_display_name_from_list)
_RE_FILE_EXT = re.compile(r'\.(mkv|mp4|avi|rar|zip|7z|ts|iso|m4v|flac|mp3)$', re.IGNORECASE)
_RE_QUALITY = re.compile(r'\b(480p|720p|1080p|2160p|4K|UHD|FHD|HD)\b', re.IGNORECASE)
_RE_SOURCE = re.compile(r'\b(BluRay|Blu-ray|WEB-DL|WEBDL|WEBRip|HDTV|BRRip|DVDRip|REMUX|Theatrical)\b', re.IGNORECASE)
_RE_CODEC = re.compile(r'\b(x264|x265|H\.?264|H\.?265|HEVC|XviD|AAC|AC3|DTS|DD5\.1|Atmos|TrueHD)\b', re.IGNORECASE)
_RE_LANG_LABEL = re.compile(r'\b(CZ|EN|SK|MULTi)\s+(DABING|dabing|TITULKY|titulky|sub|dub)\b', re.IGNORECASE)
_RE_LANG_CODE = re.compile(r'\s+(CZ|EN|SK)\b', re.IGNORECASE)
_RE_BRACKET_GROUP = re.compile(r'\s*[\(\[][^\)\]]{0,40}[\)\]]$')
_RE_TRAILING_NUM = re.compile(r'[-\s]+\d{1,3}(?:\.\d+)?(\s+(serie|série|season|sezona|disk))?\s*(dab|BEZ HESLA)?$', re.IGNORECASE)
_RE_SE_MARKER = re.compile(r'\s*[Ss]\d{1,2}[Ee]\d{1,3}.*$')
_RE_NxN_MARKER = re.compile(r'\s*\d{1,2}x\d{1,3}.*$')
_RE_TRAILING_SEP = re.compile(r'[\s\-_\.]+$')
_RE_MULTI_SPACE = re.compile(r'\s+')
_RE_MULTI_DASH = re.compile(r'-{2,}')


_RE_YEAR_TOKEN = re.compile(r'^\d{4}$')
_FILTER_STOP_WORDS = {'the', 'a', 'an', 'of', 'and', 'or', 'in', 'on', 'at', 'to', 'for', 'is', 'it', 'by'}

# Module-level unidecode for _filter_irrelevant (avoid re-import per call)
try:
    from unidecode import unidecode as _unidecode_filter
except ImportError:
    import unicodedata as _unicodedata_filter
    def _unidecode_filter(text):
        return ''.join(c for c in _unicodedata_filter.normalize('NFKD', text) if not _unicodedata_filter.combining(c))


def _filter_irrelevant(files, query):
    """Filter out files irrelevant to the search query.

    Uses word-overlap check: keeps files that share at least one significant
    query word with the filename. This is conservative — only drops files
    that have ZERO overlap with the query.
    """
    query_words = set(_unidecode_filter(query).lower().split())
    # Remove stop words, very short words, and year-like tokens
    query_words = {w for w in query_words
                   if len(w) >= 3 and w not in _FILTER_STOP_WORDS and not _RE_YEAR_TOKEN.match(w)}

    if not query_words:
        return files

    # Also add stems (strip trailing s/es for plural matching)
    stems = set()
    for w in query_words:
        stems.add(w)
        if w.endswith('es') and len(w) > 4:
            stems.add(w[:-2])
        elif w.endswith('s') and len(w) > 3:
            stems.add(w[:-1])

    filtered = []
    for f in files:
        name = f.get('name', '')
        # Strip leading bracket tags (fansub/release groups like "[Blade]", "(Lena)")
        # so they don't false-match the query
        stripped = re.sub(r'^[\(\[][^\)\]]*[\)\]]\s*', '', name)
        name_lower = _unidecode_filter(stripped).lower()
        # Keep if any query word/stem appears as substring in filename
        if any(qw in name_lower for qw in stems):
            filtered.append(f)

    dropped = len(files) - len(filtered)
    if dropped > 0:
        log_debug(f'Relevance filter: dropped {dropped}/{len(files)} files (no query word match)')

    return filtered if filtered else files


def merge_substring_series(grouped):
    """Merge series where one canonical key is substring of another.

    Example: "south park" and "mestecko south park" → merge into "south park"

    Uses precomputed word sets and length-sorted keys for O(N log N) performance.
    """
    series = grouped['series']
    keys_list = list(series.keys())

    if len(keys_list) < 2:
        return grouped

    # Precompute word sets once (avoids O(N²) split/set creation)
    word_sets = {key: set(key.split()) for key in keys_list}

    # Sort by word count (fewer words first) for directional matching
    keys_by_words = sorted(keys_list, key=lambda k: len(word_sets[k]))

    keys_to_merge = []
    for i, short_key in enumerate(keys_by_words):
        short_words = word_sets[short_key]
        short_wc = len(short_words)

        # Safety: don't merge very short keys (single short words like "lost", "dark")
        # Require >=2 words OR single word with >=6 chars for substring merging
        if short_wc == 1 and len(short_key) < 6:
            continue

        for long_key in keys_by_words[i+1:]:
            long_words = word_sets[long_key]

            # Skip if same word count (can't be proper subset)
            if len(long_words) == short_wc:
                continue

            if short_words.issubset(long_words):
                # Safety: if both groups have significant episodes and the extra
                # words are short (likely sequel/spinoff markers like Z, GT, Super),
                # don't merge — these are different series
                extra_words = long_words - short_words
                short_eps = series[short_key]['total_episodes']
                long_eps = series[long_key]['total_episodes']
                if min(short_eps, long_eps) >= 3 and all(len(w) <= 5 for w in extra_words):
                    continue
                keys_to_merge.append((short_key, long_key))

    # Perform merges
    for short_key, long_key in keys_to_merge:
        if short_key not in series or long_key not in series:
            continue

        merge_season_data(series[short_key], series[long_key])

        short_display = series[short_key].get('display_name', short_key.title())
        long_display = series[long_key].get('display_name', long_key.title())
        series[short_key]['display_name'] = pick_best_display_name(short_display, long_display)

        del series[long_key]

    return grouped


def merge_word_order_series(grouped):
    """Merge series with same words but different order.

    Example: "south park" and "park south" → merge into first encountered

    Uses get_word_set_key() to create order-independent comparison keys.

    Args:
        grouped: Dict with 'series' and 'non_series' keys

    Returns:
        Modified grouped dict with merged series
    """
    series = grouped.get('series', {})
    if not series:
        return grouped

    # Build word-set to keys mapping
    word_set_map = {}  # {word_set_key: [series_keys...]}
    for key in series.keys():
        ws_key = get_word_set_key(key)
        if ws_key not in word_set_map:
            word_set_map[ws_key] = []
        word_set_map[ws_key].append(key)

    # Find and merge duplicates
    for ws_key, keys in word_set_map.items():
        if len(keys) < 2:
            continue

        # Use first key as target
        target = keys[0]
        for source in keys[1:]:
            if source not in series or target not in series:
                continue

            log_debug(f'Word-order merge: "{source}" → "{target}"')

            # Merge season data
            merge_season_data(series[target], series[source])

            # Pick best display name
            target_display = series[target].get('display_name', target.title())
            source_display = series[source].get('display_name', source.title())
            series[target]['display_name'] = pick_best_display_name(target_display, source_display)

            del series[source]

    return grouped


def merge_dual_canonical_series(grouped):
    """Merge series where canonical key contains pipe-separated dual names.

    Handles case where episodes have different naming:
    - "The Penguin S01E01" → canonical="the penguin"
    - "Tučňák S01E02" → canonical="tucnak"
    - "The Penguin - Tučňák S01E03" → canonical="the penguin|tucnak"

    Merges all three into one series.

    Args:
        grouped: Dict with 'series' and 'non_series' keys

    Returns:
        Modified grouped dict with merged series
    """
    series = grouped.get('series', {})
    if not series:
        return grouped

    log_debug(f'merge_dual_canonical_series: checking {len(series)} series')

    keys_to_merge = {}  # {target_key: [source_keys_to_merge]}

    # Find all series with pipe in canonical key
    dual_keys = [k for k in series.keys() if '|' in k]
    log_debug(f'Found {len(dual_keys)} dual-name keys: {dual_keys}')

    for dual_key in dual_keys:
        parts = dual_key.split('|')  # e.g., ["the penguin", "tucnak"]

        # Find other series that match either component
        matches = []
        for key in series.keys():
            if key != dual_key and key in parts:
                matches.append(key)

        if matches:
            # Use first component as target
            target = parts[0]

            # If target doesn't exist as series, use dual_key as target
            if target not in series:
                target = dual_key

            if target not in keys_to_merge:
                keys_to_merge[target] = []

            # Add dual_key and matches to merge list
            if target != dual_key:
                keys_to_merge[target].append(dual_key)
            # Only add matches that aren't the target itself
            for match in matches:
                if match != target:
                    keys_to_merge[target].append(match)

    # Perform merges
    for target_key, source_keys in keys_to_merge.items():
        if target_key not in series:
            log_debug(f'Merge target not found: {target_key}')
            continue

        for source_key in source_keys:
            if source_key not in series:
                log_debug(f'Merge source not found: {source_key}')
                continue

            log_debug(f'Merging "{source_key}" → "{target_key}"')

            # Merge season data
            merge_season_data(series[target_key], series[source_key])

            # Pick best display name
            target_display = series[target_key].get('display_name', target_key.title())
            source_display = series[source_key].get('display_name', source_key.title())

            series[target_key]['display_name'] = pick_best_display_name(target_display, source_display)

            # Remove merged series
            del series[source_key]
            log_debug(f'Merged complete: removed "{source_key}"')

    return grouped


def merge_similar_series(grouped):
    """Merge series with similar canonical keys (typo tolerance).

    Uses SequenceMatcher ratio > 0.85 to catch typos like:
    - "jujuts kaisen" → "jujutsu kaisen"
    - "stranger thing" → "stranger things"

    Only merges if one group is much smaller (likely the typo variant).
    """
    from difflib import SequenceMatcher

    series = grouped.get('series', {})
    if len(series) < 2:
        return grouped

    keys = list(series.keys())
    merges = []  # (target, source)

    for i, key1 in enumerate(keys):
        for key2 in keys[i+1:]:
            # Skip pipe-separated keys (already handled by dual merge)
            if '|' in key1 or '|' in key2:
                continue

            ratio = SequenceMatcher(None, key1, key2).ratio()
            if ratio > 0.85:
                eps1 = series[key1]['total_episodes']
                eps2 = series[key2]['total_episodes']

                # Safety: don't merge if both have significant episode counts
                # (suggests genuinely different series, e.g., "dragon ball z" vs "dragon ball super")
                if min(eps1, eps2) >= 3:
                    continue

                # Merge smaller into larger
                if eps1 >= eps2:
                    merges.append((key1, key2))
                else:
                    merges.append((key2, key1))

    for target, source in merges:
        if target not in series or source not in series:
            continue

        log_debug(f'Similarity merge ({SequenceMatcher(None, target, source).ratio():.2f}): "{source}" → "{target}"')
        merge_season_data(series[target], series[source])
        target_display = series[target].get('display_name', target.title())
        source_display = series[source].get('display_name', source.title())
        series[target]['display_name'] = pick_best_display_name(target_display, source_display)
        del series[source]

    return grouped


def pick_best_display_name_from_list(names):
    """Pick best display name from a list of candidates.

    Strategy: Clean all names aggressively, then pick shortest unique name.

    Args:
        names: List of candidate names

    Returns:
        Best name choice
    """
    if not names:
        return None

    def clean_name(name):
        """Aggressively clean a display name."""
        cleaned = name
        cleaned = _RE_FILE_EXT.sub('', cleaned)
        # Replace dots and underscores with spaces (scene naming: "Movie.Name.2010")
        cleaned = cleaned.replace('.', ' ').replace('_', ' ')
        # Normalize multiple dashes/hyphens to single space
        cleaned = _RE_MULTI_DASH.sub(' ', cleaned)
        cleaned = _RE_QUALITY.sub('', cleaned)
        cleaned = _RE_SOURCE.sub('', cleaned)
        cleaned = _RE_CODEC.sub('', cleaned)
        cleaned = _RE_LANG_LABEL.sub('', cleaned)
        cleaned = _RE_LANG_CODE.sub('', cleaned)
        cleaned = _RE_BRACKET_GROUP.sub('', cleaned)
        cleaned = _RE_TRAILING_NUM.sub('', cleaned)
        cleaned = _RE_SE_MARKER.sub('', cleaned)
        cleaned = _RE_NxN_MARKER.sub('', cleaned)
        cleaned = _RE_TRAILING_SEP.sub('', cleaned)
        cleaned = _RE_MULTI_SPACE.sub(' ', cleaned)
        return cleaned.strip()

    # Clean all names
    cleaned_map = {}  # original -> cleaned
    for name in names:
        cleaned = clean_name(name)
        if cleaned and len(cleaned) >= 2:
            if cleaned not in cleaned_map:
                cleaned_map[cleaned] = name

    if not cleaned_map:
        return names[0] if names else None

    # Find most common cleaned name (appears most in originals)
    from collections import Counter
    cleaned_list = [clean_name(n) for n in names]
    cleaned_counts = Counter(c for c in cleaned_list if c and len(c) >= 2)

    if not cleaned_counts:
        return names[0]

    # Sort by: count (desc), then length (asc), then alphabetically
    sorted_names = sorted(
        cleaned_counts.items(),
        key=lambda x: (-x[1], len(x[0]), x[0])
    )

    best_cleaned = sorted_names[0][0]

    log_debug(f'Name picker: "{best_cleaned}" (appeared {sorted_names[0][1]}x from {len(names)} candidates)')

    return best_cleaned


def pick_best_display_name(name1, name2):
    """Smart name picker: choose best display name from two candidates.

    Args:
        name1: First candidate name
        name2: Second candidate name

    Returns:
        Best name choice
    """
    return pick_best_display_name_from_list([name1, name2])


def merge_season_data(target, source):
    """Merge season/episode data from source series into target series.

    Handles conflicts by merging version lists and re-sorting by quality.
    """
    # Merge seasons
    for season_num in source['seasons']:
        if season_num not in target['seasons']:
            # New season - copy entirely
            target['seasons'][season_num] = source['seasons'][season_num]
        else:
            # Season exists in both - merge episodes
            for ep_num in source['seasons'][season_num]:
                if ep_num not in target['seasons'][season_num]:
                    target['seasons'][season_num][ep_num] = source['seasons'][season_num][ep_num]
                else:
                    # Just extend — dedup/sort happens once after all merges
                    target['seasons'][season_num][ep_num].extend(source['seasons'][season_num][ep_num])

    # Recalculate total episodes
    unique_episodes = set()
    for season_num, episodes in target['seasons'].items():
        for ep_num in episodes.keys():
            unique_episodes.add((season_num, ep_num))
    target['total_episodes'] = len(unique_episodes)


def deduplicate_versions(versions):
    """Remove duplicate files from version list.

    Deduplication strategy:
    1. Primary: by ident (if valid and not 'unknown')
    2. Fallback: by name+size pair

    Args:
        versions: List of file dicts with 'ident', 'name', 'size'

    Returns:
        New list with duplicates removed, preserving order
    """
    if not versions:
        return []

    seen_idents = set()
    seen_name_size = set()
    result = []

    for v in versions:
        is_duplicate = False

        # Check by ident (primary)
        ident = v.get('ident')
        if ident and ident != 'unknown':
            if ident in seen_idents:
                is_duplicate = True
            else:
                seen_idents.add(ident)

        # Check by name+size (fallback)
        if not is_duplicate:
            name = v.get('name')
            size = v.get('size')
            if name and size:
                key = (name, size)
                if key in seen_name_size:
                    is_duplicate = True
                else:
                    seen_name_size.add(key)

        if not is_duplicate:
            result.append(v)

    return result


def group_by_series(files, token=None, enable_csfd=True, search_query=None):
    """Group file list by series, movies, and deduplicate.

    Args:
        files: List of file dicts
        token: WebShare token for CSFD enrichment
        enable_csfd: Enable CSFD metadata lookup
        search_query: Original search query for relevance filtering

    Returns:
    {
        'series': {
            'Series Name': {
                'seasons': {
                    1: {
                        1: [version1_dict, version2_dict],  # Episode 1, 2 versions (sorted by quality)
                        2: [version1_dict]                  # Episode 2, 1 version
                    },
                    2: {...}
                },
                'total_episodes': 24  # Unique episode count
            }
        },
        'movies': {
            'movie_key|year': {
                'display_name': 'Movie Name',
                'year': 2010,
                'versions': [file_dict1, ...],
                'csfd_id': '...',  # optional
                'plot': '...'      # optional
            }
        },
        'non_series': [file_dict, ...]
    }
    """
    xbmc.log(f'[YAWsP] group_by_series: Processing {len(files)} files', xbmc.LOGDEBUG)

    # Pre-filter irrelevant results if search query provided and setting enabled
    if search_query:
        try:
            filter_enabled = _addon.getSettingBool('filter_irrelevant')
        except (ValueError, AttributeError, TypeError):
            filter_enabled = True

        if filter_enabled:
            files = _filter_irrelevant(files, search_query)

    result = {'series': {}, 'movies': {}, 'non_series': []}

    for file_dict in files:
        filename = file_dict.get('name', '')
        if not filename:  # Handle empty/None filenames
            result['non_series'].append(file_dict)
            continue

        # Check for movie year pattern BEFORE episode parsing
        # This prevents movies from being misclassified as series
        movie_info = parse_movie_info(filename)

        # Only try episode parsing if NOT a movie pattern
        # Exception: allow S##E## patterns even with years (e.g., "Series.S01E01.2010.mkv")
        ep_info = None
        if not movie_info or _PATTERN_EPISODE_MARKER.search(filename):
            ep_info = parse_episode_info(filename)

        # If it's a series match, process it
        if ep_info and ep_info['is_series']:
            series = ep_info['series_name']
            season = ep_info['season']
            episode = ep_info['episode']

            # Default: use normalized name as key
            canonical_key = series
            display_name = get_display_name(ep_info['original_name'])

            # CSFD integration: dual-name detection or CSFD lookup
            plot = None
            csfd_id = None

            # Extract raw name for dual-name detection (works even when CSFD disabled)
            match = _PATTERN_S00E00.match(filename) or _PATTERN_0x00.match(filename)
            if match:
                raw_name = match.group(1)
                dual_names = extract_dual_names(raw_name)

                # Priority 1: Dual names in filename
                if dual_names and DUAL_NAMES_AVAILABLE:
                    try:
                        dual_result = create_canonical_from_dual_names(dual_names[0], dual_names[1])
                        if dual_result:
                            canonical_key = dual_result['canonical_key']
                            display_name = dual_result['display_name']
                            log_debug(f'Dual names detected: {dual_names[0]} / {dual_names[1]}')
                        else:
                            # Fallback: use normalized series name
                            log_debug(f'Dual names returned None, using fallback: {dual_names[0]} / {dual_names[1]}')
                    except Exception as e:
                        log_error(f'Dual names processing error: {e}')

                # CSFD lookup removed (feature disabled)

            # Initialize series structure if needed (use canonical_key)
            if canonical_key not in result['series']:
                series_meta = {
                    'display_name': display_name,
                    'display_name_candidates': [display_name],  # Track all candidates
                    'seasons': {},
                    'total_episodes': 0
                }
                # Add CSFD metadata if available
                if plot:
                    series_meta['plot'] = plot
                if csfd_id:
                    series_meta['csfd_id'] = csfd_id

                result['series'][canonical_key] = series_meta
            else:
                # Add this episode's display name as candidate
                if 'display_name_candidates' not in result['series'][canonical_key]:
                    result['series'][canonical_key]['display_name_candidates'] = []
                result['series'][canonical_key]['display_name_candidates'].append(display_name)

            # Initialize season dict if needed
            if season not in result['series'][canonical_key]['seasons']:
                result['series'][canonical_key]['seasons'][season] = {}

            # Add episode and metadata to file dict
            file_dict['episode'] = episode
            file_dict['season'] = season
            file_dict['series_name'] = series

            # Defer quality metadata parsing — computed on demand in version dialogs

            # Extract language tag for metadata storage
            file_dict['language'] = extract_language_tag(filename)

            # Initialize episode list if needed (for duplicates)
            if episode not in result['series'][canonical_key]['seasons'][season]:
                result['series'][canonical_key]['seasons'][season][episode] = []

            # Check for duplicates before adding
            existing_versions = result['series'][canonical_key]['seasons'][season][episode]
            is_duplicate = False

            for existing in existing_versions:
                # Primary: Check by ident (skip if None, empty, or "unknown")
                file_ident = file_dict.get('ident')
                existing_ident = existing.get('ident')

                if (file_ident and existing_ident and
                    file_ident != 'unknown' and existing_ident != 'unknown'):
                    if file_ident == existing_ident:
                        is_duplicate = True
                        log_debug(f"Skipping duplicate (ident): {filename} [ident={file_ident}]")
                        break

                # Fallback: Check by name+size
                name_match = file_dict.get('name') == existing.get('name')
                size_match = file_dict.get('size') == existing.get('size')

                if name_match and size_match and file_dict.get('name'):
                    is_duplicate = True
                    log_debug(f"Skipping duplicate (name+size): {filename} [{file_dict.get('size')} bytes]")
                    break

            # Only add if not duplicate
            if not is_duplicate:
                result['series'][canonical_key]['seasons'][season][episode].append(file_dict)
        else:
            result['non_series'].append(file_dict)

    # Sort versions by quality score (highest first) and calculate unique episode counts
    for series_name, series_data in result['series'].items():
        unique_episodes = set()
        for season_num, episodes in series_data['seasons'].items():
            for ep_num, versions in episodes.items():
                # Deduplicate versions (final cleanup)
                deduplicated = deduplicate_versions(versions)
                series_data['seasons'][season_num][ep_num] = deduplicated

                # Sort versions by size DESC (largest first)
                deduplicated.sort(key=lambda v: int(v.get('size', 0)) if v.get('size') else 0, reverse=True)

                # Track unique episodes
                unique_episodes.add((season_num, ep_num))

        # Update total with unique count
        series_data['total_episodes'] = len(unique_episodes)

        # Pick best display name from all candidates
        candidates = series_data.get('display_name_candidates', [])
        if candidates:
            best_name = pick_best_display_name_from_list(candidates)
            if best_name:
                series_data['display_name'] = best_name
            # Clean up candidates list (no longer needed)
            del series_data['display_name_candidates']

    # Merge series with substring relationships
    result = merge_substring_series(result)

    # Merge series with same words but different order
    result = merge_word_order_series(result)

    # Merge series with dual canonical names (e.g., "the penguin|tucnak")
    result = merge_dual_canonical_series(result)

    # Merge series with similar names (typo tolerance)
    result = merge_similar_series(result)

    # Single dedup+sort pass after all merges (avoids redundant per-merge dedup)
    for series_data in result['series'].values():
        unique_episodes = set()
        for season_num, episodes in series_data['seasons'].items():
            for ep_num, versions in episodes.items():
                episodes[ep_num] = deduplicate_versions(versions)
                episodes[ep_num].sort(
                    key=lambda v: int(v.get('size', 0)) if v.get('size') else 0,
                    reverse=True)
                unique_episodes.add((season_num, ep_num))
        series_data['total_episodes'] = len(unique_episodes)

    # Group remaining files as movies (if setting enabled)
    try:
        group_movies_enabled = _addon.getSettingBool('group_movies')
    except (ValueError, AttributeError, TypeError):
        group_movies_enabled = True  # Default to enabled

    if group_movies_enabled:
        try:
            movies_result = group_movies(result['non_series'])
            result['movies'] = movies_result['movies']

            # Update non_series to exclude grouped movies
            grouped_movie_idents = set()
            for movie_data in movies_result['movies'].values():
                for version in movie_data['versions']:
                    grouped_movie_idents.add(version['ident'])

            result['non_series'] = [
                f for f in result['non_series']
                if f['ident'] not in grouped_movie_idents
            ]

            # CSFD movie enrichment removed (feature disabled)
        except Exception as e:
            log_debug(f"Error grouping movies: {e}")
            # Continue without movie grouping

    return result


def group_movies(files):
    """Group movie files by title + year.

    Args:
        files: List of file dicts with 'name', 'ident', 'size'

    Returns:
        {
            'movies': {
                'inception|2010': {
                    'display_name': 'Inception',
                    'year': 2010,
                    'versions': [file_dict1, file_dict2, ...],
                    'canonical_key': 'inception|2010'
                }
            }
        }
    """
    result = {'movies': {}}

    for file_dict in files:
        movie_info = parse_movie_info(file_dict['name'])

        if not movie_info:
            continue  # Not a movie pattern

        # Create canonical key: "title|year"
        canonical_key = f"{movie_info['title']}|{movie_info['year']}"

        # Handle dual names
        display_name = movie_info['raw_title']
        if movie_info['dual_names'] and DUAL_NAMES_AVAILABLE:
            try:
                dual_result = create_canonical_from_dual_names(
                    movie_info['dual_names'][0],
                    movie_info['dual_names'][1]
                )
                if dual_result:
                    canonical_key = f"{dual_result['canonical_key']}|{movie_info['year']}"
                    display_name = dual_result['display_name']
                else:
                    log_debug(f'Movie dual names returned None: {movie_info["dual_names"]}')
            except Exception as e:
                log_error(f'Movie dual names error: {e}')

        # Initialize movie entry
        if canonical_key not in result['movies']:
            result['movies'][canonical_key] = {
                'display_name': display_name,
                'year': movie_info['year'],
                'versions': [],
                'canonical_key': canonical_key
            }

        # Add version
        result['movies'][canonical_key]['versions'].append(file_dict)

    # Deduplicate and sort versions by size (largest first)
    for movie_data in result['movies'].values():
        # Deduplicate versions (final cleanup)
        movie_data['versions'] = deduplicate_versions(movie_data['versions'])

        # Sort by size
        movie_data['versions'].sort(
            key=lambda v: int(v.get('size', 0)) if v.get('size') else 0,
            reverse=True
        )

    # Merge movies with substring title relationships (same year)
    result = merge_substring_movies(result)

    # Merge movies with identical titles across nearby years (uploader year errors)
    result = merge_crossyear_movies(result)

    # Merge dual-name movie keys with matching simple keys
    # e.g., "blade 2|blade ii|2002" merges into "blade 2|2002"
    result = merge_dual_key_movies(result)

    # Final merge: absorb 1-version orphans into larger same-year groups
    result = merge_orphan_movies(result)

    # Clean display names (dots→spaces, strip artifacts, fix reversed dual names)
    for movie_data in result['movies'].values():
        movie_data['display_name'] = _clean_movie_display_name(movie_data['display_name'])

    return result


def merge_dual_key_movies(result):
    """Merge dual-name movie keys into matching simple keys.

    Handles: "blade 2|blade ii|2002" should merge with "blade 2|2002"
    because "blade 2" is a pipe-component of the dual key and matches
    the simple key's title, with same year.
    """
    movies = result.get('movies', {})
    if len(movies) < 2:
        return result

    # Build lookup: (simple_title, year) → key for non-pipe title keys
    simple_keys = {}  # (title, year) → key
    dual_keys = []    # keys with pipes in title part
    for key, data in movies.items():
        year = data.get('year', 0)
        if '|' in key:
            title_part = key.rsplit('|', 1)[0]
            if '|' in title_part:
                dual_keys.append(key)
            else:
                simple_keys[(title_part, year)] = key
        else:
            simple_keys[(key, year)] = key

    keys_to_delete = set()
    for dual_key in dual_keys:
        if dual_key in keys_to_delete:
            continue
        year = movies[dual_key].get('year', 0)
        title_part = dual_key.rsplit('|', 1)[0]  # e.g., "blade 2|blade ii"
        components = [c.strip() for c in title_part.split('|') if c.strip()]

        # Find a simple key matching any component
        target = None
        for comp in components:
            if (comp, year) in simple_keys:
                target = simple_keys[(comp, year)]
                break
            # Also try without spaces (blade2 → blade 2)
            comp_spaced = re.sub(r'(\D)(\d)', r'\1 \2', comp)
            if comp_spaced != comp and (comp_spaced, year) in simple_keys:
                target = simple_keys[(comp_spaced, year)]
                break

        if target and target in movies and dual_key in movies:
            movies[target]['versions'].extend(movies[dual_key]['versions'])
            movies[target]['versions'] = deduplicate_versions(movies[target]['versions'])
            movies[target]['versions'].sort(
                key=lambda v: int(v.get('size', 0)) if v.get('size') else 0,
                reverse=True)
            log_debug(f'Dual-key movie merge: "{dual_key}" → "{target}"')
            keys_to_delete.add(dual_key)

    # Also merge spaceless variants (blade2 → blade 2) within same year
    for key in list(movies.keys()):
        if key in keys_to_delete or '|' not in key:
            continue
        title = key.rsplit('|', 1)[0]
        year = movies[key].get('year', 0)
        # Try adding space before digits: "blade2" → "blade 2"
        spaced = re.sub(r'(\D)(\d)', r'\1 \2', title)
        if spaced != title and (spaced, year) in simple_keys:
            target = simple_keys[(spaced, year)]
            if target in movies and key in movies:
                movies[target]['versions'].extend(movies[key]['versions'])
                movies[target]['versions'] = deduplicate_versions(movies[target]['versions'])
                movies[target]['versions'].sort(
                    key=lambda v: int(v.get('size', 0)) if v.get('size') else 0,
                    reverse=True)
                log_debug(f'Spaceless movie merge: "{key}" → "{target}"')
                keys_to_delete.add(key)

    for key in keys_to_delete:
        if key in movies:
            del movies[key]

    return result


def merge_orphan_movies(result):
    """Absorb single-version movie orphans into larger same-year groups.

    For 1-version movies: if ALL their title words appear in a larger group's
    title (same year), merge into the larger group.
    """
    movies = result.get('movies', {})
    if len(movies) < 2:
        return result

    # Separate orphans (1 version) from groups (2+ versions)
    orphans = {}
    groups = {}
    for key, data in movies.items():
        if len(data.get('versions', [])) <= 1:
            orphans[key] = data
        else:
            groups[key] = data

    if not orphans or not groups:
        return result

    keys_to_delete = set()
    for orphan_key, orphan_data in orphans.items():
        if orphan_key in keys_to_delete:
            continue
        orphan_year = orphan_data.get('year', 0)
        orphan_title = orphan_key.rsplit('|', 1)[0].replace('|', ' ') if '|' in orphan_key else orphan_key
        orphan_words = set(orphan_title.split())
        if not orphan_words:
            continue

        best_target = None
        best_versions = 0

        for group_key, group_data in groups.items():
            if group_data.get('year', 0) != orphan_year:
                continue
            group_title = group_key.rsplit('|', 1)[0].replace('|', ' ') if '|' in group_key else group_key
            group_words = set(group_title.split())

            # Check: orphan's significant words are subset of group's words
            # (or group's words are subset of orphan's — handles reversed dual names)
            sig_orphan = {w for w in orphan_words if len(w) >= 2}
            sig_group = {w for w in group_words if len(w) >= 2}
            if sig_orphan and sig_group and (sig_orphan.issubset(sig_group) or sig_group.issubset(sig_orphan)):
                versions = len(group_data.get('versions', []))
                if versions > best_versions:
                    best_target = group_key
                    best_versions = versions

        if best_target and best_target in movies:
            movies[best_target]['versions'].extend(movies[orphan_key]['versions'])
            movies[best_target]['versions'] = deduplicate_versions(movies[best_target]['versions'])
            movies[best_target]['versions'].sort(
                key=lambda v: int(v.get('size', 0)) if v.get('size') else 0,
                reverse=True)
            keys_to_delete.add(orphan_key)

    for key in keys_to_delete:
        if key in movies:
            del movies[key]

    return result


def _clean_movie_display_name(name):
    """Clean a movie display name: dots→spaces, fix artifacts, fix reversed dual names."""
    cleaned = name
    cleaned = cleaned.replace('.', ' ').replace('_', ' ')
    cleaned = _RE_MULTI_DASH.sub(' ', cleaned)  # Multiple dashes → space

    # Fix reversed dual names: "Something / Main Title" → "Main Title"
    # Keep only the part that looks like a proper title (longer, no parenthesized metadata)
    if ' / ' in cleaned:
        parts = cleaned.split(' / ', 1)
        # Pick the part that is shorter and cleaner (fewer artifacts)
        p0_clean = parts[0].strip().lstrip('(').rstrip(',')
        p1_clean = parts[1].strip().lstrip('(').rstrip(',')
        # If one part is mostly metadata (actors, language codes), use the other
        if len(p0_clean) > 0 and len(p1_clean) > 0:
            # Heuristic: if one part starts with lowercase or has commas (actor list), it's metadata
            p0_meta = p0_clean[0].islower() or p0_clean.count(',') >= 2
            p1_meta = p1_clean[0].islower() or p1_clean.count(',') >= 2
            if p0_meta and not p1_meta:
                cleaned = p1_clean
            elif p1_meta and not p0_meta:
                cleaned = p0_clean

    # Strip leading/trailing separators
    cleaned = re.sub(r'^[\s\-]+', '', cleaned)
    cleaned = re.sub(r'[\s\-]+$', '', cleaned)

    # Remove duplicate words: "Blade -Blade" → "Blade", "Matrix Matrix" → "Matrix"
    words = cleaned.split()
    if len(words) >= 2:
        seen = set()
        deduped = []
        for w in words:
            w_lower = w.lower().strip('-')
            if w_lower not in seen:
                seen.add(w_lower)
                deduped.append(w)
        if deduped:
            cleaned = ' '.join(deduped)

    cleaned = _RE_MULTI_SPACE.sub(' ', cleaned).strip()
    return cleaned


def _pick_cleaner_movie_name(name1, name2):
    """Pick the cleaner movie display name from two candidates."""
    def artifact_score(name):
        """Lower = cleaner."""
        score = 0
        score += name.count('.') * 2
        score += name.count('---') * 3
        score += name.count('_') * 2
        if name.isupper():
            score += 5
        if '|' in name or '/' in name:
            score += 3
        return score

    s1 = artifact_score(name1)
    s2 = artifact_score(name2)
    if s1 <= s2:
        return name1
    return name2


def merge_crossyear_movies(result, max_gap=3):
    """Merge movies with identical title but slightly different years.

    Handles uploader year errors (e.g., "Blade 2|2000" vs "Blade 2|2002").
    Merges into the group with more versions (assumed correct year).
    Only merges when titles match exactly and year gap ≤ max_gap.
    """
    movies = result.get('movies', {})
    if len(movies) < 2:
        return result

    # Build title → [(key, year, version_count)] mapping
    by_title = {}
    for key, data in movies.items():
        year = data.get('year', 0)
        entry = (key, year, len(data.get('versions', [])))
        # Extract title part (before last |year)
        if '|' in key:
            title = key.rsplit('|', 1)[0]
        else:
            title = key
        by_title.setdefault(title, []).append(entry)

    keys_to_delete = set()
    for title, entries in by_title.items():
        if len(entries) < 2:
            continue

        # Sort by version count desc (most versions = likely correct year)
        entries.sort(key=lambda x: -x[2])
        target_key, target_year, _ = entries[0]

        for source_key, source_year, _ in entries[1:]:
            if source_key in keys_to_delete:
                continue
            if abs(target_year - source_year) <= max_gap:
                if target_key in movies and source_key in movies:
                    movies[target_key]['versions'].extend(movies[source_key]['versions'])
                    movies[target_key]['versions'] = deduplicate_versions(movies[target_key]['versions'])
                    movies[target_key]['versions'].sort(
                        key=lambda v: int(v.get('size', 0)) if v.get('size') else 0,
                        reverse=True)
                    log_debug(f'Cross-year merge: "{source_key}" → "{target_key}"')
                    keys_to_delete.add(source_key)

    for key in keys_to_delete:
        if key in movies:
            del movies[key]

    return result


def merge_substring_movies(result):
    """Merge movies where one title is substring of another (same year).

    Example: 'avatar|2009' and '1 avatar|2009' -> merge into 'avatar|2009'
             'avatar 1|2009' and 'avatar|2009' -> merge into 'avatar|2009'

    Args:
        result: Dict with 'movies' key

    Returns:
        Modified result dict with merged movies
    """
    movies = result.get('movies', {})
    if not movies:
        return result

    # Group by year first (only merge within same year)
    by_year = {}
    for key, data in movies.items():
        year = data.get('year')
        if year not in by_year:
            by_year[year] = []
        by_year[year].append(key)

    keys_to_delete = set()
    merges = []  # [(target_key, source_key), ...]

    # Non-significant words for merging same-year edition variants
    # Year grouping already separates different-year releases; this handles
    # same-year variants like "Avatar" vs "Avatar Extended" (both 2009)
    non_significant = {
        # Edition/release variants
        'extended', 'directors', 'cut', 'theatrical', 'remastered',
        'unrated', 'special', 'edition', 'final', 'ultimate', 'dc',
        'collectors', 'anniversary', 'definitive', 'deluxe',
        # Numbering (parts/sequels within same year)
        '1', '2', '3', '4', '5', 'i', 'ii', 'iii', 'iv', 'v',
        # Language/format tags
        'dabing', 'cz', 'sk', 'en', 'de', 'fr', 'titulky', 'sub', 'dub',
        'dubbed', 'subbed', 'multi',
        # Format/container tags (often in Czech file names)
        'avi', 'mkv', 'mp4', '3d', 'hd', 'uhd',
        # Genre tags
        'scifi', 'horror', 'drama', 'comedy', 'action', 'thriller',
        'komedie', 'sportovni', 'zivotopisny', 'novinky',
        # Misc metadata
        'r', '(r', 'dvdrip',
    }

    for year, keys in by_year.items():
        if len(keys) < 2:
            continue

        # Extract title part from key (before |year)
        key_titles = {}
        for key in keys:
            if '|' in key:
                # Handle dual-name keys like 'inception|pocatek|2010'
                parts = key.rsplit('|', 1)  # Split from right to get year
                title_part = parts[0] if len(parts) > 1 else key
            else:
                title_part = key
            key_titles[key] = title_part

        # Find substring relationships
        for i, key1 in enumerate(keys):
            if key1 in keys_to_delete:
                continue
            title1 = key_titles[key1]
            words1 = set(title1.replace('|', ' ').split())

            for key2 in keys[i+1:]:
                if key2 in keys_to_delete:
                    continue
                title2 = key_titles[key2]
                words2 = set(title2.replace('|', ' ').split())

                # Check substring relationship (word-based)
                # Merge if one title's words are subset of another
                # and extra words are non-significant
                if words1.issubset(words2) and len(words1) >= 1:
                    extra_words = words2 - words1
                    if all(w in non_significant or w.isdigit() for w in extra_words):
                        merges.append((key1, key2))
                        keys_to_delete.add(key2)
                elif words2.issubset(words1) and len(words2) >= 1:
                    extra_words = words1 - words2
                    if all(w in non_significant or w.isdigit() for w in extra_words):
                        merges.append((key2, key1))
                        keys_to_delete.add(key1)
                        break  # key1 is now a merge source, don't check more

    # Perform merges
    for target_key, source_key in merges:
        if target_key not in movies or source_key not in movies:
            continue

        # Merge versions
        movies[target_key]['versions'].extend(movies[source_key]['versions'])

        # Deduplicate and re-sort
        movies[target_key]['versions'] = deduplicate_versions(movies[target_key]['versions'])
        movies[target_key]['versions'].sort(
            key=lambda v: int(v.get('size', 0)) if v.get('size') else 0,
            reverse=True
        )

        # Pick shorter/cleaner display name
        target_display = movies[target_key].get('display_name', target_key)
        source_display = movies[source_key].get('display_name', source_key)
        movies[target_key]['display_name'] = _pick_cleaner_movie_name(target_display, source_display)

        log_debug(f'Movie merge: "{source_key}" → "{target_key}"')

    # Delete merged movies
    for key in keys_to_delete:
        if key in movies:
            del movies[key]

    return result


def fetch_and_group_series(token, what, category, sort, limit=500, max_pages=20, cancel_callback=None, first_page_files=None, first_page_total=None):
    """Fetch search results and group by series.

    Args:
        token: WebShare authentication token
        what: Search query
        category: Category filter
        sort: Sort order
        limit: Results per page (default 500)
        max_pages: Maximum pages to fetch (default 20, prevents unbounded fetching)
        cancel_callback: Optional callable returning True to cancel fetching
        first_page_files: Pre-fetched files from first page (avoids double-fetch)
        first_page_total: Total result count from first page response

    Fetches up to max_pages to get episode list.
    """
    all_files = []
    offset = 0
    page = 0

    # Use pre-fetched first page if provided
    if first_page_files is not None:
        all_files.extend(first_page_files)
        if first_page_total is not None and len(first_page_files) >= first_page_total:
            return group_by_series(all_files, token=token, enable_csfd=False, search_query=what) if all_files else None
        offset = len(first_page_files)
        page = 1

    NONE_WHAT = _get_none_what()

    consecutive_short = 0

    while page < max_pages:
        # Check for cancellation
        if cancel_callback and cancel_callback():
            log_debug('fetch_and_group_series: cancelled by callback')
            break

        response = api('search', {
            'what': '' if what == NONE_WHAT else what,
            'category': category,
            'sort': sort,
            'limit': limit,
            'offset': offset,
            'wst': token,
            'maybe_removed': 'true'
        })

        if response is None:
            break

        xml = parse_xml(response.content)
        if not is_ok(xml):
            break

        # Collect files from this page
        page_files = []
        for file in xml.iter('file'):
            item = todict(file)
            page_files.append(item)

        if not page_files:
            break

        all_files.extend(page_files)

        # Early stopping: if pages are returning very few results, stop
        if len(page_files) < limit * 0.1:
            consecutive_short += 1
            if consecutive_short >= 2:
                log_debug('fetch_and_group_series: early stop (diminishing results)')
                break
        else:
            consecutive_short = 0

        # Check if more pages
        try:
            total = int(xml.find('total').text)
        except (AttributeError, ValueError, TypeError):
            break

        if offset + limit >= total:
            break

        offset += limit
        page += 1

    # Group by series and movies
    return group_by_series(all_files, token=token, enable_csfd=False, search_query=what) if all_files else None

