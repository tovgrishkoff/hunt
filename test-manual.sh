#!/bin/bash
# Скрипт для ручного тестирования scout и smart_joiner
# Использование: ./test-manual.sh [bali|ukraine|both]

set -e

PROJECT="${1:-both}"

echo "🧪 Ручное тестирование скриптов"
echo "================================"
echo ""

test_bali() {
    echo "🌴 Тестирование проекта BALI"
    echo "----------------------------"
    
    if ! docker ps | grep -q "bali-account-manager"; then
        echo "❌ Контейнер bali-account-manager не запущен!"
        echo "   Запустите: ./run-bali.sh up -d"
        return 1
    fi
    
    echo ""
    echo "1️⃣ Тест разведки (scout.py)..."
    docker exec bali-account-manager python3 /app/services/account-manager/scout.py bali_rent
    
    echo ""
    echo "2️⃣ Тест вступления (smart_joiner.py, батч 2)..."
    docker exec bali-account-manager python3 /app/services/account-manager/smart_joiner.py bali_rent 2
    
    echo ""
    echo "✅ Тесты Bali завершены"
}

test_ukraine() {
    echo ""
    echo "🇺🇦 Тестирование проекта UKRAINE"
    echo "--------------------------------"
    
    if ! docker ps | grep -q "ukraine-account-manager"; then
        echo "❌ Контейнер ukraine-account-manager не запущен!"
        echo "   Запустите: ./run-ukraine.sh up -d"
        return 1
    fi
    
    echo ""
    echo "1️⃣ Тест разведки (scout.py)..."
    docker exec ukraine-account-manager python3 /app/services/account-manager/scout.py ukraine_cars
    
    echo ""
    echo "2️⃣ Тест вступления (smart_joiner.py, батч 2)..."
    docker exec ukraine-account-manager python3 /app/services/account-manager/smart_joiner.py ukraine_cars 2
    
    echo ""
    echo "✅ Тесты Ukraine завершены"
}

case $PROJECT in
    bali)
        test_bali
        ;;
    ukraine)
        test_ukraine
        ;;
    both)
        test_bali
        test_ukraine
        ;;
    *)
        echo "❌ Неверный проект: $PROJECT"
        echo "Использование: $0 [bali|ukraine|both]"
        exit 1
        ;;
esac

echo ""
echo "================================"
echo "✅ Все тесты завершены!"
echo ""
echo "💡 Если тесты прошли успешно, можете установить Cron:"
echo "   ./install-cron.sh"
