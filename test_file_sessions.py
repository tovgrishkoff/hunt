#!/usr/bin/env python3
import asyncio
import json
import time
from telethon import TelegramClient

async def test_file_sessions_only():
    """Тестирует только файловые сессии"""
    print("🔍 Тестируем только файловые сессии...")
    
    # Загружаем конфигурацию
    with open('accounts_config.json', 'r', encoding='utf-8') as f:
        accounts = json.load(f)
    
    clients = {}
    
    for i, account in enumerate(accounts):
        try:
            print(f"\n📱 Тестируем файловую сессию {i+1}: {account['session_name']}")
            start_time = time.time()
            
            api_id = int(account['api_id'])
            
            # Используем только файловую сессию
            client = TelegramClient(
                f"sessions/{account['session_name']}", 
                api_id, 
                account['api_hash']
            )
            
            print("   Подключаемся...")
            await client.connect()
            
            print("   Проверяем авторизацию...")
            if await client.is_user_authorized():
                me = await client.get_me()
                username = getattr(me, 'username', 'No username')
                first_name = getattr(me, 'first_name', 'No name')
                
                elapsed = time.time() - start_time
                print(f"   ✅ Работает: {first_name} (@{username}) за {elapsed:.2f}с")
                
                # Создаем новый string session из файловой сессии
                new_string_session = client.session.save()
                print(f"   ✅ Создан новый string session длиной {len(new_string_session)}")
                
                clients[account['session_name']] = client
            else:
                print(f"   ❌ Файловая сессия не авторизована")
                await client.disconnect()
                
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n🎉 Рабочих файловых сессий: {len(clients)}")
    
    # Отключаем всех клиентов
    print("\n🔌 Отключаем всех клиентов...")
    for name, client in clients.items():
        try:
            await client.disconnect()
            print(f"   ✅ {name} отключен")
        except Exception as e:
            print(f"   ❌ Ошибка отключения {name}: {e}")

if __name__ == "__main__":
    asyncio.run(test_file_sessions_only())



