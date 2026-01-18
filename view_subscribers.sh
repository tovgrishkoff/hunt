#!/bin/bash

# Скрипт для быстрого просмотра подписчиков Bali Bot

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 СТАТИСТИКА ПОДПИСЧИКОВ BALI BOT"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

docker exec bali-postgres psql -U grishkoff -d bali_bot -c "
SELECT 
    s.user_id AS \"ID пользователя\",
    CASE 
        WHEN s.trial_until > NOW() THEN '🔵 Триал'
        WHEN s.subscription_active THEN '✅ Подписка'
        ELSE '❌ Неактивен'
    END AS \"Статус\",
    TO_CHAR(s.trial_until, 'DD.MM.YYYY HH24:MI') AS \"Триал до\",
    TO_CHAR(s.subscription_until, 'DD.MM.YYYY HH24:MI') AS \"Подписка до\",
    TO_CHAR(s.created_at, 'DD.MM.YYYY') AS \"Регистрация\",
    COALESCE(ub.balance, 0) AS \"Баланс\",
    COALESCE(ub.total_referrals, 0) AS \"Рефералов\",
    jsonb_array_length(s.categories) AS \"Категорий\"
FROM subscribers s
LEFT JOIN user_balance ub ON s.user_id = ub.user_id
ORDER BY s.created_at DESC;
"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📈 ОБЩАЯ СТАТИСТИКА"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

docker exec bali-postgres psql -U grishkoff -d bali_bot -c "
SELECT 
    (SELECT COUNT(*) FROM subscribers) AS \"Всего пользователей\",
    (SELECT COUNT(*) FROM subscribers WHERE subscription_active = true) AS \"Активных подписок\",
    (SELECT COUNT(*) FROM subscribers WHERE trial_until > NOW()) AS \"Активных триалов\",
    (SELECT COUNT(*) FROM messages) AS \"Всего сообщений\",
    (SELECT COUNT(*) FROM messages WHERE is_processed = false) AS \"Необработано\",
    (SELECT COUNT(*) FROM banned_users) AS \"Забанено\"
;"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "💡 Для детальной информации см. файл README_DATABASE.md"
echo ""

