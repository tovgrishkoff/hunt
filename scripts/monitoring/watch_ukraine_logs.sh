#!/bin/bash
# Скрипт для мониторинга логов в реальном времени

PROJECT="ukraine"
SERVICE=${1:-"account-manager"}

echo "📋 МОНИТОРИНГ ЛОГОВ: ${PROJECT}-${SERVICE}"
echo "Нажмите Ctrl+C для выхода"
echo ""

docker logs -f ${PROJECT}-${SERVICE} 2>&1
