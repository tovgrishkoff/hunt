#!/usr/bin/env bash
# Разблокирует постинг: помечает активные группы Bali как «прогрев пройден»
# (устанавливает warm_up_until в прошлое). После этого постер сможет находить ready-группы.
# Причина «0 постов»: ready=0, т.к. after_warmup=0 (все группы в warm-up).
set -e
cd "$(dirname "$0")/.."
CONTAINER="${POSTGRES_CONTAINER:-telegram-bali-postgres}"
USER="${POSTGRES_USER:-telegram_user_bali}"
DB="${POSTGRES_DB:-telegram_promotion_bali}"

echo "Проверка: сколько групп active/joined с warm_up_until в будущем..."
docker exec "$CONTAINER" psql -U "$USER" -d "$DB" -t -c "
SELECT COUNT(*) || ' групп с warm_up_until > NOW()' 
FROM groups 
WHERE niche = 'bali' AND status IN ('active','joined') AND warm_up_until > NOW();
"
echo ""
if [[ "$1" != "-y" && "$1" != "--yes" ]]; then
  read -p "Установить warm_up_until в прошлое для этих групп? (y/N) " -n 1 r
  echo
  if [[ "${r,}" != "y" ]]; then
    echo "Выход без изменений. Для неинтерактивного запуска: $0 -y"
    exit 0
  fi
fi

docker exec "$CONTAINER" psql -U "$USER" -d "$DB" -c "
UPDATE groups 
SET warm_up_until = NOW() - INTERVAL '25 hours'
WHERE niche = 'bali' 
  AND status IN ('active','joined') 
  AND warm_up_until > NOW();
"
echo "Готово. Запустите daily_check.sh — ready_count должен стать > 0, постер начнёт постить."
echo "Сброс счётчиков постов за день (если нужно): см. scripts/fix_lexus_poster_ready.sh (аналог для daily_posts_count)."
exit 0
