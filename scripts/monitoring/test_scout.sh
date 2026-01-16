#!/bin/bash
# Скрипт для тестирования Scout (поиск групп)

NICHE=${1:-"ukraine_cars"}

echo "=" | head -c 80
echo ""
echo "🔍 ТЕСТ SCOUT (Поиск групп)"
echo "=" | head -c 80
echo ""
echo "Ниша: $NICHE"
echo ""

docker exec ukraine-account-manager python3 services/account-manager/scout.py "$NICHE" 2>&1

echo ""
echo "✅ Тест завершен"
echo ""
echo "Проверка новых групп:"
docker exec ukraine-postgres psql -U telegram_user_ukraine -d ukraine_db -c "
SELECT COUNT(*) as new_groups
FROM targets 
WHERE status = 'new' AND niche = '$NICHE';
" 2>&1
