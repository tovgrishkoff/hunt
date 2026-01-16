#!/bin/bash
set -e

echo "🚗 Lexus Scheduler - Docker Container"
echo "======================================"
echo "📅 Расписание: 5 слотов в день по киевскому времени"
echo "   - 08:00 (morning)"
echo "   - 12:00 (noon)"
echo "   - 15:00 (afternoon)"
echo "   - 18:00 (evening)"
echo "   - 20:00 (night)"
echo ""
echo "📋 Лимиты:"
echo "   - Максимум 2 поста в день на группу"
echo "   - Один аккаунт на группу"
echo "   - Ротация групп и аккаунтов"
echo ""

# Проверяем наличие необходимых файлов
if [ ! -f "lexus_scheduler.py" ]; then
    echo "❌ Ошибка: lexus_scheduler.py не найден"
    exit 1
fi

if [ ! -f "promotion_system.py" ]; then
    echo "❌ Ошибка: promotion_system.py не найден"
    exit 1
fi

if [ ! -d "lexus_assets" ]; then
    echo "⚠️  Предупреждение: директория lexus_assets не найдена"
fi

# Запускаем планировщик
echo "🚀 Запуск планировщика Lexus..."
exec python3 lexus_scheduler.py --post
