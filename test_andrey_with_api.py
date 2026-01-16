#!/usr/bin/env python3
"""
Тест авторизации Andrey Virgin с проверкой API credentials
"""
import asyncio
from telethon import TelegramClient

# Данные Andrey Virgin
ACCOUNT = {
    "phone": "+380630429234",
    "api_id": 33336443,
    "api_hash": "9d9ee718ff58f43ccbcf028a629528fd",
    "session_name": "promotion_andrey_virgin",
    "nickname": "Andrey Virgin"
}

async def test_andrey_api():
    """Тест с проверкой API"""
    phone = ACCOUNT["phone"]
    api_id = ACCOUNT["api_id"]
    api_hash = ACCOUNT["api_hash"]
    session_name = "test_andrey_api"
    
    print(f"\n{'='*80}")
    print(f"🧪 Тест API для: Andrey Virgin ({phone})")
    print(f"{'='*80}")
    print(f"API ID: {api_id}")
    print(f"API Hash: {api_hash[:20]}...")
    print()
    
    import os
    os.makedirs("sessions", exist_ok=True)
    
    client = TelegramClient(f"sessions/{session_name}", api_id, api_hash)
    
    try:
        print("🔐 Подключение к Telegram...")
        try:
            await asyncio.wait_for(client.connect(), timeout=30.0)
            print("✅ Подключение установлено")
        except asyncio.TimeoutError:
            print("❌ Таймаут подключения - API может быть неверным")
            return
        except Exception as e:
            print(f"❌ Ошибка подключения: {e}")
            print("   Возможно, API_ID/API_HASH неверные")
            return
        
        print("\n📲 Отправляем запрос на код...")
        try:
            result = await asyncio.wait_for(
                client.send_code_request(phone),
                timeout=60.0
            )
            
            print("\n" + "="*80)
            print("✅ КОД ОТПРАВЛЕН!")
            print("="*80)
            print(f"Тип доставки: {result.type}")
            print(f"Phone code hash: {result.phone_code_hash[:30]}...")
            print("="*80)
            
            result_type_str = str(result.type).lower()
            
            if 'sms' in result_type_str:
                print("\n✅ Код отправлен по SMS")
                print("   Проверьте SMS на номер", phone)
            elif 'telegram' in result_type_str or 'app' in result_type_str:
                print("\n⚠️ Код отправлен в Telegram на устройство!")
                print("   Проверьте:")
                print("   1. Веб-версию Telegram (web.telegram.org)")
                print("   2. Telegram на Android")
                print("   3. Может появиться запрос на подтверждение")
            else:
                print(f"\n📱 Тип доставки: {result.type}")
                print("   Проверьте все возможные места получения кода")
            
            print("\n" + "="*80)
            answer = input("✉️ Пришел ли код? (y/n): ").strip().lower()
            
            if answer == 'y':
                print("\n✅ Отлично! API credentials работают!")
                print("   Теперь можно авторизоваться через authorize_new_no_proxy.py")
            else:
                print("\n⚠️ Код не пришел")
                print("   Но API credentials правильные (подключение успешно)")
                print("   Проблема в доставке кода, а не в API")
            
            await client.disconnect()
            
            # Удаляем тестовую сессию
            try:
                session_file = f"sessions/{session_name}.session"
                if os.path.exists(session_file):
                    os.remove(session_file)
            except:
                pass
            
        except asyncio.TimeoutError:
            print("❌ Таймаут отправки кода")
            await client.disconnect()
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            await client.disconnect()
        
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        try:
            await client.disconnect()
        except:
            pass

if __name__ == "__main__":
    print("🧪 Тест API credentials для Andrey Virgin")
    print("="*80)
    
    asyncio.run(test_andrey_api())

