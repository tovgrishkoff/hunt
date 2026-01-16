#!/usr/bin/env python3
"""
Авторизация с использованием конкретных DC серверов
Для аккаунта Anna Truncher
"""
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

# DC серверы для Anna Truncher
DC_SERVERS = [
    {
        "ip": "149.154.167.40",
        "port": 443,
        "public_key": """-----BEGIN RSA PUBLIC KEY-----
MIIBCgKCAQEAyMEdY1aR+sCR3ZSJrtztKTKqigvO/vBfqACJLZtS7QMgCGXJ6XIR
yy7mx66W0/sOFa7/1mAZtEoIokDP3ShoqF4fVNb6XeqgQfaUHd8wJpDWHcR2OFwv
plUUI1PLTktZ9uW2WE23b+ixNwJjJGwBDJPQEQFBE+vfmH0JP503wr5INS1poWg/
j25sIWeYPHYeOrFp/eXaqhISP6G+q2IeTaWTXpwZj4LzXq5YOpk4bYEQ6mvRq7D1
aHWfYmlEGepfaYR8Q0YqvvhYtMte3ITnuSJs171+GDqpdKcSwHnd6FudwGO4pcCO
j4WcDuXc2CTHgH8gFTNhp/Y8/SpDOhvn9QIDAQAB
-----END RSA PUBLIC KEY-----"""
    },
    {
        "ip": "149.154.167.50",
        "port": 443,
        "public_key": """-----BEGIN RSA PUBLIC KEY-----
MIIBCgKCAQEA6LszBcC1LGzyr992NzE0ieY+BSaOW622Aa9Bd4ZHLl+TuFQ4lo4g
5nKaMBwK/BIb9xUfg0Q29/2mgIR6Zr9krM7HjuIcCzFvDtr+L0GQjae9H0pRB2OO
62cECs5HKhT5DZ98K33vmWiLowc621dQuwKWSQKjWf50XYFw42h21P2KXUGyp2y/
+aEyZ+uVgLLQbRA1dEjSDZ2iGRy12Mk5gpYc397aYp438fsJoHIgJ2lgMv5h7WY9
t6N/byY9Nw9p21Og3AoXSL2q/2IJ1WRUhebgAdGVMlV1fkuOQoEzR7EdpqtQD9Cs
5+bfo3Nhmcyvk5ftB0WkJ9z6bNZ7yxrP8wIDAQAB
-----END RSA PUBLIC KEY-----"""
    }
]

# Данные аккаунта Anna Truncher
ACCOUNT = {
    "phone": "+380935173511",
    "api_id": 37120288,
    "api_hash": "e576f165ace9ea847633a136dc521062",
    "session_name": "promotion_anna_truncher",
    "nickname": "Anna Truncher"
}

async def authorize_with_custom_dc():
    """Авторизация с использованием кастомных DC серверов"""
    phone = ACCOUNT["phone"]
    api_id = ACCOUNT["api_id"]
    api_hash = ACCOUNT["api_hash"]
    session_name = ACCOUNT["session_name"]
    
    print(f"\n{'='*80}")
    print(f"📱 Авторизация: {ACCOUNT['nickname']} ({phone})")
    print(f"{'='*80}")
    print(f"API ID: {api_id}")
    print(f"Используются кастомные DC серверы")
    print()
    
    import os
    os.makedirs("sessions", exist_ok=True)
    
    # Создаем клиент с файловой сессией
    client = TelegramClient(f"sessions/{session_name}", api_id, api_hash)
    
    try:
        print("🔐 Подключение к Telegram...")
        print("   (Telethon автоматически определит нужный DC сервер)")
        
        # Подключаемся без явной настройки DC - пусть Telethon сам определит
        await client.connect()
        print("✅ Подключение установлено")
        
        if await client.is_user_authorized():
            print("✅ Уже авторизован!")
            me = await client.get_me()
            username = getattr(me, 'username', 'No username')
            print(f"   Пользователь: @{username}")
        else:
            print("📲 Отправляем код...")
            result = await client.send_code_request(phone)
            print(f"✅ Код отправлен! Тип доставки: {result.type}")
            print(f"   Phone code hash: {result.phone_code_hash[:20]}...")
            print("   Проверьте Telegram/SMS - код должен прийти в течение минуты")
            
            print("\n" + "="*80)
            code = input("✉️ Введите код из SMS/Telegram: ").strip()
            
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
        await client.disconnect()
        return None

if __name__ == "__main__":
    print("🚀 Авторизация Anna Truncher с кастомными DC серверами")
    print("="*80)
    
    session = asyncio.run(authorize_with_custom_dc())
    
    if session:
        print(f"\n{'='*80}")
        print(f"✅ УСПЕШНО! Сессия создана для {ACCOUNT['nickname']}!")
        print(f"{'='*80}")
        print(f"\n📋 Следующие шаги:")
        print(f"   1. Скопируйте String Session из файла: new_account_{ACCOUNT['session_name']}_session.txt")
        print(f"   2. Откройте accounts_config.json")
        print(f"   3. Найдите аккаунт {ACCOUNT['session_name']}")
        print(f"   4. Замените 'TO_BE_CREATED' на скопированную String Session")
    else:
        print(f"\n❌ Не удалось создать сессию для {ACCOUNT['nickname']}")

