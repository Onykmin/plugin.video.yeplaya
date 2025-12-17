#!/usr/bin/env python3
"""
Kodi Repository Generator
Builds addon zips and generates addons.xml catalog
"""

import os
import hashlib
import shutil
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).parent
REPO_DIR = REPO_ROOT / "repository.yeplaya"
ZIPS_DIR = REPO_DIR / "zips"

# Addons to include in repository
# Note: plugin.video.yeplaya is the root directory itself
ADDONS = [
    ".",  # Current directory is plugin.video.yeplaya
    "repository.yeplaya"
]

EXCLUDED_DIRS = {
    '.git', '.github', '.idea', '__pycache__',
    'tests', 'exports', '.claude', 'lib/__pycache__',
    'repository.yeplaya'  # Don't include repo folder in plugin zip
}

EXCLUDED_FILES = {
    '.gitignore', '.gitattributes', 'build_zip.py', 'build_zip.sh',
    'repo_generator.py', '.DS_Store', 'LICENSE', 'README.md'
}


def get_addon_info(addon_path):
    """Extract addon id and version from addon.xml"""
    addon_xml = addon_path / "addon.xml"
    if not addon_xml.exists():
        raise FileNotFoundError(f"addon.xml not found in {addon_path}")

    tree = ET.parse(addon_xml)
    root = tree.getroot()

    addon_id = root.get("id")
    version = root.get("version")

    return addon_id, version, tree


def create_addon_zip(addon_path_str):
    """Create zip file for addon"""
    if addon_path_str == ".":
        addon_path = REPO_ROOT
    else:
        addon_path = REPO_ROOT / addon_path_str

    if not addon_path.exists():
        print(f"⚠️  Addon {addon_path_str} not found, skipping")
        return None

    addon_id, version, _ = get_addon_info(addon_path)

    # Create addon-specific zip directory
    addon_zip_dir = ZIPS_DIR / addon_id
    addon_zip_dir.mkdir(parents=True, exist_ok=True)

    zip_path = addon_zip_dir / f"{addon_id}-{version}.zip"

    print(f"📦 Building {addon_id} v{version}...")

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(addon_path):
            # Filter out excluded directories
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]

            for file in files:
                if file in EXCLUDED_FILES:
                    continue

                file_path = Path(root) / file
                arcname = file_path.relative_to(addon_path.parent)
                zipf.write(file_path, arcname)

    print(f"   ✓ Created {zip_path.name}")
    return addon_id, version


def generate_addons_xml():
    """Generate addons.xml catalog"""
    print("\n📝 Generating addons.xml...")

    addons_root = ET.Element("addons")

    for addon_path_str in ADDONS:
        if addon_path_str == ".":
            addon_path = REPO_ROOT
        else:
            addon_path = REPO_ROOT / addon_path_str

        if not addon_path.exists():
            continue

        _, _, tree = get_addon_info(addon_path)
        addon_element = tree.getroot()
        addons_root.append(addon_element)

    # Write addons.xml
    addons_xml_path = ZIPS_DIR / "addons.xml"
    tree = ET.ElementTree(addons_root)
    ET.indent(tree, space="    ")
    tree.write(addons_xml_path, encoding="UTF-8", xml_declaration=True)

    print(f"   ✓ Created addons.xml")

    # Generate MD5 checksum
    md5_hash = hashlib.md5()
    with open(addons_xml_path, 'rb') as f:
        md5_hash.update(f.read())

    md5_path = ZIPS_DIR / "addons.xml.md5"
    with open(md5_path, 'w') as f:
        f.write(md5_hash.hexdigest())

    print(f"   ✓ Created addons.xml.md5: {md5_hash.hexdigest()}")


def copy_addon_xml_to_zips():
    """Copy addon.xml files to zip directories for Kodi compatibility"""
    for addon_path_str in ADDONS:
        if addon_path_str == ".":
            addon_path = REPO_ROOT
        else:
            addon_path = REPO_ROOT / addon_path_str

        if not addon_path.exists():
            continue

        # Get actual addon ID
        addon_id, _, _ = get_addon_info(addon_path)

        source_xml = addon_path / "addon.xml"
        dest_dir = ZIPS_DIR / addon_id
        dest_xml = dest_dir / "addon.xml"

        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_xml, dest_xml)


def main():
    print("🚀 Kodi Repository Generator\n")
    print(f"Repository: {REPO_DIR}")
    print(f"Output: {ZIPS_DIR}\n")

    # Clean zips directory
    if ZIPS_DIR.exists():
        print("🧹 Cleaning old zips...")
        shutil.rmtree(ZIPS_DIR)

    ZIPS_DIR.mkdir(parents=True)

    # Build addon zips
    built_addons = []
    for addon_id in ADDONS:
        result = create_addon_zip(addon_id)
        if result:
            built_addons.append(result)

    # Copy addon.xml files
    copy_addon_xml_to_zips()

    # Generate addons.xml catalog
    generate_addons_xml()

    print("\n✅ Repository generation complete!\n")
    print(f"Built {len(built_addons)} addon(s):")
    for addon_id, version in built_addons:
        print(f"   • {addon_id} v{version}")

    print(f"\n📂 Repository ready at: {ZIPS_DIR}")
    print("\nNext steps:")
    print("1. Commit and push repository.yeplaya/ to GitHub")
    print("2. Users install: repository.yeplaya-1.0.0.zip")
    print("3. Automatic updates enabled! 🎉")


if __name__ == "__main__":
    main()
