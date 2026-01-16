#!/bin/bash
cd /home/tovgrishkoff/PIAR/telegram_promotion_system_bali

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║          📊 ЕЖЕДНЕВНАЯ ПРОВЕРКА СИСТЕМЫ                     ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# 1. Статус сервисов
echo "1️⃣ СТАТУС СЕРВИСОВ:"
docker-compose ps | grep telegram-bali
echo ""

# 2. Статистика групп
echo "2️⃣ СТАТИСТИКА ГРУПП:"
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT status, COUNT(*) 
FROM groups 
WHERE niche = 'bali' 
GROUP BY status 
ORDER BY status;
"
echo ""

# 3. Готовые к постингу
echo "3️⃣ ГОТОВЫЕ К ПОСТИНГУ:"
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT COUNT(*) as ready_count
FROM groups 
WHERE niche = 'bali' 
  AND status = 'active' 
  AND warm_up_until <= NOW()
  AND assigned_account_id IS NOT NULL;
"
echo ""

# 4. Посты за сегодня
echo "4️⃣ ПОСТЫ ЗА СЕГОДНЯ:"
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT 
    COUNT(*) as total_posts,
    COUNT(CASE WHEN photo_path IS NOT NULL THEN 1 END) as posts_with_photo,
    COUNT(CASE WHEN success = true THEN 1 END) as successful_posts
FROM posts
WHERE sent_at >= CURRENT_DATE;
"
echo ""

# 5. Последние посты
echo "5️⃣ ПОСЛЕДНИЕ 5 ПОСТОВ:"
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT 
    g.username,
    p.sent_at,
    CASE WHEN p.photo_path IS NOT NULL THEN '📷' ELSE '📝' END as type,
    p.success
FROM posts p
JOIN groups g ON p.group_id = g.id
ORDER BY p.sent_at DESC
LIMIT 5;
"
echo ""

echo "✅ Проверка завершена!"
