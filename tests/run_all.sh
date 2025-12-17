#!/bin/bash
# Run core tests (no network/API)

cd "$(dirname "$0")/.."

echo "=== Core Tests (no network) ==="
echo ""

passed=0
failed=0

for test in tests/unit/test_*.py; do
    name=$(basename "$test")
    echo -n "$name... "

    output=$(python3 "$test" 2>&1)
    if echo "$output" | grep -qi "pass\|success" || ! echo "$output" | grep -qi "fail\|error"; then
        echo "✓"
        ((passed++))
    else
        echo "✗"
        ((failed++))
    fi
done

echo ""
echo "=============================="
echo "Passed: $passed, Failed: $failed"

[ $failed -eq 0 ] && exit 0 || exit 1
