# -*- coding: utf-8 -*-
# Module: grouping
# Author: onykmin
# License: AGPL v.3 https://www.gnu.org/licenses/agpl-3.0.html

import xbmc
import xbmcaddon
from lib.logging import log_debug, log_error, log_warning
from lib.parsing import (parse_episode_info, parse_movie_info,
                         extract_language_tag, extract_dual_names, get_display_name,
                         get_s00e00_pattern, get_0x00_pattern, get_word_set_key,
                         parse_quality_metadata)
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

# Pattern to detect an episode marker (S##E## or ##x##) ANYWHERE for the
# movie-vs-series gate. Permissive about surrounding chars — accepts ()/[]/:/
# etc. wrappers — so a bracketed marker on a file that also carries a year
# ("Westworld 2016 (S01E01)") is still routed to series parsing (#1).
import re
_PATTERN_EPISODE_MARKER = re.compile(
    r'(?<![A-Za-z0-9])(?:[Ss]\d{1,2}[Ee]\d{1,3}|\d{1,2}x\d{1,3})(?![A-Za-z0-9])')

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


def _dual_canonical(name1, name2):
    """Build (canonical_key, display_name) from a dual-name pair.

    Uses csfd_scraper.create_canonical_from_dual_names when available, else
    falls back to the same core algorithm (clean both, substring→longer,
    otherwise pipe-join sorted) so a series does not split in two merely
    because the optional csfd module is absent (audit finding #18). The keys
    track csfd's output but are not guaranteed byte-identical if csfd's
    cleaning ever diverges from clean_series_name; the goal is stable grouping
    within a single run (the chosen backend does not change mid-run). Returns
    (None, None) when the pair is not a usable dual name.
    """
    from lib.parsing import clean_series_name
    if DUAL_NAMES_AVAILABLE:
        try:
            r = create_canonical_from_dual_names(name1, name2)
            if r:
                return r.get('canonical_key'), r.get('display_name')
            return None, None
        except Exception as e:
            log_error(f'Dual names processing error: {e}')
            # fall through to the deterministic fallback
    c1 = clean_series_name(name1)
    c2 = clean_series_name(name2)
    if not c1 or not c2 or c1 == c2:
        return None, None
    if c1 in c2:
        return c2, name2
    if c2 in c1:
        return c1, name1
    return '|'.join(sorted([c1, c2])), '{} / {}'.format(name1, name2)


def _safe_size(v):
    """Parse a file dict's 'size' into an int, tolerating bad API data.

    'size' comes verbatim from the Webshare XML via todict(); it may be a
    non-numeric string, a list (duplicated <size> tags), None, or absent.
    Returns 0 for anything unparseable so version sorts never crash the
    whole grouping pass.
    """
    s = v.get('size') if isinstance(v, dict) else v
    if isinstance(s, (list, tuple)):
        s = s[0] if s else None
    if s is None:
        return 0
    try:
        return int(str(s).strip())
    except (ValueError, TypeError):
        return 0


def _version_sort_key(v):
    """Sort key for a version: (quality_score, size), used with reverse=True
    so higher quality wins and size breaks ties.

    quality_score is derived from the filename via parse_quality_metadata. The
    result is CACHED on the version dict under 'quality_meta' the first time it
    is computed, so the many re-sorts across the grouping/merge passes do not
    re-run the parse for the same file (audit round-2 #7/#34 — the cache it
    checked was never populated, so every sort re-parsed). series_ui later reads
    the same 'quality_meta' field, so populating it here is purely beneficial.
    """
    if not isinstance(v, dict):
        return (50, 0)
    meta = v.get('quality_meta')
    if not isinstance(meta, dict):
        try:
            meta = parse_quality_metadata(v.get('name', '') or '')
        except Exception:
            meta = {'quality_score': 50}
        v['quality_meta'] = meta
    score = meta.get('quality_score', 50)
    return (score, _safe_size(v))

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

    def _acronyms(words):
        # Join maximal runs of single-character tokens so a dotted acronym
        # ("C.S.I." -> c,s,i) matches the query "csi" — without matching "her"
        # inside "mother" (which is a single multi-char token, no letter run).
        out, run = set(), []
        for w in words:
            if len(w) == 1:
                run.append(w)
            else:
                if len(run) >= 2:
                    out.add(''.join(run))
                run = []
        if len(run) >= 2:
            out.add(''.join(run))
        return out

    def _matches(stem, words, acronyms):
        # Token-level match (word equality, word-prefix, or acronym). Avoids the
        # substring false-KEEP ("her" in "mother") while fixing the punctuation
        # false-DROP ("csi" vs "C.S.I."). Prefix is anchored at the WORD START,
        # so a 3-char query ("man") still matches "Manifest" without re-opening
        # the "her" in "mother" hole — "mother" does not start with "her"
        # (audit round-2 #6 — short-query prefix matches were being dropped).
        for w in words:
            if w == stem or (len(stem) >= 3 and w.startswith(stem)):
                return True
        return stem in acronyms

    filtered = []
    for f in files:
        name = f.get('name', '')
        # Strip leading bracket tags (fansub/release groups like "[Blade]", "(Lena)")
        # so they don't false-match the query
        stripped = re.sub(r'^[\(\[][^\)\]]*[\)\]]\s*', '', name)
        folded = _unidecode_filter(stripped).lower()
        # Tokenize on any non-alphanumeric run ("c.s.i. new york" -> c,s,i,new,york)
        words = [w for w in re.split(r'[^a-z0-9]+', folded) if w]
        acronyms = _acronyms(words)
        if any(_matches(s, words, acronyms) for s in stems):
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
                # Defer the spinoff guard to merge time (it depends on episode
                # counts that change as merges happen — #22). Record the extra
                # words so the guard can be re-evaluated then.
                extra_words = long_words - short_words
                keys_to_merge.append((short_key, long_key, extra_words))

    # Snapshot episode counts BEFORE any merge runs. The spinoff guard below
    # must see each group's ORIGINAL episode count; reading the live
    # total_episodes makes the decision depend on merge order, because an
    # earlier merge into `short_key` inflates the count that a later guard reads
    # (audit round-2 #4/#11 — order-dependent merge decisions).
    eps_snapshot = {k: series[k].get('total_episodes', 0) for k in series}

    # Perform merges
    for short_key, long_key, extra_words in keys_to_merge:
        if short_key not in series or long_key not in series:
            continue

        # Spinoff protection against the PRE-MERGE counts: if both groups had
        # significant episodes and the extra words are short (likely sequel/
        # spinoff markers like Z, GT, Super), they are distinct series.
        short_eps = eps_snapshot.get(short_key, 0)
        long_eps = eps_snapshot.get(long_key, 0)
        if min(short_eps, long_eps) >= 3 and all(len(w) <= 5 for w in extra_words):
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

        # Deterministic target so the surviving canonical_key does NOT depend on
        # the order files arrived from the API (#20). Prefer the key with the
        # most episodes (richest group), tie-break lexicographically.
        target = max(keys, key=lambda k: (series[k]['total_episodes'], k))
        sources = [k for k in keys if k != target]
        for source in sources:
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


def _strip_display_metadata(name, strip_trailing_num):
    """Strip filename metadata (extension, quality/source/codec/language tags,
    bracketed release/year tags, episode markers, separators) from a name.

    The single shared cleaning pipeline behind both display-name passes (audit
    round-2 #13/#28 — the two were near-identical copies). The ONLY difference
    is `strip_trailing_num`:
      - True  -> GROUPING-vote key: also strips a trailing number so different
                 encodings of one title vote together. NOT shown to the user.
      - False -> USER-FACING string: KEEPS title numbers (sequel/season numbers
                 and number-titles like "Cobra Kai 3", "The 4400",
                 "Blade Runner 2049") so the displayed title stays faithful
                 (#8/#26/#3) while still dropping "1080p BluRay" noise.
    """
    cleaned = _RE_FILE_EXT.sub('', name)
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
    if strip_trailing_num:
        cleaned = _RE_TRAILING_NUM.sub('', cleaned)
    cleaned = _RE_SE_MARKER.sub('', cleaned)
    cleaned = _RE_NxN_MARKER.sub('', cleaned)
    cleaned = _RE_TRAILING_SEP.sub('', cleaned)
    cleaned = _RE_MULTI_SPACE.sub(' ', cleaned)
    return cleaned.strip()


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
        return _strip_display_metadata(name, strip_trailing_num=True)

    def _light_clean(name):
        return _strip_display_metadata(name, strip_trailing_num=False)

    # Vote on the heavily-cleaned form (groups encodings of one title), but
    # remember a representative ORIGINAL for each so we can return a faithful
    # display string rather than the stripped vote key.
    from collections import Counter
    cleaned_list = [clean_name(n) for n in names]
    cleaned_counts = Counter(c for c in cleaned_list if c and len(c) >= 2)
    rep_original = {}  # cleaned -> first original that produced it
    for orig, c in zip(names, cleaned_list):
        if c and len(c) >= 2 and c not in rep_original:
            rep_original[c] = orig

    if not cleaned_counts:
        # Every candidate cleaned to nothing usable — fall back to the lightly
        # cleaned first candidate, not the raw filename (#29).
        return _light_clean(names[0]) or names[0]

    # Sort by: count (desc), then length (asc), then alphabetically
    sorted_names = sorted(
        cleaned_counts.items(),
        key=lambda x: (-x[1], len(x[0]), x[0])
    )
    best_cleaned = sorted_names[0][0]

    # Return a faithful, lightly-cleaned ORIGINAL for the winning group.
    display = _light_clean(rep_original.get(best_cleaned, best_cleaned))
    if not display:
        display = best_cleaned
    log_debug(f'Name picker: "{display}" (group "{best_cleaned}" x{sorted_names[0][1]} of {len(names)})')
    return display


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

        # Primary: by ident (valid, non-'unknown'). A distinct ident is a
        # distinct file — do NOT fall through to the name+size check, or two
        # genuine mirrors of the same scene release (same name+size, different
        # ident) would be collapsed and a live copy dropped for a dead one.
        ident = v.get('ident')
        has_ident = bool(ident) and ident != 'unknown'
        if has_ident:
            if ident in seen_idents:
                is_duplicate = True
            else:
                seen_idents.add(ident)
        else:
            # Fallback only when ident is absent/unknown: dedup by name+size,
            # or by name alone when size is missing. Sizes are normalized to a
            # hashable int (a list/garbage size never raises here).
            name = v.get('name')
            if name:
                key = (name, _safe_size(v))
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
    xbmc.log(f'[yeplaya] group_by_series: Processing {len(files)} files', xbmc.LOGDEBUG)

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

        # Try episode parsing when it's not a movie, OR when the filename has a
        # genuine episode marker even alongside a year ("Series 2016 (S01E01)").
        # Use the parsing S##E##/##x## patterns (which accept ()/[] wrappers) —
        # the old local _PATTERN_EPISODE_MARKER only matched _ space . - , and
        # silently misrouted bracketed-marker episodes to movies (#1).
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
                if dual_names:
                    dual_ck, dual_dn = _dual_canonical(dual_names[0], dual_names[1])
                    if dual_ck:
                        canonical_key = dual_ck
                        if dual_dn:
                            display_name = dual_dn
                        log_debug(f'Dual names detected: {dual_names[0]} / {dual_names[1]}')

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
            file_dict['series_name'] = canonical_key

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
                # Deduplicate versions (final cleanup). Sorting is deferred to
                # the single post-merge pass below — sorting here too would just
                # be redone after merges (audit round-2 #8/#19 — double sort).
                series_data['seasons'][season_num][ep_num] = deduplicate_versions(versions)

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
                    key=_version_sort_key,
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

            # Update non_series to exclude grouped movies. Use .get('ident')
            # throughout: a file with no <ident> (removed/edge entries under
            # maybe_removed) must not abort the whole exclusion step (which
            # would leave grouped movies duplicated in the flat list).
            grouped_movie_idents = set()
            for movie_data in movies_result['movies'].values():
                for version in movie_data['versions']:
                    ident = version.get('ident')
                    if ident:
                        grouped_movie_idents.add(ident)

            result['non_series'] = [
                f for f in result['non_series']
                if f.get('ident') not in grouped_movie_idents
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
        movie_info = parse_movie_info(file_dict.get('name', ''))

        if not movie_info:
            continue  # Not a movie pattern

        # Create canonical key: "title|year"
        canonical_key = f"{movie_info['title']}|{movie_info['year']}"

        # Handle dual names (deterministic regardless of csfd availability).
        display_name = movie_info['raw_title']
        if movie_info['dual_names']:
            dual_ck, dual_dn = _dual_canonical(
                movie_info['dual_names'][0], movie_info['dual_names'][1])
            if dual_ck:
                canonical_key = f"{dual_ck}|{movie_info['year']}"
                if dual_dn:
                    display_name = dual_dn

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
            key=_version_sort_key,
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


def _finalize_merged_versions(movies, target_keys, keys_to_delete):
    """Dedup + quality-sort each merge target's versions exactly once.

    Movie merges extend a target's version list possibly many times (one source
    at a time). Doing the dedup+sort inside that inner loop is O(k^2) over the
    growing list and re-parses quality metadata each pass; instead the merge
    loops collect their touched targets and call this once afterwards (audit
    round-2 #9/#27). Skips targets that were themselves merged away.
    """
    for key in target_keys:
        if key in keys_to_delete or key not in movies:
            continue
        versions = deduplicate_versions(movies[key].get('versions', []))
        versions.sort(key=_version_sort_key, reverse=True)
        movies[key]['versions'] = versions


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
    touched_targets = set()
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
            # Extend only; dedup+sort once per target after the loops (#9).
            movies[target]['versions'].extend(movies[dual_key]['versions'])
            touched_targets.add(target)
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
                touched_targets.add(target)
                log_debug(f'Spaceless movie merge: "{key}" → "{target}"')
                keys_to_delete.add(key)

    _finalize_merged_versions(movies, touched_targets, keys_to_delete)

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
    touched_targets = set()
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
            # Require ≥2 significant words to prevent single-word false matches
            # like "Fast" (1v) merging into "Fast and Furious" (2v)
            sig_orphan = {w for w in orphan_words if len(w) >= 2}
            sig_group = {w for w in group_words if len(w) >= 2}
            if len(sig_orphan) >= 2 and sig_orphan.issubset(sig_group):
                versions = len(group_data.get('versions', []))
                if versions > best_versions:
                    best_target = group_key
                    best_versions = versions

        if best_target and best_target in movies:
            # Extend only; dedup+sort once per target after the loop (#9).
            movies[best_target]['versions'].extend(movies[orphan_key]['versions'])
            touched_targets.add(best_target)
            keys_to_delete.add(orphan_key)

    _finalize_merged_versions(movies, touched_targets, keys_to_delete)

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

    # Remove only consecutive duplicate words: "Blade -Blade" → "Blade", "Matrix Matrix" → "Matrix"
    # Preserves non-consecutive: "Run Lola Run", "New York New York", "Sing Sing"
    words = cleaned.split()
    if len(words) >= 2:
        deduped = [words[0]]
        for w in words[1:]:
            if w.lower().strip('-') != deduped[-1].lower().strip('-'):
                deduped.append(w)
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
    touched_targets = set()
    for title, entries in by_title.items():
        if len(entries) < 2:
            continue

        # Sort by version count desc (most versions = likely correct year)
        entries.sort(key=lambda x: -x[2])
        target_key, target_year, _ = entries[0]

        for source_key, source_year, source_versions in entries[1:]:
            if source_key in keys_to_delete:
                continue
            if abs(target_year - source_year) <= max_gap:
                # Don't merge if both have significant version counts and aren't
                # hugely lopsided (both likely legitimate movies).
                # Skip: min >= 3 AND ratio >= 1:4 (e.g., 8v vs 10v = real).
                # Allow: 2v vs 30v = lopsided, likely year error.
                target_versions = len(movies[target_key].get('versions', []))
                smaller = min(target_versions, source_versions)
                larger = max(target_versions, source_versions)
                if smaller >= 3 and smaller * 4 >= larger:
                    continue
                if target_key in movies and source_key in movies:
                    # Extend only; defer the dedup+sort to one pass per target
                    # after the loop (audit round-2 #9 — was O(k^2) re-dedup and
                    # re-sort of the whole growing list on every absorbed source).
                    movies[target_key]['versions'].extend(movies[source_key]['versions'])
                    touched_targets.add(target_key)
                    log_debug(f'Cross-year merge: "{source_key}" → "{target_key}"')
                    keys_to_delete.add(source_key)

    _finalize_merged_versions(movies, touched_targets, keys_to_delete)

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
        # Czech genre tags (only appear as metadata, never in titles)
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
    touched_targets = set()
    for target_key, source_key in merges:
        if target_key not in movies or source_key not in movies:
            continue

        # Merge versions (extend only; dedup+sort once per target after the
        # loop — a target can absorb several sources, audit round-2 #9).
        movies[target_key]['versions'].extend(movies[source_key]['versions'])
        touched_targets.add(target_key)

        # Pick shorter/cleaner display name
        target_display = movies[target_key].get('display_name', target_key)
        source_display = movies[source_key].get('display_name', source_key)
        movies[target_key]['display_name'] = _pick_cleaner_movie_name(target_display, source_display)

        log_debug(f'Movie merge: "{source_key}" → "{target_key}"')

    _finalize_merged_versions(movies, touched_targets, keys_to_delete)

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

    NONE_WHAT = _get_none_what()
    # Relevance filtering is meaningless for the browse sentinel — pass '' so
    # group_by_series does not run _filter_irrelevant against the literal
    # '%#NONE#%' token (wasted work; would drop everything but for a fallback).
    filter_query = '' if what == NONE_WHAT else what

    # Use pre-fetched first page if provided
    if first_page_files is not None:
        all_files.extend(first_page_files)
        if first_page_total is not None and len(first_page_files) >= first_page_total:
            return group_by_series(all_files, token=token, enable_csfd=False, search_query=filter_query) if all_files else None
        offset = len(first_page_files)
        page = 1

    consecutive_short = 0
    # True once the fetch stopped for a NATURAL/error reason (reached the
    # reported total, empty/short pages, cancellation, API error) rather than
    # by hitting the page cap. Used to suppress a spurious truncation warning
    # on a clean, complete fetch that happened to use the last allowed page
    # (audit round-2 #12 — warning fired even when nothing was truncated).
    reached_end = False

    while page < max_pages:
        # Check for cancellation
        if cancel_callback and cancel_callback():
            log_debug('fetch_and_group_series: cancelled by callback')
            reached_end = True
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
            reached_end = True
            break

        xml = parse_xml(response.content)
        if not is_ok(xml):
            reached_end = True
            break

        # Collect files from this page
        page_files = []
        for file in xml.iter('file'):
            item = todict(file)
            page_files.append(item)

        if not page_files:
            reached_end = True
            break

        all_files.extend(page_files)

        # Read the server's total result count.
        try:
            total = int(xml.find('total').text)
        except (AttributeError, ValueError, TypeError):
            total = None

        # Advance by the ACTUAL number of files returned, not by `limit`. The
        # server may hand back a short page mid-stream; advancing by `limit`
        # would skip the unreturned [len(page_files), limit) slice (#10).
        offset += len(page_files)
        page += 1

        # Done when we've reached the reported total.
        if total is not None and offset >= total:
            reached_end = True
            break

        # Runaway guard (NOT the old aggressive <10% early-stop, which dropped
        # legitimate mid-stream short pages — #11): only stop early if several
        # consecutive pages are essentially empty AND we have no total to trust.
        if len(page_files) < 5:
            consecutive_short += 1
            if consecutive_short >= 3 and total is None:
                log_debug('fetch_and_group_series: stop (tiny pages, no total)')
                reached_end = True
                break
        else:
            consecutive_short = 0

    # Warn ONLY when the page cap actually truncated a larger result set — i.e.
    # the loop exited because it ran out of allowed pages, not because the fetch
    # completed naturally (audit round-2 #12 — was warning on every clean fetch
    # that reached the last allowed page).
    if page >= max_pages and not reached_end:
        log_warning('fetch_and_group_series: hit max_pages={} cap at {} files; '
                    'results may be incomplete'.format(max_pages, len(all_files)))

    # Group by series and movies
    return group_by_series(all_files, token=token, enable_csfd=False, search_query=filter_query) if all_files else None

