#!/bin/bash
# Устанавливает niche='bali' для аккаунтов Bali (сторис, партизанский PR, постинг).
# Включает: promotion_new_account, promotion_new_account_2 и всех из bali_accounts_config + role_* в bali_conversations.json

set -e
CONTAINER="${POSTGRES_CONTAINER:-telegram-bali-postgres}"
DB_USER="${POSTGRES_USER:-telegram_user_bali}"
DB_NAME="${POSTGRES_DB:-telegram_promotion_bali}"

echo "Устанавливаю niche='bali' для Bali-аккаунтов (сторис, партизанский PR)..."
docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -c "
UPDATE accounts
SET niche = 'bali', updated_at = NOW()
WHERE session_name IN (
  'promotion_new_account', 'promotion_new_account_2',
  'promotion_anna_truncher', 'promotion_lisa_soak', 'promotion_oleg_petrov',
  'promotion_lera_katina', 'promotion_lev_moiseev', 'promotion_Masha Sinugina', 'promotion_artur_biggest'
)
  AND (niche IS NULL OR niche != 'bali');
"
echo "Готово. Перезапусти activity для подхвата: docker-compose restart activity"
