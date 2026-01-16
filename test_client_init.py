#!/usr/bin/env python3
import asyncio
import json
import time
from telethon import TelegramClient
from telethon.sessions import StringSession

async def test_client_initialization():
    """Тестирует инициализацию клиентов как в системе"""
    print("🔍 Тестируем инициализацию клиентов...")
    
    # Загружаем конфигурацию
    with open('accounts_config.json', 'r', encoding='utf-8') as f:
        accounts = json.load(f)
    
    clients = {}
    
    for i, account in enumerate(accounts):
        try:
            print(f"\n📱 Инициализируем аккаунт {i+1}: {account['session_name']}")
            start_time = time.time()
            
            api_id = int(account['api_id'])
            
            string_session = account.get('string_session')
            if string_session:
                print("   Используем string session...")
                client = TelegramClient(
                    StringSession(string_session),
                    api_id,
                    account['api_hash']
                )
            else:
                print("   Используем файловую сессию...")
                client = TelegramClient(
                    f"sessions/{account['session_name']}", 
                    api_id, 
                    account['api_hash']
                )
            
            print("   Подключаемся...")
            await client.connect()
            
            print("   Проверяем авторизацию...")
            if await client.is_user_authorized():
                clients[account['session_name']] = client
                me = await client.get_me()
                username = getattr(me, 'username', 'No username')
                first_name = getattr(me, 'first_name', 'No name')
                
                elapsed = time.time() - start_time
                print(f"   ✅ Успешно инициализирован: {first_name} (@{username}) за {elapsed:.2f}с")
            else:
                print(f"   ❌ Не авторизован")
                await client.disconnect()
                
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n🎉 Инициализировано клиентов: {len(clients)}")
    
    # Отключаем всех клиентов
    print("\n🔌 Отключаем всех клиентов...")
    for name, client in clients.items():
        try:
            await client.disconnect()
            print(f"   ✅ {name} отключен")
        except Exception as e:
            print(f"   ❌ Ошибка отключения {name}: {e}")

if __name__ == "__main__":
    asyncio.run(test_client_initialization())



