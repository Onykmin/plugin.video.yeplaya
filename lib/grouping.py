# -*- coding: utf-8 -*-
# Module: grouping
# Author: onykmin
# License: AGPL v.3 https://www.gnu.org/licenses/agpl-3.0.html

import xbmc
import xbmcaddon
from lib.logging import log_debug, log_error
from lib.parsing import (parse_episode_info, parse_movie_info, parse_quality_metadata,
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
import re
_PATTERN_EPISODE_MARKER = re.compile(r'\b[Ss]\d{1,2}[Ee]\d{1,3}\b')


def merge_substring_series(grouped):
    """Merge series where one canonical key is substring of another.

    Example: "south park" and "mestecko south park" → merge into "south park"

    Merge criteria:
    - One key is substring of other (word boundaries)
    - ALL words from shorter key appear in longer key
    - At least 2 common words (avoids "Lost" vs "Lost Girl")

    Args:
        grouped: Dict with 'series' and 'non_series' keys

    Returns:
        Modified grouped dict with merged series
    """
    series = grouped['series']
    keys_to_merge = []  # [(shorter_key, longer_key), ...]

    # Find merge candidates
    keys_list = list(series.keys())
    for i, key1 in enumerate(keys_list):
        for key2 in keys_list[i+1:]:
            # Check both directions
            if key1 in key2:
                shorter, longer = key1, key2
            elif key2 in key1:
                shorter, longer = key2, key1
            else:
                continue

            # Validate merge criteria
            words_short = set(shorter.split())
            words_long = set(longer.split())

            # Merge if all shorter words in longer (substring match)
            # Examples: "penguin" ⊂ "tucnak penguin", "office" ⊂ "office us"
            if words_short.issubset(words_long):
                keys_to_merge.append((shorter, longer))

    # Perform merges
    for short_key, long_key in keys_to_merge:
        if short_key not in series or long_key not in series:
            continue  # Already merged

        # Merge season data from long into short
        merge_season_data(series[short_key], series[long_key])

        # Pick best display name
        short_display = series[short_key].get('display_name', short_key.title())
        long_display = series[long_key].get('display_name', long_key.title())

        series[short_key]['display_name'] = pick_best_display_name(short_display, long_display)

        # Remove long_key series
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


def pick_best_display_name_from_list(names):
    """Pick best display name from a list of candidates.

    Strategy: Clean all names aggressively, then pick shortest unique name.

    Args:
        names: List of candidate names

    Returns:
        Best name choice
    """
    import re

    if not names:
        return None

    def clean_name(name):
        """Aggressively clean a display name."""
        cleaned = name

        # Remove file extensions
        cleaned = re.sub(r'\.(mkv|mp4|avi|rar|zip|7z|ts|iso|m4v|flac|mp3)$', '', cleaned, flags=re.IGNORECASE)

        # Remove quality markers
        cleaned = re.sub(r'\b(480p|720p|1080p|2160p|4K|UHD|FHD|HD)\b', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\b(BluRay|Blu-ray|WEB-DL|WEBDL|WEBRip|HDTV|BRRip|DVDRip|REMUX|Theatrical)\b', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\b(x264|x265|H\.?264|H\.?265|HEVC|XviD|AAC|AC3|DTS|DD5\.1|Atmos|TrueHD)\b', '', cleaned, flags=re.IGNORECASE)

        # Remove language/subtitle markers
        cleaned = re.sub(r'\b(CZ|EN|SK|MULTi)\s+(DABING|dabing|TITULKY|titulky|sub|dub)\b', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s+(CZ|EN|SK)\b', '', cleaned, flags=re.IGNORECASE)

        # Remove release groups in brackets/parens at end
        cleaned = re.sub(r'\s*[\(\[][^\)\]]{0,40}[\)\]]$', '', cleaned)

        # Remove episode/season numbers at end: "- 01", "20 serie", "03. série", etc.
        cleaned = re.sub(r'[-\s]+\d{1,3}(?:\.\d+)?(\s+(serie|série|season|sezona|disk))?\s*(dab|BEZ HESLA)?$', '', cleaned, flags=re.IGNORECASE)

        # Remove season/episode markers
        cleaned = re.sub(r'\s*[Ss]\d{1,2}[Ee]\d{1,3}.*$', '', cleaned)
        cleaned = re.sub(r'\s*\d{1,2}x\d{1,3}.*$', '', cleaned)

        # Remove trailing separators and clean whitespace
        cleaned = re.sub(r'[\s\-_\.]+$', '', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned)

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
                    # New episode - copy versions
                    target['seasons'][season_num][ep_num] = source['seasons'][season_num][ep_num]
                else:
                    # Episode exists in both - merge versions
                    target['seasons'][season_num][ep_num].extend(source['seasons'][season_num][ep_num])

                    # Deduplicate after merge
                    target['seasons'][season_num][ep_num] = deduplicate_versions(
                        target['seasons'][season_num][ep_num]
                    )

                    # Re-sort by size
                    target['seasons'][season_num][ep_num].sort(
                        key=lambda v: int(v.get('size', 0)) if v.get('size') else 0,
                        reverse=True
                    )

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


def group_by_series(files, token=None, enable_csfd=True):
    """Group file list by series, movies, and deduplicate.

    Args:
        files: List of file dicts
        token: WebShare token for CSFD enrichment
        enable_csfd: Enable CSFD metadata lookup

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

            # Parse quality metadata for ranking
            file_dict['quality_meta'] = parse_quality_metadata(filename)

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

    # Group remaining files as movies (if setting enabled)
    try:
        group_movies_enabled = _addon.getSettingBool('group_movies')
    except:
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
            words1 = set(title1.split())

            for key2 in keys[i+1:]:
                if key2 in keys_to_delete:
                    continue
                title2 = key_titles[key2]
                words2 = set(title2.split())

                # Check substring relationship (word-based)
                # Merge if one title's words are subset of another
                if words1.issubset(words2) and len(words1) >= 1:
                    # title1 is shorter/simpler -> merge title2 into title1
                    merges.append((key1, key2))
                    keys_to_delete.add(key2)
                elif words2.issubset(words1) and len(words2) >= 1:
                    # title2 is shorter/simpler -> merge title1 into title2
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
        if len(source_display) < len(target_display) and not any(c in source_display for c in '|/'):
            movies[target_key]['display_name'] = source_display

        log_debug(f'Movie merge: "{source_key}" → "{target_key}"')

    # Delete merged movies
    for key in keys_to_delete:
        if key in movies:
            del movies[key]

    return result


def fetch_and_group_series(token, what, category, sort, limit=500, max_pages=20, cancel_callback=None):
    """Fetch search results and group by series.

    Args:
        token: WebShare authentication token
        what: Search query
        category: Category filter
        sort: Sort order
        limit: Results per page (default 500)
        max_pages: Maximum pages to fetch (default 20, prevents unbounded fetching)
        cancel_callback: Optional callable returning True to cancel fetching

    Fetches up to max_pages to get episode list.
    """
    all_files = []
    offset = 0
    page = 0

    NONE_WHAT = _get_none_what()

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
    return group_by_series(all_files, token=token, enable_csfd=False) if all_files else None

