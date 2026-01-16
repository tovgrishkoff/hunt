#!/usr/bin/env python3
"""
Авторизация конкретного аккаунта по имени сессии
Использование: python3 authorize_specific.py promotion_alex_ever
"""

import asyncio
import json
import sys
from telethon import TelegramClient

async def authorize_specific(session_name_to_auth):
    """Авторизация конкретного аккаунта"""
    with open('accounts_config.json', 'r', encoding='utf-8') as f:
        accounts = json.load(f)
    
    # Находим нужный аккаунт
    account = None
    for acc in accounts:
        if acc['session_name'] == session_name_to_auth:
            account = acc
            break
    
    if not account:
        print(f"❌ Аккаунт {session_name_to_auth} не найден в конфиге")
        print(f"Доступные аккаунты:")
        for acc in accounts:
            print(f"  - {acc['session_name']}")
        return False
    
    session_name = account['session_name']
    phone = account['phone']
    api_id = int(account['api_id'])
    api_hash = account['api_hash']
    
    print(f"\n{'='*60}")
    print(f"📱 Авторизация: {session_name}")
    print(f"   Телефон: {phone}")
    print(f"{'='*60}\n")
    
    client = TelegramClient(f"sessions/{session_name}", api_id, api_hash)
    
    try:
        await client.connect()
        print("✅ Подключение установлено")
        
        if await client.is_user_authorized():
            me = await client.get_me()
            username = getattr(me, 'username', 'No username')
            print(f"✅ Уже авторизован как @{username}")
            await client.disconnect()
            return True
        
        print("📲 Отправляем код...")
        await client.send_code_request(phone)
        print(f"📨 Код отправлен на {phone}")
        
        code = input("\nВведите код из SMS/Telegram: ").strip()
        
        try:
            await client.sign_in(phone, code)
            print("✅ Авторизация успешна!")
        except Exception as e:
            error_str = str(e).lower()
            if "password" in error_str or "two-step" in error_str or "2fa" in error_str:
                print("🔐 Требуется пароль 2FA:")
                password = input("Пароль 2FA: ").strip()
                await client.sign_in(password=password)
                print("✅ Авторизация с 2FA успешна!")
            else:
                raise
        
        me = await client.get_me()
        username = getattr(me, 'username', 'No username')
        first_name = getattr(me, 'first_name', 'No name')
        print(f"✅ Авторизован как {first_name} (@{username})")
        
        # Обновляем string_session
        try:
            session_string = client.session.save()
            account['string_session'] = session_string
            account['nickname'] = first_name
            
            with open('accounts_config.json', 'w', encoding='utf-8') as f:
                json.dump(accounts, f, indent=2, ensure_ascii=False)
            print("✅ Конфигурация обновлена!")
        except:
            pass
        
        await client.disconnect()
        return True
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        try:
            await client.disconnect()
        except:
            pass
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python3 authorize_specific.py <session_name>")
        print("\nПримеры:")
        print("  python3 authorize_specific.py promotion_alex_ever")
        print("  python3 authorize_specific.py promotion_rod_shaihutdinov")
        sys.exit(1)
    
    session_name = sys.argv[1]
    asyncio.run(authorize_specific(session_name))
