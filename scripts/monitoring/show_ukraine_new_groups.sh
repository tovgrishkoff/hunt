#!/bin/bash
# Скрипт для отображения списка новых групп (статус: new)

LIMIT=${1:-100}

echo "📋 Список новых групп (status='new', niche='ukraine_cars')"
echo "Лимит: $LIMIT"
echo "=" | head -c 80 && echo ""

docker exec ukraine-postgres psql -U telegram_user_ukraine -d ukraine_db -c "
SELECT 
    id,
    link,
    COALESCE(title, 'N/A') as title,
    niche,
    status,
    TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') as created
FROM targets 
WHERE status = 'new' AND niche = 'ukraine_cars' 
ORDER BY id 
LIMIT $LIMIT;
" 2>&1

echo ""
echo "Всего новых групп:"
docker exec ukraine-postgres psql -U telegram_user_ukraine -d ukraine_db -t -c "SELECT COUNT(*) FROM targets WHERE status = 'new' AND niche = 'ukraine_cars';" 2>&1
