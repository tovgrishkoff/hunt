#!/bin/bash

# Детальный мониторинг с фильтрацией по ключевым событиям

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${CYAN}========================================================${NC}"
echo -e "${CYAN}   📊 DETAILED MONITORING (BALI + LEXUS)   ${NC}"
echo -e "${CYAN}========================================================${NC}"
echo ""

# BALI: ACCOUNT MANAGER - Детальные логи
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}🏝️  BALI: Account Manager - Key Events (Last 20 entries)${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
if docker ps --format "{{.Names}}" | grep -q "^telegram-bali-account-manager$"; then
    docker logs --tail=100 telegram-bali-account-manager 2>&1 | grep -E "Joined|FloodWait|Sleeping|✅|❌|📋 Обработаем|Next slot|Woke up" | tail -20
else
    echo -e "${RED}❌ Container not running!${NC}"
fi
echo ""

# BALI: MARKETER - Детальные логи
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}🏝️  BALI: Marketer - Key Events (Last 20 entries)${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
if docker ps --format "{{.Names}}" | grep -q "^telegram-bali-marketer$"; then
    docker logs --tail=100 telegram-bali-marketer 2>&1 | grep -E "Sent|Posted|Write forbidden|banned|✅|❌|Next slot|Woke up|No groups available" | tail -20
else
    echo -e "${RED}❌ Container not running!${NC}"
fi
echo ""

# LEXUS: SCHEDULER - Детальные логи
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}🚗 LEXUS: Scheduler - Key Events (Last 20 entries)${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
if docker ps --format "{{.Names}}" | grep -q "^lexus-scheduler$"; then
    docker logs --tail=100 lexus-scheduler 2>&1 | grep -E "Posted|Sent|Failed|✅|❌|Next slot|Woke up|Starting Lexus posting" | tail -20
else
    echo -e "${RED}❌ Container not running!${NC}"
fi
echo ""

# ОШИБКИ (только критические)
echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${RED}🚨 CRITICAL ERRORS (Last 2 hours)${NC}"
echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

bali_critical=$(docker-compose logs --since 2h 2>&1 | grep -iE "error|exception|failed|❌" | grep -vE "Got difference|INFO|WARNING|DEBUG" | tail -10)
lexus_critical=$(docker logs --since 2h lexus-scheduler 2>&1 | grep -iE "error|exception|failed|❌" | grep -vE "INFO|WARNING|DEBUG" | tail -10)

if [ -z "$bali_critical" ] && [ -z "$lexus_critical" ]; then
    echo -e "${GREEN}✅ No critical errors found${NC}"
else
    if [ ! -z "$bali_critical" ]; then
        echo -e "${YELLOW}Bali System:${NC}"
        echo "$bali_critical"
        echo ""
    fi
    if [ ! -z "$lexus_critical" ]; then
        echo -e "${YELLOW}Lexus System:${NC}"
        echo "$lexus_critical"
    fi
fi

echo ""
echo -e "${CYAN}========================================================${NC}"
