#!/usr/bin/env python3
"""
Скрипт для проверки статуса авторизации аккаунтов
"""

import asyncio
import json
import os
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError

async def check_account_auth(account_name, api_id, api_hash, phone):
    """Проверяет авторизацию одного аккаунта"""
    session_file = f"sessions/{account_name}.session"
    
    if not os.path.exists(session_file):
        return f"❌ {account_name}: Файл сессии не найден"
    
    try:
        client = TelegramClient(session_file, api_id, api_hash)
        await client.connect()
        
        if await client.is_user_authorized():
            me = await client.get_me()
            username = getattr(me, 'username', 'No username')
            first_name = getattr(me, 'first_name', 'No name')
            return f"✅ {account_name}: Авторизован как {first_name} (@{username})"
        else:
            return f"❌ {account_name}: Не авторизован"
            
    except Exception as e:
        return f"❌ {account_name}: Ошибка - {str(e)}"
    finally:
        if 'client' in locals():
            await client.disconnect()

async def main():
    """Основная функция"""
    print("🔍 Проверка авторизации аккаунтов")
    print("=" * 40)
    
    # Загружаем конфигурацию
    try:
        with open('accounts_config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
    except FileNotFoundError:
        print("❌ Файл accounts_config.json не найден!")
        return
    except json.JSONDecodeError:
        print("❌ Ошибка в формате accounts_config.json!")
        return
    
    # Проверяем каждый аккаунт
    for account in config:
        account_name = account.get('session_name', 'unknown')
        api_id = account.get('api_id')
        api_hash = account.get('api_hash')
        phone = account.get('phone')
        
        if not all([api_id, api_hash, phone]):
            print(f"❌ {account_name}: Неполная конфигурация")
            continue
            
        result = await check_account_auth(account_name, api_id, api_hash, phone)
        print(result)
    
    print("\n" + "=" * 40)
    print("✅ Проверка завершена!")

if __name__ == "__main__":
    asyncio.run(main())
