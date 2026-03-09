#!/usr/bin/env bash
# Сбрасывает блоклист по причине «аккаунт не участник группы» для Bali,
# чтобы постер снова попробовал эти связки (group, account).
# После этого группы со статусом no_accounts_left переводим в active.
# Причина «0 успешно, 48 ошибок»: все аккаунты для групп уже в блоклисте.
set -e
cd "$(dirname "$0")/.."
CONTAINER="${POSTGRES_CONTAINER:-telegram-bali-postgres}"
USER="${POSTGRES_USER:-telegram_user_bali}"
DB="${POSTGRES_DB:-telegram_promotion_bali}"

echo "Блоклист для Bali (записи по причине «не участник»):"
docker exec "$CONTAINER" psql -U "$USER" -d "$DB" -t -c "
SELECT COUNT(*) || ' записей (participant/member/участник)' 
FROM account_group_blocklist b 
JOIN groups g ON g.id = b.group_id 
WHERE g.niche = 'bali' 
  AND (b.reason ILIKE '%participant%' OR b.reason ILIKE '%member%' OR b.reason ILIKE '%участник%' OR b.reason ILIKE '%not a member%');
"
echo ""
echo "Группы no_accounts_left:"
docker exec "$CONTAINER" psql -U "$USER" -d "$DB" -t -c "
SELECT COUNT(*) || ' групп' FROM groups WHERE niche = 'bali' AND status = 'no_accounts_left';
"
echo ""
if [[ "$1" != "-y" && "$1" != "--yes" ]]; then
  read -p "Удалить эти записи блоклиста и перевести no_accounts_left → active? (y/N) " -n 1 r
  echo
  if [[ "${r,}" != "y" ]]; then
    echo "Выход. Для неинтерактивного запуска: $0 -y"
    exit 0
  fi
fi

echo "Удаляю записи блоклиста (причина: не участник)..."
docker exec "$CONTAINER" psql -U "$USER" -d "$DB" -c "
DELETE FROM account_group_blocklist
WHERE group_id IN (SELECT id FROM groups WHERE niche = 'bali')
  AND (reason ILIKE '%participant%' OR reason ILIKE '%member%' OR reason ILIKE '%участник%' OR reason ILIKE '%not a member%');
"
echo "Перевожу no_accounts_left → active..."
docker exec "$CONTAINER" psql -U "$USER" -d "$DB" -c "
UPDATE groups 
SET status = 'active', updated_at = NOW()
WHERE niche = 'bali' AND status = 'no_accounts_left';
"
echo "Готово. Следующий слот постера попробует эти группы снова. Если аккаунт реально не в группе — снова попадёт в блоклист; тогда нужен account-manager (вступление в группы со status=new)."
exit 0
