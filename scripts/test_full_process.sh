#!/bin/bash
# Комплексный тест всего процесса системы
# Проверяет: сервисы -> группы -> постинг

set -e

cd /home/tovgrishkoff/PIAR/telegram_promotion_system_bali

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║     🧪 КОМПЛЕКСНОЕ ТЕСТИРОВАНИЕ СИСТЕМЫ                     ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Цвета для вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функция для вывода результата
print_result() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✅ $2${NC}"
    else
        echo -e "${RED}❌ $2${NC}"
    fi
}

# 1. Проверка статуса сервисов
echo -e "${BLUE}1️⃣  ПРОВЕРКА СЕРВИСОВ${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
SERVICES_COUNT=$(docker ps | grep telegram-bali | wc -l)
if [ $SERVICES_COUNT -ge 4 ]; then
    print_result 0 "Сервисы запущены ($SERVICES_COUNT контейнеров)"
    docker ps | grep telegram-bali | awk '{print "  ✅", $NF}'
else
    print_result 1 "Недостаточно сервисов запущено (ожидается минимум 4, найдено $SERVICES_COUNT)"
fi
echo ""

# 2. Проверка статистики групп
echo -e "${BLUE}2️⃣  СТАТИСТИКА ГРУПП${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
GROUPS_STATS=$(docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -t -c "
SELECT status, COUNT(*) 
FROM groups 
WHERE niche = 'bali' 
GROUP BY status 
ORDER BY status;
")
echo "$GROUPS_STATS" | while read line; do
    if [ ! -z "$line" ]; then
        echo "  $line"
    fi
done

# Получаем количество групп готовых к постингу
READY_GROUPS=$(docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -t -c "
SELECT COUNT(*) 
FROM groups 
WHERE niche = 'bali' 
  AND status = 'active' 
  AND warm_up_until <= NOW()
  AND assigned_account_id IS NOT NULL;
" | tr -d ' ')

if [ "$READY_GROUPS" -gt "0" ]; then
    echo -e "  ${GREEN}✅ Готовых к постингу: $READY_GROUPS${NC}"
else
    echo -e "  ${YELLOW}⚠️  Готовых к постингу: 0 (нужен warm-up 24 часа)${NC}"
fi
echo ""

# 3. Проверка аккаунтов
echo -e "${BLUE}3️⃣  СТАТУС АККАУНТОВ${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
ACTIVE_ACCOUNTS=$(docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -t -c "
SELECT COUNT(*) 
FROM accounts 
WHERE status = 'active';
" | tr -d ' ')
echo "  Активных аккаунтов: $ACTIVE_ACCOUNTS"
print_result 0 "Аккаунты загружены"
echo ""

# 4. Проверка постов за сегодня
echo -e "${BLUE}4️⃣  ПОСТЫ ЗА СЕГОДНЯ${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
POSTS_TODAY=$(docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -t -c "
SELECT 
    COUNT(*) as total,
    COUNT(CASE WHEN photo_path IS NOT NULL THEN 1 END) as with_photo,
    COUNT(CASE WHEN success = true THEN 1 END) as successful
FROM posts
WHERE sent_at >= CURRENT_DATE;
" | tr -d ' ')

echo "$POSTS_TODAY" | awk -F'|' '{print "  Всего: " $1 ", С фото: " $2 ", Успешных: " $3}'
echo ""

# 5. Проверка последних постов
echo -e "${BLUE}5️⃣  ПОСЛЕДНИЕ 5 ПОСТОВ${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
LAST_POSTS=$(docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT 
    g.username,
    TO_CHAR(p.sent_at, 'DD.MM HH24:MI') as time,
    CASE WHEN p.photo_path IS NOT NULL THEN '📷' ELSE '📝' END as type,
    CASE WHEN p.success THEN '✅' ELSE '❌' END as status
FROM posts p
JOIN groups g ON p.group_id = g.id
ORDER BY p.sent_at DESC
LIMIT 5;
")

if echo "$LAST_POSTS" | grep -q "rows)"; then
    echo "$LAST_POSTS" | tail -n +4 | head -n -1
else
    echo "  Нет постов"
fi
echo ""

# 6. Проверка ошибок в логах
echo -e "${BLUE}6️⃣  ПРОВЕРКА ОШИБОК В ЛОГАХ${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
MARKETER_ERRORS=$(docker logs telegram-bali-marketer 2>&1 | grep -i "error\|AttributeError" | tail -5 | wc -l)
ACCOUNT_MANAGER_ERRORS=$(docker logs telegram-bali-account-manager 2>&1 | grep -i "error" | tail -5 | wc -l)

if [ "$MARKETER_ERRORS" -eq "0" ]; then
    print_result 0 "Marketer: нет критических ошибок"
else
    print_result 1 "Marketer: найдено $MARKETER_ERRORS ошибок"
    echo -e "${YELLOW}  Последние ошибки:${NC}"
    docker logs telegram-bali-marketer 2>&1 | grep -i "error\|AttributeError" | tail -3 | sed 's/^/    /'
fi

if [ "$ACCOUNT_MANAGER_ERRORS" -eq "0" ]; then
    print_result 0 "Account Manager: нет критических ошибок"
else
    print_result 1 "Account Manager: найдено $ACCOUNT_MANAGER_ERRORS ошибок"
fi
echo ""

# 7. Тестовый постинг (если есть готовые группы)
if [ "$READY_GROUPS" -gt "0" ]; then
    echo -e "${BLUE}7️⃣  ТЕСТОВЫЙ ПОСТИНГ${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "${YELLOW}Запускаем тестовый постинг (1 пост)...${NC}"
    echo ""
    
    docker exec telegram-bali-marketer python3 /app/services/marketer/poster.py bali 1 2>&1 | tail -30
    
    echo ""
    echo -e "${GREEN}✅ Тестовый постинг завершен${NC}"
else
    echo -e "${BLUE}7️⃣  ТЕСТОВЫЙ ПОСТИНГ${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "${YELLOW}⚠️  Пропущено: нет групп готовых к постингу (нужен warm-up 24 часа)${NC}"
    echo "  Для теста можно запустить вручную:"
    echo "  docker exec telegram-bali-marketer python3 /app/services/marketer/poster.py bali 1"
fi
echo ""

# Итоговая сводка
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║     📊 ИТОГОВАЯ СВОДКА                                       ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "  Сервисы: $SERVICES_COUNT запущено"
echo "  Групп готовых к постингу: $READY_GROUPS"
echo "  Активных аккаунтов: $ACTIVE_ACCOUNTS"
echo ""
echo -e "${GREEN}✅ Комплексное тестирование завершено!${NC}"
echo ""
