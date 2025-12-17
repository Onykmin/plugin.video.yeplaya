#!/bin/bash
# Run ALL tests (including network/API)

cd "$(dirname "$0")/.."

echo "=== All Tests (including network/API) ==="
echo ""

passed=0
failed=0

for dir in tests/unit tests/integration tests/external tests/docs; do
    [ -d "$dir" ] || continue
    for test in "$dir"/test_*.py; do
        [ -f "$test" ] || continue
        name=$(basename "$test")
        echo -n "$(basename $(dirname $test))/$name... "

        output=$(python3 "$test" 2>&1)
        if echo "$output" | grep -qi "pass\|success" || ! echo "$output" | grep -qi "fail\|error"; then
            echo "✓"
            ((passed++))
        else
            echo "✗"
            ((failed++))
        fi
    done
done

echo ""
echo "=============================="
echo "Passed: $passed, Failed: $failed"

[ $failed -eq 0 ] && exit 0 || exit 1
