# -*- coding: utf-8 -*-
# Module: wdqs
# Author: onykmin
# License: AGPL v.3 https://www.gnu.org/licenses/agpl-3.0.html

"""Wikidata Query Service (WDQS) SPARQL client — random-movie title source.

Implements the query shape and failure handling measured and specified in
WDQS_DEEP_DIVE.md (repo root). Do NOT "improve" the query or the constants
below without re-reading that doc — every choice here traces to a measured
number, not a guess:

- GROUP BY ?film (+ SAMPLE/MIN aggregates) instead of bare DISTINCT: bare
  DISTINCT dedupes the whole result TUPLE, not the film. A film with a
  multi-valued property in the SELECT (e.g. wdt:P577) yields one tuple per
  value, so DISTINCT sees many "different" rows for ONE film (doc §1
  lines 25-30: 10 rows all "Barbarella"). wdt:P577 IS selected below (see
  next bullet), but only ever wrapped in MIN() under this GROUP BY — never
  bare — which is the form the doc proves robust against that fan-out.
- wdt:P31 wd:Q11424 direct (NOT P31/P279* subclass traversal): subclass
  traversal broadens what counts as a "film" (doc line 53).
- wdt:P577 (publication date) IS selected, but ONLY as (MIN(?date) AS ?d)
  under the existing GROUP BY ?film — never bare/SAMPLE-less in the
  projection. Bare DISTINCT + P577 is what fan-out looked like (doc §1
  lines 25-30: 10 rows, 1 distinct film, "Barbarella" x10); MIN() under
  GROUP BY collapses a multi-valued P577 back to one row per film the same
  way SAMPLE() already does for cs/en. Measured live at LIMIT 500 OFFSET 0,
  sitelinks>=20: 500 rows in vs 500 distinct films out — EQUAL, no
  multiplication — and P577 coverage was 500/500 (100%) at that pool
  quality gate.
- No director (P57) or genre (P136), and no rdfs:label lookups for either:
  human-readable labels for those require an explicit label JOIN inside
  GROUP_CONCAT, and that shape hit an HTTP 504 "upstream request timeout"
  measured at ~65s live — the same failure family as the doc's Q5
  SERVICE wikibase:label 504 at 65.2s (doc lines 56-61). Bare Q-ids are
  cheap but useless to display, so these are dropped entirely rather than
  shipped half-working.
- No SERVICE wikibase:label: combined with explicit OPTIONALs it produced
  an HTTP 504 at 65.2s (doc lines 56-61). Explicit OPTIONAL + FILTER(LANG())
  only.
- sitelinks >= 20 is a POOL QUALITY choice, not a latency lever — latency is
  non-monotonic in threshold (doc line 23: >=5 fastest at 6.43s, >=10
  slowest at 45.45s). Do not retune this looking for speed.
"""

import random
import time

import requests
import xbmcaddon

from lib.logging import log_warning, log_error, log_debug


# ----------------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------------

ENDPOINT = 'https://query.wikidata.org/sparql'

# Popularity gate: films with >= this many Wikipedia sitelinks. Doc line 23:
# a pool-quality choice (bigger/more obscure vs smaller/more mainstream),
# explicitly NOT tuned for query speed.
SITELINKS_MIN = 20

# Measured pool size at SITELINKS_MIN=20 (doc line 13). Changes slowly; not
# re-counted per call (a COUNT query is itself 6-45s, doc lines 76-78).
# Random OFFSET must stay within 0..POOL_TOTAL-limit so we never overshoot
# the pool end, which costs 28.50s to return 0 rows (doc lines 63-74) — the
# single worst-case latency in the whole spec.
POOL_TOTAL = 8937

# Client-side timeout. Must be at/below the server's published 60s hard
# query deadline (doc line 179) — a >60s client wait would just be us
# waiting past the point the server has already given up.
REQUEST_TIMEOUT = 60

# At most one retry, with backoff. Never hammer a throttled/erroring
# service (doc lines 174-178).
MAX_RETRIES = 1
RETRY_BACKOFF_SECONDS = 2

_QUERY_TEMPLATE = (
    "SELECT ?film (MIN(?date) AS ?d) (SAMPLE(?cs) AS ?csL) (SAMPLE(?en) AS ?enL) WHERE {{\n"
    "  ?film wdt:P31 wd:Q11424 ;\n"
    "        wikibase:sitelinks ?sl .\n"
    "  FILTER(?sl >= {sitelinks_min})\n"
    "  OPTIONAL {{ ?film wdt:P577 ?date }}\n"
    "  OPTIONAL {{ ?film rdfs:label ?cs . FILTER(LANG(?cs) = \"cs\") }}\n"
    "  OPTIONAL {{ ?film rdfs:label ?en . FILTER(LANG(?en) = \"en\") }}\n"
    "}}\n"
    "GROUP BY ?film\n"
    "LIMIT {limit} OFFSET {offset}"
)


def build_query(limit, offset):
    """Build the SPARQL query text for a LIMIT/OFFSET page of the film pool.

    GROUP BY ?film + SAMPLE/MIN aggregates (not bare DISTINCT) — see module
    docstring; this is the form WDQS_DEEP_DIVE.md §1 proves free of the
    tuple-fan-out bug. P577 (publication date) is included via
    (MIN(?date) AS ?d) specifically BECAUSE it's under this GROUP BY: the
    doc's fan-out bug (§1, 10 rows / 1 distinct film, "Barbarella" x10) was
    bare DISTINCT with a multi-valued property in the SELECT and no
    aggregation — MIN() here is what makes selecting P577 safe, collapsing
    any multi-valued date back to one row per film exactly like SAMPLE()
    already does for cs/en. Measured live: LIMIT 500 OFFSET 0 with this
    exact shape returned 500 rows for 500 distinct films (equal — no
    multiplication) and P577 coverage was 100% (500/500) at the
    sitelinks>=20 pool quality gate. Kept as a standalone, testable function
    so tests can assert on the emitted text without any network access.
    """
    return _QUERY_TEMPLATE.format(sitelinks_min=SITELINKS_MIN,
                                   limit=int(limit), offset=int(offset))


def _addon_user_agent():
    """Build a policy-compliant User-Agent for WDQS calls only.

    Wikimedia's User-Agent policy (https://foundation.wikimedia.org/wiki/
    Policy:User-Agent_policy) requires an informative UA with contact info
    or the client "may be blocked without notice"; throttling is bucketed
    by UA+IP (doc lines 156-163). This MUST be a distinct request/session
    from lib.api's Webshare client: lib/api.py's UA is a spoofed Chrome
    browser string with a Referer header aimed at webshare.cz, and sending
    that to WDQS would both violate the policy and put our WDQS calls in
    Webshare's throttling bucket by mistake (doc line 163).

    Falls back to a static string if Addon() is unavailable (e.g. import-
    time issues in a non-Kodi context) so this never raises.
    """
    try:
        addon = xbmcaddon.Addon()
        addon_id = addon.getAddonInfo('id') or 'plugin.video.yeplaya'
        version = addon.getAddonInfo('version') or '0.0.0'
    except Exception:
        addon_id = 'plugin.video.yeplaya'
        version = '0.0.0'
    project_url = 'https://github.com/Onykmin/plugin.video.yeplaya'
    return '{addon_id}/{version} ({url}; Kodi addon) python-requests/{rv}'.format(
        addon_id=addon_id, version=version, url=project_url,
        rv=getattr(requests, '__version__', '?'))


def _headers():
    """Per-call headers dict — never shared with lib.api's session/UA."""
    return {
        'User-Agent': _addon_user_agent(),
        'Accept': 'application/sparql-results+json',
    }


def _parse_bindings(payload):
    """Turn WDQS JSON bindings into [{'id', 'cs', 'en', 'y'?}, ...].

    Bindings for an unmatched OPTIONAL are ABSENT from the dict entirely,
    not present-with-null (doc §3 line 206 / measured shape) — every field
    read here is a .get(), never a direct key lookup. Rows with neither cs
    nor en are dropped (doc: 3 of 2000 rows, 0.15%, had neither) rather than
    surfaced as unusable "titles".

    'd' (?d, MIN(?date)) is read the same defensive way and turned into an
    int year via the raw value's first 4 characters — measured live format
    is "1998-05-18T00:00:00Z" (xsd:dateTime), so d[:4] is always the year
    when present and well-formed. 'y' is OMITTED from the record entirely
    when unknown or malformed (never stored as None) — this keeps the
    on-disk payload minimal (see lib/movie_pool.py's PREFETCH_BATCH comment
    for the measured byte cost) and mirrors how cs/en already only exist as
    keys when present... except cs/en are always present as either a string
    or None (see above) while 'y' is present only when known, since unlike
    cs/en there is no user-facing fallback value for a missing year.
    """
    records = []
    try:
        bindings = payload['results']['bindings']
    except (KeyError, TypeError) as e:
        log_warning("wdqs: unexpected payload shape: {}".format(e))
        return records

    for row in bindings:
        film_uri = row.get('film', {}).get('value', '')
        if not film_uri:
            continue
        qid = film_uri.rsplit('/', 1)[-1]
        cs = row.get('csL', {}).get('value') or None
        en = row.get('enL', {}).get('value') or None
        if cs is None and en is None:
            # Measured edge case (doc line 206): title-less rows must be
            # skipped, not passed through as unusable picks.
            continue
        record = {'id': qid, 'cs': cs, 'en': en}
        d = row.get('d', {}).get('value')
        if d and d[:4].isdigit():
            record['y'] = int(d[:4])
        records.append(record)
    return records


def _get(params):
    """Single GET with the required failure handling. Returns a
    requests.Response on HTTP success, or None on any failure (never raises).

    Failure handling per doc §3 lines 174-182:
    - status_code checked BEFORE any .json() parse (error bodies from WDQS
      are NOT JSON; doc measured a JSONDecodeError on a raw 502 body).
    - 429: honor Retry-After if present, else a fixed backoff; retried at
      most once total. 403 (ban) never retried.
    - Other 5xx: one bounded retry with backoff, then give up.
    - Timeout / connection errors: caught, logged, treated as failure.
    """
    attempt = 0
    while True:
        try:
            resp = requests.get(ENDPOINT, params=params, headers=_headers(),
                                 timeout=REQUEST_TIMEOUT)
        except requests.Timeout:
            log_warning("wdqs: request timed out (attempt {})".format(attempt + 1))
            return None
        except requests.RequestException as e:
            log_warning("wdqs: request failed: {}".format(e))
            return None

        if resp.status_code == 200:
            return resp

        if resp.status_code == 403:
            # Policy: 403 means the client is already banned for ignoring
            # throttling. Stop immediately — retrying makes it worse.
            log_error("wdqs: HTTP 403 (banned) — not retrying")
            return None

        if resp.status_code == 429:
            if attempt >= MAX_RETRIES:
                log_warning("wdqs: HTTP 429 after {} attempt(s), giving up".format(
                    attempt + 1))
                return None
            retry_after = resp.headers.get('Retry-After')
            try:
                delay = float(retry_after) if retry_after is not None else RETRY_BACKOFF_SECONDS
            except (TypeError, ValueError):
                delay = RETRY_BACKOFF_SECONDS
            log_warning("wdqs: HTTP 429, backing off {}s".format(delay))
            time.sleep(delay)
            attempt += 1
            continue

        # Other non-200 (5xx etc): bounded retry with fixed backoff.
        if attempt >= MAX_RETRIES:
            log_warning("wdqs: HTTP {} after {} attempt(s), giving up".format(
                resp.status_code, attempt + 1))
            return None
        log_warning("wdqs: HTTP {}, retrying after backoff".format(resp.status_code))
        time.sleep(RETRY_BACKOFF_SECONDS)
        attempt += 1


def fetch_candidates(count):
    """Fetch up to `count` candidate film records from WDQS.

    Public source seam (doc §6 line 227): callers ask for a COUNT of
    candidates, never an offset — the random OFFSET into WDQS's pool is
    picked internally so this interface stays swappable for a future
    non-offset source (e.g. TMDB) without a rewrite.

    Returns a list of {'id': str, 'cs': str|None, 'en': str|None} dicts
    (each guaranteed to have at least one of cs/en), or [] on any failure
    (network error, bad status after retries, unparsable payload). Never
    raises out to callers.
    """
    count = int(count)
    if count <= 0:
        return []
    limit = min(count, POOL_TOTAL)
    max_offset = max(POOL_TOTAL - limit, 0)
    offset = random.randint(0, max_offset)

    query = build_query(limit, offset)
    params = {'query': query, 'format': 'json'}

    resp = _get(params)
    if resp is None:
        return []

    try:
        payload = resp.json()
    except ValueError as e:
        log_warning("wdqs: non-JSON response body: {}".format(e))
        return []

    records = _parse_bindings(payload)
    log_debug("wdqs: fetched {} usable records (limit={}, offset={})".format(
        len(records), limit, offset))
    return records
