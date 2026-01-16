#!/bin/bash

# Проверка причин отсутствия постов в Marketer

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}========================================================${NC}"
echo -e "${CYAN}   🔍 WHY NO POSTS? (MARKETER DIAGNOSTICS)   ${NC}"
echo -e "${CYAN}========================================================${NC}"
echo ""

# Проверяем логи за последние 2 часа
echo -e "${YELLOW}📋 Checking Marketer logs (last 2 hours)...${NC}"
echo ""

# Ищем ключевые сообщения
NO_GROUPS=$(docker logs --since 2h telegram-bali-marketer 2>&1 | grep -iE "No groups|No active groups|No groups available" | tail -5)
SKIPPING=$(docker logs --since 2h telegram-bali-marketer 2>&1 | grep -iE "Skipping|skipping" | tail -5)
SENT=$(docker logs --since 2h telegram-bali-marketer 2>&1 | grep -iE "✅ Sent|✅ Posted|Successfully posted" | tail -5)
FAILED=$(docker logs --since 2h telegram-bali-marketer 2>&1 | grep -iE "❌|Failed|error" | grep -v "Got difference" | tail -5)
WOKE_UP=$(docker logs --since 2h telegram-bali-marketer 2>&1 | grep -iE "Woke up|Next slot|Starting posting" | tail -5)

echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}⏰ WAKE-UP EVENTS${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
if [ ! -z "$WOKE_UP" ]; then
    echo "$WOKE_UP"
else
    echo -e "${YELLOW}No wake-up events found in last 2 hours${NC}"
fi
echo ""

echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}🚫 "NO GROUPS" MESSAGES${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
if [ ! -z "$NO_GROUPS" ]; then
    echo -e "${RED}$NO_GROUPS${NC}"
else
    echo -e "${GREEN}✅ No 'No groups' messages found${NC}"
fi
echo ""

echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}⏭️  SKIPPING MESSAGES${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
if [ ! -z "$SKIPPING" ]; then
    echo "$SKIPPING"
else
    echo -e "${GREEN}✅ No skipping messages${NC}"
fi
echo ""

echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}✅ SUCCESSFUL POSTS${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
if [ ! -z "$SENT" ]; then
    echo -e "${GREEN}$SENT${NC}"
    echo ""
    echo -e "${GREEN}✅ Posts were sent! Count: $(echo "$SENT" | wc -l)${NC}"
else
    echo -e "${RED}❌ No successful posts found in last 2 hours${NC}"
fi
echo ""

echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}❌ FAILURES${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
if [ ! -z "$FAILED" ]; then
    echo -e "${RED}$FAILED${NC}"
else
    echo -e "${GREEN}✅ No failures found${NC}"
fi
echo ""

# Итоговый диагноз
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}💡 DIAGNOSIS${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

if [ ! -z "$NO_GROUPS" ]; then
    echo -e "${YELLOW}🔍 REASON: No active groups available${NC}"
    echo -e "   Marketer woke up but found no groups to post to"
    echo -e "   → Check groups status: ./check_groups_status.sh"
    echo -e "   → Wait for Account Manager slot (09:00) to join new groups"
elif [ ! -z "$SENT" ]; then
    echo -e "${GREEN}✅ Posts were sent! Check logs above for details${NC}"
elif [ -z "$WOKE_UP" ]; then
    echo -e "${YELLOW}⏰ Marketer hasn't woken up for a slot yet${NC}"
    echo -e "   Next slot will be shown in: ./check_status.sh"
else
    echo -e "${YELLOW}❓ Unknown reason. Check logs manually:${NC}"
    echo -e "   docker logs --since 2h telegram-bali-marketer | tail -50"
fi

echo ""
echo -e "${CYAN}========================================================${NC}"
