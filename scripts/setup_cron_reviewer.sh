#!/bin/bash
# Скрипт для настройки автоматического запуска Ревизора раз в сутки
# 
# Использование:
#   bash scripts/setup_cron_reviewer.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CRON_LOG="$PROJECT_DIR/logs/cron_reviewer.log"

# Создаем директорию для логов, если не существует
mkdir -p "$PROJECT_DIR/logs"

# Имя контейнера Account Manager (где будет запускаться скрипт)
CONTAINER_NAME="telegram-bali-account-manager"

# Путь к скрипту Ревизора внутри контейнера
REVIEWER_SCRIPT="/app/scripts/group_reviewer.py"

# Проверяем, существует ли контейнер
if ! docker ps --format "{{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
    echo "⚠️  Контейнер ${CONTAINER_NAME} не запущен"
    echo "   Запустите: cd $PROJECT_DIR && docker-compose up -d account-manager"
    echo ""
    echo "   Скрипт все равно будет добавлен в crontab, но не будет работать пока контейнер не запущен"
    read -p "Продолжить? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Проверяем, существует ли скрипт на хосте (для проверки)
if [ ! -f "$PROJECT_DIR/scripts/group_reviewer.py" ]; then
    echo "❌ Скрипт Ревизора не найден: $PROJECT_DIR/scripts/group_reviewer.py"
    exit 1
fi

# Проверяем, доступен ли скрипт внутри контейнера
if docker exec "${CONTAINER_NAME}" test -f "${REVIEWER_SCRIPT}" 2>/dev/null; then
    echo "✅ Скрипт найден внутри контейнера: ${REVIEWER_SCRIPT}"
else
    echo "⚠️  Скрипт не найден внутри контейнера (возможно, нужно пересобрать образ)"
    echo "   Убедитесь, что scripts/group_reviewer.py доступен в контейнере"
fi

# Создаем временный файл для cron задачи
CRON_TEMP=$(mktemp)

# Сохраняем текущие cron задачи
crontab -l > "$CRON_TEMP" 2>/dev/null || true

# Проверяем, есть ли уже такая задача
if grep -q "group_reviewer.py" "$CRON_TEMP" 2>/dev/null; then
    echo "⚠️  Задача для Ревизора уже существует в crontab"
    echo ""
    echo "Текущие задачи:"
    grep "group_reviewer.py" "$CRON_TEMP"
    echo ""
    read -p "Заменить существующую задачу? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Отменено"
        rm "$CRON_TEMP"
        exit 0
    fi
    # Удаляем старую задачу
    sed -i '/group_reviewer.py/d' "$CRON_TEMP"
fi

# Добавляем новую задачу (каждый день в 03:00)
# Запускаем через docker exec в контейнере account-manager, где есть все зависимости
CRON_LINE="0 3 * * * /usr/bin/docker exec -t ${CONTAINER_NAME} python ${REVIEWER_SCRIPT} >> ${CRON_LOG} 2>&1"

echo "$CRON_LINE" >> "$CRON_TEMP"

# Устанавливаем новую crontab
crontab "$CRON_TEMP"
rm "$CRON_TEMP"

echo "✅ Задача добавлена в crontab"
echo ""
echo "Расписание: каждый день в 03:00"
echo "Логи будут сохраняться в: $CRON_LOG"
echo ""
echo "Для проверки:"
echo "  crontab -l | grep group_reviewer"
echo ""
echo "Для удаления:"
echo "  crontab -e  # (найти строку и удалить)"
