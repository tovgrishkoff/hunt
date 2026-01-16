#!/bin/bash
# Скрипт для запуска импорта данных
# Автоматически определяет DATABASE_URL

cd "$(dirname "$0")/.."

# Проверяем, запущен ли PostgreSQL контейнер
if docker ps | grep -q "telegram-postgres-promotion-advanced"; then
    echo "✅ Found existing PostgreSQL container"
    export DATABASE_URL="postgresql://telegram_user:telegram_password@localhost:5437/telegram_promotion"
elif docker ps | grep -q "telegram-combine-postgres"; then
    echo "✅ Found new PostgreSQL container"
    export DATABASE_URL="postgresql://telegram_user:telegram_password@localhost:5437/telegram_promotion"
else
    echo "⚠️ PostgreSQL container not found. Starting..."
    docker-compose up -d postgres
    sleep 5
    export DATABASE_URL="postgresql://telegram_user:telegram_password@localhost:5437/telegram_promotion"
fi

# Установка DATABASE_URL
export DATABASE_URL="postgresql://telegram_user:telegram_password@localhost:5437/telegram_promotion"
echo "📊 Using DATABASE_URL: postgresql://telegram_user:***@localhost:5437/telegram_promotion"

# Инициализация БД
echo "📊 Initializing database..."
python3 -c "from shared.database.session import init_db; init_db(); print('✅ Database tables created')" || {
    echo "❌ Failed to initialize database"
    exit 1
}

# Импорт аккаунтов
echo ""
echo "📥 Importing accounts..."
export DATABASE_URL="postgresql://telegram_user:telegram_password@localhost:5437/telegram_promotion"
python3 scripts/import_all_accounts.py || {
    echo "❌ Failed to import accounts"
    exit 1
}

# Импорт групп
echo ""
echo "📥 Importing groups..."
export DATABASE_URL="postgresql://telegram_user:telegram_password@localhost:5437/telegram_promotion"
python3 scripts/import_groups.py --niche cars || {
    echo "❌ Failed to import groups"
    exit 1
}

echo ""
echo "✅ Import completed successfully!"

