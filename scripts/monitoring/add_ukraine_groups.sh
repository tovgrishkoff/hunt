#!/bin/bash
# Скрипт для добавления групп Ukraine/Lexus в БД
# Использование: ./add_ukraine_groups.sh [файл_с_группами.txt]

PROJECT="ukraine"
DB_NAME="ukraine_db"
DB_USER="telegram_user_ukraine"
NICHE="ukraine_cars"

INPUT_FILE=${1:-"targets.txt"}

echo "=" | head -c 80
echo ""
echo "📋 ДОБАВЛЕНИЕ ГРУПП В БД UKRAINE"
echo "=" | head -c 80
echo ""

if [ ! -f "$INPUT_FILE" ]; then
    echo "❌ Файл $INPUT_FILE не найден!"
    echo ""
    echo "Использование:"
    echo "  $0 [файл_с_группами.txt]"
    echo ""
    echo "Файл должен содержать ссылки на группы (по одной на строку):"
    echo "  @group1"
    echo "  @group2"
    echo "  t.me/group3"
    echo "  https://t.me/group4"
    exit 1
fi

echo "📁 Файл: $INPUT_FILE"
echo "📊 Ниша: $NICHE"
echo ""

# Добавляем группы через Python скрипт
docker exec -i ukraine-account-manager python3 << PYEOF 2>&1
import asyncio
import sys
import re
from datetime import datetime

sys.path.insert(0, '/app')
from lexus_db.session import AsyncSessionLocal
from lexus_db.models import Target
from sqlalchemy import select

def normalize_group_link(link):
    """Нормализация ссылки на группу"""
    link = link.strip()
    if not link:
        return None
    
    # Убираем пробелы и переносы строк
    link = re.sub(r'\s+', '', link)
    
    # Если это @username
    if link.startswith('@'):
        return link.lower()
    
    # Если это t.me/... или https://t.me/...
    if 't.me/' in link:
        match = re.search(r't\.me/([^/?\s]+)', link)
        if match:
            username = match.group(1)
            return f"@{username}" if not username.startswith('@') else f"@{username.lstrip('@')}"
    
    # Если это полная ссылка https://...
    if link.startswith('http'):
        match = re.search(r't\.me/([^/?\s]+)', link)
        if match:
            username = match.group(1)
            return f"@{username}" if not username.startswith('@') else f"@{username.lstrip('@')}"
    
    return link

async def add_groups():
    # Читаем файл
    with open('/tmp/groups_input.txt', 'r') as f:
        lines = f.readlines()
    
    async with AsyncSessionLocal() as session:
        added = 0
        skipped = 0
        errors = 0
        
        for line in lines:
            link = line.strip()
            if not link or link.startswith('#'):
                continue
            
            normalized_link = normalize_group_link(link)
            if not normalized_link:
                print(f"⚠️  Пропущена невалидная ссылка: {link}")
                errors += 1
                continue
            
            # Проверяем, существует ли уже
            result = await session.execute(
                select(Target).where(Target.link == normalized_link)
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                skipped += 1
                continue
            
            # Создаем группу
            target = Target(
                link=normalized_link,
                niche='$NICHE',
                status='new',
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            
            session.add(target)
            added += 1
        
        await session.commit()
        print(f"\n📊 Итого:")
        print(f"  ✅ Добавлено: {added}")
        print(f"  ⏭️  Пропущено (уже есть): {skipped}")
        if errors > 0:
            print(f"  ⚠️  Ошибок: {errors}")

asyncio.run(add_groups())
PYEOF

# Копируем файл в контейнер
docker cp "$INPUT_FILE" ukraine-account-manager:/tmp/groups_input.txt

# Запускаем скрипт
docker exec ukraine-account-manager python3 << PYEOF 2>&1
import asyncio
import sys
import re
from datetime import datetime

sys.path.insert(0, '/app')
from lexus_db.session import AsyncSessionLocal
from lexus_db.models import Target
from sqlalchemy import select

def normalize_group_link(link):
    """Нормализация ссылки на группу"""
    link = link.strip()
    if not link:
        return None
    
    link = re.sub(r'\s+', '', link)
    
    if link.startswith('@'):
        return link.lower()
    
    if 't.me/' in link:
        match = re.search(r't\.me/([^/?\s]+)', link)
        if match:
            username = match.group(1)
            return f"@{username}" if not username.startswith('@') else f"@{username.lstrip('@')}"
    
    if link.startswith('http'):
        match = re.search(r't\.me/([^/?\s]+)', link)
        if match:
            username = match.group(1)
            return f"@{username}" if not username.startswith('@') else f"@{username.lstrip('@')}"
    
    return link

async def add_groups():
    with open('/tmp/groups_input.txt', 'r') as f:
        lines = f.readlines()
    
    async with AsyncSessionLocal() as session:
        added = 0
        skipped = 0
        errors = 0
        
        for line in lines:
            link = line.strip()
            if not link or link.startswith('#'):
                continue
            
            normalized_link = normalize_group_link(link)
            if not normalized_link:
                print(f"⚠️  Пропущена: {link}")
                errors += 1
                continue
            
            result = await session.execute(
                select(Target).where(Target.link == normalized_link)
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                skipped += 1
                continue
            
            target = Target(
                link=normalized_link,
                niche='$NICHE',
                status='new',
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            
            session.add(target)
            added += 1
        
        await session.commit()
        print(f"\n📊 Итого: добавлено {added}, пропущено {skipped}")
        if errors > 0:
            print(f"⚠️  Ошибок: {errors}")

asyncio.run(add_groups())
PYEOF

echo ""
echo "✅ Готово!"
echo ""
echo "Проверка:"
docker exec ${PROJECT}-postgres psql -U ${DB_USER} -d ${DB_NAME} -c "
SELECT COUNT(*) as total_groups,
       COUNT(*) FILTER (WHERE status = 'new') as new_groups,
       COUNT(*) FILTER (WHERE status = 'joined') as joined_groups
FROM targets 
WHERE niche = '$NICHE';
" 2>&1
