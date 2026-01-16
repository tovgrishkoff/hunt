#!/usr/bin/env python3
"""
ТОЧНАЯ копия рабочего authorize_account.py для Oleg Petrov
БЕЗ прокси, точно как работало вчера
"""
import asyncio
import json
from telethon import TelegramClient

async def test_oleg_exact():
    """Точная копия метода из authorize_account.py"""
    print("🔐 Тест отправки кода для Oleg Petrov")
    print("Используется ТОЧНО тот же метод, что работал вчера")
    print()
    
    # Данные Oleg Petrov
    phone = "+380731005075"
    api_id = 38166279
    api_hash = "5326e0a7fb4803c973bc0b7025eb65af"
    session_name = "test_oleg_petrov_exact"
    
    print(f"📱 Тестируем: {session_name} ({phone})")
    print(f"API ID: {api_id}")
    print(f"API Hash: {api_hash}")
    print()
    
    import os
    os.makedirs("sessions", exist_ok=True)
    
    # Создаем клиент - ТОЧНО как в authorize_account.py (БЕЗ прокси!)
    client = TelegramClient(f"sessions/{session_name}", api_id, api_hash)
    
    try:
        await client.connect()
        print("✅ Подключение установлено")
        
        if await client.is_user_authorized():
            print("✅ Уже авторизован!")
            me = await client.get_me()
            username = getattr(me, 'username', 'No username')
            print(f"   Пользователь: @{username}")
            print("\n⚠️ Аккаунт уже авторизован в этой сессии")
            print("   Удаляю сессию и создаю новую для теста...")
            await client.disconnect()
            
            # Удаляем сессию
            try:
                session_file = f"sessions/{session_name}.session"
                if os.path.exists(session_file):
                    os.remove(session_file)
                    print(f"✅ Удалена сессия: {session_file}")
            except:
                pass
            
            # Создаем новый клиент
            client = TelegramClient(f"sessions/{session_name}", api_id, api_hash)
            await client.connect()
            print("✅ Новое подключение установлено")
        
        print("\n📲 Отправляем код...")
        print("   (ТОЧНО как в authorize_account.py - строка 57)")
        
        # ТОЧНО как в рабочем скрипте - строка 57
        result = await client.send_code_request(phone)
        
        print("="*80)
        print("✅ КОД ОТПРАВЛЕН!")
        print("="*80)
        print(f"Тип доставки: {result.type}")
        print(f"Phone code hash: {result.phone_code_hash[:30]}...")
        print("="*80)
        print()
        print("📱 Проверьте Telegram/SMS на номер", phone)
        print("   Код должен прийти в течение минуты")
        print()
        
        # Спрашиваем результат
        print("="*80)
        answer = input("✉️ Пришел ли код? (y/n): ").strip().lower()
        
        if answer == 'y':
            print("\n✅ Отлично! Метод работает!")
            print("   Значит проблема была в прокси или в чем-то другом")
            print("   Попробуйте новые аккаунты БЕЗ прокси")
        else:
            print("\n⚠️ Код не пришел")
            print("   Но метод точно такой же, как работал вчера")
            print("   Возможно:")
            print("   1. Telegram временно блокирует запросы")
            print("   2. Нужно подождать между попытками")
            print("   3. Проблемы с сетью")
        
        await client.disconnect()
        
        # Удаляем тестовую сессию
        try:
            session_file = f"sessions/{session_name}.session"
            if os.path.exists(session_file):
                os.remove(session_file)
                print(f"\n✅ Удалена тестовая сессия")
        except:
            pass
        
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        try:
            await client.disconnect()
        except:
            pass

if __name__ == "__main__":
    asyncio.run(test_oleg_exact())

