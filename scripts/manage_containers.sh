#!/bin/bash
# Скрипт для управления контейнерами системы

cd "$(dirname "$0")/.."

echo "📊 УПРАВЛЕНИЕ КОНТЕЙНЕРАМИ"
echo "=========================="
echo ""

case "$1" in
    status)
        echo "✅ НОВАЯ СИСТЕМА (docker-compose):"
        echo "----------------------------------"
        docker-compose ps
        echo ""
        echo "🛑 СТАРЫЕ КОНТЕЙНЕРЫ:"
        echo "--------------------"
        docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E "(lexus-scheduler|telegram-promotion-advanced|telegram-postgres-promotion-advanced)"
        ;;
    
    stop-old)
        echo "🛑 Остановка старых контейнеров..."
        echo ""
        docker stop lexus-scheduler telegram-promotion-advanced telegram-postgres-promotion-advanced 2>/dev/null || echo "  (некоторые контейнеры уже остановлены)"
        echo ""
        echo "✅ Старые контейнеры остановлены"
        echo ""
        echo "💡 Чтобы удалить контейнеры:"
        echo "   docker rm lexus-scheduler telegram-promotion-advanced telegram-postgres-promotion-advanced"
        ;;
    
    start-new)
        echo "🚀 Запуск новой системы..."
        docker-compose up -d
        echo ""
        echo "✅ Новая система запущена"
        ;;
    
    restart-new)
        echo "🔄 Перезапуск новой системы..."
        docker-compose restart
        echo ""
        echo "✅ Новая система перезапущена"
        ;;
    
    logs)
        SERVICE="${2:-marketer}"
        echo "📋 Логи сервиса: $SERVICE"
        echo "--------------------------"
        docker-compose logs -f "$SERVICE"
        ;;
    
    *)
        echo "Использование: $0 {status|stop-old|start-new|restart-new|logs [service]}"
        echo ""
        echo "Команды:"
        echo "  status      - Показать статус всех контейнеров"
        echo "  stop-old    - Остановить старые контейнеры (lexus-scheduler, telegram-promotion-advanced)"
        echo "  start-new   - Запустить новую систему (docker-compose)"
        echo "  restart-new - Перезапустить новую систему"
        echo "  logs        - Показать логи (по умолчанию: marketer)"
        echo ""
        echo "Примеры:"
        echo "  $0 status"
        echo "  $0 stop-old"
        echo "  $0 logs marketer"
        echo "  $0 logs postgres"
        exit 1
        ;;
esac

