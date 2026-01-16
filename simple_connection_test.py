#!/usr/bin/env python3
import asyncio
import json
from telethon import TelegramClient

async def test_connection():
    """Простой тест подключения к Telegram"""
    print("🔍 Тестируем подключение к Telegram...")
    
    # Загружаем первый аккаунт для теста
    try:
        with open('accounts_config.json', 'r', encoding='utf-8') as f:
            accounts = json.load(f)
        
        if not accounts:
            print("❌ Нет аккаунтов в конфигурации")
            return
        
        account = accounts[0]
        print(f"📱 Тестируем аккаунт: {account['session_name']}")
        print(f"   API ID: {account['api_id']}")
        print(f"   Phone: {account['phone']}")
        
        # Создаем клиент с минимальными настройками
        client = TelegramClient(
            'test_connection',
            account['api_id'],
            account['api_hash']
        )
        
        print("🔗 Пытаемся подключиться...")
        await client.connect()
        print("✅ Подключение установлено!")
        
        print("🔍 Проверяем авторизацию...")
        is_auth = await client.is_user_authorized()
        
        if is_auth:
            print("✅ Пользователь авторизован!")
            me = await client.get_me()
            username = getattr(me, 'username', 'No username')
            print(f"   Пользователь: @{username}")
        else:
            print("❌ Пользователь НЕ авторизован")
        
        await client.disconnect()
        print("✅ Отключение завершено")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_connection())



