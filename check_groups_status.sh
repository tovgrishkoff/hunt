#!/bin/bash

# Диагностика статуса групп в базе данных

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${CYAN}========================================================${NC}"
echo -e "${CYAN}   📊 DIAGNOSTICS: GROUPS STATUS IN DATABASE   ${NC}"
echo -e "${CYAN}========================================================${NC}"
echo ""

# Проверяем, что PostgreSQL контейнер запущен
if ! docker ps --format "{{.Names}}" | grep -q "telegram-bali-postgres"; then
    echo -e "${RED}❌ PostgreSQL container is not running!${NC}"
    exit 1
fi

echo -e "${YELLOW}📋 Checking groups status in database...${NC}"
echo ""

# Выполняем SQL запросы через docker exec
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT 
    status,
    COUNT(*) as count
FROM groups
GROUP BY status
ORDER BY count DESC;
" 2>/dev/null

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}📊 DETAILED STATUS BREAKDOWN${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Детальная статистика
docker exec telegram-bali-postgres psql -U telegram_user -d telegram_promotion -c "
SELECT 
    CASE 
        WHEN status = 'active' AND can_post = true THEN 'active (can_post)'
        WHEN status = 'active' AND can_post = false THEN 'active (no_post)'
        WHEN status = 'new' THEN 'new (waiting)'
        WHEN status = 'banned' THEN 'banned'
        WHEN status = 'inaccessible' THEN 'inaccessible'
        ELSE status
    END as group_status,
    COUNT(*) as count
FROM groups
GROUP BY 
    CASE 
        WHEN status = 'active' AND can_post = true THEN 'active (can_post)'
        WHEN status = 'active' AND can_post = false THEN 'active (no_post)'
        WHEN status = 'new' THEN 'new (waiting)'
        WHEN status = 'banned' THEN 'banned'
        WHEN status = 'inaccessible' THEN 'inaccessible'
        ELSE status
    END
ORDER BY count DESC;
" 2>/dev/null

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}⏰ WARM-UP STATUS${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Группы в warm-up периоде
docker exec telegram-bali-postgres psql -U telegram_user -d telegram_promotion -c "
SELECT 
    COUNT(*) FILTER (WHERE warm_up_until > NOW()) as in_warmup,
    COUNT(*) FILTER (WHERE warm_up_until <= NOW() OR warm_up_until IS NULL) as warmup_complete
FROM groups
WHERE status = 'active';
" 2>/dev/null

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}🔍 RECENT JOIN ACTIVITY${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Последние вступления
docker exec telegram-bali-postgres psql -U telegram_user -d telegram_promotion -c "
SELECT 
    username,
    status,
    can_post,
    joined_at,
    warm_up_until,
    CASE 
        WHEN warm_up_until > NOW() THEN '⏳ In warm-up'
        WHEN warm_up_until <= NOW() THEN '✅ Ready'
        ELSE '❓ Unknown'
    END as ready_status
FROM groups
WHERE joined_at IS NOT NULL
ORDER BY joined_at DESC
LIMIT 10;
" 2>/dev/null

echo ""
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}💡 DIAGNOSIS${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Автоматический анализ
ACTIVE_CAN_POST=$(docker exec telegram-bali-postgres psql -U telegram_user -d telegram_promotion -t -c "SELECT COUNT(*) FROM groups WHERE status = 'active' AND can_post = true;" 2>/dev/null | tr -d ' ')
NEW_GROUPS=$(docker exec telegram-bali-postgres psql -U telegram_user -d telegram_promotion -t -c "SELECT COUNT(*) FROM groups WHERE status = 'new';" 2>/dev/null | tr -d ' ')

if [ -z "$ACTIVE_CAN_POST" ]; then
    ACTIVE_CAN_POST=0
fi

if [ -z "$NEW_GROUPS" ]; then
    NEW_GROUPS=0
fi

echo -e "Active groups (can_post=true): ${CYAN}${ACTIVE_CAN_POST}${NC}"
echo -e "New groups (waiting to join): ${CYAN}${NEW_GROUPS}${NC}"
echo ""

if [ "$ACTIVE_CAN_POST" -eq 0 ]; then
    echo -e "${YELLOW}⚠️  WARNING: No active groups available for posting!${NC}"
    echo ""
    if [ "$NEW_GROUPS" -gt 0 ]; then
        echo -e "${GREEN}✅ Solution: Account Manager will join ${NEW_GROUPS} groups in next slot (09:00)${NC}"
        echo -e "   After joining, groups will enter warm-up period (24h)"
        echo -e "   Then they will be available for Marketer"
    else
        echo -e "${RED}❌ Problem: No new groups to join either!${NC}"
        echo -e "   Account Manager should search for new groups in next slot"
    fi
else
    echo -e "${GREEN}✅ Good: ${ACTIVE_CAN_POST} active groups available for posting${NC}"
    if [ "$ACTIVE_CAN_POST" -lt 5 ]; then
        echo -e "${YELLOW}   Consider: Low number of active groups, Account Manager should add more${NC}"
    fi
fi

echo ""
echo -e "${CYAN}========================================================${NC}"
