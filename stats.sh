#!/bin/bash
# Быстрая статистика подписчиков

echo "📊 Статистика подписчиков бота"
echo "================================"

PGPASSWORD=testpass psql -h localhost -p 5434 -U grishkoff -d bali_bot << EOF
SELECT 
    COUNT(*) as "Всего подписчиков",
    COUNT(CASE WHEN subscription_active = TRUE THEN 1 END) as "Активные подписки",
    COUNT(CASE WHEN trial_until > NOW() THEN 1 END) as "Активные триалы",
    COUNT(CASE WHEN trial_until < NOW() AND subscription_active = FALSE THEN 1 END) as "Истекшие триалы",
    COUNT(CASE WHEN categories != '[]' THEN 1 END) as "С выбранными нишами"
FROM subscribers;

\echo ''
\echo '👥 Детали по пользователям:'
\echo '----------------------------'

SELECT 
    user_id as "ID пользователя",
    CASE 
        WHEN subscription_active = TRUE AND subscription_until IS NULL THEN '✅ Безлимит'
        WHEN subscription_active = TRUE THEN '✅ Подписка'
        WHEN trial_until > NOW() THEN '⏳ Триал'
        ELSE '❌ Истек'
    END as "Статус",
    CASE 
        WHEN trial_until > NOW() THEN CONCAT(EXTRACT(DAY FROM trial_until - NOW()), ' дн.')
        WHEN subscription_until > NOW() THEN CONCAT(EXTRACT(DAY FROM subscription_until - NOW()), ' дн.')
        ELSE '-'
    END as "Осталось",
    CASE 
        WHEN categories = '[]' THEN '❌ Нет'
        ELSE '✅ Да'
    END as "Ниши"
FROM subscribers
ORDER BY user_id;
EOF

echo ""
echo "================================"



