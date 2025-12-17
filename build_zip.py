#!/usr/bin/env python3
"""Build Kodi addon ZIP for distribution"""

import os
import subprocess
import sys
import xml.etree.ElementTree as ET

# Parse addon.xml for single source of truth
tree = ET.parse('addon.xml')
root = tree.getroot()
ADDON_ID = root.get('id')
VERSION = root.get('version')
EXPORT_DIR = 'exports'
ZIP_NAME = f'{ADDON_ID}-{VERSION}.zip'

def main():
    print('=' * 70)
    print('Building Kodi addon ZIP')
    print('=' * 70)
    print()

    # Save current directory
    start_dir = os.getcwd()

    try:
        # Clean old ZIP
        zip_path = os.path.join(EXPORT_DIR, ZIP_NAME)
        if os.path.exists(zip_path):
            print(f'Removing old ZIP: {ZIP_NAME}')
            os.remove(zip_path)

        # Create exports directory
        os.makedirs(EXPORT_DIR, exist_ok=True)

        # Create ZIP from parent directory
        print(f'Creating ZIP: {ZIP_NAME}')
        os.chdir('..')

        result = subprocess.run([
            'zip', '-r', f'{ADDON_ID}/{EXPORT_DIR}/{ZIP_NAME}', ADDON_ID,
            '-x', f'{ADDON_ID}/.git/*',
            '-x', f'{ADDON_ID}/__pycache__/*',
            '-x', f'{ADDON_ID}/.idea/*',
            '-x', f'{ADDON_ID}/.vscode/*',
            '-x', f'{ADDON_ID}/.claude/*',
            '-x', f'{ADDON_ID}/exports/*',
            '-x', f'{ADDON_ID}/tests/*',
            '-x', '*.pyc',
            '-x', f'{ADDON_ID}/.gitignore',
            '-x', f'{ADDON_ID}/LICENSE',
            '-x', f'{ADDON_ID}/README.md',
            '-x', f'{ADDON_ID}/build_zip.sh',
            '-x', f'{ADDON_ID}/build_zip.py',
            '-q'
        ], check=True)

        os.chdir(ADDON_ID)

        # Show result
        print()
        print('=' * 70)
        print('✓ ZIP created successfully')
        print('=' * 70)
        print()

        subprocess.run(['ls', '-lh', zip_path])
        print()

        result = subprocess.run(['sha256sum', zip_path], capture_output=True, text=True)
        checksum = result.stdout.split()[0] if result.stdout else 'N/A'
        print(f'SHA256: {checksum}')
        print()
        print(f'Location: {os.path.abspath(zip_path)}')
        print()
        print('=' * 70)
        print('Ready to install in Kodi!')
        print('=' * 70)

    except subprocess.CalledProcessError as e:
        print(f'✗ Error creating ZIP: {e}', file=sys.stderr)
        return 1
    except Exception as e:
        print(f'✗ Error: {e}', file=sys.stderr)
        return 1
    finally:
        os.chdir(start_dir)

    return 0

if __name__ == '__main__':
    sys.exit(main())
