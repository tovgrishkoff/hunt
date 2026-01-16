#!/usr/bin/env python3
"""
Восстановление файловых сессий из string_session для проблемных аккаунтов
"""

import asyncio
import json
from telethon import TelegramClient
from telethon.sessions import StringSession

async def fix_sessions():
    with open('accounts_config.json', 'r') as f:
        accounts = json.load(f)
    
    print(f"📋 Восстановление сессий для {len(accounts)} аккаунтов\n")
    
    for account in accounts:
        session_name = account['session_name']
        string_session = account.get('string_session', '')
        api_id = int(account['api_id'])
        api_hash = account['api_hash']
        
        if not string_session:
            print(f"⚠️ {session_name}: нет string_session, пропускаем\n")
            continue
        
        print(f"🔄 {session_name}...")
        
        try:
            # Сначала проверяем файловую сессию
            file_client = TelegramClient(f'sessions/{session_name}', api_id, api_hash)
            try:
                await asyncio.wait_for(file_client.connect(), timeout=5.0)
                if await file_client.is_user_authorized():
                    me = await file_client.get_me()
                    print(f"   ✅ Файловая сессия уже работает (@{me.username})\n")
                    await file_client.disconnect()
                    continue
                await file_client.disconnect()
            except:
                try:
                    await file_client.disconnect()
                except:
                    pass
            
            # Восстанавливаем из string_session
            print(f"   Восстановление из string_session...")
            string_client = TelegramClient(StringSession(string_session), api_id, api_hash)
            await string_client.connect()
            
            if not await string_client.is_user_authorized():
                print(f"   ❌ String session не валиден\n")
                await string_client.disconnect()
                continue
            
            me = await string_client.get_me()
            username = getattr(me, 'username', 'No username')
            
            # Копируем auth_key в файловую сессию
            string_auth_key = string_client.session.auth_key
            await string_client.disconnect()
            
            if not string_auth_key:
                print(f"   ❌ Не удалось получить auth_key\n")
                continue
            
            # Создаем новую файловую сессию с auth_key
            file_client = TelegramClient(f'sessions/{session_name}', api_id, api_hash)
            await file_client.connect()
            
            # Устанавливаем auth_key
            file_client.session.auth_key = string_auth_key
            file_client.session.save()
            await file_client.disconnect()
            
            # Проверяем, что восстановление прошло успешно
            check_client = TelegramClient(f'sessions/{session_name}', api_id, api_hash)
            await check_client.connect()
            
            if await check_client.is_user_authorized():
                me = await check_client.get_me()
                print(f"   ✅ Сессия восстановлена! (@{me.username})\n")
            else:
                print(f"   ⚠️ Сессия восстановлена, но не авторизована\n")
            
            await check_client.disconnect()
            
        except Exception as e:
            print(f"   ❌ Ошибка: {str(e)[:60]}\n")
    
    print("✅ Готово!")

if __name__ == "__main__":
    asyncio.run(fix_sessions())
