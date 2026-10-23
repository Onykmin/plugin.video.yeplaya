#!/usr/bin/env python3
"""Run core tests (offline): the unit suite under pytest."""

import subprocess
import sys
from pathlib import Path


def main():
    tests_dir = Path(__file__).parent
    return subprocess.call([sys.executable, '-m', 'pytest', str(tests_dir / 'unit'), '-q'])


if __name__ == '__main__':
    sys.exit(main())
