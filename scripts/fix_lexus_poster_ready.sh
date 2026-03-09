#!/bin/bash
# Сброс daily_posts_count для ukraine_cars, чтобы постер снова видел группы.
# Используйте, если "492 active" но "0 ready" из-за daily_posts_count >= 2.
# Безопасно: маркетер и так сбрасывает счётчики в полночь; этот скрипт — ручной сброс при необходимости.
cd /home/tovgrishkoff/PIAR/telegram_promotion_system_bali

echo "🔄 Сброс daily_posts_count для ниши ukraine_cars..."
docker exec lexus-postgres psql -U telegram_user_bali -d telegram_promotion_lexus -c "
UPDATE groups 
SET daily_posts_count = 0 
WHERE niche = 'ukraine_cars' AND COALESCE(daily_posts_count, 0) <> 0;
"
echo "✅ Готово. Запустите daily_check_lexus.sh и проверьте poster_ready."
echo "   Если poster_ready всё ещё 0 — смотрите can_post_false (тогда нужна проверка прав: scripts/check_lexus_permissions_and_update_db.py)."
