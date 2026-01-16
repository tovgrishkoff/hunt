#!/bin/bash
# Скрипт для установки asyncpg в контейнер account-manager

PROJECT=${1:-"ukraine"}
CONTAINER="${PROJECT}-account-manager"

echo "🔧 Установка asyncpg в контейнер ${CONTAINER}..."

docker exec ${CONTAINER} pip install asyncpg 2>&1

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ asyncpg установлен!"
    echo ""
    echo "Проверка:"
    docker exec ${CONTAINER} python3 -c "import asyncpg; print('✅ asyncpg работает')" 2>&1
else
    echo ""
    echo "❌ Ошибка установки asyncpg"
    exit 1
fi
