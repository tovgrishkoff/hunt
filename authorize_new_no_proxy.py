#!/usr/bin/env python3
"""
Авторизация новых аккаунтов БЕЗ прокси
Использует точно такой же метод, как authorize_account.py (который работал)
"""
import asyncio
import json
from telethon import TelegramClient

# Новые аккаунты БЕЗ прокси
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
    """Авторизация - ТОЧНО как в authorize_account.py (БЕЗ прокси)"""
    phone = account_data["phone"]
    api_id = account_data["api_id"]
    api_hash = account_data["api_hash"]
    session_name = account_data["session_name"]
    
    print(f"\n{'='*80}")
    print(f"📱 Авторизация: {account_data['nickname']} ({phone})")
    print(f"{'='*80}")
    print(f"API ID: {api_id}")
    print(f"Session: {session_name}")
    print("⚠️ БЕЗ ПРОКСИ - точно как работало для Oleg Petrov")
    print()
    
    import os
    os.makedirs("sessions", exist_ok=True)
    
    # Создаем клиент - ТОЧНО как в authorize_account.py (БЕЗ прокси!)
    client = TelegramClient(f"sessions/{session_name}", api_id, api_hash)
    
    try:
        print("🔐 Подключение к Telegram...")
        print("   (это может занять до 30 секунд)")
        
        # Добавляем таймаут для подключения
        try:
            await asyncio.wait_for(client.connect(), timeout=30.0)
            print("✅ Подключение установлено")
        except asyncio.TimeoutError:
            print("❌ Таймаут подключения (30 секунд)")
            print("   Возможные причины:")
            print("   1. Проблемы с сетью")
            print("   2. Telegram блокирует подключение")
            print("   3. Нужно подождать и попробовать снова")
            await client.disconnect()
            return None
        except Exception as e:
            print(f"❌ Ошибка подключения: {e}")
            await client.disconnect()
            return None
        
        if await client.is_user_authorized():
            print("✅ Уже авторизован!")
            me = await client.get_me()
            username = getattr(me, 'username', 'No username')
            print(f"   Пользователь: @{username}")
        else:
            print("📲 Отправляем код...")
            # ТОЧНО как в authorize_account.py - строка 57
            result = await client.send_code_request(phone)
            
            print("="*80)
            print("✅ Код отправлен!")
            print("="*80)
            print(f"Тип доставки: {result.type}")
            print(f"Next type: {getattr(result, 'next_type', 'N/A')}")
            print("="*80)
            print()
            
            # Проверяем, куда отправлен код
            result_type_str = str(result.type).lower()
            if 'telegram' in result_type_str or 'app' in result_type_str:
                print("⚠️ ВАЖНО: Код отправлен в Telegram на уже авторизованное устройство!")
                print("   Проверьте Telegram на Android устройстве")
                print("   Код должен прийти в уведомлениях Telegram")
                print("   Или может появиться запрос на подтверждение новой авторизации")
            elif 'sms' in result_type_str:
                print("📱 Код отправлен по SMS")
                print("   Проверьте SMS на номер", phone)
            else:
                print("📱 Проверьте Telegram/SMS на номер", phone)
            
            print("   Код должен прийти в течение минуты")
            print()
            print("💡 Если аккаунт уже залогинен на Android:")
            print("   - Код может прийти в Telegram на это устройство")
            print("   - Или может потребоваться подтверждение с устройства")
            print("   - Если код не приходит - выйдите из аккаунта на Android и попробуйте снова")
            print()
            
            # В интерактивном режиме запрашиваем код
            print("="*80)
            print("Введите код из SMS/Telegram:")
            code = input("Код: ").strip()
            
            if not code:
                print("❌ Код не введен!")
                await client.disconnect()
                return None
            
            try:
                await client.sign_in(phone, code)
                print("✅ Авторизация успешна!")
            except Exception as e:
                error_str = str(e)
                if "PASSWORD_HASH_INVALID" in error_str or "two-step" in error_str.lower():
                    print("🔐 Требуется пароль 2FA:")
                    password = input("Пароль 2FA: ").strip()
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
        
        # Получаем информацию о пользователе
        me = await client.get_me()
        username = getattr(me, 'username', 'No username')
        first_name = getattr(me, 'first_name', 'No name')
        
        print(f"\n✅ Пользователь: {first_name} (@{username})")
        print(f"   ID: {me.id}")
        
        # Создаем string session
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
        print(f"✅ Файловая сессия: sessions/{session_name}.session")
        
        await client.disconnect()
        return session_string
        
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        try:
            await client.disconnect()
        except:
            pass
        return None

def main():
    print("🚀 Авторизация новых аккаунтов БЕЗ прокси")
    print("="*80)
    print("Используется ТОЧНО тот же метод, что работал для Oleg Petrov")
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
        print(f"\n📋 Следующие шаги:")
        print(f"   1. Скопируйте String Session из файла: new_account_{account['session_name']}_session.txt")
        print(f"   2. Откройте accounts_config.json")
        print(f"   3. Найдите аккаунт {account['session_name']}")
        print(f"   4. Замените 'TO_BE_CREATED' на скопированную String Session")
    else:
        print(f"\n❌ Не удалось создать сессию для {account['nickname']}")

if __name__ == "__main__":
    main()

