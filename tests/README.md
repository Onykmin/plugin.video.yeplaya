# Test Suite

Tests series/movie grouping, CSFD integration, deduplication, search relevance.

## Quick Start

```bash
# Unit tests (fast, no network):
./tests/run_all.sh               # or ./tests/run_all.py

# All tests (includes integration/network):
./tests/run_all_tests.sh

# Single test:
python3 tests/unit/test_deduplication.py

# With pytest:
pytest tests/

# Skip network tests:
SKIP_LIVE_TESTS=1 python3 tests/integration/test_csfd_integration.py
```

## Structure

```
tests/
├── unit/                        # Fast, no network (110+ tests)
│   ├── test_deduplication.py        (40) Quality parsing, Czech normalization
│   ├── test_series_parsing.py       (4)  Episode parsing (S##E##, ##x##)
│   ├── test_absolute_episodes.py    (32) Absolute episodes, season text, parentheses, dash, 3-digit
│   ├── test_movie_grouping.py       (18) Movie detection, year extraction
│   ├── test_series_with_articles.py (3)  Article normalization (The/A/An)
│   ├── test_penguin_grouping.py     (1)  Dual-name edge case
│   ├── test_search_relevance.py     (11) Search scoring algorithms
│   └── test_kodi_flow.py            (1)  Navigation workflow simulation
├── integration/                 # Network/API required
│   ├── test_csfd_integration.py     ⚠️  End-to-end CSFD workflow
│   ├── test_api_grouping.py         ⚠️  Live Webshare API
│   └── test_webshare_integration.py ⚠️  Full API + auth
├── external/
│   └── test_csfd_scraper.py         ⚠️  csfd_scraper.py module
├── docs/
│   └── test_cache_persistence.py    📚  Kodi cache behavior (educational)
├── run_all.sh / run_all.py      # Unit tests only
└── run_all_tests.sh             # All tests
```

## Key Details

**Library Structure (`lib/`)**: parsing, grouping, metadata, api, ui, routing, cache, database, playback, search

**Grouping Strategy**:
1. Parse filename → series/season/episode
2. CSFD lookup → dual-name detection
3. Canonical key: `lowercase_name|alt_name|year`
4. Group by key → rank by quality_score

**Quality Score (0-125)**: Resolution + Source + Codec + Audio + Repack/Proper

**Kodi Lifecycle**: Each navigation = new Python process → module cache resets

## Migration Status ✅

**10 test files migrated to lib/**, 2 unchanged (csfd_scraper, cache_persistence doc)
