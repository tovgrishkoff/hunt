#!/bin/bash
# Скрипт для проверки статуса системы Ukraine/Lexus

PROJECT="ukraine"
DB_NAME="ukraine_db"
DB_USER="telegram_user_ukraine"

echo "=" | head -c 80
echo ""
echo "📊 СТАТУС СИСТЕМЫ UKRAINE/LEXUS"
echo "=" | head -c 80
echo ""

# Проверка контейнеров
echo ""
echo "🐳 КОНТЕЙНЕРЫ:"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "ukraine|NAMES" || echo "Нет контейнеров Ukraine"

# Проверка БД
echo ""
echo "🗄️  БАЗА ДАННЫХ:"
docker exec ${PROJECT}-postgres psql -U ${DB_USER} -d ${DB_NAME} -c "
SELECT 
    'Аккаунты: ' || COUNT(*) FILTER (WHERE status = 'active') || ' активных, ' ||
    COUNT(*) FILTER (WHERE status = 'cooldown') || ' в cooldown, ' ||
    COUNT(*) || ' всего' as summary
FROM accounts;
" 2>/dev/null || echo "❌ Не удалось подключиться к БД"

# Проверка групп
echo ""
echo "📋 ГРУППЫ:"
docker exec ${PROJECT}-postgres psql -U ${DB_USER} -d ${DB_NAME} -c "
SELECT 
    'Новых: ' || COUNT(*) FILTER (WHERE status = 'new') || ', ' ||
    'Вступили: ' || COUNT(*) FILTER (WHERE status = 'joined') || ', ' ||
    'Ошибок: ' || COUNT(*) FILTER (WHERE status = 'error') || ', ' ||
    COUNT(*) || ' всего' as summary
FROM targets
WHERE niche = 'ukraine_cars';
" 2>/dev/null || echo "❌ Не удалось подключиться к БД"

# Последние посты
echo ""
echo "📢 ПОСЛЕДНИЕ ПОСТЫ (сегодня):"
docker exec ${PROJECT}-postgres psql -U ${DB_USER} -d ${DB_NAME} -c "
SELECT 
    TO_CHAR(created_at, 'HH24:MI:SS') as time,
    (SELECT title FROM targets WHERE id = post_history.target_id) as group_name,
    CASE 
        WHEN status = 'success' THEN '✅'
        ELSE '❌'
    END as status,
    LEFT(message_content, 50) || '...' as message_preview
FROM post_history
WHERE DATE(created_at) = CURRENT_DATE
ORDER BY created_at DESC
LIMIT 10;
" 2>/dev/null || echo "❌ Не удалось подключиться к БД"

# Последние вступления
echo ""
echo "🚪 ПОСЛЕДНИЕ ВСТУПЛЕНИЯ:"
docker exec ${PROJECT}-postgres psql -U ${DB_USER} -d ${DB_NAME} -c "
SELECT 
    TO_CHAR(joined_at, 'YYYY-MM-DD HH24:MI:SS') as joined_time,
    title as group_name,
    (SELECT session_name FROM accounts WHERE id = assigned_account_id) as account,
    CASE 
        WHEN warmup_ends_at > NOW() THEN '⏳ Прогрев'
        ELSE '✅ Готово'
    END as warmup_status
FROM targets
WHERE status = 'joined' AND niche = 'ukraine_cars'
ORDER BY joined_at DESC
LIMIT 10;
" 2>/dev/null || echo "❌ Не удалось подключиться к БД"

echo ""
echo "=" | head -c 80
echo ""
