#!/bin/bash
# Скрипт для тестирования Smart Joiner (вступление в группы)

NICHE=${1:-"ukraine_cars"}
BATCH_SIZE=${2:-3}

echo "=" | head -c 80
echo ""
echo "🚪 ТЕСТ SMART JOINER (Вступление в группы)"
echo "=" | head -c 80
echo ""
echo "Ниша: $NICHE"
echo "Размер батча: $BATCH_SIZE"
echo ""

docker exec ukraine-account-manager python3 services/account-manager/smart_joiner.py "$NICHE" "$BATCH_SIZE" 2>&1

echo ""
echo "✅ Тест завершен"
echo ""
echo "Проверка вступивших групп:"
docker exec ukraine-postgres psql -U telegram_user_ukraine -d ukraine_db -c "
SELECT COUNT(*) as joined_groups
FROM targets 
WHERE status = 'joined' AND niche = '$NICHE';
" 2>&1

echo ""
echo "Последние вступления:"
docker exec ukraine-postgres psql -U telegram_user_ukraine -d ukraine_db -c "
SELECT 
    TO_CHAR(joined_at, 'HH24:MI:SS') as time,
    link as group_link,
    (SELECT session_name FROM accounts WHERE id = assigned_account_id) as account
FROM targets 
WHERE status = 'joined' AND niche = '$NICHE'
ORDER BY joined_at DESC
LIMIT 5;
" 2>&1
