#!/usr/bin/env bash
# Full pipeline: fresh texts → schedule from today → Notion sync
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"
[[ -f .env ]] && set -a && source .env && set +a

START_DAY="${1:-$(TZ=Asia/Makassar date +%F)}"
RUN_YT_PREVIEW="${RUN_YT_PREVIEW:-0}"

run() {
  if docker inspect -f '{{.State.Running}}' reels-autopost 2>/dev/null | grep -q true; then
    docker exec reels-autopost python -m uploader.main --tz Asia/Makassar "$@"
  else
    python3 -m uploader.main --tz Asia/Makassar "$@"
  fi
}

echo "== full_reels_pipeline start=$START_DAY =="
run rebuild-texts --min-reel-num 411
run schedule-crosspost --start-day "$START_DAY" --min-reel-num 411
if [[ "$RUN_YT_PREVIEW" == "1" ]]; then
  run sync-notion-schedule --min-reel-num 411 --yt-preview
else
  run sync-notion-schedule --min-reel-num 411
fi
echo "DONE. YT SEO at publish time via yt-autopost (Whisper+OpenAI)."
