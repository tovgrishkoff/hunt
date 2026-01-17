#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="/home/tovgrishkoff/PIAR/telegram_promotion_system_bali"
LOG_DIR="${REPO_DIR}/data/logs"

if [ ! -d "${REPO_DIR}/.git" ]; then
  exit 0
fi

mkdir -p "${LOG_DIR}"

cd "${REPO_DIR}"

if [ -z "$(git status --porcelain)" ]; then
  exit 0
fi

export GIT_AUTHOR_NAME="autosave"
export GIT_AUTHOR_EMAIL="autosave@local"
export GIT_COMMITTER_NAME="autosave"
export GIT_COMMITTER_EMAIL="autosave@local"

git add -A
git commit -m "chore: autosave $(date -u '+%Y-%m-%d %H:%M:%S UTC')" >/dev/null

# Push if remote is configured
if git remote get-url origin >/dev/null 2>&1; then
  git push origin main >> "${LOG_DIR}/git_autosave.log" 2>&1 || true
fi
