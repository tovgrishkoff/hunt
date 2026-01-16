#!/bin/bash
# Скрипт для инициализации БД Ukraine

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "🔧 Инициализация БД Ukraine..."
echo ""

# Используем SQL скрипт
docker exec -i ukraine-postgres psql -U telegram_user_ukraine -d ukraine_db < "$SCRIPT_DIR/init_ukraine_db.sql" 2>&1

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ БД успешно инициализирована!"
    echo ""
    echo "Проверка таблиц:"
    docker exec ukraine-postgres psql -U telegram_user_ukraine -d ukraine_db -c "\dt" 2>&1
else
    echo ""
    echo "❌ Ошибка при инициализации БД"
    exit 1
fi
