#!/usr/bin/env python3
"""
Ручная авторизация promotion_alex_ever
"""

import asyncio
import json
from telethon import TelegramClient

async def manual_auth():
    # Загружаем конфигурацию
    with open('accounts_config.json', 'r', encoding='utf-8') as f:
        accounts = json.load(f)
    
    # Находим аккаунт promotion_alex_ever
    account = None
    for acc in accounts:
        if acc['session_name'] == 'promotion_alex_ever':
            account = acc
            break
    
    if not account:
        print("❌ Аккаунт promotion_alex_ever не найден в конфиге")
        return
    
    session_name = account['session_name']
    phone = account['phone']
    api_id = int(account['api_id'])
    api_hash = account['api_hash']
    
    print("=" * 60)
    print("📱 РУЧНАЯ АВТОРИЗАЦИЯ promotion_alex_ever")
    print("=" * 60)
    print(f"Телефон: {phone}")
    print(f"API ID: {api_id}")
    print("=" * 60)
    print()
    
    # Удаляем старую сессию, если есть
    import os
    session_file = f"sessions/{session_name}.session"
    if os.path.exists(session_file):
        print(f"🗑️  Удаляем старую сессию...")
        try:
            os.remove(session_file)
            print("✅ Старая сессия удалена")
        except:
            print("⚠️ Не удалось удалить старую сессию")
        print()
    
    # Создаем новый клиент
    client = TelegramClient(f"sessions/{session_name}", api_id, api_hash)
    
    try:
        print("🔌 Подключение к Telegram...")
        await client.connect()
        print("✅ Подключено\n")
        
        # Проверяем, авторизован ли уже
        if await client.is_user_authorized():
            me = await client.get_me()
            print(f"✅ Уже авторизован как @{me.username}")
            await client.disconnect()
            return
        
        # Отправляем код
        print(f"📨 Отправляем код на {phone}...")
        await client.send_code_request(phone)
        print("✅ Код отправлен!")
        print()
        
        # Запрашиваем код
        print("=" * 60)
        code = input("📱 Введите код из SMS/Telegram: ").strip()
        print("=" * 60)
        print()
        
        try:
            # Пытаемся войти с кодом
            print("🔐 Авторизация...")
            await client.sign_in(phone, code)
            print("✅ Авторизация успешна!")
        except Exception as e:
            error_str = str(e).lower()
            if "password" in error_str or "two-step" in error_str or "2fa" in error_str:
                print("🔐 Требуется пароль 2FA")
                print()
                password = input("Введите пароль 2FA: ").strip()
                await client.sign_in(password=password)
                print("✅ Авторизация с 2FA успешна!")
            else:
                print(f"❌ Ошибка: {e}")
                await client.disconnect()
                return
        
        # Получаем информацию о пользователе
        me = await client.get_me()
        username = getattr(me, 'username', 'No username')
        first_name = getattr(me, 'first_name', 'No name')
        
        print()
        print("=" * 60)
        print(f"✅ АВТОРИЗАЦИЯ УСПЕШНА!")
        print(f"Пользователь: {first_name} (@{username})")
        print("=" * 60)
        print()
        
        # Сохраняем string_session в конфиг
        try:
            session_string = client.session.save()
            account['string_session'] = session_string
            account['nickname'] = first_name
            
            with open('accounts_config.json', 'w', encoding='utf-8') as f:
                json.dump(accounts, f, indent=2, ensure_ascii=False)
            
            print("✅ String session сохранен в конфиг")
            print("✅ Файловая сессия создана")
            print()
        except Exception as e:
            print(f"⚠️ Не удалось сохранить string_session: {e}")
        
        await client.disconnect()
        
        print("=" * 60)
        print("✅ ГОТОВО! Сессия создана и сохранена")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        try:
            await client.disconnect()
        except:
            pass

if __name__ == "__main__":
    print("\n🚀 Запуск ручной авторизации...\n")
    asyncio.run(manual_auth())
