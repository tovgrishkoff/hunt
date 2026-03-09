#!/bin/bash
# Скрипт проверки системы Lexus

cd /home/tovgrishkoff/PIAR/telegram_promotion_system_bali

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║          🧪 ТЕСТ СИСТЕМЫ LEXUS - ПОЛНАЯ ПРОВЕРКА           ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# 1. Проверка контейнеров
echo "1️⃣ ПРОВЕРКА КОНТЕЙНЕРОВ:"
docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E "(lexus|NAME)"
echo ""

# 2. Проверка БД
echo "2️⃣ ПРОВЕРКА БАЗЫ ДАННЫХ LEXUS:"
# Определяем контейнер БД (может быть lexus-postgres или telegram-bali-postgres)
DB_CONTAINER=""
if docker ps --format "{{.Names}}" | grep -q "^lexus-postgres$"; then
    DB_CONTAINER="lexus-postgres"
elif docker ps --format "{{.Names}}" | grep -q "^telegram-bali-postgres$"; then
    DB_CONTAINER="telegram-bali-postgres"
else
    echo "   ⚠️ Контейнер БД не найден"
    DB_CONTAINER=""
fi

if [ -n "$DB_CONTAINER" ]; then
    docker exec $DB_CONTAINER psql -U telegram_user_bali -d telegram_promotion_lexus -c "
    SELECT 
        (SELECT COUNT(*) FROM accounts) as accounts,
        (SELECT COUNT(*) FROM groups) as groups,
        (SELECT COUNT(*) FROM posts) as posts;
    " 2>&1 | tail -5
else
    echo "   ❌ БД недоступна"
fi
echo ""

# 3. Проверка разделения БД
echo "3️⃣ ПРОВЕРКА РАЗДЕЛЕНИЯ БД:"
# Ищем контейнер БД Bali
BALI_DB_CONTAINER=""
if docker ps --format "{{.Names}}" | grep -q "^bali-postgres$"; then
    BALI_DB_CONTAINER="bali-postgres"
elif docker ps --format "{{.Names}}" | grep -q "^telegram-bali-postgres$"; then
    BALI_DB_CONTAINER="telegram-bali-postgres"
fi

if [ -n "$BALI_DB_CONTAINER" ]; then
    BALI_LEXUS=$(docker exec $BALI_DB_CONTAINER psql -U telegram_user_bali -d telegram_promotion_bali -t -c "SELECT COUNT(*) FROM groups WHERE niche='ukraine_cars';" 2>&1 | grep -E "^[[:space:]]*[0-9]+" | tr -d ' ' || echo "0")
    if [ "$BALI_LEXUS" == "0" ] || [ -z "$BALI_LEXUS" ]; then
        echo "   ✅ Bali БД не содержит Lexus данных"
    else
        echo "   ⚠️ В Bali БД найдено $BALI_LEXUS Lexus групп"
    fi
else
    echo "   ℹ️ Контейнер БД Bali не запущен (это нормально, если используется отдельная БД)"
fi
echo ""

# 4. Проверка подключения
echo "4️⃣ ПРОВЕРКА ПОДКЛЮЧЕНИЯ К БД:"
docker exec lexus-marketer env | grep "POSTGRES_DB=" | head -1
echo ""

# 5. Проверка логов marketer
echo "5️⃣ ПРОВЕРКА ЛОГОВ LEXUS-MARKETER:"
docker logs lexus-marketer --tail 20 2>&1 | grep -E "(✅.*Database|✅.*init|Next slot)" | tail -3
echo ""

# 6. Проверка логов account-manager
echo "6️⃣ ПРОВЕРКА ЛОГОВ LEXUS-ACCOUNT-MANAGER:"
docker logs lexus-account-manager --tail 20 2>&1 | grep -E "(✅|STEP|Next slot)" | tail -3
echo ""

# 7. Проверка ошибок
echo "7️⃣ ПРОВЕРКА ОШИБОК:"
ERRORS_M=$(docker logs lexus-marketer --tail 100 2>&1 | grep -iE "error|fatal|exception" | grep -v "grep" | wc -l)
ERRORS_A=$(docker logs lexus-account-manager --tail 100 2>&1 | grep -iE "error|fatal|exception" | grep -v "grep" | wc -l)
echo "   Marketer ошибок: $ERRORS_M"
echo "   Account-manager ошибок: $ERRORS_A"
if [ "$ERRORS_M" -lt 10 ] && [ "$ERRORS_A" -lt 10 ]; then
    echo "   ✅ Критических ошибок нет"
else
    echo "   ⚠️ Обнаружено много ошибок, проверьте логи"
fi
echo ""

# 8. Итоговый статус
echo "🔟 ИТОГОВЫЙ СТАТУС:"
if docker ps | grep -q "lexus-marketer.*Up"; then
    echo "   ✅ Lexus-marketer: Работает"
else
    echo "   ❌ Lexus-marketer: Остановлен"
fi

if docker ps | grep -q "lexus-account-manager.*Up"; then
    echo "   ✅ Lexus-account-manager: Работает"
else
    echo "   ❌ Lexus-account-manager: Остановлен"
fi

# Проверяем контейнер БД (может быть разное имя)
DB_CONTAINER=""
if docker ps --format "{{.Names}}" | grep -q "^lexus-postgres$"; then
    DB_CONTAINER="lexus-postgres"
    echo "   ✅ Lexus-postgres: Работает"
elif docker ps --format "{{.Names}}" | grep -q "^telegram-bali-postgres$"; then
    DB_CONTAINER="telegram-bali-postgres"
    echo "   ✅ Telegram-bali-postgres: Работает (используется для Lexus БД)"
else
    echo "   ❌ Контейнер БД: Не найден"
fi

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                    ✅ ТЕСТ ЗАВЕРШЕН                          ║"
echo "╚══════════════════════════════════════════════════════════════╝"
