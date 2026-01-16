#!/bin/bash

# Цвета для вывода
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

# Функция для вывода заголовка
print_header() {
    echo -e "${CYAN}========================================================${NC}"
    echo -e "${CYAN}   🚀 SYSTEM STATUS MONITOR (BALI + LEXUS)   ${NC}"
    echo -e "${CYAN}========================================================${NC}"
    echo ""
}

# Функция для проверки статуса контейнера
check_container_status() {
    local container_name=$1
    if docker ps --format "{{.Names}}" | grep -q "^${container_name}$"; then
        local status=$(docker ps --format "{{.Status}}" --filter "name=^${container_name}$")
        echo -e "${GREEN}✅ Running${NC} - ${status}"
        return 0
    else
        echo -e "${RED}❌ Not running${NC}"
        return 1
    fi
}

# Функция для получения последних логов
get_recent_logs() {
    local container=$1
    local lines=${2:-5}
    if docker ps --format "{{.Names}}" | grep -q "^${container}$"; then
        docker logs --tail=${lines} ${container} 2>&1 | tail -${lines}
    else
        echo -e "${RED}Container not running${NC}"
    fi
}

# Функция для подсчета ошибок
count_errors() {
    local container=$1
    local since=${2:-1h}
    if docker ps --format "{{.Names}}" | grep -q "^${container}$"; then
        local count=$(docker logs --since ${since} ${container} 2>&1 | grep -i "error\|exception\|failed\|❌" | grep -v "Got difference" | wc -l)
        echo ${count}
    else
        echo "0"
    fi
}

# Очистка экрана (опционально, можно раскомментировать)
# clear

print_header

# 1. ПРОВЕРКА КОНТЕЙНЕРОВ
echo -e "${YELLOW}📊 ACTIVE CONTAINERS STATUS:${NC}"
echo ""
echo -e "${BLUE}Bali System:${NC}"
check_container_status "telegram-bali-account-manager"
check_container_status "telegram-bali-marketer"
check_container_status "telegram-bali-activity"
check_container_status "telegram-bali-secretary"
check_container_status "telegram-bali-postgres"

echo ""
echo -e "${BLUE}Lexus System:${NC}"
check_container_status "lexus-scheduler"
check_container_status "lexus-secretary"

echo ""

# 2. BALI: ACCOUNT MANAGER (Вступление)
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}🏝️  BALI: Account Manager (Joining Groups)${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
if docker ps --format "{{.Names}}" | grep -q "^telegram-bali-account-manager$"; then
    echo -e "${YELLOW}Last 5 log entries:${NC}"
    get_recent_logs "telegram-bali-account-manager" 5
    echo ""
    errors=$(count_errors "telegram-bali-account-manager")
    if [ "$errors" -gt 0 ]; then
        echo -e "${RED}⚠️  Errors in last hour: ${errors}${NC}"
    else
        echo -e "${GREEN}✅ No errors in last hour${NC}"
    fi
else
    echo -e "${RED}❌ Container not running!${NC}"
fi
echo ""

# 3. BALI: MARKETER (Постинг)
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}🏝️  BALI: Marketer (Posting Messages)${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
if docker ps --format "{{.Names}}" | grep -q "^telegram-bali-marketer$"; then
    echo -e "${YELLOW}Last 5 log entries:${NC}"
    get_recent_logs "telegram-bali-marketer" 5
    echo ""
    errors=$(count_errors "telegram-bali-marketer")
    if [ "$errors" -gt 0 ]; then
        echo -e "${RED}⚠️  Errors in last hour: ${errors}${NC}"
    else
        echo -e "${GREEN}✅ No errors in last hour${NC}"
    fi
else
    echo -e "${RED}❌ Container not running!${NC}"
fi
echo ""

# 4. LEXUS: SCHEDULER (Рассылка Украина)
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}🚗 LEXUS: Scheduler (Ukraine Car Sales)${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
if docker ps --format "{{.Names}}" | grep -q "^lexus-scheduler$"; then
    echo -e "${YELLOW}Last 5 log entries:${NC}"
    get_recent_logs "lexus-scheduler" 5
    echo ""
    errors=$(count_errors "lexus-scheduler")
    if [ "$errors" -gt 0 ]; then
        echo -e "${RED}⚠️  Errors in last hour: ${errors}${NC}"
    else
        echo -e "${GREEN}✅ No errors in last hour${NC}"
    fi
else
    echo -e "${RED}❌ Container not running!${NC}"
fi
echo ""

# 5. LEXUS: SECRETARY (Пересылка DM)
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}📬 LEXUS: Secretary (Forward DMs to @grishkoff)${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
if docker ps --format "{{.Names}}" | grep -q "^lexus-secretary$"; then
    echo -e "${YELLOW}Last 5 log entries:${NC}"
    get_recent_logs "lexus-secretary" 5
    echo ""
    errors=$(count_errors "lexus-secretary")
    if [ "$errors" -gt 0 ]; then
        echo -e "${RED}⚠️  Errors in last hour: ${errors}${NC}"
    else
        echo -e "${GREEN}✅ No errors in last hour${NC}"
    fi
else
    echo -e "${RED}❌ Container not running!${NC}"
fi
echo ""

# 6. СТАТИСТИКА ОШИБОК
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}⚠️  ERROR SUMMARY (Last 1 hour)${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

total_errors=0

# Проверяем ошибки в Bali системе
bali_errors=$(docker-compose logs --since 1h 2>&1 | grep -iE "error|exception|failed|❌" | grep -vE "Got difference|INFO|WARNING" | tail -5)
if [ ! -z "$bali_errors" ]; then
    echo -e "${RED}Bali System Errors:${NC}"
    echo "$bali_errors"
    total_errors=$(echo "$bali_errors" | wc -l)
else
    echo -e "${GREEN}✅ Bali: No critical errors${NC}"
fi

# Проверяем ошибки в Lexus системе
if docker ps --format "{{.Names}}" | grep -q "^lexus-scheduler$"; then
    lexus_errors=$(docker logs --since 1h lexus-scheduler 2>&1 | grep -iE "error|exception|failed|❌" | grep -vE "INFO|WARNING" | tail -5)
    if [ ! -z "$lexus_errors" ]; then
        echo ""
        echo -e "${RED}Lexus System Errors:${NC}"
        echo "$lexus_errors"
        total_errors=$((total_errors + $(echo "$lexus_errors" | wc -l)))
    else
        echo -e "${GREEN}✅ Lexus: No critical errors${NC}"
    fi
fi

echo ""

# 7. КРАТКАЯ СТАТИСТИКА (опционально, если есть файлы логов)
if [ -f "logs/group_post_history.json" ]; then
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}📊 QUICK STATS${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    
    # Подсчет групп с историей постов (если Python доступен)
    if command -v python3 &> /dev/null; then
        python3 << EOF
import json
from datetime import datetime, timezone
from pathlib import Path

try:
    history_file = Path('logs/group_post_history.json')
    if history_file.exists():
        with open(history_file, 'r') as f:
            history = json.load(f)
        
        today = datetime.now(timezone.utc).date()
        groups_with_posts = len(history)
        posts_today = 0
        
        for group_data in history.values():
            if isinstance(group_data, dict):
                for timestamps in group_data.values():
                    if isinstance(timestamps, list):
                        for ts in timestamps:
                            try:
                                post_time = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                                if post_time.date() == today:
                                    posts_today += 1
                            except:
                                pass
        
        print(f"Groups with posts: {groups_with_posts}")
        print(f"Posts today: {posts_today}")
    else:
        print("No post history file found")
except Exception as e:
    print(f"Error reading stats: {e}")
EOF
    fi
    echo ""
fi

# 8. СЛЕДУЮЩИЕ СЛОТЫ (краткая информация)
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}⏰ NEXT SCHEDULED SLOTS${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Пытаемся найти информацию о следующих слотах в логах
if docker ps --format "{{.Names}}" | grep -q "^telegram-bali-account-manager$"; then
    next_slot=$(docker logs telegram-bali-account-manager 2>&1 | grep -i "Next slot" | tail -1)
    if [ ! -z "$next_slot" ]; then
        echo -e "${BLUE}Bali Account Manager:${NC} ${next_slot}"
    fi
fi

if docker ps --format "{{.Names}}" | grep -q "^telegram-bali-marketer$"; then
    next_slot=$(docker logs telegram-bali-marketer 2>&1 | grep -i "Next slot" | tail -1)
    if [ ! -z "$next_slot" ]; then
        echo -e "${BLUE}Bali Marketer:${NC} ${next_slot}"
    fi
fi

if docker ps --format "{{.Names}}" | grep -q "^lexus-scheduler$"; then
    next_slot=$(docker logs lexus-scheduler 2>&1 | grep -i "Next slot" | tail -1)
    if [ ! -z "$next_slot" ]; then
        echo -e "${BLUE}Lexus Scheduler:${NC} ${next_slot}"
    fi
fi

echo ""
echo -e "${CYAN}========================================================${NC}"
echo -e "${GREEN}✅ Status check completed${NC}"
echo -e "${CYAN}========================================================${NC}"
