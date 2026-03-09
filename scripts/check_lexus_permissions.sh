#!/bin/bash
# Проверка прав на постинг в группах Lexus и обновление can_post в БД
# Запуск: ./scripts/check_lexus_permissions.sh [--limit N] [--dry-run]

cd "$(dirname "$0")/.."

if ! docker ps --format "{{.Names}}" | grep -q "^lexus-marketer$"; then
    echo "❌ Контейнер lexus-marketer не запущен!"
    echo "   Запустите: docker-compose -f docker-compose.lexus.yml up -d lexus-marketer"
    exit 1
fi

echo "🔍 Проверка прав на постинг в группах Lexus..."
docker exec lexus-marketer python3 /app/scripts/check_lexus_permissions_and_update_db.py "$@"
