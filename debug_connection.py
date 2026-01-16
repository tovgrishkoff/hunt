#!/usr/bin/env python3
import asyncio
import json
import time
from telethon import TelegramClient

async def debug_connection():
    """Отладка подключения к Telegram"""
    print("🔍 Отладка подключения к Telegram...")
    
    # Загружаем конфигурацию
    with open('accounts_config.json', 'r', encoding='utf-8') as f:
        accounts = json.load(f)
    
    if not accounts:
        print("❌ Нет аккаунтов в конфигурации")
        return
    
    account = accounts[0]
    print(f"📱 Тестируем аккаунт: {account['session_name']}")
    print(f"   API ID: {account['api_id']}")
    print(f"   Phone: {account['phone']}")
    
    # Создаем клиент
    client = TelegramClient(
        f"sessions/{account['session_name']}",
        account['api_id'],
        account['api_hash']
    )
    
    try:
        print("🔗 Начинаем подключение...")
        start_time = time.time()
        
        await client.connect()
        
        connect_time = time.time() - start_time
        print(f"✅ Подключение установлено за {connect_time:.2f} секунд")
        
        print("🔍 Проверяем авторизацию...")
        start_time = time.time()
        
        is_auth = await client.is_user_authorized()
        
        auth_time = time.time() - start_time
        print(f"✅ Проверка авторизации заняла {auth_time:.2f} секунд")
        
        if is_auth:
            print("✅ Пользователь авторизован!")
            
            print("👤 Получаем информацию о пользователе...")
            start_time = time.time()
            
            me = await client.get_me()
            
            user_time = time.time() - start_time
            print(f"✅ Получение данных пользователя заняло {user_time:.2f} секунд")
            
            username = getattr(me, 'username', 'No username')
            first_name = getattr(me, 'first_name', 'No name')
            print(f"   Пользователь: {first_name} (@{username})")
        else:
            print("❌ Пользователь НЕ авторизован")
        
        print("🔌 Отключаемся...")
        start_time = time.time()
        
        await client.disconnect()
        
        disconnect_time = time.time() - start_time
        print(f"✅ Отключение заняло {disconnect_time:.2f} секунд")
        
        print("🎉 Все операции выполнены успешно!")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_connection())



