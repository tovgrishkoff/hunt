#!/usr/bin/env python3
"""
Скрипт для проверки реального членства аккаунтов в группах
Проверяет, действительно ли аккаунты являются участниками групп, в которые они "вступили"
"""
import asyncio
import sys
import os
from pathlib import Path

# Добавляем корень проекта в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import ChannelPrivateError, UsernameNotOccupiedError
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Настройка подключения к БД
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://telegram_user_bali:telegram_password_bali@telegram-bali-postgres:5432/telegram_promotion_bali')

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

async def check_membership(client: TelegramClient, username: str) -> tuple[bool, str]:
    """
    Проверяет, является ли аккаунт участником группы
    
    Returns:
        (is_member: bool, error_message: str)
    """
    try:
        entity = await client.get_entity(username)
        
        # Пытаемся получить информацию о группе
        try:
            full_chat = await client.get_entity(entity)
            # Если получили без ошибок - значит участник
            return True, "Участник"
        except ChannelPrivateError:
            return False, "Группа приватная или нет доступа"
        except Exception as e:
            # Пробуем отправить тестовое сообщение (не отправляем, просто проверяем доступ)
            try:
                # Получаем права доступа
                me = await client.get_me()
                permissions = await client.get_permissions(entity, me)
                if permissions:
                    return True, "Участник (проверено через permissions)"
            except:
                pass
            return False, f"Ошибка проверки: {str(e)[:100]}"
            
    except UsernameNotOccupiedError:
        return False, "Группа не существует"
    except ChannelPrivateError:
        return False, "Группа приватная"
    except Exception as e:
        return False, f"Ошибка: {str(e)[:100]}"

async def check_group_account_membership(group_username: str, account_id: int, string_session: str, api_id: int, api_hash: str):
    """Проверяет членство конкретного аккаунта в конкретной группе"""
    try:
        session_obj = StringSession(string_session.strip())
        client = TelegramClient(session_obj, int(api_id), api_hash)
        
        await client.connect()
        
        if not await client.is_user_authorized():
            print(f"  ❌ Аккаунт не авторизован")
            await client.disconnect()
            return False, "Аккаунт не авторизован"
        
        is_member, error = await check_membership(client, group_username)
        
        await client.disconnect()
        
        return is_member, error
        
    except Exception as e:
        return False, f"Ошибка создания клиента: {str(e)[:100]}"

async def main():
    """Основная функция"""
    print("=" * 80)
    print("🔍 ПРОВЕРКА ЧЛЕНСТВА АККАУНТОВ В ГРУППАХ")
    print("=" * 80)
    
    db = SessionLocal()
    
    try:
        # Получаем группы со статусом active и привязанными аккаунтами
        query = text("""
            SELECT g.id, g.username, g.status, g.assigned_account_id,
                   a.id as account_id, a.session_name, a.string_session, a.api_id, a.api_hash
            FROM groups g
            JOIN accounts a ON g.assigned_account_id = a.id
            WHERE g.niche = 'bali' 
              AND g.status = 'active'
              AND g.assigned_account_id IS NOT NULL
            ORDER BY g.id
            LIMIT 20
        """)
        
        result = db.execute(query)
        groups = result.fetchall()
        
        print(f"\n📋 Найдено {len(groups)} групп для проверки\n")
        
        not_members = []
        members = []
        
        for idx, group in enumerate(groups, 1):
            group_id, username, status, assigned_account_id, account_id, session_name, string_session, api_id, api_hash = group
            
            print(f"[{idx}/{len(groups)}] Группа: {username}")
            print(f"  Аккаунт: {session_name} (id={account_id})")
            
            is_member, error = await check_group_account_membership(
                username, account_id, string_session, api_id, api_hash
            )
            
            if is_member:
                print(f"  ✅ Участник")
                members.append((username, session_name))
            else:
                print(f"  ❌ НЕ участник: {error}")
                not_members.append((username, session_name, error))
            
            print()
            
            # Пауза между проверками
            await asyncio.sleep(2)
        
        # Итоговая статистика
        print("=" * 80)
        print("📊 ИТОГОВАЯ СТАТИСТИКА")
        print("=" * 80)
        print(f"✅ Участники: {len(members)}")
        print(f"❌ НЕ участники: {len(not_members)}")
        
        if not_members:
            print("\n❌ Группы, где аккаунты НЕ являются участниками:")
            for username, account, error in not_members:
                print(f"  - {username} (аккаунт: {account}): {error}")
        
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(main())
