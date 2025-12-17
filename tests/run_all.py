#!/usr/bin/env python3
"""Run core tests (no network/API)"""

import sys
import subprocess
from pathlib import Path

def main():
    tests_dir = Path(__file__).parent
    unit_dir = tests_dir / 'unit'
    passed = failed = 0

    print("=== Core Tests (no network) ===\n")

    for test in sorted(unit_dir.glob('test_*.py')):
        print(f"{test.name}...", end=" ")
        result = subprocess.run([sys.executable, test], capture_output=True)

        if result.returncode == 0:
            print("✓")
            passed += 1
        else:
            print("✗")
            failed += 1

    print(f"\n{'='*30}")
    print(f"Passed: {passed}, Failed: {failed}")
    return 1 if failed else 0

if __name__ == '__main__':
    sys.exit(main())
