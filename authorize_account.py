#!/usr/bin/env python3
import asyncio
import json
import sys
from telethon import TelegramClient
from telethon.sessions import StringSession

async def authorize_account(session_name_to_auth=None):
    """Авторизация одного аккаунта"""
    print("🔐 Авторизация аккаунта")
    
    # Загружаем конфигурацию
    with open('accounts_config.json', 'r', encoding='utf-8') as f:
        accounts = json.load(f)
    
    if not accounts:
        print("❌ Нет аккаунтов в конфигурации")
        return
    
    # Находим нужный аккаунт
    account = None
    if session_name_to_auth:
        for acc in accounts:
            if acc['session_name'] == session_name_to_auth:
                account = acc
                break
        if not account:
            print(f"❌ Аккаунт {session_name_to_auth} не найден")
            print("Доступные аккаунты:")
            for acc in accounts:
                print(f"  - {acc['session_name']}")
            return
    else:
        # Берем первый аккаунт
        account = accounts[0]
    session_name = account['session_name']
    phone = account['phone']
    api_id = account['api_id']
    api_hash = account['api_hash']
    
    print(f"📱 Авторизуем: {session_name} ({phone})")
    
    # Создаем клиент
    client = TelegramClient(f"sessions/{session_name}", api_id, api_hash)
    
    try:
        await client.connect()
        print("✅ Подключение установлено")
        
        if await client.is_user_authorized():
            print("✅ Уже авторизован!")
            me = await client.get_me()
            username = getattr(me, 'username', 'No username')
            print(f"   Пользователь: @{username}")
        else:
            print("📲 Отправляем код...")
            await client.send_code_request(phone)
            
            # В интерактивном режиме запрашиваем код
            print("Введите код из SMS/Telegram:")
            code = input("Код: ")
            
            try:
                await client.sign_in(phone, code)
                print("✅ Авторизация успешна!")
            except Exception as e:
                if "PASSWORD_HASH_INVALID" in str(e) or "two-step" in str(e).lower():
                    print("🔐 Требуется пароль 2FA:")
                    password = input("Пароль 2FA: ")
                    await client.sign_in(password=password)
                    print("✅ Авторизация с 2FA успешна!")
                else:
                    raise e
        
        # Получаем информацию о пользователе
        me = await client.get_me()
        username = getattr(me, 'username', 'No username')
        first_name = getattr(me, 'first_name', 'No name')
        
        print(f"✅ Пользователь: {first_name} (@{username})")
        
        # Создаем string session
        session_string = client.session.save()
        
        # Обновляем конфигурацию
        account['string_session'] = session_string
        account['nickname'] = first_name
        
        # Сохраняем обновленную конфигурацию
        with open('accounts_config.json', 'w', encoding='utf-8') as f:
            json.dump(accounts, f, indent=2, ensure_ascii=False)
        
        print("✅ Конфигурация обновлена!")
        print(f"✅ String session сохранен")
        
        await client.disconnect()
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        await client.disconnect()

if __name__ == "__main__":
    session_name = None
    if len(sys.argv) > 1:
        session_name = sys.argv[1]
        print(f"🎯 Авторизуем конкретный аккаунт: {session_name}\n")
    else:
        print("💡 Подсказка: можно указать конкретный аккаунт")
        print("   Пример: python3 authorize_account.py promotion_alex_ever\n")
    
    asyncio.run(authorize_account(session_name))



