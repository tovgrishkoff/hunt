#!/usr/bin/env python3
"""
Скрипт для миграции аккаунтов и групп Ukraine/Lexus в БД
"""
import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

# Добавляем путь к модулям
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from lexus_db.session import AsyncSessionLocal
from lexus_db.models import Account, Target
from sqlalchemy import select
import re


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


async def migrate_accounts():
    """Миграция аккаунтов"""
    print("=" * 80)
    print("👤 МИГРАЦИЯ АККАУНТОВ")
    print("=" * 80)
    
    # Загружаем конфигурацию
    base_dir = Path(__file__).parent.parent.parent
    
    accounts_config_file = base_dir / "accounts_config.json"
    lexus_config_file = base_dir / "lexus_accounts_config.json"
    
    if not accounts_config_file.exists():
        print(f"❌ Файл {accounts_config_file} не найден!")
        return
    
    if not lexus_config_file.exists():
        print(f"❌ Файл {lexus_config_file} не найден!")
        return
    
    with open(accounts_config_file, 'r') as f:
        accounts_config = json.load(f)
    
    with open(lexus_config_file, 'r') as f:
        lexus_config = json.load(f)
    
    lexus_allowed = set(lexus_config.get('allowed_accounts', []))
    
    async with AsyncSessionLocal() as session:
        added = 0
        skipped = 0
        
        for acc_config in accounts_config:
            session_name = acc_config.get('session_name', '')
            
            # Добавляем только аккаунты из Lexus
            if session_name not in lexus_allowed:
                continue
            
            # Проверяем, существует ли уже
            result = await session.execute(
                select(Account).where(Account.session_name == session_name)
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                print(f"⏭️  Пропущен (уже есть): {session_name}")
                skipped += 1
                continue
            
            # Создаем аккаунт
            account = Account(
                session_name=session_name,
                phone=acc_config.get('phone'),
                session_string=acc_config.get('string_session'),
                api_id=acc_config.get('api_id'),
                api_hash=acc_config.get('api_hash'),
                status='active',
                daily_posts_count=0,
                last_stats_reset=datetime.utcnow(),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            
            session.add(account)
            print(f"✅ Добавлен: {session_name}")
            added += 1
        
        await session.commit()
        print(f"\n📊 Итого: добавлено {added}, пропущено {skipped}")


async def migrate_groups():
    """Миграция групп из group_niches.json"""
    print("\n" + "=" * 80)
    print("📋 МИГРАЦИЯ ГРУПП")
    print("=" * 80)
    
    base_dir = Path(__file__).parent.parent.parent
    group_niches_file = base_dir / "group_niches.json"
    
    if not group_niches_file.exists():
        print(f"❌ Файл {group_niches_file} не найден!")
        return
    
    with open(group_niches_file, 'r') as f:
        group_niches = json.load(f)
    
    # Фильтруем только ukraine_cars
    ukraine_cars_groups = {
        group: niche for group, niche in group_niches.items()
        if niche == 'ukraine_cars'
    }
    
    print(f"📋 Найдено {len(ukraine_cars_groups)} групп с нишей 'ukraine_cars'")
    
    async with AsyncSessionLocal() as session:
        added = 0
        skipped = 0
        
        for group_link, niche in ukraine_cars_groups.items():
            normalized_link = normalize_group_link(group_link)
            if not normalized_link:
                print(f"⚠️  Пропущена невалидная ссылка: {group_link}")
                skipped += 1
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
                niche=niche,
                status='new',
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            
            session.add(target)
            added += 1
        
        await session.commit()
        print(f"\n📊 Итого: добавлено {added}, пропущено {skipped}")


async def main():
    """Основная функция"""
    await migrate_accounts()
    await migrate_groups()
    
    print("\n" + "=" * 80)
    print("✅ МИГРАЦИЯ ЗАВЕРШЕНА")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
