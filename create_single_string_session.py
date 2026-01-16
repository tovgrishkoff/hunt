#!/usr/bin/env python3
"""
Скрипт для создания String Session для одного аккаунта
Использование: python3 create_single_string_session.py
"""

import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

# Список аккаунтов для выбора
ACCOUNTS = {
    "1": {
        "phone": "+380935173511",
        "api_id": 37120288,
        "api_hash": "e576f165ace9ea847633a136dc521062",
        "session_name": "promotion_anna_truncher",
        "nickname": "Anna Truncher",
        "username": "trencher"
    },
    "2": {
        "phone": "+380931849825",
        "api_id": 34601626,
        "api_hash": "eba8c7b793884b92a65c48436b646600",
        "session_name": "promotion_artur_biggest",
        "nickname": "Artur Biggest",
        "username": "biggestart"
    },
    "3": {
        "phone": "+380630429234",
        "api_id": 33336443,
        "api_hash": "9d9ee718ff58f43ccbcf028a629528fd",
        "session_name": "promotion_andrey_virgin",
        "nickname": "Andrey Virgin",
        "username": "virginarte"
    }
}

async def create_string_session(account_data):
    """Создание String Session для аккаунта"""
    phone = account_data["phone"]
    api_id = account_data["api_id"]
    api_hash = account_data["api_hash"]
    session_name = account_data["session_name"]
    
    print(f"\n{'='*80}")
    print(f"📱 Создание String Session для {account_data['nickname']} ({phone})")
    print(f"{'='*80}")
    print(f"API ID: {api_id}")
    print(f"Username: @{account_data['username']}")
    print()
    
    try:
        # Используем StringSession
        client = TelegramClient(StringSession(), api_id, api_hash)
        
        print("🔐 Подключение к Telegram...")
        await client.connect()
        
        # Проверяем, авторизован ли уже
        if not await client.is_user_authorized():
            print(f"📲 Отправляю код на {phone}...")
            try:
                sent_code = await client.send_code_request(phone)
                print("✅ Код отправлен! Проверьте Telegram/SMS")
                print(f"   Тип: {sent_code.type}")
            except Exception as e:
                print(f"❌ Ошибка при отправке кода: {e}")
                await client.disconnect()
                return None
            
            code = input("✉️ Введите код из Telegram/SMS: ").strip()
            
            if not code:
                print("❌ Код не введен!")
                await client.disconnect()
                return None
            
            try:
                await client.sign_in(phone, code)
                print("✅ Код подтвержден!")
            except Exception as e:
                # Может потребоваться пароль 2FA
                error_msg = str(e).lower()
                if "password" in error_msg or "2fa" in error_msg or "PASSWORD_HASH_INVALID" in str(e):
                    print(f"⚠️ Требуется пароль 2FA: {e}")
                    password = input("🔐 Введите пароль 2FA: ").strip()
                    if password:
                        await client.sign_in(password=password)
                        print("✅ Авторизация с 2FA успешна!")
                    else:
                        print("❌ Пароль не введен!")
                        await client.disconnect()
                        return None
                else:
                    print(f"❌ Ошибка при входе: {e}")
                    await client.disconnect()
                    return None
        else:
            print("✅ Аккаунт уже авторизован!")
        
        print("\n✅ Авторизация успешна!")
        
        # Получаем String Session
        string_session = client.session.save()
        
        # Получаем информацию о пользователе
        me = await client.get_me()
        
        print("\n" + "="*80)
        print("📋 String Session (скопируйте это):")
        print("="*80)
        print(string_session)
        print("="*80)
        
        print(f"\n👤 Информация об аккаунте:")
        print(f"   Username: @{me.username or 'no_username'}")
        print(f"   Имя: {me.first_name or ''} {me.last_name or ''}")
        print(f"   ID: {me.id}")
        
        # Сохраняем в файл
        filename = f'new_account_{session_name}_session.txt'
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"Phone: {phone}\n")
            f.write(f"API ID: {api_id}\n")
            f.write(f"API Hash: {api_hash}\n")
            f.write(f"Session Name: {session_name}\n")
            f.write(f"Username: @{me.username or 'no_username'}\n")
            f.write(f"Full Name: {me.first_name or ''} {me.last_name or ''}\n")
            f.write(f"User ID: {me.id}\n")
            f.write(f"\nString Session:\n{string_session}\n")
        
        print(f"\n✅ Сессия сохранена в файл: {filename}")
        
        await client.disconnect()
        return string_session
        
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    print("🚀 Создание String Session для одного аккаунта")
    print("="*80)
    print("\nВыберите аккаунт:")
    print()
    
    for key, account in ACCOUNTS.items():
        print(f"  {key}. {account['nickname']} ({account['phone']}) @{account['username']}")
    
    print()
    choice = input("Введите номер аккаунта (1-3): ").strip()
    
    if choice not in ACCOUNTS:
        print(f"❌ Неверный выбор: {choice}")
        return
    
    account = ACCOUNTS[choice]
    print(f"\n✅ Выбран: {account['nickname']} ({account['phone']})")
    
    # Запускаем асинхронную функцию
    session = asyncio.run(create_string_session(account))
    
    if session:
        print(f"\n✅ Успешно создана сессия для {account['nickname']}!")
        print(f"   Скопируйте String Session из файла: new_account_{account['session_name']}_session.txt")
    else:
        print(f"\n❌ Не удалось создать сессию для {account['nickname']}")

if __name__ == "__main__":
    main()

