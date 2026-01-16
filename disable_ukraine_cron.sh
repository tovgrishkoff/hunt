#!/bin/bash
# Скрипт для отключения cron задач для ukraine-account-manager
# (так как теперь работает как daemon)

set -e

echo "🔄 Отключение cron задач для ukraine-account-manager..."
echo ""

# Создаем резервную копию
BACKUP_FILE="/tmp/crontab_backup_$(date +%Y%m%d_%H%M%S).txt"
crontab -l > "$BACKUP_FILE" 2>/dev/null || echo "" > "$BACKUP_FILE"
echo "✅ Создана резервная копия: $BACKUP_FILE"

# Обновляем crontab
crontab -l 2>/dev/null | sed -E 's/^([^#]*ukraine-account-manager.*(scout\.py|smart_joiner\.py).*)$/# 🇺🇦 ОТКЛЮЧЕНО - РАБОТАЕТ DAEMON (было: \1)/' | crontab -

echo "✅ Cron задачи для ukraine-account-manager отключены"
echo ""
echo "📋 Проверка изменений:"
crontab -l | grep -E "(ОТКЛЮЧЕНО|ukraine-account-manager.*scout|ukraine-account-manager.*joiner)" | head -5

echo ""
echo "✅ Готово! Теперь ukraine-account-manager работает как daemon"
