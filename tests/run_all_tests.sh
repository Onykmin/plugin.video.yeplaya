#!/bin/bash
# Run ALL tests (unit + integration). Integration tests that need the network
# skip themselves when SKIP_LIVE_TESTS=1 or their cached fixtures are missing.

cd "$(dirname "$0")/.." || exit 1
exec python3 -m pytest tests -q "$@"
