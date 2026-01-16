#!/bin/bash
# Скрипт для запуска проекта Bali
set -e

# Загружаем переменные из .env.bali
if [ -f .env.bali ]; then
    export $(cat .env.bali | grep -v '^#' | xargs)
else
    echo "❌ Файл .env.bali не найден!"
    echo "Создайте его на основе .env.bali.example"
    exit 1
fi

# Запускаем docker-compose
docker-compose -f docker-compose.template.yml "$@"
