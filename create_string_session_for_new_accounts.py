#!/usr/bin/env python3
"""
Скрипт для создания String Session для новых аккаунтов
"""

import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

# Новые аккаунты для создания сессий
NEW_ACCOUNTS = [
    {
        "phone": "+380935173511",
        "api_id": 37120288,
        "api_hash": "e576f165ace9ea847633a136dc521062",
        "session_name": "promotion_anna_truncher",
        "nickname": "Anna Truncher",
        "username": "trencher"
    },
    {
        "phone": "+380931849825",
        "api_id": 34601626,
        "api_hash": "eba8c7b793884b92a65c48436b646600",
        "session_name": "promotion_artur_biggest",
        "nickname": "Artur Biggest",
        "username": "biggestart"
    },
    {
        "phone": "+380630429234",
        "api_id": 33336443,
        "api_hash": "9d9ee718ff58f43ccbcf028a629528fd",
        "session_name": "promotion_andrey_virgin",
        "nickname": "Andrey Virgin",
        "username": "virginarte"
    }
]

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
            await client.send_code_request(phone)
            print("✅ Код отправлен! Проверьте Telegram/SMS")
            
            code = input("✉️ Введите код из Telegram/SMS: ").strip()
            
            try:
                await client.sign_in(phone, code)
                print("✅ Код подтвержден!")
            except Exception as e:
                # Может потребоваться пароль 2FA
                error_msg = str(e).lower()
                if "password" in error_msg or "2fa" in error_msg or "PASSWORD_HASH_INVALID" in str(e):
                    password = input("🔐 Введите пароль 2FA: ").strip()
                    await client.sign_in(password=password)
                    print("✅ Авторизация с 2FA успешна!")
                else:
                    raise
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

async def main():
    print("🚀 Создание String Sessions для новых аккаунтов")
    print("="*80)
    
    sessions = {}
    
    for account in NEW_ACCOUNTS:
        session = await create_string_session(account)
        if session:
            sessions[account["session_name"]] = session
        print()
    
    print("\n" + "="*80)
    print("📊 Итоги:")
    print("="*80)
    print(f"Успешно создано сессий: {len(sessions)}/{len(NEW_ACCOUNTS)}")
    
    if sessions:
        print("\n✅ Готовые сессии для добавления в accounts_config.json:")
        for session_name, session in sessions.items():
            print(f"\n{session_name}:")
            print(session[:50] + "...")

if __name__ == "__main__":
    asyncio.run(main())

