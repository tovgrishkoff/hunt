#!/usr/bin/env bash
# 3 reels/day: IG + YT + Pinterest (if PINTEREST_* in .env), spread across days.
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"
[[ -f .env ]] && set -a && source .env && set +a

START="${1:-}"  # optional YYYY-MM-DD
ARGS=(--tz "${TZ:-Asia/Makassar}" schedule-crosspost
  --reels-dir "${READY_DIR:-output/reels}"
  --post-texts-dir "${INGEST_POST_TEXTS_DIR:-output/post_texts}"
  --ig-times "${UPLOAD_TIMES:-09:00,13:00,19:00}"
  --yt-times "${UPLOAD_YT_TIMES:-10:00,14:00,20:00}"
  --pinterest-times "${UPLOAD_PINTEREST_TIMES:-11:00,15:00,21:00}"
  --min-reel-num "${SCHEDULE_MIN_REEL_NUM:-411}"
)
[[ -n "$START" ]] && ARGS+=(--start-day "$START")

echo "== schedule_crosspost $(date -Is) start=${START:-today} =="
if docker inspect -f '{{.State.Running}}' reels-autopost 2>/dev/null | grep -q true; then
  docker exec reels-autopost python -m uploader.main "${ARGS[@]}"
else
  python3 -m uploader.main "${ARGS[@]}"
fi
echo "DONE"
