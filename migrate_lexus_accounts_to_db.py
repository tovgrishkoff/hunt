#!/usr/bin/env python3
"""
Скрипт миграции аккаунтов Lexus в новую БД telegram_promotion_lexus
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lexus_db.session import AsyncSessionLocal, init_db
from lexus_db.models import Account
from sqlalchemy import select
import os

# Устанавливаем переменные окружения для подключения к новой БД
os.environ['DATABASE_URL'] = 'postgresql://telegram_user_bali:telegram_password_bali@localhost:5440/telegram_promotion_lexus'
os.environ['POSTGRES_HOST'] = 'localhost'
os.environ['POSTGRES_PORT'] = '5440'
os.environ['POSTGRES_DB'] = 'telegram_promotion_lexus'

async def main():
    """Миграция аккаунтов Lexus"""
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║     МИГРАЦИЯ АККАУНТОВ LEXUS В НОВУЮ БД                     ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()
    
    # Загружаем конфигурацию
    accounts_config_path = Path('accounts_config.json')
    lexus_config_path = Path('lexus_accounts_config.json')
    
    if not accounts_config_path.exists():
        print(f"❌ Файл {accounts_config_path} не найден!")
        return
    
    if not lexus_config_path.exists():
        print(f"❌ Файл {lexus_config_path} не найден!")
        return
    
    # Загружаем все аккаунты
    with open(accounts_config_path, 'r', encoding='utf-8') as f:
        all_accounts = json.load(f)
    
    # Загружаем список разрешенных аккаунтов Lexus
    with open(lexus_config_path, 'r', encoding='utf-8') as f:
        lexus_config = json.load(f)
    
    allowed_accounts = set(lexus_config.get('allowed_accounts', []))
    print(f"✅ Разрешенные аккаунты Lexus: {sorted(allowed_accounts)}")
    print()
    
    # Фильтруем только Lexus аккаунты
    lexus_accounts = [
        acc for acc in all_accounts
        if acc.get('session_name') in allowed_accounts
    ]
    
    print(f"📋 Найдено {len(lexus_accounts)} аккаунтов Lexus для миграции")
    print()
    
    # Подключаемся к БД
    async with AsyncSessionLocal() as session:
        # Инициализируем БД (создаем таблицы если их нет)
        await init_db()
        print("✅ БД инициализирована")
        print()
        
        # Добавляем аккаунты
        added = 0
        updated = 0
        
        for acc_config in lexus_accounts:
            session_name = acc_config.get('session_name')
            
            # Проверяем, есть ли уже такой аккаунт
            result = await session.execute(
                select(Account).where(Account.session_name == session_name)
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                # Обновляем существующий
                existing.api_id = acc_config.get('api_id')
                existing.api_hash = acc_config.get('api_hash')
                existing.string_session = acc_config.get('string_session')
                existing.phone = acc_config.get('phone')
                existing.nickname = acc_config.get('nickname')
                existing.bio = acc_config.get('bio')
                existing.proxy = acc_config.get('proxy')
                existing.status = 'active'
                updated += 1
                print(f"  🔄 Обновлен: {session_name}")
            else:
                # Создаем новый
                new_account = Account(
                    session_name=session_name,
                    api_id=acc_config.get('api_id'),
                    api_hash=acc_config.get('api_hash'),
                    string_session=acc_config.get('string_session'),
                    phone=acc_config.get('phone'),
                    nickname=acc_config.get('nickname'),
                    bio=acc_config.get('bio'),
                    proxy=acc_config.get('proxy'),
                    status='active'
                )
                session.add(new_account)
                added += 1
                print(f"  ✅ Добавлен: {session_name}")
        
        await session.commit()
        print()
        print(f"✅ Миграция завершена:")
        print(f"   Добавлено: {added}")
        print(f"   Обновлено: {updated}")
        print()
        
        # Проверяем результат
        result = await session.execute(select(Account))
        all_accounts_db = result.scalars().all()
        print(f"📊 Всего аккаунтов в БД: {len(all_accounts_db)}")
        for acc in all_accounts_db:
            print(f"   - {acc.session_name} ({acc.status})")

if __name__ == "__main__":
    asyncio.run(main())
