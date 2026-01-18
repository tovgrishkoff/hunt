#!/bin/bash
# Команды для мониторинга бота

# Цвета для вывода
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== КОМАНДЫ ДЛЯ МОНИТОРИНГА БОТА ===${NC}\n"

echo -e "${GREEN}1. КОЛИЧЕСТВО ПОДПИСЧИКОВ:${NC}"
echo "cd /home/tovgrishkoff/mvp2105/backup_working_version && source ../venv/bin/activate && python3 -c \"
import asyncio
import asyncpg
from config import DB_DSN

async def count_subscribers():
    conn = await asyncpg.connect(DB_DSN)
    count = await conn.fetchval('SELECT COUNT(*) FROM subscribers')
    print(f'Всего подписчиков: {count}')
    await conn.close()

asyncio.run(count_subscribers())
\""

echo -e "\n${GREEN}2. ПОДРОБНАЯ СТАТИСТИКА ПОДПИСЧИКОВ:${NC}"
echo "cd /home/tovgrishkoff/mvp2105/backup_working_version && source ../venv/bin/activate && python3 -c \"
import asyncio
import asyncpg
import json
from config import DB_DSN

async def get_stats():
    conn = await asyncpg.connect(DB_DSN)
    
    # Общее количество
    total = await conn.fetchval('SELECT COUNT(*) FROM subscribers')
    print(f'📊 Всего подписчиков: {total}')
    
    # Подписчики с нишами
    rows = await conn.fetch('SELECT user_id, niches FROM subscribers')
    with_niches = sum(1 for row in rows if row['niches'] and json.loads(row['niches']))
    print(f'📂 С выбранными нишами: {with_niches}')
    
    # Подписчики по странам
    rows = await conn.fetch('SELECT countries FROM subscribers')
    countries = {}
    for row in rows:
        if row['countries']:
            user_countries = json.loads(row['countries'])
            for country in user_countries:
                countries[country] = countries.get(country, 0) + 1
    
    print(f'🌍 Подписчики по странам:')
    for country, count in sorted(countries.items(), key=lambda x: -x[1]):
        print(f'   {country}: {count}')
    
    await conn.close()

asyncio.run(get_stats())
\""

echo -e "\n${GREEN}3. ЛОГИ В РЕАЛЬНОМ ВРЕМЕНИ (мониторинг):${NC}"
echo "tail -f /home/tovgrishkoff/mvp2105/backup_working_version/monitor_output.log"

echo -e "\n${GREEN}4. ЛОГИ С ФИЛЬТРАЦИЕЙ (только спам):${NC}"
echo "tail -f /home/tovgrishkoff/mvp2105/backup_working_version/monitor_output.log | grep --line-buffered -E '(КРИТИЧЕСКИЙ СПАМ|заблокирован|отфильтрован|🚫)'"

echo -e "\n${GREEN}5. ЛОГИ С ФИЛЬТРАЦИЕЙ (только обработка сообщений):${NC}"
echo "tail -f /home/tovgrishkoff/mvp2105/backup_working_version/monitor_output.log | grep --line-buffered -E '(ШАГ|КЛАССИФИКАЦИЯ|обработк)'"

echo -e "\n${GREEN}6. ПОСЛЕДНИЕ N СТРОК ЛОГОВ:${NC}"
echo "tail -n 50 /home/tovgrishkoff/mvp2105/backup_working_version/monitor_output.log"

echo -e "\n${GREEN}7. СТАТИСТИКА ЗАБЛОКИРОВАННОГО СПАМА:${NC}"
echo "tail -n 500 /home/tovgrishkoff/mvp2105/backup_working_version/monitor_output.log | grep -c 'КРИТИЧЕСКИЙ СПАМ' && echo 'заблокировано как критический спам'"

echo -e "\n${GREEN}8. ПРОВЕРКА СТАТУСА ПРОЦЕССА:${NC}"
echo "ps aux | grep '[p]ython3 user_monitor_bot.py'"

echo -e "\n${GREEN}9. ПЕРЕЗАПУСК МОНИТОРИНГА:${NC}"
echo "cd /home/tovgrishkoff/mvp2105/backup_working_version && kill \$(ps aux | grep '[p]ython3 user_monitor_bot.py' | awk '{print \$2}') 2>/dev/null; sleep 2; source ../venv/bin/activate && nohup python3 user_monitor_bot.py > monitor_output.log 2>&1 &"

echo -e "\n${YELLOW}Примечание: Для выполнения команд скопируйте нужную команду и выполните в терминале${NC}\n"

