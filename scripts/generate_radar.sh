#!/usr/bin/env bash
# JZ3 Topic 205 — crontab entry point for JZ2 Market Radar
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

LOG_DIR="${RADAR_LOG_DIR:-$ROOT/logs}"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/radar-$(date +%Y%m%d).log"

export PYTHONUNBUFFERED=1

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

echo "[$(date -Iseconds)] radar start" >>"$LOG_FILE"
if python3 "$ROOT/scripts/radar.py" >>"$LOG_FILE" 2>&1; then
  echo "[$(date -Iseconds)] radar ok" >>"$LOG_FILE"
else
  code=$?
  echo "[$(date -Iseconds)] radar failed exit=$code" >>"$LOG_FILE"
  exit "$code"
fi
