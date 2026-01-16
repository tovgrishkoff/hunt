#!/usr/bin/env python3
"""
Тест отправки кода для rod shaihutdinov
ТОЧНАЯ копия рабочего authorize_account.py - БЕЗ прокси
"""
import asyncio
from telethon import TelegramClient

# Данные rod shaihutdinov (давно работает)
ACCOUNT = {
    "phone": "+447456798894",
    "api_id": 29459367,
    "api_hash": "f287e6c6d48079f088d1620e565e35ba",
    "session_name": "promotion_rod_shaihutdinov",
    "nickname": "Артем_Князев_2"
}

async def test_rod_exact():
    """Точная копия метода из authorize_account.py - БЕЗ прокси"""
    print("🔐 Тест отправки кода для rod shaihutdinov")
    print("Используется ТОЧНО тот же метод, что работал (БЕЗ прокси)")
    print()
    
    phone = ACCOUNT["phone"]
    api_id = ACCOUNT["api_id"]
    api_hash = ACCOUNT["api_hash"]
    session_name = "test_rod_shaihutdinov"
    
    print(f"📱 Тестируем: {ACCOUNT['nickname']} ({phone})")
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
        print("   (ТОЧНО как в authorize_account.py - строка 57, БЕЗ прокси)")
        print("   Подождите, это может занять до 2 минут...")
        print()
        
        # ТОЧНО как в рабочем скрипте - строка 57
        result = await client.send_code_request(phone)
        
        print("="*80)
        print("✅ КОД ОТПРАВЛЕН!")
        print("="*80)
        print(f"Тип доставки: {result.type}")
        print(f"Phone code hash: {result.phone_code_hash[:30]}...")
        print(f"Next type: {getattr(result, 'next_type', 'N/A')}")
        print(f"Timeout: {getattr(result, 'timeout', 'N/A')} секунд")
        print("="*80)
        print()
        print("📱 Проверьте Telegram/SMS на номер", phone)
        print("   Код должен прийти в течение минуты")
        print()
        print("💡 Если код ПРИШЕЛ:")
        print("   - Значит метод работает правильно")
        print("   - Проблема была в прокси или в конкретных аккаунтах")
        print()
        print("💡 Если код НЕ ПРИШЕЛ:")
        print("   - Возможно, Telegram временно блокирует запросы")
        print("   - Нужно подождать между попытками")
        print("   - Или проблема в сети")
        print()
        
        # Спрашиваем результат
        print("="*80)
        answer = input("✉️ Пришел ли код? (y/n): ").strip().lower()
        
        if answer == 'y':
            print("\n✅ Отлично! Метод работает!")
            print("   Значит проблема была в прокси или в конкретных аккаунтах")
            print("   Попробуйте новые аккаунты БЕЗ прокси через authorize_new_no_proxy.py")
        else:
            print("\n⚠️ Код не пришел")
            print("   Но метод точно такой же, как работал раньше")
            print("   Возможно:")
            print("   1. Telegram временно блокирует запросы")
            print("   2. Нужно подождать 10-15 минут между попытками")
            print("   3. Проблемы с сетью")
            print("   4. Слишком много попыток с одного IP")
        
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
    print("🧪 Тест отправки кода для rod shaihutdinov")
    print("="*80)
    print("Проверяем, работает ли отправка кода для давно работающего аккаунта")
    print("Используется ТОЧНО тот же метод, что работал (БЕЗ прокси)")
    print("="*80)
    
    asyncio.run(test_rod_exact())

