#!/bin/bash
# Удобный скрипт для добавления аккаунтов и групп Ukraine в БД

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=" | head -c 80
echo ""
echo "📥 ДОБАВЛЕНИЕ ДАННЫХ UKRAINE/LEXUS В БД"
echo "=" | head -c 80
echo ""

cd "$PROJECT_DIR"

# Запускаем миграцию (скрипт работает на хосте)
echo ""
echo "🚀 Запуск миграции..."
python3 scripts/monitoring/add_ukraine_data_simple.py

echo ""
echo "✅ Готово!"
echo ""
echo "Проверка:"
docker exec ukraine-postgres psql -U telegram_user_ukraine -d ukraine_db -c "
SELECT 
    (SELECT COUNT(*) FROM accounts) as accounts,
    (SELECT COUNT(*) FROM targets WHERE niche = 'ukraine_cars') as groups;
" 2>&1
