#!/bin/bash
# Скрипт для проверки логов системы Ukraine/Lexus

PROJECT="ukraine"
SERVICE=${1:-"account-manager"}
LINES=${2:-50}

echo "=" | head -c 80
echo ""
echo "📋 ЛОГИ: ${PROJECT}-${SERVICE} (последние ${LINES} строк)"
echo "=" | head -c 80
echo ""

# Проверка ошибок
echo ""
echo "❌ ОШИБКИ:"
docker logs ${PROJECT}-${SERVICE} --tail=${LINES} 2>&1 | grep -iE "(error|exception|traceback|failed|fail)" | tail -20 || echo "Ошибок не найдено"

echo ""
echo "=" | head -c 80
echo ""
echo "📋 ПОЛНЫЙ ЛОГ:"
echo "=" | head -c 80
echo ""

# Полный лог
docker logs ${PROJECT}-${SERVICE} --tail=${LINES} 2>&1
