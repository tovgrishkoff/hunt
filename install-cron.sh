#!/bin/bash
# Скрипт для установки Cron задач для мульти-проектной системы
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🚀 Установка Cron задач для Telegram Promotion System"
echo ""

# Проверяем, что контейнеры запущены
if ! docker ps | grep -q "bali-account-manager"; then
    echo "⚠️  Предупреждение: контейнер bali-account-manager не запущен"
    echo "   Запустите: ./run-bali.sh up -d"
    echo ""
fi

if ! docker ps | grep -q "ukraine-account-manager"; then
    echo "⚠️  Предупреждение: контейнер ukraine-account-manager не запущен"
    echo "   Запустите: ./run-ukraine.sh up -d"
    echo ""
fi

# Создаем директории для логов (если не существуют)
mkdir -p data/bali/logs
mkdir -p data/ukraine/logs

echo "Выберите вариант установки:"
echo "1) Только Bali"
echo "2) Только Ukraine"
echo "3) Оба проекта (рекомендуется)"
echo ""
read -p "Ваш выбор (1-3): " choice

case $choice in
    1)
        echo "📅 Устанавливаем Cron для проекта Bali..."
        # Добавляем в существующий crontab
        (crontab -l 2>/dev/null; cat crontab.bali) | crontab -
        echo "✅ Cron задачи для Bali установлены"
        ;;
    2)
        echo "📅 Устанавливаем Cron для проекта Ukraine..."
        (crontab -l 2>/dev/null; cat crontab.ukraine) | crontab -
        echo "✅ Cron задачи для Ukraine установлены"
        ;;
    3)
        echo "📅 Устанавливаем Cron для обоих проектов..."
        (crontab -l 2>/dev/null; cat crontab.combined) | crontab -
        echo "✅ Cron задачи для обоих проектов установлены"
        ;;
    *)
        echo "❌ Неверный выбор"
        exit 1
        ;;
esac

echo ""
echo "📋 Текущие Cron задачи:"
echo "===================="
crontab -l | grep -E "bali|ukraine" || echo "Задачи не найдены"
echo "===================="
echo ""
echo "✅ Установка завершена!"
echo ""
echo "💡 Полезные команды:"
echo "   Просмотр всех cron задач: crontab -l"
echo "   Редактирование: crontab -e"
echo "   Удаление всех: crontab -r"
echo ""
echo "📊 Логи будут писаться в:"
echo "   Bali:   data/bali/logs/scout_cron.log и joiner_cron.log"
echo "   Ukraine: data/ukraine/logs/scout_cron.log и joiner_cron.log"
