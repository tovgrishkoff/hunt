#!/bin/bash
# Скрипт для проверки постов в группах

PROJECT="ukraine"
DB_NAME="ukraine_db"
DB_USER="telegram_user_ukraine"
DAYS=${1:-1}

echo "=" | head -c 80
echo ""
echo "📢 ПОСТЫ ЗА ПОСЛЕДНИЕ ${DAYS} ДНЕЙ"
echo "=" | head -c 80
echo ""

docker exec ${PROJECT}-postgres psql -U ${DB_USER} -d ${DB_NAME} -c "
SELECT 
    TO_CHAR(post_history.created_at, 'YYYY-MM-DD HH24:MI:SS') as posted_at,
    targets.title as group_name,
    targets.link as group_link,
    accounts.session_name as account,
    CASE 
        WHEN post_history.status = 'success' THEN '✅'
        WHEN post_history.status = 'error' THEN '❌'
        ELSE '⚠️'
    END as status,
    LEFT(post_history.message_content, 60) || '...' as message_preview,
    post_history.error_message
FROM post_history
JOIN targets ON post_history.target_id = targets.id
LEFT JOIN accounts ON post_history.account_id = accounts.id
WHERE post_history.created_at >= NOW() - INTERVAL '${DAYS} days'
ORDER BY post_history.created_at DESC;
" 2>/dev/null

echo ""
echo "📊 СТАТИСТИКА:"
docker exec ${PROJECT}-postgres psql -U ${DB_USER} -d ${DB_NAME} -c "
SELECT 
    DATE(created_at) as date,
    COUNT(*) FILTER (WHERE status = 'success') as success,
    COUNT(*) FILTER (WHERE status = 'error') as errors,
    COUNT(*) as total
FROM post_history
WHERE created_at >= NOW() - INTERVAL '${DAYS} days'
GROUP BY DATE(created_at)
ORDER BY date DESC;
" 2>/dev/null

echo ""
