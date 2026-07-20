#!/usr/bin/env bash
set -euo pipefail

# ========================================
# AgenticOS Production Build (Linux)
# ========================================
# Builds Mission Control frontend, compiles Rust/Tauri backend,
# generates installers (AppImage, DEB, RPM), portable archive, and checksums.
#
# Usage:
#   ./scripts/build.sh                 # Release build
#   ./scripts/build.sh --debug         # Debug build
#   ./scripts/build.sh --skip-frontend # Skip npm build
#   ./scripts/build.sh --skip-rust     # Skip cargo build
#
# Output: dist/artifacts/

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MISSION_DIR="$REPO_ROOT/apps/mission-control"
TAURI_DIR="$MISSION_DIR/src-tauri"
OUT_DIR="${OUT_DIR:-$REPO_ROOT/dist}"
ARTIFACTS_DIR="$OUT_DIR/artifacts"

# --- Color helpers ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
GRAY='\033[0;90m'
NC='\033[0m' # No Color

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  AgenticOS Production Build (Linux)${NC}"
echo -e "${CYAN}========================================${NC}"

# --- Parse args ---
CONFIG="Release"
SKIP_FRONTEND=false
SKIP_RUST=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --debug) CONFIG="Debug" ;;
        --skip-frontend) SKIP_FRONTEND=true ;;
        --skip-rust) SKIP_RUST=true ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
    shift
done

RELEASE_DIR="$(echo "$CONFIG" | tr '[:upper:]' '[:lower:]')"

# --- Prerequisites ---
echo -e "\n${YELLOW}[1/5] Checking prerequisites...${NC}"
MISSING=()

command -v node >/dev/null 2>&1 || MISSING+=("Node.js")
command -v npm >/dev/null 2>&1 || MISSING+=("npm")
command -v rustc >/dev/null 2>&1 || MISSING+=("Rust (rustc)")
command -v cargo >/dev/null 2>&1 || MISSING+=("Cargo")

if [ ${#MISSING[@]} -gt 0 ]; then
    echo -e "${RED}Missing prerequisites: ${MISSING[*]}${NC}" >&2
    echo -e "${YELLOW}Install missing tools:${NC}"
    echo "  Rust: https://rustup.rs"
    echo "  Node.js: https://nodejs.org"
    if ! command -v cargo >/dev/null 2>&1; then
        echo -e "${YELLOW}Rust/Cargo not found — will skip Tauri build step.${NC}"
        SKIP_RUST=true
    fi
fi

# Check Linux packaging tools
if [[ "$SKIP_RUST" == false ]]; then
    if ! command -v dpkg-deb >/dev/null 2>&1; then
        echo -e "${YELLOW}  Warning: dpkg-deb not found — DEB packaging may fail${NC}"
    fi
    if ! command -v rpmbuild >/dev/null 2>&1; then
        echo -e "${YELLOW}  Warning: rpmbuild not found — RPM packaging may fail${NC}"
    fi
fi

# --- Version Metadata ---
echo -e "\n${YELLOW}[2/5] Reading version metadata...${NC}"
APP_VERSION=$(python3 -c "
import json
with open('$TAURI_DIR/tauri.conf.json') as f:
    print(json.load(f)['version'])
")
PRODUCT_NAME=$(python3 -c "
import json
with open('$TAURI_DIR/tauri.conf.json') as f:
    print(json.load(f)['productName'])
")
COMMIT_HASH=$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo "unknown")
BUILD_DATE=$(date '+%Y-%m-%d %H:%M:%S')
GIT_TAG=$(git -C "$REPO_ROOT" describe --tags --exact-match 2>/dev/null || echo "untagged")

echo -e "  ${GREEN}Version:   $APP_VERSION${NC}"
echo -e "  ${GREEN}Commit:    $COMMIT_HASH${NC}"
echo -e "  ${GREEN}Tag:       $GIT_TAG${NC}"

# --- Output dirs ---
echo -e "\n${YELLOW}[3/5] Preparing output directories...${NC}"
mkdir -p "$ARTIFACTS_DIR"
echo -e "  ${GREEN}Output:    $OUT_DIR${NC}"
echo -e "  ${GREEN}Artifacts: $ARTIFACTS_DIR${NC}"

# --- Frontend build ---
if [ "$SKIP_FRONTEND" = false ]; then
    echo -e "\n${YELLOW}[4/5] Building Mission Control frontend...${NC}"
    pushd "$MISSION_DIR" >/dev/null

    echo -e "  ${GRAY}Installing npm dependencies...${NC}"
    npm ci --legacy-peer-deps 2>&1 | sed 's/^/    /'

    echo -e "  ${GRAY}Building Next.js static export...${NC}"
    npm run build 2>&1 | sed 's/^/    /'

    if [ ! -d "$MISSION_DIR/out" ]; then
        echo -e "${RED}Frontend build failed: 'out/' directory not found.${NC}" >&2
        exit 1
    fi
    echo -e "  ${GREEN}Frontend build complete.${NC}"

    popd >/dev/null
else
    echo -e "\n${YELLOW}[4/5] Skipping frontend build.${NC}"
fi

# --- Rust/Tauri build ---
BUNDLE_ARGS=""
if [ "$CONFIG" = "Debug" ]; then
    BUNDLE_ARGS="--debug"
fi
BUNDLE_ARGS="$BUNDLE_ARGS --bundles appimage,deb,rpm"

if [ "$SKIP_RUST" = false ]; then
    echo -e "\n${YELLOW}[5/5] Building Rust/Tauri backend...${NC}"
    pushd "$TAURI_DIR" >/dev/null

    echo -e "  ${GRAY}Running cargo tauri build (Config: $CONFIG)...${NC}"
    npx tauri build $BUNDLE_ARGS 2>&1 | sed 's/^/    /'

    echo -e "  ${GREEN}Tauri build complete.${NC}"
    popd >/dev/null
else
    echo -e "\n${YELLOW}[5/5] Skipping Rust/Tauri build.${NC}"
fi

# --- Collect artifacts ---
echo -e "\n${YELLOW}Collecting build artifacts...${NC}"

# Determine Rust target directory
RUST_TARGET="$(rustc -vV | grep 'host:' | awk '{print $2}')"
RUST_TARGET="${RUST_TARGET:-x86_64-unknown-linux-gnu}"
BUNDLE_DIR="$TAURI_DIR/target/$RUST_TARGET/$RELEASE_DIR/bundle"

if [ -d "$BUNDLE_DIR" ]; then
    echo -e "  ${GRAY}Copying bundle artifacts from $BUNDLE_DIR...${NC}"

    # AppImage
    for f in "$BUNDLE_DIR"/appimage/*.AppImage; do
        if [ -f "$f" ]; then
            dest="$ARTIFACTS_DIR/$PRODUCT_NAME-x86_64.AppImage"
            cp "$f" "$dest"
            echo -e "  ${GREEN}+ $(basename $dest)${NC}"
        fi
    done

    # DEB
    for f in "$BUNDLE_DIR"/deb/*.deb; do
        if [ -f "$f" ]; then
            dest="$ARTIFACTS_DIR/$PRODUCT_NAME-x86_64.deb"
            cp "$f" "$dest"
            echo -e "  ${GREEN}+ $(basename $dest)${NC}"
        fi
    done

    # RPM
    for f in "$BUNDLE_DIR"/rpm/*.rpm; do
        if [ -f "$f" ]; then
            dest="$ARTIFACTS_DIR/$PRODUCT_NAME-x86_64.rpm"
            cp "$f" "$dest"
            echo -e "  ${GREEN}+ $(basename $dest)${NC}"
        fi
    done
else
    echo -e "  ${YELLOW}Bundle directory not found: $BUNDLE_DIR${NC}"
    echo -e "  ${YELLOW}Artifact collection skipped. Build may have failed.${NC}"
fi

# --- Generate checksums ---
echo -e "\n${YELLOW}Generating SHA256 checksums...${NC}"
CHECKSUMS_FILE="$ARTIFACTS_DIR/SHA256SUMS.txt"
: > "$CHECKSUMS_FILE"

for f in "$ARTIFACTS_DIR"/*; do
    if [ -f "$f" ] && [ "$(basename "$f")" != "SHA256SUMS.txt" ]; then
        hash=$(sha256sum "$f" | awk '{print $1}')
        echo "$hash  $(basename "$f")" >> "$CHECKSUMS_FILE"
        echo -e "  ${GRAY}${hash:0:16}...  $(basename "$f")${NC}"
    fi
done

echo -e "  ${GREEN}Checksums saved: $CHECKSUMS_FILE${NC}"

# --- Installer report ---
echo -e "\n${YELLOW}Generating installer report...${NC}"
REPORT_PATH="$ARTIFACTS_DIR/installer-report.json"

# Build JSON with python
python3 -c "
import json, os

artifacts_dir = '$ARTIFACTS_DIR'
artifacts = []
for f in sorted(os.listdir(artifacts_dir)):
    fp = os.path.join(artifacts_dir, f)
    if os.path.isfile(fp) and f not in ('SHA256SUMS.txt', 'installer-report.json'):
        artifacts.append({
            'name': f,
            'size': os.path.getsize(fp),
            'path': fp
        })

report = {
    'version': '$APP_VERSION',
    'productName': '$PRODUCT_NAME',
    'commit': '$COMMIT_HASH',
    'buildDate': '$BUILD_DATE',
    'gitTag': '$GIT_TAG',
    'config': '$CONFIG',
    'platform': 'linux-x64',
    'artifacts': artifacts
}

with open('$REPORT_PATH', 'w') as f:
    json.dump(report, f, indent=2)

print('  Report: $REPORT_PATH')
"

# --- Summary ---
echo -e "\n${CYAN}========================================${NC}"
echo -e "${CYAN}  Build Complete${NC}"
echo -e "${CYAN}========================================${NC}"
echo -e "  ${GREEN}Version: $APP_VERSION${NC}"
echo -e "  ${GREEN}Commit:  $COMMIT_HASH${NC}"
echo -e "  ${GREEN}Output:  $ARTIFACTS_DIR${NC}"
echo ""

for f in "$ARTIFACTS_DIR"/*; do
    if [ -f "$f" ]; then
        size=$(stat --format=%s "$f" 2>/dev/null || stat -f%z "$f" 2>/dev/null)
        if [ "$size" -gt 1048576 ]; then
            size_str="$(echo "scale=2; $size / 1048576" | bc) MB"
        else
            size_str="$(echo "scale=0; $size / 1024" | bc) KB"
        fi
        echo -e "  $(basename "$f") ($size_str)"
    fi
done

echo -e "\n${CYAN}Done.${NC}"
