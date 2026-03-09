#!/bin/bash

# Пульт управления аккаунтами промо-систем
# Показывает статусы аккаунтов в:
# - Bali Promo (telegram_promotion_bali)
# - Lexus Promo (telegram_promotion_lexus)
#
# Использует только docker exec + SQL, ничего в БД не меняет.

set -euo pipefail

cd /home/tovgrishkoff/PIAR/telegram_promotion_system_bali || exit 1

SEP="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║              🧭 ПУЛЬТ АККАУНТОВ ПРОМО-СИСТЕМ                ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

###############################################################################
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
###############################################################################

print_block_header() {
  local title="$1"
  echo "$SEP"
  printf "📦 %s\n" "$title"
  echo "$SEP"
}

check_container() {
  local name="$1"
  if docker ps --format '{{.Names}}' | grep -q "^${name}\$"; then
    return 0
  else
    return 1
  fi
}

###############################################################################
# BALI PROMO (telegram_promotion_bali, telegram-bali-postgres)
###############################################################################

print_block_header "BALI PROMO (telegram_promotion_bali)"

if ! check_container "telegram-bali-postgres"; then
  echo "⚠️  Контейнер telegram-bali-postgres не запущен – информация недоступна"
else
  echo "1) Статусы аккаунтов:"
  docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
  SELECT 
      session_name,
      status,
      COALESCE(daily_posts_count, 0) AS daily_posts,
      next_allowed_action_time
  FROM accounts
  ORDER BY 
      CASE 
        WHEN status = 'active' THEN 1
        WHEN status = 'disabled' THEN 2
        WHEN status = 'banned' THEN 3
        ELSE 9
      END,
      session_name;
  "
  echo ""

  echo "2) Краткая статистика по статусам:"
  docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
  SELECT 
      status,
      COUNT(*) AS count
  FROM accounts
  GROUP BY status
  ORDER BY status;
  "
fi

echo ""

###############################################################################
# LEXUS PROMO (telegram_promotion_lexus, lexus-postgres)
###############################################################################

print_block_header "LEXUS PROMO (telegram_promotion_lexus)"

if ! check_container "lexus-postgres"; then
  echo "⚠️  Контейнер lexus-postgres не запущен – информация недоступна"
else
  echo "1) Статусы аккаунтов:"
  docker exec lexus-postgres psql -U telegram_user_bali -d telegram_promotion_lexus -c "
  SELECT 
      session_name,
      status,
      COALESCE(daily_posts_count, 0) AS daily_posts,
      next_allowed_action_time
  FROM accounts
  ORDER BY 
      CASE 
        WHEN status = 'active' THEN 1
        WHEN status = 'disabled' THEN 2
        WHEN status = 'banned' THEN 3
        ELSE 9
      END,
      session_name;
  "
  echo ""

  echo "2) Краткая статистика по статусам:"
  docker exec lexus-postgres psql -U telegram_user_bali -d telegram_promotion_lexus -c "
  SELECT 
      status,
      COUNT(*) AS count
  FROM accounts
  GROUP BY status
  ORDER BY status;
  "
fi

echo ""

###############################################################################
# ПЕРЕСЕЧЕНИЕ АККАУНТОВ МЕЖДУ BALI PROMO И LEXUS PROMO
###############################################################################

print_block_header "ПЕРЕСЕЧЕНИЕ АККАУНТОВ (Bali Promo vs Lexus Promo)"

if check_container "telegram-bali-postgres" && check_container "lexus-postgres"; then
  docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -t -A -F',' -c "
  SELECT session_name FROM accounts WHERE status = 'active';
  " | sort > /tmp/bali_active_accounts.txt

  docker exec lexus-postgres psql -U telegram_user_bali -d telegram_promotion_lexus -t -A -F',' -c "
  SELECT session_name FROM accounts WHERE status = 'active';
  " | sort > /tmp/lexus_active_accounts.txt

  echo "Аккаунты, которые активны в ОБЕИХ промо-базах:"
  if comm -12 /tmp/bali_active_accounts.txt /tmp/lexus_active_accounts.txt | grep -q '.'; then
    comm -12 /tmp/bali_active_accounts.txt /tmp/lexus_active_accounts.txt
  else
    echo "✅ Пересечений активных аккаунтов не найдено."
  fi

  rm -f /tmp/bali_active_accounts.txt /tmp/lexus_active_accounts.txt
else
  echo "ℹ️  Нельзя посчитать пересечения: один из postgres-контейнеров не запущен."
fi

echo ""
echo "✅ Пульт аккаунтов отработал."

