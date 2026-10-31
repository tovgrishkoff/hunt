#!/usr/bin/env bash
# Scan output/reels for new R###.mov → IG caption + Notion + queue (no batch CSV required).
# text_id: render_results.csv → sidecar R411.json → plan CSV → auto R411→T001, R412→T002…
# Optional: upload output/render_results.csv from local render for exact text_id mapping.
# Cron: */15 * * * * …/scripts/ingest_new_reels.sh >> …/output/logs/ingest.log 2>&1
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

USE_DOCKER="${INGEST_USE_DOCKER:-1}"
TZ_NAME="${TZ:-Asia/Makassar}"
ARGS=(
  --tz "$TZ_NAME"
  ingest-reels
  --reels-dir "${READY_DIR:-output/reels}"
  --texts "${UPLOAD_TEXTS_CSV:-texts_kailas.csv}"
  --post-texts-dir "${INGEST_POST_TEXTS_DIR:-output/post_texts}"
)

if [[ -n "${INGEST_PLAN_CSV:-}" ]]; then
  ARGS+=(--plan "$INGEST_PLAN_CSV")
fi
if [[ "${INGEST_YT_PREVIEW:-0}" == "1" ]]; then
  ARGS+=(--yt-preview)
fi
if [[ "${INGEST_NOTION_PREFILL:-1}" != "0" ]]; then
  ARGS+=(--notion-prefill)
fi
# Queue slots: run schedule-crosspost.sh after ingest (3/day IG+YT).
if [[ "${INGEST_AUTO_PLAN_IG:-0}" == "1" ]]; then
  ARGS+=(--auto-plan-ig)
fi
if [[ "${INGEST_AUTO_PLAN_YT:-0}" == "1" ]]; then
  ARGS+=(--auto-plan-yt)
fi

echo "== ingest_new_reels $(date -Is) =="

if [[ "$USE_DOCKER" == "1" ]] && docker inspect -f '{{.State.Running}}' reels-autopost 2>/dev/null | grep -q true; then
  docker exec reels-autopost python -m uploader.main "${ARGS[@]}"
else
  python3 -m uploader.main "${ARGS[@]}"
fi

# Optional: auto-schedule new reels (copy_*.MOV, R###.mov) not yet in queue
if [[ "${INGEST_AUTO_SCHEDULE:-1}" == "1" ]]; then
  WATCH_ARGS=(--tz "$TZ_NAME" watch-reels
    --reels-dir "${READY_DIR:-output/reels}"
    --texts "${UPLOAD_TEXTS_CSV:-texts_kailas.csv}"
    --post-texts-dir "${INGEST_POST_TEXTS_DIR:-output/post_texts}"
  )
  if [[ "$USE_DOCKER" == "1" ]] && docker inspect -f '{{.State.Running}}' reels-autopost 2>/dev/null | grep -q true; then
    docker exec reels-autopost python -m uploader.main "${WATCH_ARGS[@]}"
  else
    python3 -m uploader.main "${WATCH_ARGS[@]}"
  fi
fi

echo "DONE"
