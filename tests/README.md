# Test Suite

Tests series/movie grouping, CSFD integration, deduplication, search relevance,
persistence (cache, favorites, state), API error handling.

## Quick Start

```bash
./tests/run_all.sh              # unit tests (offline); same as: pytest tests/unit
./tests/run_all_tests.sh        # unit + integration
pytest tests/unit/test_cache.py # single file

# Skip live-network integration tests:
SKIP_LIVE_TESTS=1 pytest tests/
```

## Structure

```
tests/
├── conftest.py     # Kodi module mocks (xbmc, xbmcaddon, xbmcgui, ...)
├── unit/           # Offline tests, one file per lib module / concern
├── integration/    # Cached API fixtures; some files can hit the network
├── run_all.sh / run_all.py   # pytest tests/unit
└── run_all_tests.sh          # pytest tests
```

Tests are plain pytest: running a test file with `python file.py` does not
execute them; use `pytest`.

## Conventions

- Assert observable behaviour (inputs -> outputs, files on disk, Kodi calls),
  not a re-statement of the implementation.
- Time-dependent code (cache TTL): patch the clock, never `sleep`.
- Filesystem state goes in `tmp_path`; Kodi API is mocked by `conftest.py`.
