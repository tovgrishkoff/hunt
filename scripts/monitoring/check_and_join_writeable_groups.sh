#!/bin/bash
# Скрипт-обертка для проверки и вступления в группы, где можно постить

echo "🔍 ПРОВЕРКА И ВСТУПЛЕНИЕ В ГРУППЫ (где можно постить)"
echo "======================================================"
echo ""

cd "$(dirname "$0")/../.."

# Запускаем в контейнере (поддержка разных имен сервиса)
if docker ps --format '{{.Names}}' | grep -q '^ukraine-account-manager$'; then
  CONTAINER_NAME="ukraine-account-manager"
elif docker ps --format '{{.Names}}' | grep -q '^telegram-bali-account-manager$'; then
  CONTAINER_NAME="telegram-bali-account-manager"
else
  echo "Error: No account-manager container found (ukraine-account-manager or telegram-bali-account-manager)"
  exit 1
fi

docker exec "$CONTAINER_NAME" python3 /app/scripts/monitoring/check_and_join_writeable_groups.py
