#!/bin/bash
# Run core tests (offline): the unit suite under pytest.

cd "$(dirname "$0")/.." || exit 1
exec python3 -m pytest tests/unit -q "$@"
