#!/bin/bash
# Скрипт для запуска старых контейнеров для параллельного тестирования

cd "$(dirname "$0")/.."

echo "🔄 ЗАПУСК СТАРЫХ КОНТЕЙНЕРОВ ДЛЯ ТЕСТИРОВАНИЯ"
echo "=============================================="
echo ""

# Запускаем lexus-scheduler через docker-compose
if [ -f "docker-compose.lexus.yml" ]; then
    echo "📦 Запуск lexus-scheduler..."
    docker-compose -f docker-compose.lexus.yml up -d 2>&1 | grep -v "^Network\|^Creating\|^Created"
    
    if docker ps | grep -q "lexus-scheduler"; then
        echo "✅ lexus-scheduler запущен"
    else
        echo "❌ Ошибка запуска lexus-scheduler"
    fi
else
    echo "⚠️  docker-compose.lexus.yml не найден, пытаемся запустить контейнер напрямую..."
    docker start lexus-scheduler 2>/dev/null && echo "✅ lexus-scheduler запущен" || echo "❌ Не удалось запустить lexus-scheduler"
fi

echo ""

# Запускаем telegram-promotion-advanced
echo "📦 Запуск telegram-promotion-advanced..."
if docker start telegram-promotion-advanced 2>/dev/null; then
    echo "✅ telegram-promotion-advanced запущен"
else
    echo "❌ Не удалось запустить telegram-promotion-advanced (возможно контейнер удален)"
fi

echo ""
echo "📊 СТАТУС КОНТЕЙНЕРОВ:"
echo "---------------------"
docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E "(lexus|promotion-advanced|combine)"

echo ""
echo "💡 ПРИМЕЧАНИЕ:"
echo "Старые контейнеры запущены для параллельного тестирования."
echo "После проверки работы новой системы можно их остановить:"
echo "  bash scripts/manage_containers.sh stop-old"

