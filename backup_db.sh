#!/bin/bash

# Скрипт для автоматического бэкапа базы данных Bali Bot
# Запускается ежедневно через cron в 03:00

# Настройки
BACKUP_DIR="/home/tovgrishkoff/mvp2105/backups"
CONTAINER_NAME="bali-postgres"
DB_NAME="bali_bot"
DB_USER="grishkoff"
DATE=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/bali_bot_backup_$DATE.sql"
BACKUP_FILE_GZ="$BACKUP_FILE.gz"

# Создаем директорию для бэкапов, если её нет
mkdir -p "$BACKUP_DIR"

echo "🔄 Начинаем резервное копирование базы данных..."
echo "📁 Файл: $BACKUP_FILE"

# Создаем бэкап через Docker контейнер
docker exec $CONTAINER_NAME pg_dump -U $DB_USER $DB_NAME > "$BACKUP_FILE"

# Проверяем успешность создания бэкапа
if [ $? -eq 0 ]; then
    # Сжимаем бэкап
    gzip "$BACKUP_FILE"
    
    if [ $? -eq 0 ]; then
        echo "✅ Бэкап успешно создан: $BACKUP_FILE_GZ"
        echo "📊 Размер бэкапа: $(du -h $BACKUP_FILE_GZ | cut -f1)"
        
        # Удаляем старые бэкапы (старше 30 дней)
        find "$BACKUP_DIR" -name "bali_bot_backup_*.sql.gz" -type f -mtime +30 -delete
        echo "🧹 Старые бэкапы (>30 дней) удалены"
        
        # Показываем последние 5 бэкапов
        echo ""
        echo "📋 Последние 5 бэкапов:"
        ls -lh "$BACKUP_DIR"/bali_bot_backup_*.sql.gz | tail -5
    else
        echo "❌ Ошибка при сжатии бэкапа"
        exit 1
    fi
else
    echo "❌ Ошибка при создании бэкапа"
    exit 1
fi

echo "✨ Бэкап завершен успешно"






