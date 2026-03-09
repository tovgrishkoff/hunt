#!/bin/bash
cd /home/tovgrishkoff/PIAR/telegram_promotion_system_bali

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║          📊 ПРОВЕРКА СТАТУСА АККАУНТОВ И ГРУПП              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# 1. Статусы аккаунтов
echo "1️⃣ СТАТУСЫ АККАУНТОВ:"
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT status, COUNT(*) as count 
FROM accounts 
GROUP BY status 
ORDER BY status;
"
echo ""

# 2. Аккаунты с количеством забаненных групп
echo "2️⃣ АККАУНТЫ И ЗАБАНЕННЫЕ ГРУППЫ:"
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT 
    a.session_name, 
    a.status, 
    COUNT(b.id) as blocked_groups_count,
    CASE 
        WHEN COUNT(b.id) > 50 THEN '⚠️ МНОГО БАНОВ'
        WHEN COUNT(b.id) > 30 THEN '⚠️ СРЕДНЕ'
        ELSE '✅ НОРМА'
    END as status_indicator
FROM accounts a 
LEFT JOIN account_group_blocklist b ON a.id = b.account_id 
WHERE a.status = 'active' 
GROUP BY a.id, a.session_name, a.status 
ORDER BY blocked_groups_count DESC;
"
echo ""

# 3. Статистика постов по аккаунтам за последние 7 дней
echo "3️⃣ СТАТИСТИКА ПОСТОВ ПО АККАУНТАМ (7 дней):"
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT 
    a.session_name,
    COUNT(p.id) as total_posts,
    COUNT(CASE WHEN p.success = true THEN 1 END) as successful_posts,
    COUNT(CASE WHEN p.success = false THEN 1 END) as failed_posts,
    ROUND(
        COUNT(CASE WHEN p.success = true THEN 1 END)::numeric / 
        NULLIF(COUNT(p.id), 0) * 100, 
        1
    ) as success_rate_percent
FROM accounts a 
LEFT JOIN posts p ON a.id = p.account_id 
WHERE a.status = 'active' 
  AND p.sent_at >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY a.id, a.session_name 
ORDER BY successful_posts DESC;
"
echo ""

# 4. Группы без доступных аккаунтов
echo "4️⃣ ГРУППЫ БЕЗ ДОСТУПНЫХ АККАУНТОВ:"
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT 
    g.username,
    g.status,
    COUNT(DISTINCT b.account_id) as blocked_accounts_count,
    (SELECT COUNT(*) FROM accounts WHERE status = 'active') as total_active_accounts
FROM groups g
LEFT JOIN account_group_blocklist b ON g.id = b.group_id
WHERE g.status = 'active'
  AND g.niche = 'bali'
GROUP BY g.id, g.username, g.status
HAVING COUNT(DISTINCT b.account_id) >= (SELECT COUNT(*) FROM accounts WHERE status = 'active')
ORDER BY blocked_accounts_count DESC
LIMIT 10;
"
echo ""

# 5. Группы с частыми ошибками за сегодня
echo "5️⃣ ГРУППЫ С ЧАСТЫМИ ОШИБКАМИ (сегодня):"
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT 
    g.username,
    COUNT(p.id) as total_attempts,
    COUNT(CASE WHEN p.success = false THEN 1 END) as failed_attempts,
    COUNT(CASE WHEN p.success = true THEN 1 END) as successful_attempts,
    MAX(p.sent_at) as last_attempt
FROM groups g
JOIN posts p ON g.id = p.group_id
WHERE p.sent_at >= CURRENT_DATE
  AND g.niche = 'bali'
GROUP BY g.id, g.username
HAVING COUNT(CASE WHEN p.success = false THEN 1 END) >= 3
ORDER BY failed_attempts DESC, last_attempt DESC
LIMIT 10;
"
echo ""

echo "✅ Проверка завершена!"
