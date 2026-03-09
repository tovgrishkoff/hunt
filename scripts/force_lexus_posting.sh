#!/bin/bash
# Удобная обертка для форс-постинга Lexus

BATCH_SIZE=${1:-20}
DRY_RUN=${2:-}

# Копируем скрипт в контейнер (если нужно)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
docker cp "$SCRIPT_DIR/force_lexus_posting.py" lexus-marketer:/app/force_lexus_posting.py 2>/dev/null

if [ "$DRY_RUN" == "dry-run" ] || [ "$DRY_RUN" == "--dry-run" ]; then
    docker exec lexus-marketer python3 /app/force_lexus_posting.py --batch-size "$BATCH_SIZE" --dry-run
else
    docker exec lexus-marketer python3 /app/force_lexus_posting.py --batch-size "$BATCH_SIZE"
fi
