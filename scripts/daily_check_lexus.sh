#!/bin/bash
cd /home/tovgrishkoff/PIAR/telegram_promotion_system_bali

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║          📊 ЕЖЕДНЕВНАЯ ПРОВЕРКА LEXUS (ukraine_cars)        ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# 1. Статус сервисов Lexus
echo "1️⃣ СТАТУС СЕРВИСОВ LEXUS:"
docker-compose -f docker-compose.lexus.yml ps
echo ""

# 2. Статистика групп по нише ukraine_cars
echo "2️⃣ СТАТИСТИКА ГРУПП (ukraine_cars):"
docker exec lexus-postgres psql -U telegram_user_bali -d telegram_promotion_lexus -c "
SELECT status, COUNT(*) 
FROM groups 
WHERE niche = 'ukraine_cars' 
GROUP BY status 
ORDER BY status;
"
echo ""

# 3. Готовые к постингу по Lexus
echo "3️⃣ ГОТОВЫЕ К ПОСТИНГУ (ukraine_cars):"
docker exec lexus-postgres psql -U telegram_user_bali -d telegram_promotion_lexus -c "
SELECT COUNT(*) as ready_count
FROM groups 
WHERE niche = 'ukraine_cars' 
  AND status = 'active' 
  AND warm_up_until <= NOW()
  AND assigned_account_id IS NOT NULL;
"
echo ""

# 3b. Как видит группы ПОСТЕР (те же фильтры: can_post + daily_posts_count < 2)
echo "3️⃣b ГРУППЫ ДЛЯ ПОСТЕРА:"
docker exec lexus-postgres psql -U telegram_user_bali -d telegram_promotion_lexus -c "
SELECT COUNT(*) as poster_ready
FROM groups 
WHERE niche = 'ukraine_cars' 
  AND status IN ('active', 'joined')
  AND (warm_up_until IS NULL OR warm_up_until <= NOW())
  AND (can_post IS NULL OR can_post = true)
  AND (daily_posts_count IS NULL OR daily_posts_count < 2);
"
echo "3️⃣b Почему 0? (can_post=false / daily_posts_count>=2):"
docker exec lexus-postgres psql -U telegram_user_bali -d telegram_promotion_lexus -c "
SELECT 
  COUNT(*) FILTER (WHERE can_post = false) as can_post_false,
  COUNT(*) FILTER (WHERE COALESCE(daily_posts_count, 0) >= 2) as daily_ge_2
FROM groups 
WHERE niche = 'ukraine_cars' AND status IN ('active', 'joined');
"
echo ""

# 3c. Аккаунты
echo "3️⃣c АККАУНТЫ:"
docker exec lexus-postgres psql -U telegram_user_bali -d telegram_promotion_lexus -c "
SELECT session_name, status FROM accounts ORDER BY session_name;
"
echo ""

# 4. Посты за сегодня по Lexus
echo "4️⃣ ПОСТЫ ЗА СЕГОДНЯ (ukraine_cars):"
docker exec lexus-postgres psql -U telegram_user_bali -d telegram_promotion_lexus -c "
SELECT 
    COUNT(*) as total_posts,
    COUNT(CASE WHEN photo_path IS NOT NULL THEN 1 END) as posts_with_photo,
    COUNT(CASE WHEN success = true THEN 1 END) as successful_posts
FROM posts
WHERE sent_at >= CURRENT_DATE
  AND niche = 'ukraine_cars';
"
echo ""

# 5. Последние 5 постов по Lexus
echo "5️⃣ ПОСЛЕДНИЕ 5 ПОСТОВ (ukraine_cars):"
docker exec lexus-postgres psql -U telegram_user_bali -d telegram_promotion_lexus -c "
SELECT 
    g.username,
    p.sent_at,
    CASE WHEN p.photo_path IS NOT NULL THEN '📷' ELSE '📝' END as type,
    p.success
FROM posts p
JOIN groups g ON p.group_id = g.id
WHERE p.niche = 'ukraine_cars'
ORDER BY p.sent_at DESC
LIMIT 5;
"
echo ""

echo "✅ Проверка Lexus завершена!"
echo ""
echo "💡 Постинг идёт из контейнера lexus-marketer (слоты 08:00, 12:00, 15:00, 18:00, 20:00 по Киеву)."
echo ""
echo "❓ Если poster_ready = 0 (постинг не идёт):"
echo "   • Много can_post_false → перепроверить права и выставить can_post=True где можно:"
echo "     docker exec lexus-marketer python3 /app/scripts/check_lexus_permissions_and_update_db.py"
echo "     (с --limit 100 для теста или без лимита для всех)"
echo "   • Много daily_ge_2 → сброс счётчиков: ./scripts/fix_lexus_poster_ready.sh"
echo "   Разовый постинг: docker exec lexus-marketer python3 main.py ukraine_cars 20"
echo ""
echo "❓ «Аккаунт не участник» / «A wait of N seconds»:"
echo "   Это FloodWait от Telegram (лимит запросов). Ждать N сек или ~5 ч. Постер больше не помечает группу как inaccessible."
echo "❓ Вступления не идут:"
echo "   • account-manager вступает только в группы со status='new' (их добавляет Scout в STEP 1)."
echo "   • Логи вступлений: docker logs lexus-account-manager --tail 80 | grep -E 'STEP 2|join|Join|вступл'"
echo "   • Если аккаунты в FloodWait — вступления тоже будут ждать до истечения."
echo ""
echo "❓ «Session used under two different IP addresses» (два аккаунта не создают клиент):"
echo "   Сессии использовались и в контейнере, и с хоста — Telegram инвалидировал ключ."
echo "   Переавторизация (с хоста, с тем же прокси что в конфиге):"
echo "     cd PIAR/telegram_promotion_system_bali"
echo "     POSTGRES_HOST=localhost POSTGRES_PORT=5440 POSTGRES_DB=telegram_promotion_lexus python3 scripts/create_lexus_sessions.py"
echo "   Выбрать номера сломанных аккаунтов (например 2,3), ввести код из Telegram, 2FA если есть."
echo "   После успеха: docker-compose -f docker-compose.lexus.yml restart lexus-marketer lexus-account-manager"

