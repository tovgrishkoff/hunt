#!/usr/bin/env python3
"""
Ручное создание String Session для одного аккаунта
Использует файловую сессию (как в рабочем authorize_account.py), затем конвертирует в StringSession
"""
import asyncio
import json
import sys
from telethon import TelegramClient
from telethon.sessions import StringSession

# Данные аккаунтов
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

async def create_string_session_manual(account_data):
    """Создание String Session через файловую сессию (как в authorize_account.py)"""
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
    
    # Создаем директорию для сессий если её нет
    import os
    os.makedirs("sessions", exist_ok=True)
    
    try:
        # Используем файловую сессию (как в рабочем authorize_account.py)
        print("🔐 Подключение к Telegram...")
        client = TelegramClient(f"sessions/{session_name}", api_id, api_hash)
        
        await client.connect()
        print("✅ Подключение установлено")
        
        if await client.is_user_authorized():
            print("✅ Аккаунт уже авторизован!")
        else:
            print(f"📲 Отправляем код на {phone}...")
            await client.send_code_request(phone)
            print("✅ Код отправлен! Проверьте Telegram/SMS")
            
            # В интерактивном режиме запрашиваем код
            print("\n" + "="*80)
            code = input("✉️ Введите код из SMS/Telegram: ").strip()
            
            if not code:
                print("❌ Код не введен!")
                await client.disconnect()
                return None
            
            try:
                await client.sign_in(phone, code)
                print("✅ Код подтвержден!")
            except Exception as e:
                error_str = str(e)
                if "PASSWORD_HASH_INVALID" in error_str or "two-step" in error_str.lower() or "password" in error_str.lower():
                    print("🔐 Требуется пароль 2FA")
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
        
        # Получаем информацию о пользователе
        me = await client.get_me()
        username = getattr(me, 'username', 'No username')
        first_name = getattr(me, 'first_name', 'No name')
        
        print(f"\n✅ Пользователь: {first_name} (@{username})")
        print(f"   ID: {me.id}")
        
        # Конвертируем файловую сессию в StringSession
        print("\n💾 Конвертируем в StringSession...")
        string_session = client.session.save()
        
        print("\n" + "="*80)
        print("📋 String Session (скопируйте это):")
        print("="*80)
        print(string_session)
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
            f.write(f"\nString Session:\n{string_session}\n")
        
        print(f"\n✅ Сессия сохранена в файл: {filename}")
        print(f"✅ Файловая сессия: sessions/{session_name}.session")
        
        await client.disconnect()
        return string_session
        
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    print("🚀 Ручное создание String Session (по одному аккаунту)")
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
    print("   Используется метод файловой сессии (как в authorize_account.py)")
    
    # Запускаем асинхронную функцию
    session = asyncio.run(create_string_session_manual(account))
    
    if session:
        print(f"\n{'='*80}")
        print(f"✅ УСПЕШНО! Сессия создана для {account['nickname']}!")
        print(f"{'='*80}")
        print(f"\n📋 Следующие шаги:")
        print(f"   1. Скопируйте String Session из файла: new_account_{account['session_name']}_session.txt")
        print(f"   2. Откройте accounts_config.json")
        print(f"   3. Найдите аккаунт {account['session_name']}")
        print(f"   4. Замените 'TO_BE_CREATED' на скопированную String Session")
        print(f"\n💡 Файловая сессия сохранена: sessions/{account['session_name']}.session")
    else:
        print(f"\n❌ Не удалось создать сессию для {account['nickname']}")

if __name__ == "__main__":
    main()

