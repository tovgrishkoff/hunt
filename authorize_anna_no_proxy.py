#!/usr/bin/env python3
"""
Авторизация Anna Truncher БЕЗ прокси - для проверки
Возможно прокси блокирует запросы
"""
import asyncio
from telethon import TelegramClient

# Данные аккаунта Anna Truncher
ACCOUNT = {
    "phone": "+380935173511",
    "api_id": 37120288,
    "api_hash": "e576f165ace9ea847633a136dc521062",
    "session_name": "promotion_anna_truncher_no_proxy",
    "nickname": "Anna Truncher"
}

async def authorize_anna():
    """Авторизация БЕЗ прокси"""
    phone = ACCOUNT["phone"]
    api_id = ACCOUNT["api_id"]
    api_hash = ACCOUNT["api_hash"]
    session_name = ACCOUNT["session_name"]
    
    print(f"\n{'='*80}")
    print(f"📱 Авторизация: {ACCOUNT['nickname']} ({phone})")
    print(f"{'='*80}")
    print(f"API ID: {api_id}")
    print(f"Session: {session_name}")
    print("⚠️ БЕЗ ПРОКСИ - для проверки")
    print()
    
    import os
    os.makedirs("sessions", exist_ok=True)
    
    # Создаем клиент БЕЗ прокси
    client = TelegramClient(f"sessions/{session_name}", api_id, api_hash)
    
    try:
        print("🔐 Подключение к Telegram...")
        await client.connect()
        print("✅ Подключение установлено")
        
        if await client.is_user_authorized():
            print("✅ Уже авторизован!")
            me = await client.get_me()
            username = getattr(me, 'username', 'No username')
            print(f"   Пользователь: @{username}")
        else:
            print("📲 Отправляем код...")
            print("   Подождите, это может занять до 2 минут...")
            
            try:
                result = await client.send_code_request(phone)
                print(f"✅ Код отправлен! Тип доставки: {result.type}")
                print(f"   Phone code hash: {result.phone_code_hash[:20]}...")
                print("   Проверьте Telegram/SMS - код должен прийти в течение минуты")
                print("   Если код не пришел, возможно:")
                print("   - Номер не зарегистрирован в Telegram")
                print("   - Telegram блокирует запросы с этого API_ID")
                print("   - Проблемы с оператором связи")
            except Exception as e:
                print(f"❌ Ошибка при отправке кода: {e}")
                print("\nВозможные причины:")
                print("1. API_ID/API_HASH неверные или заблокированы")
                print("2. Номер телефона не зарегистрирован в Telegram")
                print("3. Слишком много попыток - нужно подождать")
                await client.disconnect()
                return None
            
            print("\n" + "="*80)
            code = input("✉️ Введите код из SMS/Telegram (или нажмите Enter для отмены): ").strip()
            
            if not code:
                print("❌ Код не введен - отмена")
                await client.disconnect()
                return None
            
            try:
                await client.sign_in(phone, code)
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

if __name__ == "__main__":
    print("🚀 Авторизация Anna Truncher БЕЗ прокси")
    print("="*80)
    print("Проверка: возможно прокси блокирует запросы")
    print("="*80)
    
    session = asyncio.run(authorize_anna())
    
    if session:
        print(f"\n{'='*80}")
        print(f"✅ УСПЕШНО! Сессия создана для {ACCOUNT['nickname']}!")
        print(f"{'='*80}")
    else:
        print(f"\n❌ Не удалось создать сессию для {ACCOUNT['nickname']}")
        print("\n💡 Рекомендации:")
        print("   1. Проверьте, что номер +380935173511 зарегистрирован в Telegram")
        print("   2. Проверьте API_ID/API_HASH на https://my.telegram.org/apps")
        print("   3. Подождите 10-15 минут и попробуйте снова")
        print("   4. Попробуйте авторизоваться через официальное приложение Telegram")

