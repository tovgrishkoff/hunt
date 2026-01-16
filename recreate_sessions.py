#!/usr/bin/env python3
"""
Пересоздание проблемных сессий из string_session
"""

import asyncio
import json
import shutil
from pathlib import Path
from telethon import TelegramClient
from telethon.sessions import StringSession

async def recreate_sessions():
    with open('accounts_config.json', 'r') as f:
        accounts = json.load(f)
    
    print("🔄 Пересоздание проблемных сессий\n")
    
    for account in accounts:
        session_name = account['session_name']
        string_session = account.get('string_session', '')
        api_id = int(account['api_id'])
        api_hash = account['api_hash']
        
        if not string_session:
            print(f"⚠️ {session_name}: нет string_session, пропускаем\n")
            continue
        
        print(f"🔄 {session_name}...")
        
        # Проверяем текущий статус
        session_path = Path(f'sessions/{session_name}.session')
        try:
            client = TelegramClient(f'sessions/{session_name}', api_id, api_hash)
            await asyncio.wait_for(client.connect(), timeout=5.0)
            if await client.is_user_authorized():
                me = await client.get_me()
                print(f"   ✅ Уже работает (@{me.username})\n")
                await client.disconnect()
                continue
            await client.disconnect()
        except:
            pass
        
        # Удаляем старую сессию
        if session_path.exists():
            try:
                # Делаем резервную копию
                backup_path = session_path.with_suffix('.session.backup')
                if backup_path.exists():
                    backup_path.unlink()
                shutil.copy2(session_path, backup_path)
                session_path.unlink()
                print(f"   📦 Старая сессия сохранена в backup")
            except Exception as e:
                print(f"   ⚠️ Не удалось удалить старую сессию: {e}")
        
        # Создаем новую сессию из string_session
        try:
            print(f"   🔄 Создание новой сессии из string_session...")
            
            # Используем string_session для создания файловой сессии
            string_client = TelegramClient(StringSession(string_session), api_id, api_hash)
            await string_client.connect()
            
            if not await string_client.is_user_authorized():
                print(f"   ❌ String session не валиден\n")
                await string_client.disconnect()
                continue
            
            me = await string_client.get_me()
            username = getattr(me, 'username', 'No username')
            
            # Получаем auth_key
            auth_key = string_client.session.auth_key
            await string_client.disconnect()
            
            if not auth_key:
                print(f"   ❌ Не удалось получить auth_key\n")
                continue
            
            # Создаем новую файловую сессию
            file_client = TelegramClient(f'sessions/{session_name}', api_id, api_hash)
            await file_client.connect()
            
            # Устанавливаем auth_key
            file_client.session.auth_key = auth_key
            file_client.session.save()
            await file_client.disconnect()
            
            # Проверяем новую сессию
            check_client = TelegramClient(f'sessions/{session_name}', api_id, api_hash)
            await check_client.connect()
            
            if await check_client.is_user_authorized():
                me = await check_client.get_me()
                print(f"   ✅ Сессия пересоздана! (@{me.username})\n")
            else:
                print(f"   ⚠️ Сессия создана, но не авторизована\n")
            
            await check_client.disconnect()
            
        except Exception as e:
            print(f"   ❌ Ошибка: {str(e)[:60]}\n")
    
    print("✅ Готово!")

if __name__ == "__main__":
    asyncio.run(recreate_sessions())
