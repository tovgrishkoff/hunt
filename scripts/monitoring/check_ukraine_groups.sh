#!/bin/bash
# Скрипт для проверки групп (куда вступили)

PROJECT="ukraine"
DB_NAME="ukraine_db"
DB_USER="telegram_user_ukraine"

echo "=" | head -c 80
echo ""
echo "🚪 ГРУППЫ (UKRAINE_CARS)"
echo "=" | head -c 80
echo ""

echo ""
echo "📊 СТАТИСТИКА ПО СТАТУСАМ:"
docker exec ${PROJECT}-postgres psql -U ${DB_USER} -d ${DB_NAME} -c "
SELECT 
    status,
    COUNT(*) as count,
    CASE status
        WHEN 'new' THEN '🆕'
        WHEN 'joined' THEN '✅'
        WHEN 'error' THEN '❌'
        WHEN 'banned_from_chat' THEN '🚫'
        ELSE '⚠️'
    END as icon
FROM targets
WHERE niche = 'ukraine_cars'
GROUP BY status
ORDER BY count DESC;
" 2>/dev/null

echo ""
echo "✅ ВСТУПИЛИ (последние 20):"
docker exec ${PROJECT}-postgres psql -U ${DB_USER} -d ${DB_NAME} -c "
SELECT 
    TO_CHAR(joined_at, 'YYYY-MM-DD HH24:MI:SS') as joined_time,
    title as group_name,
    link as group_link,
    (SELECT session_name FROM accounts WHERE id = assigned_account_id) as account,
    CASE 
        WHEN warmup_ends_at > NOW() THEN 
            '⏳ Прогрев до ' || TO_CHAR(warmup_ends_at, 'HH24:MI:SS')
        ELSE '✅ Готово к постингу'
    END as warmup_status,
    daily_posts_in_group || '/2 постов сегодня' as posts_today
FROM targets
WHERE status = 'joined' AND niche = 'ukraine_cars'
ORDER BY joined_at DESC
LIMIT 20;
" 2>/dev/null

echo ""
echo "🆕 НОВЫЕ ГРУППЫ (ожидают вступления):"
docker exec ${PROJECT}-postgres psql -U ${DB_USER} -d ${DB_NAME} -c "
SELECT 
    title as group_name,
    link as group_link,
    TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') as added_time
FROM targets
WHERE status = 'new' AND niche = 'ukraine_cars'
ORDER BY created_at DESC
LIMIT 20;
" 2>/dev/null

echo ""
echo "❌ ОШИБКИ ВСТУПЛЕНИЯ:"
docker exec ${PROJECT}-postgres psql -U ${DB_USER} -d ${DB_NAME} -c "
SELECT 
    title as group_name,
    link as group_link,
    error_message,
    TO_CHAR(updated_at, 'YYYY-MM-DD HH24:MI:SS') as error_time
FROM targets
WHERE status = 'error' AND niche = 'ukraine_cars'
ORDER BY updated_at DESC
LIMIT 20;
" 2>/dev/null

echo ""
