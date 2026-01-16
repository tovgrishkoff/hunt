#!/bin/bash
# Скрипт для запуска проекта Ukraine
set -e

# Загружаем переменные из .env.ukraine
if [ -f .env.ukraine ]; then
    export $(cat .env.ukraine | grep -v '^#' | xargs)
else
    echo "❌ Файл .env.ukraine не найден!"
    echo "Создайте его на основе .env.ukraine.example"
    exit 1
fi

# Создаем временный docker-compose файл с подставленными переменными
# (Docker Compose не поддерживает переменные в ключах секций)
COMPOSE_FILE="docker-compose.ukraine.yml"
envsubst < docker-compose.template.yml > "$COMPOSE_FILE"

# Запускаем docker-compose
docker-compose -f "$COMPOSE_FILE" "$@"

# Удаляем временный файл после завершения (опционально, можно оставить для отладки)
# rm -f "$COMPOSE_FILE"
