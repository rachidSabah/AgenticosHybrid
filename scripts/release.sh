#!/usr/bin/env bash
set -euo pipefail

# ========================================
# AgenticOS Release (Linux)
# ========================================
# Creates a GitHub Release with all build artifacts.
#
# Usage:
#   ./scripts/release.sh v1.0.0-rc1
#   ./scripts/release.sh v1.0.0-rc1 --dry-run
#   CHANNEL=beta ./scripts/release.sh v1.0.0-rc1
# ========================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TAURI_DIR="$REPO_ROOT/apps/mission-control/src-tauri"

VERSION="${1:-}"
ARTIFACTS_DIR="${ARTIFACTS_DIR:-$REPO_ROOT/dist/packages}"
DRY_RUN="${DRY_RUN:-false}"
CHANNEL="${CHANNEL:-stable}"

# Parse args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=true; shift ;;
        *) VERSION="$1"; shift ;;
    esac
done

if [ -z "$VERSION" ]; then
    VERSION=$(python3 -c "
import json
with open('$TAURI_DIR/tauri.conf.json') as f:
    print('v' + json.load(f)['version'])
")
fi

[[ "$VERSION" == v* ]] || VERSION="v$VERSION"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
GRAY='\033[0;90m'
NC='\033[0m'

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  AgenticOS Release $VERSION${NC}"
echo -e "${CYAN}  Channel: $CHANNEL${NC}"
echo -e "${CYAN}========================================${NC}"

# Check prerequisites
HAS_GH=$(command -v gh >/dev/null && echo true || echo false)
HAS_CURL=$(command -v curl >/dev/null && echo true || echo false)

if [ "$HAS_GH" = false ] && [ "$HAS_CURL" = false ]; then
    echo -e "${RED}Either GitHub CLI (gh) or curl is required.${NC}" >&2
    echo -e "${YELLOW}Install gh: https://cli.github.com${NC}" >&2
    exit 1
fi

# Verify artifacts
echo -e "\n${YELLOW}Verifying release assets...${NC}"
REQUIRED_ASSETS=(
    "AgenticOS-x86_64.AppImage"
    "AgenticOS-x86_64.deb"
    "AgenticOS-x86_64.rpm"
    "SHA256SUMS.txt"
    "release-manifest.json"
)

ASSETS=()
MISSING_ASSETS=()

for r in "${REQUIRED_ASSETS[@]}"; do
    path="$ARTIFACTS_DIR/$r"
    if [ -f "$path" ]; then
        size=$(stat --format=%s "$path" 2>/dev/null || stat -f%z "$path" 2>/dev/null)
        if [ "$size" -gt 1048576 ]; then
            size_str="$(echo "scale=2; $size / 1048576" | bc) MB"
        else
            size_str="$(echo "scale=0; $size / 1024" | bc) KB"
        fi
        echo -e "  ${GREEN}✓ $r ($size_str)${NC}"
        ASSETS+=("$path")
    else
        echo -e "  ${RED}✗ $r (missing)${NC}"
        MISSING_ASSETS+=("$r")
    fi
done

if [ ${#MISSING_ASSETS[@]} -gt 0 ]; then
    echo -e "${YELLOW}Missing assets: ${MISSING_ASSETS[*]}${NC}" >&2
    echo -e "${YELLOW}Run scripts/build.sh then scripts/package.sh first.${NC}" >&2
    if [ "$DRY_RUN" = false ]; then
        echo -e "${YELLOW}Continue without these assets? (y/N)${NC}"
        read -r CONTINUE
        [ "$CONTINUE" != "y" ] && exit 1
    fi
fi

# Generate release notes
echo -e "\n${YELLOW}Generating release notes...${NC}"
LAST_TAG=$(git -C "$REPO_ROOT" describe --tags --abbrev=0 2>/dev/null || echo "")
COMMITS_SINCE=""
if [ -n "$LAST_TAG" ]; then
    COMMITS_SINCE=$(git -C "$REPO_ROOT" log --oneline "$LAST_TAG"..HEAD 2>/dev/null || echo "Initial release.")
else
    COMMITS_SINCE="Initial release."
fi

NOTES_PATH="$ARTIFACTS_DIR/release-notes.md"
cat > "$NOTES_PATH" << EOF
## AgenticOS $VERSION

**Channel:** $CHANNEL

### Installation

**Linux:**
- **AppImage**: Download \`AgenticOS-x86_64.AppImage\`, chmod +x, and run
- **DEB**: Download \`AgenticOS-x86_64.deb\` and run \`sudo dpkg -i\`
- **RPM**: Download \`AgenticOS-x86_64.rpm\` and run \`sudo rpm -i\`

### System Requirements
- Linux x86_64, glibc >= 2.28
- GTK3, WebKit2GTK

### Changelog

$COMMITS_SINCE

### Checksums

See \`SHA256SUMS.txt\` attached to this release.

### Assets
EOF

for a in "${ASSETS[@]}"; do
    echo "- $(basename "$a")" >> "$NOTES_PATH"
done

echo -e "  ${GREEN}Release notes: $NOTES_PATH${NC}"

# Dry run
if [ "$DRY_RUN" = true ]; then
    echo -e "\n${YELLOW}[DRY RUN] Would create release:${NC}"
    echo -e "  ${GRAY}Tag: $VERSION${NC}"
    echo -e "  ${GRAY}Assets:${NC}"
    for a in "${ASSETS[@]}"; do
        echo -e "  ${GRAY}  - $a${NC}"
    done
    echo -e "\n${CYAN}Dry run complete.${NC}"
    exit 0
fi

# Create release
echo -e "\n${YELLOW}Creating GitHub Release $VERSION...${NC}"

if [ "$HAS_GH" = true ]; then
    GH_ARGS=(
        release create "$VERSION"
        --title "AgenticOS $VERSION"
        --notes-file "$NOTES_PATH"
        --target main
    )

    if [ "$CHANNEL" != "stable" ]; then
        GH_ARGS+=(--prerelease)
    fi

    for a in "${ASSETS[@]}"; do
        GH_ARGS+=("$a")
    done

    echo -e "  ${GRAY}Running: gh ${GH_ARGS[*]}${NC}"
    gh "${GH_ARGS[@]}" 2>&1 | sed 's/^/  /'

    if [ -n "$LASTEXITCODE" ] && [ "$LASTEXITCODE" -ne 0 ]; then
        echo -e "${RED}Release creation failed.${NC}" >&2
        exit 1
    fi
else
    # GitHub API fallback
    TOKEN="${GITHUB_TOKEN:-}"
    if [ -z "$TOKEN" ]; then
        echo -e "${RED}GITHUB_TOKEN env var is required when gh CLI is not available.${NC}" >&2
        exit 1
    fi

    REPO="rachidSabah/AgenticosHybrid"
    API_URL="https://api.github.com/repos/$REPO/releases"
    NOTES_CONTENT=$(cat "$NOTES_PATH")

    JSON_BODY=$(python3 -c "
import json
body = {
    'tag_name': '$VERSION',
    'target_commitish': 'main',
    'name': 'AgenticOS $VERSION',
    'body': '''$NOTES_CONTENT''',
    'prerelease': $( [ "$CHANNEL" = "stable" ] && echo false || echo true )
}
print(json.dumps(body))
")

    echo -e "  ${GRAY}Creating release via API...${NC}"
    RESPONSE=$(curl -s -X POST \
        -H "Authorization: token $TOKEN" \
        -H "Content-Type: application/json" \
        "$API_URL" \
        -d "$JSON_BODY")

    RELEASE_ID=$(echo "$RESPONSE" | python3 -c "import json,sys; print(json.load(sys.stdin).get('id', ''))")

    if [ -z "$RELEASE_ID" ]; then
        ERROR_MSG=$(echo "$RESPONSE" | python3 -c "import json,sys; print(json.load(sys.stdin).get('message', 'unknown'))")
        echo -e "${RED}Release failed: $ERROR_MSG${NC}" >&2
        exit 1
    fi

    echo -e "  ${GREEN}Release created: https://github.com/$REPO/releases/tag/$VERSION${NC}"

    # Upload assets
    echo -e "  ${YELLOW}Uploading assets...${NC}"
    UPLOAD_URL="https://uploads.github.com/repos/$REPO/releases/$RELEASE_ID/assets"

    for a in "${ASSETS[@]}"; do
        FILENAME=$(basename "$a")
        echo -e "  ${GRAY}Uploading $FILENAME...${NC}"
        curl -s -X POST \
            -H "Authorization: token $TOKEN" \
            -H "Content-Type: application/octet-stream" \
            "$UPLOAD_URL?name=$FILENAME" \
            --data-binary "@$a" > /dev/null
        echo -e "  ${GREEN}  ✓ $FILENAME uploaded${NC}"
    done
fi

echo -e "\n${CYAN}========================================${NC}"
echo -e "${CYAN}  Release $VERSION published!${NC}"
echo -e "${CYAN}========================================${NC}"
echo -e "  ${GREEN}https://github.com/rachidSabah/AgenticosHybrid/releases/tag/$VERSION${NC}"
echo -e "\n${CYAN}Done.${NC}"
