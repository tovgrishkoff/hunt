#!/usr/bin/env python3
"""
Быстрое восстановление файловых сессий из string_session
"""

import asyncio
import json
from telethon import TelegramClient
from telethon.sessions import StringSession

async def restore_all():
    with open('accounts_config.json', 'r') as f:
        accounts = json.load(f)
    
    print(f"📋 Найдено {len(accounts)} аккаунтов\n")
    
    for account in accounts:
        session_name = account['session_name']
        string_session = account.get('string_session', '')
        api_id = int(account['api_id'])
        api_hash = account['api_hash']
        
        if not string_session:
            print(f"⚠️ {session_name}: нет string_session")
            continue
        
        try:
            print(f"🔄 {session_name}...", end=" ")
            
            # Проверяем string_session
            string_client = TelegramClient(StringSession(string_session), api_id, api_hash)
            await string_client.connect()
            
            if not await string_client.is_user_authorized():
                print("❌ string_session не валиден")
                await string_client.disconnect()
                continue
            
            me = await string_client.get_me()
            username = getattr(me, 'username', 'No username')
            
            # Восстанавливаем файловую сессию
            session_path = f'sessions/{session_name}'
            file_client = TelegramClient(session_path, api_id, api_hash)
            await file_client.connect()
            
            if await file_client.is_user_authorized():
                print(f"✅ уже авторизован (@{username})")
            else:
                # Копируем auth_key
                string_auth_key = string_client.session.auth_key
                if string_auth_key:
                    file_client.session.auth_key = string_auth_key
                    file_client.session.save()
                    print(f"✅ восстановлен (@{username})")
                else:
                    print("❌ не удалось получить auth_key")
            
            await string_client.disconnect()
            await file_client.disconnect()
            
        except Exception as e:
            print(f"❌ ошибка: {str(e)[:50]}")
    
    print("\n✅ Готово!")

if __name__ == "__main__":
    asyncio.run(restore_all())
