#!/usr/bin/env bash
set -euo pipefail

# ========================================
# AgenticOS Packaging (Linux)
# ========================================
# Validates and packages build artifacts for distribution.
#
# Usage:
#   ./scripts/package.sh
#   ./scripts/package.sh --artifacts-dir ./dist/artifacts --out-dir ./dist/packages
# ========================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TAURI_DIR="$REPO_ROOT/apps/mission-control/src-tauri"

ARTIFACTS_DIR="${ARTIFACTS_DIR:-$REPO_ROOT/dist/artifacts}"
OUT_DIR="${OUT_DIR:-$REPO_ROOT/dist/packages}"
VERSION="${VERSION:-}"

# Parse args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --artifacts-dir) ARTIFACTS_DIR="$2"; shift 2 ;;
        --out-dir) OUT_DIR="$2"; shift 2 ;;
        --version) VERSION="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

if [ -z "$VERSION" ]; then
    VERSION=$(python3 -c "
import json
with open('$TAURI_DIR/tauri.conf.json') as f:
    print(json.load(f)['version'])
")
fi

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  AgenticOS Packaging${NC}"
echo -e "${CYAN}========================================${NC}"

if [ ! -d "$ARTIFACTS_DIR" ]; then
    echo -e "${RED}Artifacts directory not found: $ARTIFACTS_DIR${NC}" >&2
    echo -e "${YELLOW}Run scripts/build.sh first.${NC}" >&2
    exit 1
fi

mkdir -p "$OUT_DIR"

# Validate artifacts
echo -e "\n${YELLOW}Validating artifacts...${NC}"
REQUIRED=(
    "AgenticOS-x86_64.AppImage"
    "AgenticOS-x86_64.deb"
    "AgenticOS-x86_64.rpm"
)
MISSING=()

for r in "${REQUIRED[@]}"; do
    path="$ARTIFACTS_DIR/$r"
    if [ -f "$path" ]; then
        size=$(stat --format=%s "$path" 2>/dev/null || stat -f%z "$path" 2>/dev/null)
        if [ "$size" -gt 1048576 ]; then
            size_str="$(echo "scale=2; $size / 1048576" | bc) MB"
        else
            size_str="$(echo "scale=0; $size / 1024" | bc) KB"
        fi
        echo -e "  ${GREEN}✓ $r ($size_str)${NC}"
    else
        echo -e "  ${RED}✗ $r (missing)${NC}"
        MISSING+=("$r")
    fi
done

# Copy artifacts to packages directory
echo -e "\n${YELLOW}Copying artifacts...${NC}"
cp "$ARTIFACTS_DIR"/* "$OUT_DIR/" 2>/dev/null || true

# Validate checksums
CHECKSUMS_FILE="$ARTIFACTS_DIR/SHA256SUMS.txt"
if [ -f "$CHECKSUMS_FILE" ]; then
    echo -e "\n${YELLOW}Validating SHA256 checksums...${NC}"
    while IFS= read -r line; do
        if echo "$line" | grep -qE '^[a-f0-9]+\s+'; then
            expected_hash=$(echo "$line" | awk '{print $1}')
            filename=$(echo "$line" | awk '{$1=""; print $0}' | sed 's/^ //')
            filepath="$OUT_DIR/$filename"
            if [ -f "$filepath" ]; then
                actual_hash=$(sha256sum "$filepath" | awk '{print $1}')
                if [ "$actual_hash" = "$expected_hash" ]; then
                    echo -e "  ${GREEN}✓ $filename${NC}"
                else
                    echo -e "  ${RED}✗ $filename (hash mismatch)${NC}"
                fi
            fi
        fi
    done < "$CHECKSUMS_FILE"
fi

# Generate release manifest
echo -e "\n${YELLOW}Generating release manifest...${NC}"
COMMIT_HASH=$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo "unknown")

python3 -c "
import json, os

out_dir = '$OUT_DIR'
required = ['AgenticOS-x86_64.AppImage', 'AgenticOS-x86_64.deb', 'AgenticOS-x86_64.rpm']
manifest = {
    'version': '$VERSION',
    'releaseDate': '$(date +%Y-%m-%d)',
    'platform': 'linux-x64',
    'architecture': 'x86_64',
    'artifacts': {}
}

for r in required:
    path = os.path.join(out_dir, r)
    if os.path.exists(path):
        import hashlib
        with open(path, 'rb') as f:
            h = hashlib.sha256(f.read()).hexdigest()
        manifest['artifacts'][r] = {
            'size': os.path.getsize(path),
            'sha256': h
        }

with open(os.path.join(out_dir, 'release-manifest.json'), 'w') as f:
    json.dump(manifest, f, indent=2)

print(f'  Manifest: {os.path.join(out_dir, \"release-manifest.json\")}')
"

# Summary
echo -e "\n${CYAN}========================================${NC}"
echo -e "${CYAN}  Package Summary${NC}"
echo -e "${CYAN}========================================${NC}"

if [ ${#MISSING[@]} -gt 0 ]; then
    echo -e "  ${YELLOW}Missing artifacts:${NC}"
    for m in "${MISSING[@]}"; do
        echo -e "  ${YELLOW}  · $m${NC}"
    done
else
    echo -e "  ${GREEN}All required artifacts present.${NC}"
fi

echo -e "  ${GREEN}Output: $OUT_DIR${NC}"
echo -e "\n${CYAN}Done.${NC}"
