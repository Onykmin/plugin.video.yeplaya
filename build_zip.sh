#!/bin/bash
# Build ZIP for Kodi addon distribution

set -e  # Exit on error

cd "$(dirname "$0")"

# Parse addon.xml for single source of truth
ADDON_ID=$(grep '<addon' addon.xml | sed -n 's/.*id="\([^"]*\)".*/\1/p')
VERSION=$(grep '<addon' addon.xml | sed -n 's/.*version="\([^"]*\)".*/\1/p')
EXPORT_DIR="exports"
ZIP_NAME="${ADDON_ID}-${VERSION}.zip"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}Building Kodi addon ZIP...${NC}"

# Clean old ZIP
if [ -f "${EXPORT_DIR}/${ZIP_NAME}" ]; then
    echo "Removing old ZIP..."
    rm -f "${EXPORT_DIR}/${ZIP_NAME}"
fi

# Create exports directory if needed
mkdir -p "${EXPORT_DIR}"

# Create ZIP (from parent directory to get correct structure)
echo "Creating ZIP..."
cd ..
zip -r "${ADDON_ID}/${EXPORT_DIR}/${ZIP_NAME}" "${ADDON_ID}" \
    -x "${ADDON_ID}/.git/*" \
    -x "${ADDON_ID}/.github/*" \
    -x "${ADDON_ID}/__pycache__/*" \
    -x "${ADDON_ID}/.idea/*" \
    -x "${ADDON_ID}/.vscode/*" \
    -x "${ADDON_ID}/.claude/*" \
    -x "${ADDON_ID}/exports/*" \
    -x "${ADDON_ID}/tests/*" \
    -x "${ADDON_ID}/repository.yeplaya/*" \
    -x "${ADDON_ID}/*.pyc" \
    -x "${ADDON_ID}/.gitignore" \
    -x "${ADDON_ID}/LICENSE" \
    -x "${ADDON_ID}/README.md" \
    -x "${ADDON_ID}/build_zip.sh" \
    -x "${ADDON_ID}/build_zip.py" \
    -x "${ADDON_ID}/repo_generator.py" \
    -q

cd "${ADDON_ID}"

# Show result
echo -e "${GREEN}✓ ZIP created successfully${NC}"
ls -lh "${EXPORT_DIR}/${ZIP_NAME}"
echo ""
# Cross-platform SHA256
if command -v sha256sum &> /dev/null; then
    echo "SHA256: $(sha256sum ${EXPORT_DIR}/${ZIP_NAME} | awk '{print $1}')"
else
    echo "SHA256: $(shasum -a 256 ${EXPORT_DIR}/${ZIP_NAME} | awk '{print $1}')"
fi
echo ""
echo -e "${GREEN}Ready to install in Kodi!${NC}"
