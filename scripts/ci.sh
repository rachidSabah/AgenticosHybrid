#!/usr/bin/env bash
# Local CI sequence for Agentic OS.
# Runs ruff (format+check), ty, and pytest — mirroring GitHub CI.
set -euo pipefail
cd "$(dirname "$0")/.."

RUN="uv run"
ONLY=""
SKIP=""
DRY=""

for arg in "$@"; do
  case "$arg" in
    --only=*) ONLY="${arg#*=}" ;;
    --skip=*) SKIP="${arg#*=}" ;;
    --dry-run) DRY=1 ;;
  esac
done

should_run() {
  local id="$1"
  [[ -z "$ONLY" || "$ONLY" == "$id" ]] && { [[ -z "$SKIP" ]] || "$SKIP" != "$id" ]; }
}

run_cmd() { echo "▶ $*"; [[ -z "$DRY" ]] && "$@"; }

should_run format && run_cmd $RUN ruff format
should_run check  && run_cmd $RUN ruff check
should_run ty     && run_cmd $RUN ty check
should_run test   && run_cmd $RUN pytest -v --tb=short

should_run frontend && {
  echo "▶ frontend: typecheck / lint / test / build"
  if [[ -z "$DRY" ]]; then
    cd apps/mission-control
    npm ci --legacy-peer-deps
    npm run typecheck
    npm run lint
    npm run test
    npm run build
    cd - >/dev/null
  fi
}

echo "CI sequence complete."
