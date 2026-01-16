#!/bin/bash
# Скрипт для проверки аккаунтов

PROJECT="ukraine"
DB_NAME="ukraine_db"
DB_USER="telegram_user_ukraine"

echo "=" | head -c 80
echo ""
echo "👤 АККАУНТЫ"
echo "=" | head -c 80
echo ""

echo ""
echo "📊 СТАТИСТИКА:"
docker exec ${PROJECT}-postgres psql -U ${DB_USER} -d ${DB_NAME} -c "
SELECT 
    status,
    COUNT(*) as count,
    CASE status
        WHEN 'active' THEN '✅'
        WHEN 'cooldown' THEN '⏳'
        WHEN 'banned' THEN '🚫'
        ELSE '⚠️'
    END as icon
FROM accounts
GROUP BY status
ORDER BY count DESC;
" 2>/dev/null

echo ""
echo "📋 ДЕТАЛИ АККАУНТОВ:"
docker exec ${PROJECT}-postgres psql -U ${DB_USER} -d ${DB_NAME} -c "
SELECT 
    session_name,
    status,
    daily_posts_count || '/20 постов сегодня' as posts_today,
    CASE 
        WHEN next_allowed_action_time IS NULL THEN '✅ Готов'
        WHEN next_allowed_action_time > NOW() THEN 
            '⏳ FloodWait до ' || TO_CHAR(next_allowed_action_time, 'HH24:MI:SS')
        ELSE '✅ Готов'
    END as availability,
    TO_CHAR(last_stats_reset, 'YYYY-MM-DD') as last_reset
FROM accounts
ORDER BY session_name;
" 2>/dev/null

echo ""
