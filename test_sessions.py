#!/usr/bin/env python3
import asyncio
import json
from telethon import TelegramClient
from telethon.sessions import StringSession

async def test_sessions():
    """Тестирование сессий аккаунтов"""
    print("🔍 Тестирование сессий аккаунтов...")
    
    # Загружаем конфигурацию
    with open('accounts_config.json', 'r', encoding='utf-8') as f:
        accounts = json.load(f)
    
    for account in accounts:
        try:
            print(f"\n📱 Тестируем аккаунт: {account['session_name']}")
            print(f"   Телефон: {account['phone']}")
            
            api_id = int(account['api_id'])
            api_hash = account['api_hash']
            string_session = account.get('string_session')
            
            if string_session:
                print("   Используем string session...")
                client = TelegramClient(
                    StringSession(string_session),
                    api_id,
                    api_hash
                )
            else:
                print("   Используем файловую сессию...")
                client = TelegramClient(
                    f"sessions/{account['session_name']}", 
                    api_id, 
                    api_hash
                )
            
            await client.connect()
            print("   ✅ Подключение установлено")
            
            if await client.is_user_authorized():
                me = await client.get_me()
                username = getattr(me, 'username', 'No username')
                first_name = getattr(me, 'first_name', 'No name')
                print(f"   ✅ Авторизован: {first_name} (@{username})")
            else:
                print("   ❌ НЕ авторизован!")
                
            await client.disconnect()
            print("   ✅ Отключение завершено")
            
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
    
    print("\n🏁 Тестирование завершено")

if __name__ == "__main__":
    asyncio.run(test_sessions())



