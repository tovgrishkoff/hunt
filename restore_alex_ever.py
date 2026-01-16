#!/usr/bin/env python3
"""
Восстановление сессии promotion_alex_ever из string_session
"""

import asyncio
import json
from telethon import TelegramClient
from telethon.sessions import StringSession

async def restore():
    with open('accounts_config.json', 'r') as f:
        accounts = json.load(f)
    
    account = None
    for acc in accounts:
        if acc['session_name'] == 'promotion_alex_ever':
            account = acc
            break
    
    if not account:
        print("❌ Аккаунт не найден")
        return
    
    string_session = account.get('string_session', '')
    if not string_session:
        print("❌ Нет string_session")
        return
    
    print("🔄 Восстановление сессии promotion_alex_ever из string_session...\n")
    
    try:
        # Используем string_session
        string_client = TelegramClient(StringSession(string_session), account['api_id'], account['api_hash'])
        await string_client.connect()
        
        if not await string_client.is_user_authorized():
            print("❌ String session не валиден")
            await string_client.disconnect()
            return
        
        me = await string_client.get_me()
        username = getattr(me, 'username', 'No username')
        print(f"✅ String session валиден (@{username})")
        
        # Получаем auth_key
        auth_key = string_client.session.auth_key
        await string_client.disconnect()
        
        if not auth_key:
            print("❌ Не удалось получить auth_key")
            return
        
        # Создаем новую файловую сессию
        print("💾 Создание файловой сессии...")
        file_client = TelegramClient('sessions/promotion_alex_ever', account['api_id'], account['api_hash'])
        await file_client.connect()
        
        # Устанавливаем auth_key
        file_client.session.auth_key = auth_key
        file_client.session.save()
        await file_client.disconnect()
        
        # Проверяем
        print("🔍 Проверка новой сессии...")
        check_client = TelegramClient('sessions/promotion_alex_ever', account['api_id'], account['api_hash'])
        await check_client.connect()
        
        if await check_client.is_user_authorized():
            me = await check_client.get_me()
            print(f"✅ Сессия восстановлена! (@{me.username})")
        else:
            print("❌ Сессия не авторизована")
        
        await check_client.disconnect()
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(restore())
