# -*- coding: utf-8 -*-
# Module: grouping
# Author: onykmin
# License: AGPL v.3 https://www.gnu.org/licenses/agpl-3.0.html

import itertools
import re

import xbmc
import xbmcaddon
from lib.logging import log_debug, log_error, log_warning
from lib.parsing import (clean_series_name, parse_episode_info, parse_movie_info,
                         extract_language_tag, extract_dual_names, get_display_name,
                         match_episode_marker, EPISODE_MARKER_ANYWHERE, LEGACY_EPISODE_MARKER_ANYWHERE,
                         extract_season_from_text, apply_season_readings,
                         get_word_set_key, legacy_site_prefix_key, parse_quality_metadata,
                         strip_site_prefix)
from lib.api import api, parse_xml, is_ok
from lib.utils import todict

# NONE_WHAT lives in lib.keys (single source of truth); keys has no
# intra-package imports so this top-level import cannot cause a cycle.
from lib.keys import NONE_WHAT, alias_keys, normalize_series_key, normalize_movie_key

_addon = xbmcaddon.Addon()

# Check if dual names available
try:
    from csfd_scraper import create_canonical_from_dual_names, format_display_name
    DUAL_NAMES_AVAILABLE = True
except ImportError:
    DUAL_NAMES_AVAILABLE = False

# "Alias (Original) - 10": the name part of an absolute-numbered file whose
# name ends in a bracketed second name (extract_dual_names rejects years/tags).
_PATTERN_ABSOLUTE_ALIAS = re.compile(
    r'^(.+?\s*[\(\[][^\)\]]+[\)\]])\s*-\s*(?:ep?\.?\s*)?\d{1,3}(?!\d)', re.IGNORECASE)

# Compiled patterns for display name cleaning (used in pick_best_display_name_from_list)
_RE_FILE_EXT = re.compile(r'\.(mkv|mp4|avi|rar|zip|7z|ts|iso|m4v|flac|mp3)$', re.IGNORECASE)
_RE_QUALITY = re.compile(r'\b(480p|720p|1080p|2160p|4K|UHD|FHD|HD)\b', re.IGNORECASE)
_RE_SOURCE = re.compile(r'\b(BluRay|Blu-ray|WEB-DL|WEBDL|WEBRip|HDTV|BRRip|DVDRip|REMUX|Theatrical)\b', re.IGNORECASE)
_RE_CODEC = re.compile(r'\b(x264|x265|H\.?264|H\.?265|HEVC|XviD|AAC|AC3|DTS|DD5\.1|Atmos|TrueHD)\b', re.IGNORECASE)
_RE_LANG_LABEL = re.compile(r'\b(CZ|EN|SK|MULTi)\s+(DABING|dabing|TITULKY|titulky|sub|dub)\b', re.IGNORECASE)
_RE_LANG_CODE = re.compile(r'\s+(CZ|EN|SK)\b', re.IGNORECASE)
_RE_INNER_HYPHEN = re.compile(r'(?<=\w)-(?=\w)')
_RE_DANGLING_HYPHEN = re.compile(r'(?<=\w)-(?=\s|$)')
_RE_LEADING_HYPHEN = re.compile(r'(?:^|\s)-\w')
_RE_LANG_CODE_TAIL = re.compile(r'\s+(CZ|EN|SK)$', re.IGNORECASE)
_RE_UNCLOSED_TAIL = re.compile(r'\s*[\(\[](?![^\)\]]*[^\W\d_]{2})[^\)\]]*$')
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

    The one dual-key algorithm: clean both names like every series key
    (clean_series_name), a name inside the other gives the longer one,
    otherwise the two are pipe-joined sorted. The key never depends on whether
    csfd_scraper is importable; csfd only words the display name. Returns
    (None, None) when the pair is not a usable dual name.
    """
    c1 = clean_series_name(name1)
    c2 = clean_series_name(name2)
    if not c1 or not c2 or c1 == c2:
        return None, None
    if c1 in c2:
        return c2, name2
    if c2 in c1:
        return c1, name1
    display = format_display_name(name1, name2) if DUAL_NAMES_AVAILABLE else '{} / {}'.format(name1, name2)
    return '|'.join(sorted([c1, c2])), display


def _legacy_dual_key(name1, name2):
    """The key csfd_scraper's own cleaning built for this pair before dual keys shared
    clean_series_name ("penguin, the|tucnak", "star wars ii|..."), else None. Rows
    stored under it resolve through the group's aliases."""
    if not DUAL_NAMES_AVAILABLE:
        return None
    try:
        found = create_canonical_from_dual_names(name1, name2)
    except Exception as e:
        log_error(f'Dual names processing error: {e}')
        return None
    return found.get('canonical_key') if found else None


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
        # Parse via float so a decimal-form byte string ("1685758999.0")
        # ranks correctly. int(str(s)) raised ValueError on those and returned
        # 0, collapsing the sort key so the version list ended up unsorted even
        # though sizelize() (which uses float()) still rendered the size label.
        return int(float(str(s).strip()))
    except (ValueError, TypeError):
        return 0


def _version_sort_key(v):
    """Sort key for a version: (quality_score, size, ident), used with reverse=True
    so higher quality wins, size breaks ties and ident makes the order independent
    of input order (mirrors with equal name+size are kept, policy: distinct idents).

    quality_score is derived from the filename via parse_quality_metadata. The
    result is CACHED on the version dict under 'quality_meta' the first time it
    is computed, so the many re-sorts across the grouping/merge passes do not
    re-run the parse for the same file (audit round-2 #7/#34 — the cache it
    checked was never populated, so every sort re-parsed). series_ui later reads
    the same 'quality_meta' field, so populating it here is purely beneficial.
    """
    if not isinstance(v, dict):
        return (50, 0, '')
    meta = v.get('quality_meta')
    if not isinstance(meta, dict):
        try:
            meta = parse_quality_metadata(v.get('name', '') or '')
        except Exception:
            meta = {'quality_score': 50}
        v['quality_meta'] = meta
    score = meta.get('quality_score', 50)
    return (score, _safe_size(v), str(v.get('ident') or ''))

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
        # A title glued to an upload counter ("1Dune") also matches as "dune".
        words += [re.sub(r'^\d+', '', w) for w in words if re.match(r'\d+[a-z]', w)]
        if any(_matches(s, words, acronyms) for s in stems):
            filtered.append(f)

    dropped = len(files) - len(filtered)
    if dropped > 0:
        log_debug(f'Relevance filter: dropped {dropped}/{len(files)} files (no query word match)')

    return filtered if filtered else files


def _merge_roots(edges, order):
    """{loser: survivor} for directed (loser, winner) pairs: a loser joins the
    best-ordered winner offered to it (order(k) smaller = better, total because
    keys are unique), and a winner that is itself a loser leads on to its own
    winner. A loser offered two unrelated winners joins only one, so the result
    does not depend on the order the pairs or keys arrive in."""
    parent = {}
    for lo, hi in edges:
        if lo not in parent or order(hi) < order(parent[lo]):
            parent[lo] = hi

    def root(k):
        path = []
        while k in parent and k not in path:
            path.append(k)
            k = parent[k]
        # a chain that loops back (reachable only via dual-name keys): the
        # smallest key on the loop leads
        return min(path[path.index(k):]) if k in path else k
    roots = {k: root(k) for k in parent}
    return {k: r for k, r in roots.items() if k != r}


def _carry_aliases(target, source_key, source):
    """Record that `source_key` (and everything already merged into it) is now
    part of `target`: any of them may have been a user's stored key."""
    target.setdefault('aliases', []).extend([source_key] + source.get('aliases', []))


def _merge_to_fixpoint(result, bucket, passes):
    """Run the merge passes in order, again and again until a round leaves the
    group keys unchanged. Every merge removes a group, so this terminates."""
    while True:
        before = set(result[bucket])
        for merge in passes:
            result = merge(result)
        if set(result[bucket]) == before:
            return result


def _carry_dual_name_aliases(series):
    """A dual key ("starcom|u s space force") also answers to each of its names:
    rows stored before the name pair was known sit under one of them. A name is
    skipped when another group holds it as its key or in a dual key of its own
    (a franchise stub, or one name shared by two shows): it would be ambiguous."""
    claims = {}
    for key in series:
        for name in set(key.split('|')) if '|' in key else ():
            claims[name] = claims.get(name, 0) + 1
    for key, group in series.items():
        if '|' in key:
            group.setdefault('aliases', []).extend(
                n for n in key.split('|') if n not in series and claims[n] == 1)


def _separate_colliding_identities(series):
    """Give dual groups of different shows distinct state identities.

    A group's playback state and favorite sit under its identity, the LAST `|`
    segment of its key (keys.normalize_series_key). "odboj|star wars" and
    "povstalci|star wars" (and the plain "star wars") all read "star wars": one
    show's S01E01 would mark the others'. Groups that share an identity AND hold
    different uploads at the same episodes (_only_collisions) are different shows:
    each dual one moves its own name (a part no other key mentions) to the end.
    The old key stays an alias. No such name: the key is left as it is.
    """
    by_identity = {}
    for key in series:
        by_identity.setdefault(normalize_series_key(key), []).append(key)
    mentioned = {}
    for key in series:
        for part in key.split('|'):
            mentioned[part] = mentioned.get(part, 0) + 1
    coords = {k: _coord_sizes(g) for k, g in series.items()}
    for keys in by_identity.values():
        for key in sorted(keys):
            if '|' not in key or not any(_only_collisions(coords[key], coords[o]) for o in keys if o != key):
                continue
            parts = key.split('|')
            own = [p for p in parts[:-1] if mentioned[p] == 1]
            if own:
                new_key = '|'.join([p for p in parts if p != own[0]] + [own[0]])
                series[new_key] = series.pop(key)
                series[new_key].setdefault('aliases', []).append(key)


def _owned_elsewhere(series):
    """Predicate (group key, old key): the old key's identity is that of another
    show (a group holding other uploads at the same episodes), so rows stored
    under it belong to that group, not to this one."""
    holders = {}
    for key in series:
        holders.setdefault(normalize_series_key(key), []).append(key)
    coords = {k: _coord_sizes(g) for k, g in series.items()}

    def owned_elsewhere(key, old):
        identity = normalize_series_key(old)
        return identity != normalize_series_key(key) and any(
            _only_collisions(coords[key], coords[o]) for o in holders.get(identity, ()))
    return owned_elsewhere


def _finalize_aliases(groups, normalize, owned_elsewhere=None):
    """Every group exposes `aliases` (sorted list; see keys.alias_keys), minus
    any `owned_elsewhere(group key, alias)`."""
    for key, group in groups.items():
        group['aliases'] = [a for a in alias_keys(key, group.get('aliases', ()), normalize)
                            if not (owned_elsewhere and owned_elsewhere(key, a))]


def _series_order(series, longer_wins=False):
    """Survivor order: most episodes, then most files, then (typo variants only,
    `longer_wins`: a typo is usually a truncation) the longer key, then the key
    itself. Snapshot of the groups before the pass so earlier merges of the same
    pass cannot change the decision."""
    size = {k: (-v.get('total_episodes', 0),
                -sum(len(vs) for eps in v['seasons'].values() for vs in eps.values()))
            for k, v in series.items()}
    return lambda k: (size[k][0], size[k][1], -len(k) if longer_wins else 0, k)


# Content evidence for merges. A coordinate is (season, episode); one file size
# at a coordinate in both groups means both names carry the same upload.
_MIN_SHARED_COORDS = 3
_MIN_SHARED_FRACTION = 0.25


def _coord_sizes(group):
    """{(season, episode): known file sizes} of a group."""
    return {(s, e): {_safe_size(v) for v in vs} - {0}
            for s, eps in group['seasons'].items() for e, vs in eps.items()}


def _content_overlap(a, b):
    """(shared, collided) over the coordinates both size maps hold: `shared`
    when some file size is common to both, `collided` when none is."""
    shared = collided = 0
    for coord in a.keys() & b.keys():
        if a[coord] & b[coord]:
            shared += 1
        else:
            collided += 1
    return shared, collided


def _is_same_show(shared, collided):
    """Enough shared (coordinate, size) pairs, and not a fringe of a mostly
    colliding overlap (different uploads of one show still share a few)."""
    return (shared >= _MIN_SHARED_COORDS
            and shared >= _MIN_SHARED_FRACTION * (shared + collided))


def _only_collisions(a, b):
    """True when the groups collide on several coordinates, season 1 among them,
    and share no file on any. One collision is just another upload of an
    episode; a distinct show or spinoff numbers from S01, while collisions only
    in later seasons are a continuation released under another title ("The
    Culling Game S03E01")."""
    shared, collided = _content_overlap(a, b)
    return (collided >= _MIN_SHARED_COORDS and shared == 0
            and any(c[0] == 1 for c in a.keys() & b.keys()))


def _franchise_stubs(series):
    """Plain keys that name a franchise, not a show: at least two unrelated
    substantial (>= 3 episodes) longer names contain the key's words and the
    key itself holds fewer episodes than the largest of them ("star wars" next
    to "star wars rebels" and "star wars resistance"). Such a key absorbs
    none of them; the dominant key of a family ("south park") is no stub."""
    plain = {k: set(k.split()) for k in series if '|' not in k}
    eps = {k: series[k].get('total_episodes', 0) for k in plain}
    stubs = set()
    for short, words in plain.items():
        longer = [k for k in plain if words < plain[k] and eps[k] >= 3]
        minimal = [k for k in longer if not any(plain[o] < plain[k] for o in longer)]
        if len(minimal) >= 2 and eps[short] < max(eps[k] for k in minimal):
            stubs.add(short)
    return stubs


def _absorb_series(series, survivors):
    """Merge each loser into its survivor (sorted: deterministic version lists)."""
    for source_key in sorted(survivors):
        target_key = survivors[source_key]
        log_debug(f'Series merge: "{source_key}" → "{target_key}"')
        merge_season_data(series[target_key], series[source_key])
        _merge_display_names(series, target_key, source_key)
        _carry_aliases(series[target_key], source_key, series[source_key])
        del series[source_key]


def merge_substring_series(grouped):
    """Merge series where one canonical key's words are a subset of another's.

    Example: "south park" and "mestecko south park" → merge into one group.

    Uses precomputed word sets and length-sorted keys for O(N log N) performance.
    The survivor is the better-ordered related key (see _series_order); a key
    related to two incomparable groups joins only the better one.
    """
    series = grouped['series']
    keys_list = sorted(series)

    if len(keys_list) < 2:
        return grouped

    # Precompute word sets once (avoids O(N²) split/set creation)
    word_sets = {key: set(key.split()) for key in keys_list}

    # Sort by word count (fewer words first) for directional matching
    keys_by_words = sorted(keys_list, key=lambda k: (len(word_sets[k]), k))

    # Spinoff protection reads each group's ORIGINAL episode count (#22).
    eps = {k: series[k].get('total_episodes', 0) for k in series}
    stubs = _franchise_stubs(series)
    coords = {k: _coord_sizes(series[k]) for k in series}

    edges = []
    for i, short_key in enumerate(keys_by_words):
        short_words = word_sets[short_key]
        short_wc = len(short_words)

        # A franchise stub ("star wars") is not the parent of its sibling shows
        if short_key in stubs:
            continue

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
                # If both groups had significant episodes and the extra words
                # are short (likely sequel/spinoff markers like Z, GT, Super),
                # they are distinct series.
                extra_words = long_words - short_words
                if min(eps[short_key], eps[long_key]) >= 3 and all(len(w) <= 5 for w in extra_words):
                    continue
                # Same episodes under both names but no file in common: two
                # uploads of different shows, not one show. Exempt: a dual key
                # and a key that spells out two other keys ("hra na olihen" +
                # "squid game") state in their own file names that the names
                # are one show.
                if ('|' not in short_key and '|' not in long_key
                        and _only_collisions(coords[short_key], coords[long_key])
                        and not any(short_words | word_sets[k] == long_words
                                    and not short_words & word_sets[k]
                                    for k in keys_list if '|' not in k)):
                    continue
                edges.append((long_key, short_key))

    # The generic (fewest-words) key stays the survivor, as before; among
    # equally generic candidates the one with more episodes/files, then key.
    rank = _series_order(series)
    _absorb_series(series, _merge_roots(
        edges, lambda k: (len(word_sets[k]),) + rank(k)))
    return grouped


def merge_word_order_series(grouped):
    """Merge series with same words but different order.

    Example: "south park" and "park south" → merge into one group.

    Uses get_word_set_key() to create order-independent comparison keys; the
    survivor is the best-ordered member (see _series_order).

    Args:
        grouped: Dict with 'series' and 'non_series' keys

    Returns:
        Modified grouped dict with merged series
    """
    series = grouped.get('series', {})
    if not series:
        return grouped

    by_words = {}
    for key in series:
        by_words.setdefault(get_word_set_key(key), []).append(key)

    order = _series_order(series)
    survivors = {}
    for keys in by_words.values():
        # ties on content go to the greater key ("south park" over "park south")
        best = max(keys, key=lambda k: (-order(k)[0], -order(k)[1], k))
        survivors.update({k: best for k in keys if k != best})
    _absorb_series(series, survivors)
    return grouped


def merge_dual_canonical_series(grouped):
    """Merge series where canonical key contains pipe-separated dual names.

    Handles case where episodes have different naming:
    - "The Penguin S01E01" → canonical="the penguin"
    - "Tučňák S01E02" → canonical="tucnak"
    - "The Penguin - Tučňák S01E03" → canonical="the penguin|tucnak"

    Merges all three into one series. A dual key's own target is its first
    component (or the dual key itself when that is absent); a component key
    shared by several dual keys joins only one of them (the best-ordered), and
    two dual keys are never merged with each other.

    Args:
        grouped: Dict with 'series' and 'non_series' keys

    Returns:
        Modified grouped dict with merged series
    """
    series = grouped.get('series', {})
    if not series:
        return grouped

    stubs = _franchise_stubs(series)
    edges = []
    for dual_key in sorted(k for k in series if '|' in k):
        parts = dual_key.split('|')
        # a franchise stub shared by several dual keys would bridge unrelated shows
        related = [p for p in parts if p in series and p not in stubs]
        if not related:
            continue
        target = parts[0] if parts[0] in related else dual_key
        edges.extend((k, target) for k in [dual_key] + related if k != target)

    _absorb_series(series, _merge_roots(edges, _series_order(series)))
    return grouped


def merge_similar_series(grouped):
    """Merge series with similar canonical keys (typo tolerance).

    Uses SequenceMatcher ratio > 0.85 to catch typos like:
    - "jujuts kaisen" → "jujutsu kaisen"
    - "stranger thing" → "stranger things"

    Only merges if one group is much smaller (likely the typo variant); on a
    tie the longer key survives (a typo is usually a truncation).
    """
    from difflib import SequenceMatcher

    series = grouped.get('series', {})
    if len(series) < 2:
        return grouped

    # Skip pipe-separated keys (already handled by dual merge)
    keys = sorted(k for k in series if '|' not in k)
    eps = {k: series[k]['total_episodes'] for k in keys}
    coords = {k: _coord_sizes(series[k]) for k in keys}
    words = {k: set(k.split()) for k in keys}
    rank = _series_order(series, longer_wins=True)
    edges = []

    for i, key1 in enumerate(keys):
        for key2 in keys[i+1:]:
            if SequenceMatcher(None, key1, key2).ratio() > 0.85:
                # A key that merely extends the other by whole words is the
                # substring pass's business (stub and spinoff guards), not a typo
                if words[key1] <= words[key2] or words[key2] <= words[key1]:
                    continue
                # Safety: don't merge if both have significant episode counts
                # (suggests genuinely different series, e.g., "dragon ball z" vs "dragon ball super")
                if min(eps[key1], eps[key2]) >= 3:
                    continue
                if _only_collisions(coords[key1], coords[key2]):
                    continue
                # The better-ordered key of the pair survives.
                lo, hi = (key1, key2) if rank(key2) < rank(key1) else (key2, key1)
                edges.append((lo, hi))

    _absorb_series(series, _merge_roots(edges, rank))
    return grouped


def merge_same_content_series(grouped):
    """Merge groups that hold the same files under different names.

    Two groups with enough shared (coordinate, file size) pairs are one show
    uploaded under two names ("game of thrones" / "game of thrones hra o truny"),
    whatever their key text says. Candidate pairs come from a size index, so
    groups sharing no file size are never compared; the survivor is the
    best-ordered key (see _series_order).
    """
    series = grouped.get('series', {})
    coords = {k: _coord_sizes(g) for k, g in series.items()}
    holders = {}
    for key in sorted(coords):
        for sizes in coords[key].values():
            for size in sizes:
                holders.setdefault(size, set()).add(key)
    pairs = set()
    for keys in holders.values():
        pairs.update(itertools.combinations(sorted(keys), 2))

    rank = _series_order(series)
    edges = []
    for a, b in sorted(pairs):
        if _is_same_show(*_content_overlap(coords[a], coords[b])):
            edges.append((a, b) if rank(b) < rank(a) else (b, a))
    _absorb_series(series, _merge_roots(edges, rank))
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
    cleaned = _unhyphenate(cleaned)
    cleaned = _RE_QUALITY.sub('', cleaned)
    cleaned = _RE_SOURCE.sub('', cleaned)
    cleaned = _RE_CODEC.sub('', cleaned)
    cleaned = _RE_LANG_LABEL.sub('', cleaned)
    cleaned = _RE_LANG_CODE.sub('', cleaned)
    cleaned = _RE_BRACKET_GROUP.sub('', cleaned)
    cleaned = _RE_UNCLOSED_TAIL.sub('', cleaned)
    if strip_trailing_num:
        cleaned = _RE_TRAILING_NUM.sub('', cleaned)
    cleaned = _RE_SE_MARKER.sub('', cleaned)
    cleaned = _RE_NxN_MARKER.sub('', cleaned)
    cleaned = _RE_TRAILING_SEP.sub('', cleaned)
    cleaned = _RE_MULTI_SPACE.sub(' ', cleaned)
    return cleaned.strip()


def _unhyphenate(name):
    """Scene names use hyphens as word separators ("Barbie-a-ruzove-balerinky").
    Hyphens inside words are separators when there are at least two and they
    outnumber the spaces; otherwise ("Spider-Man", "Gekijo-ban Chenso Man Reze-hen")
    they are part of the title."""
    inner = len(_RE_INNER_HYPHEN.findall(name))
    if inner >= 2 and inner > name.count(' '):
        return _RE_INNER_HYPHEN.sub(' ', name)
    return name


def _pick_majority(pairs):
    """Pick the display string from (vote_key, display) pairs.

    The vote key groups spellings of one title (hyphens fold into spaces so
    "Fight-Club" counts for "Fight Club"); the biggest group wins, ties go to
    the shorter key. Inside the winning group the most common display wins, so
    the result depends only on the multiset of pairs, never on their order.
    """
    from collections import Counter
    key_counts = Counter(vk for vk, _ in pairs)
    best_key = min(key_counts, key=lambda k: (-key_counts[k], len(k), k))
    shown = Counter(d for vk, d in pairs if vk == best_key)
    return min(shown, key=lambda d: (-shown[d], d.isupper(), d.count('-'), len(d), d))


def _fold_hyphens(name):
    return _RE_MULTI_SPACE.sub(' ', name.replace('-', ' ')).strip()


def pick_best_display_name_from_list(names):
    """Pick the display name by majority vote over ALL candidate names.

    Each candidate is cleaned aggressively (trailing number stripped) to group
    encodings of one title; the winner is shown in its lightly cleaned form,
    which keeps title numbers ("Cobra Kai 3", "Blade Runner 2049").

    Args:
        names: List of candidate names

    Returns:
        Best name choice
    """
    if not names:
        return None

    pairs = []
    for n in names:
        heavy = _strip_display_metadata(n, strip_trailing_num=True)
        light = _strip_display_metadata(n, strip_trailing_num=False)
        if heavy and len(heavy) >= 2 and light:
            pairs.append((_fold_hyphens(heavy), light))

    if not pairs:
        # Every candidate cleaned to nothing usable — fall back to the lightly
        # cleaned first candidate, not the raw filename (#29).
        return _strip_display_metadata(names[0], strip_trailing_num=False) or names[0]

    display = _pick_majority(pairs)
    log_debug(f'Name picker: "{display}" of {len(names)} candidates')
    return display


def _merge_display_names(series, target_key, source_key):
    """Carry source's display candidates into target and re-vote its display
    name over the whole merged multiset (counts survive any number of merges)."""
    target, source = series[target_key], series[source_key]
    for key, entry in ((target_key, target), (source_key, source)):
        if not entry.get('display_name_candidates'):
            entry['display_name_candidates'] = [entry.get('display_name', key.title())]
    target['display_name_candidates'].extend(source['display_name_candidates'])
    voted = pick_best_display_name_from_list(target['display_name_candidates'])
    if voted:
        target['display_name'] = voted


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


def _file_series_keys(filename, ep_info, legacy_site=False):
    """(canonical_key, display_name, legacy_keys) a parsed series file is grouped under.

    `legacy_keys` are the keys it had before its alias / dual name was read: rows stored under
    them resolve through the group's aliases. `legacy_site` reads the name with the site-prefix
    list older versions used (key derivation for `_site_legacy_series_keys`).
    """
    series = ep_info['series_name']
    canonical_key = series
    legacy_key = None   # key this file had before its alias was read
    legacy_dual_key = None
    display_name = get_display_name(ep_info['original_name'])

    # Extract raw name for dual-name detection (works even when CSFD disabled)
    bare = strip_site_prefix(filename, legacy_site)
    match = match_episode_marker(bare)
    alias_read_from_parens = not match
    if not match:  # season text ("S3") is not part of the name the alias key is built from
        match = _PATTERN_ABSOLUTE_ALIAS.match(extract_season_from_text(bare)[1])
    if match:
        raw_name = match.group(1)
        if '\u2013' in raw_name or '\u2014' in raw_name:
            # keys used to keep the text after an en/em dash ("peaky
            # blinders – gangy z birminghamu"): rows stored under it
            old_key = clean_series_name(raw_name)
            if old_key != series:
                legacy_key = old_key
        dual_names = extract_dual_names(raw_name)

        # Priority 1: Dual names in filename
        if dual_names:
            dual_ck, dual_dn = _dual_canonical(dual_names[0], dual_names[1])
            if dual_ck:
                canonical_key = dual_ck
                legacy_dual_key = _legacy_dual_key(dual_names[0], dual_names[1])
                if alias_read_from_parens:
                    legacy_key = series
                if dual_dn:
                    display_name = dual_dn
                log_debug(f'Dual names detected: {dual_names[0]} / {dual_names[1]}')

        # CSFD lookup removed (feature disabled)

    return canonical_key, display_name, [k for k in (legacy_key, legacy_dual_key) if k]


def _site_legacy_series_keys(filename):
    """Keys this file had before its release-site prefix was recognised (group aliases).

    The key that was only the site ("7hitmovies best") is left out: it names every title of that
    site, so no row or favorite under it can be attributed to this series.
    """
    if strip_site_prefix(filename) == strip_site_prefix(filename, legacy=True):
        return []
    old_info = parse_episode_info(filename, legacy_site=True)
    if not old_info or not old_info['is_series']:
        return []
    old_key, _, old_legacy = _file_series_keys(filename, old_info, legacy_site=True)
    site_only = legacy_site_prefix_key(filename)
    return [k for k in (old_key, *old_legacy, old_info.get('legacy_series_name')) if k and k != site_only]


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

    # Parse everything first: "Name NN - MM" is season NN only given the show's other files.
    parsed = []
    for file_dict in files:
        filename = file_dict.get('name', '')
        # Check for movie year pattern BEFORE episode parsing
        # This prevents movies from being misclassified as series
        movie_info = parse_movie_info(filename) if filename else None

        # Try episode parsing when it's not a movie, OR when the filename has a
        # genuine episode marker even alongside a year ("Series 2016 (S01E01)").
        # Use the parsing marker pattern (which accepts ()/[] wrappers and a gap
        # between season and episode) — the old local pattern only matched _ space . - , and
        # silently misrouted bracketed-marker episodes to movies (#1).
        ep_info = None
        if filename and (not movie_info or EPISODE_MARKER_ANYWHERE.search(filename)):
            ep_info = parse_episode_info(filename)
        parsed.append((movie_info, ep_info))
    apply_season_readings([ep_info for _, ep_info in parsed])

    for index, file_dict in enumerate(files):  # no zip(strict=): Kodi 19 ships Python < 3.10
        movie_info, ep_info = parsed[index]
        filename = file_dict.get('name', '')
        if not filename:  # Handle empty/None filenames
            result['non_series'].append(file_dict)
            continue

        # If it's a series match, process it
        if ep_info and ep_info['is_series']:
            season = ep_info['season']
            episode = ep_info['episode']

            canonical_key, display_name, legacy_keys = _file_series_keys(filename, ep_info)

            # Initialize series structure if needed (use canonical_key)
            if canonical_key not in result['series']:
                series_meta = {
                    'display_name': display_name,
                    'display_name_candidates': [display_name],
                    'seasons': {},
                    'total_episodes': 0
                }
                result['series'][canonical_key] = series_meta
            else:
                # Add this episode's display name as candidate
                result['series'][canonical_key]['display_name_candidates'].append(display_name)
            # keys this file had before its season marker was parsed ("suits s03")
            for old_key in (*legacy_keys, ep_info.get('legacy_series_name'), *_site_legacy_series_keys(filename)):
                if old_key and old_key != canonical_key:
                    result['series'][canonical_key].setdefault('aliases', []).append(old_key)

            # Initialize season dict if needed
            if season not in result['series'][canonical_key]['seasons']:
                result['series'][canonical_key]['seasons'][season] = {}

            if movie_info and not LEGACY_EPISODE_MARKER_ANYWHERE.search(filename):
                # a movie until its marker spelling was recognised ("Show.S03.E01.2025"): playback
                # state stored under that movie key resolves for the episode (state.resolve_state_key)
                file_dict['legacy_movie_key'] = _movie_key_and_display(movie_info)[0]

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

            # Duplicates (same ident) are collapsed by deduplicate_versions below;
            # same name+size with a distinct ident is a mirror and is kept.
            result['series'][canonical_key]['seasons'][season][episode].append(file_dict)
        else:
            result['non_series'].append(file_dict)

    # Sort versions by quality score (highest first) and calculate unique episode counts
    for _series_key, series_data in result['series'].items():
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
        # Candidates are kept: merges re-vote over every member file's name.
        best_name = pick_best_display_name_from_list(series_data['display_name_candidates'])
        if best_name:
            series_data['display_name'] = best_name

    # Substring, word-order, dual-name ("the penguin|tucnak") and typo-similarity
    # merges, repeated until a round merges nothing (a merge can create a key
    # that relates to another group).
    result = _merge_to_fixpoint(result, 'series', (
        merge_substring_series, merge_word_order_series,
        merge_dual_canonical_series, merge_similar_series,
        merge_same_content_series))

    _separate_colliding_identities(result['series'])
    _carry_dual_name_aliases(result['series'])
    owned_elsewhere = _owned_elsewhere(result['series'])
    _finalize_aliases(result['series'], normalize_series_key, owned_elsewhere)


    # Single dedup+sort pass after all merges (avoids redundant per-merge dedup)
    for group_key, series_data in result['series'].items():
        unique_episodes = set()
        for season_num, episodes in series_data['seasons'].items():
            for ep_num, versions in episodes.items():
                # Merges re-key groups after series_name was set. Rebind each
                # member to its final group key so the state key built from the
                # file (list time) equals the one play() builds from the URL.
                for v in versions:
                    if v.get('series_name') != group_key:
                        if not owned_elsewhere(group_key, v.get('series_name') or ''):
                            v['premerge_series_name'] = v.get('series_name')
                        v['series_name'] = group_key
                    # list-item state lookup (utils.tolistitem) resolves rows
                    # stored under any key this group was merged from
                    v['series_aliases'] = series_data['aliases']
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
            grouped_movie_obj_ids = set()
            for movie_data in movies_result['movies'].values():
                for version in movie_data['versions']:
                    ident = version.get('ident')
                    if ident:
                        grouped_movie_idents.add(ident)
                    else:
                        # Ident-less versions can't be excluded by ident; fall
                        # back to object identity (the movie pipeline reuses the
                        # same dicts from non_series, never copies) so they don't
                        # stay duplicated in the flat list.
                        grouped_movie_obj_ids.add(id(version))

            result['non_series'] = [
                f for f in result['non_series']
                if f.get('ident') not in grouped_movie_idents
                and id(f) not in grouped_movie_obj_ids
            ]

            # CSFD movie enrichment removed (feature disabled)
        except Exception as e:
            log_debug(f"Error grouping movies: {e}")
            # Continue without movie grouping

    return result


def _movie_key_and_display(movie_info):
    """Canonical key "title|year" and raw display title of one parsed movie file."""
    canonical_key = f"{movie_info['title']}|{movie_info['year']}"
    display_name = movie_info['raw_title']
    # Handle dual names (deterministic regardless of csfd availability).
    if movie_info['dual_names']:
        dual_ck, dual_dn = _dual_canonical(
            movie_info['dual_names'][0], movie_info['dual_names'][1])
        if dual_ck:
            canonical_key = f"{dual_ck}|{movie_info['year']}"
            if dual_dn:
                display_name = dual_dn
    return canonical_key, display_name


def _vote_movie_display(key, movie_data):
    """Display name voted over the member files of a (merged) movie group.

    Every version's own title is cleaned and votes; only files whose own key is
    the group's key count (an edition/alias merged in cannot rename the group),
    falling back to everyone. Versions survive merges, so counts do too.
    """
    own, every = [], []
    for v in movie_data['versions']:
        info = parse_movie_info(v.get('name', ''))
        if not info:
            continue
        k, display = _movie_key_and_display(info)
        cleaned = _clean_movie_display_name(display)
        if cleaned:
            every.append((_fold_hyphens(cleaned), cleaned))
            if k == key:
                own.append(every[-1])
    pairs = own or every
    if not pairs:
        return _clean_movie_display_name(movie_data['display_name'])
    return _pick_majority(pairs)


def _legacy_dual_alias(dual_names, year, canonical_key):
    """The pre-shared-cleaning dual key of a parsed movie ("a|b|year"), else None."""
    old_key = _legacy_dual_key(*dual_names[:2]) if dual_names else None
    old_key = '{}|{}'.format(old_key, year) if old_key else None
    return old_key if old_key != canonical_key else None


def _site_legacy_movie_keys(filename):
    """Keys this file had before its release-site prefix was recognised (group aliases)."""
    if strip_site_prefix(filename) == strip_site_prefix(filename, legacy=True):
        return []
    old_info = parse_movie_info(filename, legacy_site=True)
    if not old_info:
        return []
    old_key = _movie_key_and_display(old_info)[0]
    return [k for k in (old_key, _legacy_dual_alias(old_info['dual_names'], old_info['year'], old_key)) if k]


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

        canonical_key, display_name = _movie_key_and_display(movie_info)

        # Initialize movie entry
        if canonical_key not in result['movies']:
            result['movies'][canonical_key] = {
                'display_name': display_name,
                'year': movie_info['year'],
                'versions': [],
                'canonical_key': canonical_key
            }
        old_keys = [*_site_legacy_movie_keys(file_dict.get('name', '')),
                    _legacy_dual_alias(movie_info['dual_names'], movie_info['year'], canonical_key)]
        result['movies'][canonical_key].setdefault('aliases', []).extend(
            k for k in old_keys if k and k != canonical_key)

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

    # Substring-title (same year), identical title across nearby years (uploader
    # year errors), dual-name keys into simple keys ("blade 2|blade ii|2002" into
    # "blade 2|2002"), then 1-version orphans into larger same-year groups.
    result = _merge_to_fixpoint(result, 'movies', (
        merge_substring_movies, merge_crossyear_movies,
        merge_dual_key_movies, merge_orphan_movies))

    # Display names: majority vote over every member file's cleaned title
    for key, movie_data in result['movies'].items():
        movie_data['display_name'] = _vote_movie_display(key, movie_data)

    _finalize_aliases(result['movies'], normalize_movie_key)
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


def _movie_order(movies):
    """Survivor order for movie groups: most files, then the shorter key, then
    the key. Snapshot of the groups before the pass."""
    size = {k: len(v.get('versions', [])) for k, v in movies.items()}
    return lambda k: (-size[k], len(k), k)


def _absorb_movies(movies, survivors):
    """Merge each loser's versions into its survivor, then dedup+sort once."""
    for source_key in sorted(survivors):
        target_key = survivors[source_key]
        log_debug(f'Movie merge: "{source_key}" → "{target_key}"')
        movies[target_key]['versions'].extend(movies[source_key]['versions'])
        _carry_aliases(movies[target_key], source_key, movies[source_key])
        del movies[source_key]
    _finalize_merged_versions(movies, set(survivors.values()), ())


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
            _carry_aliases(movies[target], dual_key, movies[dual_key])
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
                _carry_aliases(movies[target], key, movies[key])
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
    for orphan_key, orphan_data in sorted(orphans.items()):
        if orphan_key in keys_to_delete:
            continue
        orphan_year = orphan_data.get('year', 0)
        orphan_title = orphan_key.rsplit('|', 1)[0].replace('|', ' ') if '|' in orphan_key else orphan_key
        orphan_words = set(orphan_title.split())
        if not orphan_words:
            continue

        best_target = None
        best_versions = 0

        # Sorted: a tie on version count goes to the first key, not the first arrival.
        for group_key, group_data in sorted(groups.items()):
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
            _carry_aliases(movies[best_target], orphan_key, movies[orphan_key])
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
    cleaned = _unhyphenate(cleaned)
    # Release tags are not part of the title ("BRrip CZ dabing", "1080p")
    for tag in (_RE_QUALITY, _RE_SOURCE, _RE_CODEC, _RE_LANG_LABEL, _RE_LANG_CODE_TAIL):
        cleaned = tag.sub('', cleaned)
    # Unclosed bracket tail with no word in it ("Barbie (2023") is a cut-off year/tag
    cleaned = _RE_UNCLOSED_TAIL.sub('', cleaned)
    if not _RE_LEADING_HYPHEN.search(cleaned):  # "-Title-" pairs are kept
        cleaned = _RE_DANGLING_HYPHEN.sub('', cleaned)  # "dvířka-" left by a removed tag

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
    cleaned = re.sub(r'[\s\-,]+$', '', cleaned)

    # Remove only consecutive duplicate words: "Blade -Blade" → "Blade", "Matrix Matrix" → "Matrix"
    # Preserves non-consecutive: "Run Lola Run", "New York New York", "Sing Sing"
    words = cleaned.split()
    if len(words) >= 2:
        deduped = [words[0]]
        for w in words[1:]:
            if w.lower().strip('-[]()') != deduped[-1].lower().strip('-[]()'):
                deduped.append(w)
        cleaned = ' '.join(deduped)

    cleaned = _RE_MULTI_SPACE.sub(' ', cleaned).strip()
    return cleaned


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
    for _title, entries in by_title.items():
        if len(entries) < 2:
            continue

        # Sort by version count desc (most versions = likely correct year)
        entries.sort(key=lambda x: (-x[2], x[0]))
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
                    _carry_aliases(movies[target_key], source_key, movies[source_key])
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
    The survivor is the group with more files (then the shorter key), so the
    majority title keeps its key whatever order the files arrived in.

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

    rank = _movie_order(movies)
    edges = []
    for _year, keys in by_year.items():
        if len(keys) < 2:
            continue
        keys = sorted(keys)

        # Word set of the title part, dual-name keys included
        # ('inception|pocatek|2010' -> {inception, pocatek}).
        words = {key: set(key.rsplit('|', 1)[0].replace('|', ' ').split()) for key in keys}

        for i, key1 in enumerate(keys):
            for key2 in keys[i+1:]:
                # Related if one title's words are a subset of the other's and
                # the extra words are non-significant.
                small, big = ((key1, key2) if words[key1] <= words[key2] else (key2, key1))
                extra = words[big] - words[small]
                if words[small] <= words[big] and words[small]:
                    if all(w in non_significant or w.isdigit() for w in extra):
                        if extra and not any(w.isdigit() for w in extra):
                            # edition/language tags are not part of the title:
                            # the generic key survives
                            edges.append((big, small))
                        else:
                            # a title number or a repeated token: the larger group
                            # (the majority title) survives
                            edges.append((key1, key2) if rank(key2) < rank(key1) else (key2, key1))

    _absorb_movies(movies, _merge_roots(edges, rank))
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

