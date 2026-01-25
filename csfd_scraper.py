"""CSFD metadata scraper for YAWsP.

Provides series title lookup from CSFD.cz (Czech-Slovak Film Database)
to enable grouping series with different names (Czech vs Original).

Based on metadata.csfd.cz Kodi addon XML scraper patterns.
"""

import re
import sqlite3
import os

try:
    import xbmc
    import xbmcaddon
    KODI_ENV = True
except ImportError:
    KODI_ENV = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    from unidecode import unidecode
except ImportError:
    # Fallback using unicodedata for Czech character normalization
    import unicodedata
    def unidecode(text):
        """Normalize Unicode to ASCII - handles Czech characters."""
        normalized = unicodedata.normalize('NFKD', text)
        return ''.join([c for c in normalized if not unicodedata.combining(c)])

# Constants from csfdcz.xml
USER_AGENT = 'Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.97 Safari/537.36'
CSFD_SEARCH_URL = 'https://www.csfd.cz/hledat/?q={query}'
CSFD_DETAIL_URL = 'https://www.csfd.cz/film/{film_id}/prehled/'
TIMEOUT = 5


def _log(message, level='DEBUG'):
    """Log message to Kodi or stdout."""
    if KODI_ENV:
        levels = {
            'DEBUG': xbmc.LOGDEBUG,
            'INFO': xbmc.LOGINFO,
            'WARNING': xbmc.LOGWARNING,
            'ERROR': xbmc.LOGERROR
        }
        xbmc.log(f'[YAWsP CSFD] {message}', levels.get(level, xbmc.LOGDEBUG))
    else:
        print(f'[CSFD] {message}')


def init_csfd_cache():
    """Initialize SQLite cache database.

    Returns: sqlite3.Connection or None
    """
    if not KODI_ENV:
        # For tests: use temp dir
        cache_path = os.path.join(os.path.dirname(__file__), 'csfd_cache.db')
    else:
        try:
            addon = xbmcaddon.Addon()
            # Try both xbmc.translatePath (Kodi 18) and xbmcvfs.translatePath (Kodi 19+)
            try:
                from xbmc import translatePath
            except ImportError:
                from xbmcvfs import translatePath

            addon_data = translatePath(addon.getAddonInfo('profile'))
            if not os.path.exists(addon_data):
                os.makedirs(addon_data)
            cache_path = os.path.join(addon_data, 'csfd_cache.db')
        except Exception as e:
            _log(f'Failed to get addon data path: {e}', 'WARNING')
            return None

    try:
        conn = sqlite3.connect(cache_path)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS csfd_cache (
                search_name TEXT PRIMARY KEY,
                canonical_key TEXT,
                display_name TEXT,
                original_title TEXT,
                czech_title TEXT,
                csfd_id TEXT,
                plot TEXT,
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        _log(f'CSFD cache initialized: {cache_path}', 'DEBUG')
        return conn
    except sqlite3.Error as e:
        _log(f'Failed to init cache: {e}', 'WARNING')
        return None


def search_csfd(query, timeout=TIMEOUT):
    """Search CSFD for series/movie by name.

    Args:
        query: Series name (e.g., "suits")
        timeout: HTTP timeout in seconds

    Returns: List of dicts [{id, title, year}, ...] or None
    """
    if not REQUESTS_AVAILABLE:
        _log('requests library not available', 'WARNING')
        return None

    try:
        url = CSFD_SEARCH_URL.format(query=query.replace(' ', '+'))
        headers = {'User-Agent': USER_AGENT}

        _log(f'Searching CSFD: {url}', 'DEBUG')
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()

        # Parse search results (pattern from csfdcz.xml line 52)
        pattern = r'<a href="/film/([0-9]*)[^"]*?" class="film-title-name">([^<]*)</a> <span class="film-title-info"><span class="info">(.*?)</span>'
        matches = re.findall(pattern, response.text, re.DOTALL)

        if not matches:
            _log(f'No CSFD results for: {query}', 'DEBUG')
            return None

        results = []
        for film_id, title, info in matches:
            # Extract year from info (e.g., "(2011)")
            year_match = re.search(r'\((\d{4})\)', info)
            year = year_match.group(1) if year_match else ''

            results.append({
                'id': film_id,
                'title': title.strip(),
                'year': year
            })

        _log(f'Found {len(results)} CSFD results for: {query}', 'DEBUG')
        return results

    except requests.Timeout:
        _log(f'CSFD search timeout: {query}', 'WARNING')
        return None
    except requests.RequestException as e:
        _log(f'CSFD search error: {e}', 'WARNING')
        return None
    except Exception as e:
        _log(f'CSFD search parse error: {e}', 'ERROR')
        return None


def get_csfd_titles(film_id, timeout=TIMEOUT):
    """Get all title variants for a CSFD film ID.

    Args:
        film_id: CSFD film ID (e.g., "228986")
        timeout: HTTP timeout in seconds

    Returns: Dict {local, original, czech, is_series} or None
    """
    if not REQUESTS_AVAILABLE:
        return None

    try:
        url = CSFD_DETAIL_URL.format(film_id=film_id)
        headers = {'User-Agent': USER_AGENT}

        _log(f'Fetching CSFD detail: {film_id}', 'DEBUG')
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        html = response.text

        titles = {}

        # Local title (h1) - csfdcz.xml line 98
        local_match = re.search(r'<h1[^>]*>([^<]*)<', html)
        if local_match:
            titles['local'] = local_match.group(1).strip()

        # Extract film-names section - csfdcz.xml line 103
        film_names_match = re.search(r'<ul class="film-names">([\s\S]*?)</ul>', html)
        if film_names_match:
            film_names = film_names_match.group(1)

            # Czech title - csfdcz.xml line 167
            czech_match = re.search(r'class="flag" title="Česko"[^>]*>([^<]*)', film_names)
            if czech_match:
                titles['czech'] = czech_match.group(1).strip()

            # Original title: first non-Czech flag - csfdcz.xml line 107
            original_match = re.search(r'class="flag" title="(?!Česko)[^"]*"[^>]*>([^<]*)<', film_names)
            if original_match:
                titles['original'] = original_match.group(1).strip()

        # Fallbacks
        if not titles.get('original'):
            titles['original'] = titles.get('local', '')
        if not titles.get('czech'):
            titles['czech'] = titles.get('local', '')

        # Series detection
        titles['is_series'] = bool(re.search(r'(seriál|TV seriál)', html, re.IGNORECASE))

        # Plot/description extraction
        plot_match = re.search(r'<div class="film-plot-full"[^>]*>\s*<p>(.*?)</p>', html, re.DOTALL)
        if plot_match:
            plot = plot_match.group(1).strip()
            # Clean HTML tags and entities
            plot = re.sub(r'<[^>]+>', '', plot)
            plot = plot.replace('&nbsp;', ' ')
            titles['plot'] = plot
        else:
            # Try shorter plot version
            plot_match = re.search(r'<div class="film-plot"[^>]*>\s*<p>(.*?)</p>', html, re.DOTALL)
            if plot_match:
                plot = plot_match.group(1).strip()
                plot = re.sub(r'<[^>]+>', '', plot)
                plot = plot.replace('&nbsp;', ' ')
                titles['plot'] = plot

        _log(f'CSFD titles: orig={titles.get("original")}, cz={titles.get("czech")}, series={titles["is_series"]}, plot={len(titles.get("plot", ""))} chars', 'DEBUG')
        return titles

    except requests.RequestException as e:
        _log(f'CSFD detail error: {e}', 'WARNING')
        return None
    except Exception as e:
        _log(f'CSFD detail parse error: {e}', 'ERROR')
        return None


def format_display_name(original, czech):
    """Format dual name compactly, prioritizing Czech.

    Args:
        original: Original title
        czech: Czech title

    Returns: Formatted string (Czech preferred, or 'Czech / EN' if both exist)
    """
    if not original and not czech:
        return ''

    # If only one title exists, use it
    if not czech:
        return original
    if not original:
        return czech

    # If both are same, use one
    if original.lower() == czech.lower():
        return czech

    # Both exist and differ - show Czech / Original (compact)
    return f'{czech} / {original}'


def _clean_for_canonical(name):
    """Clean name for canonical key (normalize, lowercase, unidecode, strip articles).

    IMPORTANT: Must normalize separators (dots, hyphens, underscores) to spaces
    so that 'Penguin.The' matches 'Penguin The' and 'South-Park' matches 'South Park'.
    """
    if not name:
        return ''

    # Normalize separators (dots, hyphens, underscores) to spaces FIRST
    # This ensures 'Game.of.Thrones' becomes 'Game of Thrones'
    cleaned = re.sub(r'[\.\-_]+', ' ', name)

    # Remove extra spaces
    cleaned = re.sub(r'\s+', ' ', cleaned.strip())
    # Normalize Czech diacritics
    cleaned = unidecode(cleaned)
    # Lowercase
    cleaned = cleaned.lower()

    # Strip common English articles from beginning
    if cleaned.startswith('the '):
        cleaned = cleaned[4:]
    elif cleaned.startswith('a '):
        cleaned = cleaned[2:]
    elif cleaned.startswith('an '):
        cleaned = cleaned[3:]

    return cleaned.strip()


def create_canonical_from_dual_names(name1, name2):
    """Create canonical key and display name from dual names already in filename.

    Args:
        name1: First name (e.g., "Suits")
        name2: Second name (e.g., "Kravataci")

    Returns: Dict {canonical_key, display_name, original, czech} or None
    """
    if not name1 or not name2:
        return None

    # Clean both names for canonical key
    clean1 = _clean_for_canonical(name1)
    clean2 = _clean_for_canonical(name2)

    if not clean1 or not clean2 or clean1 == clean2:
        return None

    # Handle substring case: if one name is substring of other, use longer name only
    # E.g., "South Park" vs "Městečko South Park" -> use "mestecko south park" only
    if clean1 in clean2:
        canonical_key = clean2
        display_name = name2  # Use longer name as display
        _log(f'Substring detected: {name1} in {name2} -> {canonical_key}', 'DEBUG')
    elif clean2 in clean1:
        canonical_key = clean1
        display_name = name1  # Use longer name as display
        _log(f'Substring detected: {name2} in {name1} -> {canonical_key}', 'DEBUG')
    else:
        # Create canonical key (sorted)
        canonical_key = '|'.join(sorted([clean1, clean2]))
        # Display name (preserve original case)
        display_name = format_display_name(name1, name2)
        _log(f'Dual names detected: {name1} + {name2} -> {canonical_key}', 'DEBUG')

    return {
        'canonical_key': canonical_key,
        'display_name': display_name,
        'original': name1,
        'czech': name2
    }

def get_episode_title(film_id, season, episode, timeout=TIMEOUT):
    """Get episode title from CSFD series page.

    Args:
        film_id: CSFD film/series ID
        season: Season number
        episode: Episode number
        timeout: HTTP timeout

    Returns: Episode title string or None
    """
    if not REQUESTS_AVAILABLE:
        return None

    try:
        # CSFD series episodes URL: https://www.csfd.cz/film/{id}/prehled/epizody/
        url = f'https://www.csfd.cz/film/{film_id}/prehled/epizody/'
        headers = {'User-Agent': USER_AGENT}

        _log(f'Fetching CSFD episodes: {film_id} S{season:02d}E{episode:02d}', 'DEBUG')
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        html = response.text

        # Find season section
        season_pattern = rf'<h3[^>]*>.*?{season}\.?\s*série.*?</h3>(.*?)(?=<h3|$)'
        season_match = re.search(season_pattern, html, re.DOTALL | re.IGNORECASE)

        if not season_match:
            _log(f'Season {season} not found for {film_id}', 'DEBUG')
            return None

        season_html = season_match.group(1)

        # Find episode within season
        # Pattern: <li>X. Episode Title</li> where X is episode number
        episode_pattern = rf'<li[^>]*>\s*{episode}\.\s*([^<]+)</li>'
        episode_match = re.search(episode_pattern, season_html, re.IGNORECASE)

        if episode_match:
            title = episode_match.group(1).strip()
            _log(f'Found episode title: S{season:02d}E{episode:02d} = {title}', 'DEBUG')
            return title

        _log(f'Episode {episode} not found in season {season} for {film_id}', 'DEBUG')
        return None

    except requests.RequestException as e:
        _log(f'CSFD episode fetch error: {e}', 'WARNING')
        return None
    except Exception as e:
        _log(f'CSFD episode parse error: {e}', 'ERROR')
        return None


def get_movie_metadata(canonical_key, year, timeout=TIMEOUT):
    """Get CSFD metadata for movie with year-based matching.

    Args:
        canonical_key: e.g., "inception" or "inception|pocatek"
        year: Movie release year for disambiguation

    Returns:
        {'csfd_id': str, 'plot': str, 'titles': {...}} or None
    """
    if not REQUESTS_AVAILABLE:
        return None

    # Extract search term(s)
    if '|' in canonical_key:
        parts = canonical_key.split('|')
        # Try Czech name first (more likely on CSFD)
        search_terms = [parts[1], parts[0]]
    else:
        search_terms = [canonical_key]

    for search_term in search_terms:
        # Search with year for better matching
        query = f"{search_term} {year}"
        results = search_csfd(query, timeout)

        if not results:
            continue

        # Find best match by year proximity
        best_match = None
        best_year_diff = float('inf')

        for result in results[:5]:  # Check top 5
            result_year = result.get('year')
            if result_year:
                try:
                    result_year = int(result_year)
                    year_diff = abs(result_year - year)

                    # Accept if year matches exactly or within 1 year
                    if year_diff <= 1 and year_diff < best_year_diff:
                        best_match = result
                        best_year_diff = year_diff
                except ValueError:
                    continue

        if best_match:
            film_id = best_match['id']
            titles = get_csfd_titles(film_id, timeout)

            if titles:
                return {
                    'csfd_id': film_id,
                    'plot': titles.get('plot', ''),
                    'titles': titles
                }

    return None


def lookup_series_csfd(series_name, cache_db):
    """Lookup series on CSFD, return canonical key with caching.

    Args:
        series_name: Cleaned series name from filename
        cache_db: sqlite3.Connection for caching

    Returns: Dict {canonical_key, display_name, original, czech} or None
    """
    if not REQUESTS_AVAILABLE:
        return None

    # Check cache
    if cache_db:
        try:
            cursor = cache_db.execute(
                'SELECT canonical_key, display_name, original_title, czech_title, plot, csfd_id FROM csfd_cache WHERE search_name = ?',
                (series_name,)
            )
            row = cursor.fetchone()
            if row:
                _log(f'CSFD cache hit: {series_name}', 'DEBUG')
                return {
                    'canonical_key': row[0],
                    'display_name': row[1],
                    'original': row[2],
                    'czech': row[3],
                    'plot': row[4] if len(row) > 4 else None,
                    'csfd_id': row[5] if len(row) > 5 else None
                }
        except sqlite3.Error as e:
            _log(f'Cache query error: {e}', 'WARNING')

    # Cache miss - query CSFD
    _log(f'CSFD cache miss, querying: {series_name}', 'DEBUG')

    # Search
    results = search_csfd(series_name)
    if not results:
        return None

    # Pick first result (best match by CSFD ranking)
    film_id = results[0]['id']

    # Get titles
    titles = get_csfd_titles(film_id)
    if not titles:
        return None

    # Filter series only (optional - depends on csfd_series_only setting)
    # For now, accept both movies and series (episode patterns will filter later)

    original = titles.get('original', '')
    czech = titles.get('czech', '')

    # Clean for canonical key
    original_clean = _clean_for_canonical(original)
    czech_clean = _clean_for_canonical(czech)

    # Create canonical key: alphabetically sorted, pipe-separated
    names = sorted(filter(None, [original_clean, czech_clean]))
    if not names:
        return None

    canonical_key = '|'.join(names) if len(names) > 1 else names[0]
    display_name = format_display_name(original, czech)
    plot = titles.get('plot', '')

    # Store in cache
    if cache_db:
        try:
            cache_db.execute(
                'INSERT OR REPLACE INTO csfd_cache (search_name, canonical_key, display_name, original_title, czech_title, csfd_id, plot) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (series_name, canonical_key, display_name, original, czech, film_id, plot)
            )
            cache_db.commit()
            _log(f'CSFD cached: {series_name} -> {canonical_key}', 'DEBUG')
        except sqlite3.Error as e:
            _log(f'Cache insert error: {e}', 'WARNING')

    return {
        'canonical_key': canonical_key,
        'display_name': display_name,
        'original': original,
        'czech': czech,
        'plot': plot,
        'csfd_id': film_id
    }
