#!/usr/bin/env python3
"""
Авторизация с таймаутами и детальным логированием
Для отладки проблем с подключением
"""
import asyncio
from telethon import TelegramClient

# Данные аккаунтов
ACCOUNTS = {
    "1": {
        "phone": "+380935173511",
        "api_id": 37120288,
        "api_hash": "e576f165ace9ea847633a136dc521062",
        "session_name": "promotion_anna_truncher",
        "nickname": "Anna Truncher"
    },
    "2": {
        "phone": "+380931849825",
        "api_id": 34601626,
        "api_hash": "eba8c7b793884b92a65c48436b646600",
        "session_name": "promotion_artur_biggest",
        "nickname": "Artur Biggest"
    },
    "3": {
        "phone": "+380630429234",
        "api_id": 33336443,
        "api_hash": "9d9ee718ff58f43ccbcf028a629528fd",
        "session_name": "promotion_andrey_virgin",
        "nickname": "Andrey Virgin"
    }
}

async def authorize_account(account_data):
    """Авторизация с таймаутами"""
    phone = account_data["phone"]
    api_id = account_data["api_id"]
    api_hash = account_data["api_hash"]
    session_name = account_data["session_name"]
    
    print(f"\n{'='*80}")
    print(f"📱 Авторизация: {account_data['nickname']} ({phone})")
    print(f"{'='*80}")
    print(f"API ID: {api_id}")
    print(f"Session: {session_name}")
    print()
    
    import os
    os.makedirs("sessions", exist_ok=True)
    
    # Создаем клиент БЕЗ прокси
    client = TelegramClient(f"sessions/{session_name}", api_id, api_hash)
    
    try:
        print("🔐 Подключение к Telegram...")
        print("   Таймаут: 30 секунд")
        
        # Подключение с таймаутом
        try:
            await asyncio.wait_for(client.connect(), timeout=30.0)
            print("✅ Подключение установлено")
        except asyncio.TimeoutError:
            print("❌ Таймаут подключения!")
            print("   Telegram не отвечает в течение 30 секунд")
            print("   Возможные причины:")
            print("   1. Проблемы с сетью/интернетом")
            print("   2. Telegram временно недоступен")
            print("   3. API_ID/API_HASH неверные или заблокированы")
            print("   4. Нужно подождать и попробовать снова")
            try:
                await client.disconnect()
            except:
                pass
            return None
        except Exception as e:
            print(f"❌ Ошибка подключения: {e}")
            print(f"   Тип ошибки: {type(e).__name__}")
            try:
                await client.disconnect()
            except:
                pass
            return None
        
        print("\n🔍 Проверка авторизации...")
        try:
            is_authorized = await asyncio.wait_for(
                client.is_user_authorized(), 
                timeout=10.0
            )
        except asyncio.TimeoutError:
            print("⚠️ Таймаут проверки авторизации")
            is_authorized = False
        except Exception as e:
            print(f"⚠️ Ошибка проверки авторизации: {e}")
            is_authorized = False
        
        if is_authorized:
            print("✅ Уже авторизован!")
            try:
                me = await asyncio.wait_for(client.get_me(), timeout=10.0)
                username = getattr(me, 'username', 'No username')
                print(f"   Пользователь: @{username}")
            except Exception as e:
                print(f"⚠️ Ошибка получения информации: {e}")
        else:
            print("📲 Отправляем код...")
            print("   Таймаут: 60 секунд")
            
            try:
                result = await asyncio.wait_for(
                    client.send_code_request(phone),
                    timeout=60.0
                )
                
                print("="*80)
                print("✅ КОД ОТПРАВЛЕН!")
                print("="*80)
                print(f"Тип доставки: {result.type}")
                print(f"Next type: {getattr(result, 'next_type', 'N/A')}")
                print("="*80)
                print()
                
                # Проверяем, куда отправлен код
                result_type_str = str(result.type).lower()
                if 'telegram' in result_type_str or 'app' in result_type_str:
                    print("⚠️ Код отправлен в Telegram на устройство!")
                    print("   Проверьте Telegram на Windows/Android")
                elif 'sms' in result_type_str:
                    print("📱 Код отправлен по SMS")
                else:
                    print("📱 Проверьте Telegram/SMS")
                
                print("   Код должен прийти в течение минуты")
                print()
                
                # В интерактивном режиме запрашиваем код
                print("="*80)
                code = input("✉️ Введите код из SMS/Telegram: ").strip()
                
                if not code:
                    print("❌ Код не введен!")
                    await client.disconnect()
                    return None
                
                print("\n🔐 Подтверждаем код...")
                try:
                    await asyncio.wait_for(
                        client.sign_in(phone, code),
                        timeout=30.0
                    )
                    print("✅ Авторизация успешна!")
                except Exception as e:
                    error_str = str(e)
                    if "PASSWORD_HASH_INVALID" in error_str or "two-step" in error_str.lower():
                        print("🔐 Требуется пароль 2FA:")
                        password = input("🔐 Пароль 2FA: ").strip()
                        if password:
                            await client.sign_in(password=password)
                            print("✅ Авторизация с 2FA успешна!")
                        else:
                            print("❌ Пароль не введен!")
                            await client.disconnect()
                            return None
                    else:
                        print(f"❌ Ошибка: {e}")
                        await client.disconnect()
                        return None
                        
            except asyncio.TimeoutError:
                print("❌ Таймаут отправки кода!")
                print("   Telegram не отвечает в течение 60 секунд")
                await client.disconnect()
                return None
            except Exception as e:
                print(f"❌ Ошибка при отправке кода: {e}")
                await client.disconnect()
                return None
        
        # Получаем информацию о пользователе
        print("\n📋 Получаем информацию о пользователе...")
        me = await client.get_me()
        username = getattr(me, 'username', 'No username')
        first_name = getattr(me, 'first_name', 'No name')
        
        print(f"\n✅ Пользователь: {first_name} (@{username})")
        print(f"   ID: {me.id}")
        
        # Создаем string session
        print("\n💾 Создаем String Session...")
        session_string = client.session.save()
        
        print("\n" + "="*80)
        print("📋 String Session (скопируйте это):")
        print("="*80)
        print(session_string)
        print("="*80)
        
        # Сохраняем в файл
        filename = f'new_account_{session_name}_session.txt'
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"Phone: {phone}\n")
            f.write(f"API ID: {api_id}\n")
            f.write(f"API Hash: {api_hash}\n")
            f.write(f"Session Name: {session_name}\n")
            f.write(f"Username: @{username}\n")
            f.write(f"Full Name: {first_name} {me.last_name or ''}\n")
            f.write(f"User ID: {me.id}\n")
            f.write(f"\nString Session:\n{session_string}\n")
        
        print(f"\n✅ Сессия сохранена в файл: {filename}")
        
        await client.disconnect()
        return session_string
        
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        try:
            await client.disconnect()
        except:
            pass
        return None

def main():
    print("🚀 Авторизация с таймаутами и детальным логированием")
    print("="*80)
    print("\nВыберите аккаунт:")
    print()
    
    for key, account in ACCOUNTS.items():
        print(f"  {key}. {account['nickname']} ({account['phone']})")
    
    print()
    choice = input("Введите номер аккаунта (1-3): ").strip()
    
    if choice not in ACCOUNTS:
        print(f"❌ Неверный выбор: {choice}")
        return
    
    account = ACCOUNTS[choice]
    print(f"\n✅ Выбран: {account['nickname']} ({account['phone']})")
    
    # Запускаем асинхронную функцию
    session = asyncio.run(authorize_account(account))
    
    if session:
        print(f"\n{'='*80}")
        print(f"✅ УСПЕШНО! Сессия создана для {account['nickname']}!")
        print(f"{'='*80}")
    else:
        print(f"\n❌ Не удалось создать сессию для {account['nickname']}")

if __name__ == "__main__":
    main()

