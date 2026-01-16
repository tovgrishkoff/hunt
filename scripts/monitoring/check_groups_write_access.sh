#!/bin/bash
# Скрипт-обертка для проверки прав на постинг в группах

echo "🔍 ПРОВЕРКА ПРАВ НА ПОСТИНГ В ГРУППАХ"
echo "=================================="
echo ""

cd "$(dirname "$0")/../.."

# Проверяем, запускаем ли мы из контейнера или с хоста
if [ -f "/.dockerenv" ] || [ -n "$DOCKER_CONTAINER" ]; then
    # Внутри контейнера
    python3 scripts/monitoring/check_groups_write_access.py
else
    # На хосте - запускаем в контейнере
    docker exec ukraine-account-manager python3 /app/scripts/monitoring/check_groups_write_access.py
fi
