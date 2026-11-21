#!/usr/bin/env bash
# Lead Hunter: разбор очереди лидов → first_touch ЛС.
# Host cron is UTC; fire during UTC 01–12 (= Asia/Makassar 09–20).
# Script also guards local work hours + flock.
#
# Example crontab:
#   15,45 1-12 * * * TZ=Asia/Makassar /home/tovgrishkoff/PIAR/telegram_promotion_system_bali/scripts/leadhunter_outreach_send.sh

set -euo pipefail
export TZ="${TZ:-Asia/Makassar}"

ROOT="/home/tovgrishkoff/PIAR/telegram_promotion_system_bali"
cd "$ROOT"
PY="$ROOT/.venv/bin/python3"
LOG="$ROOT/logs/leadhunter_outreach_send.log"
LOCK="/tmp/leadhunter_outreach_send.lock"
# Soft: config still caps max_dm_per_run / per-account daily
LIMIT="${SEND_LIMIT:-1}"

mkdir -p "$ROOT/logs"

hour="$(date +%H)"
hour=$((10#$hour))
if (( hour < 9 || hour >= 21 )); then
  exit 0
fi

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "$(date -Is) skip: already running" >>"$LOG"
  exit 0
fi

{
  echo "===== LH SEND $(date) ====="
  "$PY" scripts/leadhunter_outreach.py send --live --limit "$LIMIT"
  echo "===== DONE $(date) ====="
} >>"$LOG" 2>&1
