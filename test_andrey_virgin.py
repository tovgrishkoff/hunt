#!/usr/bin/env python3
"""
Тест отправки кода для Andrey Virgin
Проверяем, куда именно Telegram отправляет код
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

async def test_andrey():
    """Тест отправки кода для Andrey Virgin"""
    phone = ACCOUNT["phone"]
    api_id = ACCOUNT["api_id"]
    api_hash = ACCOUNT["api_hash"]
    session_name = "test_andrey_virgin"
    
    print(f"\n{'='*80}")
    print(f"🔍 Тест: Andrey Virgin ({phone})")
    print(f"{'='*80}")
    print(f"API ID: {api_id}")
    print(f"API Hash: {api_hash}")
    print()
    
    import os
    os.makedirs("sessions", exist_ok=True)
    
    # Создаем клиент БЕЗ прокси
    client = TelegramClient(f"sessions/{session_name}", api_id, api_hash)
    
    try:
        print("🔐 Подключение к Telegram...")
        print("   Таймаут: 30 секунд")
        
        try:
            await asyncio.wait_for(client.connect(), timeout=30.0)
            print("✅ Подключение установлено")
        except asyncio.TimeoutError:
            print("❌ Таймаут подключения!")
            print("   Telegram не отвечает в течение 30 секунд")
            try:
                await client.disconnect()
            except:
                pass
            return
        except Exception as e:
            print(f"❌ Ошибка подключения: {e}")
            try:
                await client.disconnect()
            except:
                pass
            return
        
        print("\n📲 Отправляем запрос на код...")
        print("   Таймаут: 60 секунд")
        print("   Подождите...")
        
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
            print(f"Next type: {getattr(result, 'next_type', 'N/A')}")
            print(f"Timeout: {getattr(result, 'timeout', 'N/A')} секунд")
            print("="*80)
            
            # Детальный анализ
            result_type_str = str(result.type).lower()
            print("\n🔍 АНАЛИЗ ТИПА ДОСТАВКИ:")
            print("="*80)
            
            if 'sms' in result_type_str:
                print("✅ Код отправлен по SMS")
                print("   Проверьте SMS на номер", phone)
                print("   Код должен прийти в течение 1-2 минут")
            elif 'telegram' in result_type_str or 'app' in result_type_str:
                print("⚠️ ВАЖНО: Код отправлен в Telegram на уже авторизованное устройство!")
                print("   Проверьте:")
                print("   1. Telegram на Android устройстве")
                print("   2. Веб-версию Telegram (web.telegram.org)")
                print("   3. Telegram Desktop (если установлен)")
                print("   Код должен прийти в уведомлениях или появиться запрос на подтверждение")
            elif 'call' in result_type_str:
                print("📞 Код будет отправлен голосовым звонком")
                print("   Ответьте на звонок и прослушайте код")
            elif 'whatsapp' in result_type_str:
                print("💬 Код отправлен через WhatsApp")
                print("   Проверьте WhatsApp на номер", phone)
            else:
                print(f"❓ Тип доставки: {result.type}")
                print("   Проверьте все возможные места получения кода")
            
            print("\n" + "="*80)
            print("💡 ЧТО ДЕЛАТЬ:")
            print("="*80)
            
            if 'telegram' in result_type_str or 'app' in result_type_str:
                print("1. Откройте Telegram на Android/веб/Desktop")
                print("2. Проверьте уведомления - код должен быть там")
                print("3. Или может появиться запрос: 'Новая авторизация с IP...'")
                print("4. Подтвердите авторизацию на устройстве")
                print("5. Затем введите код в скрипт (или попробуйте авторизоваться снова)")
            else:
                print("1. Проверьте указанный метод доставки")
                print("2. Подождите 2-3 минуты")
                print("3. Если код не приходит - попробуйте запросить снова")
            
            print("\n" + "="*80)
            answer = input("✉️ Пришел ли код? (y/n): ").strip().lower()
            
            if answer == 'y':
                print("\n✅ Отлично! Код пришел!")
                print("   Теперь можно авторизоваться через authorize_new_no_proxy.py")
            else:
                print("\n⚠️ Код не пришел")
                print("   Рекомендации:")
                print("   1. Проверьте все устройства с Telegram")
                print("   2. Выйдите из аккаунта на всех устройствах")
                print("   3. Попробуйте снова - тогда код придет по SMS")
            
            await client.disconnect()
            
            # Удаляем тестовую сессию
            try:
                session_file = f"sessions/{session_name}.session"
                if os.path.exists(session_file):
                    os.remove(session_file)
                    print(f"\n✅ Удалена тестовая сессия")
            except:
                pass
            
        except asyncio.TimeoutError:
            print("\n❌ Таймаут отправки кода!")
            print("   Telegram не отвечает в течение 60 секунд")
            await client.disconnect()
        except Exception as e:
            print(f"\n❌ Ошибка при отправке кода: {e}")
            print(f"   Тип ошибки: {type(e).__name__}")
            import traceback
            traceback.print_exc()
            await client.disconnect()
        
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        try:
            await client.disconnect()
        except:
            pass

if __name__ == "__main__":
    print("🧪 Тест отправки кода для Andrey Virgin")
    print("="*80)
    print("Проверяем, куда именно Telegram отправляет код")
    print("="*80)
    
    asyncio.run(test_andrey())

