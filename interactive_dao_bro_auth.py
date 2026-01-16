#!/usr/bin/env python3
import asyncio
import json
import sys
from telethon import TelegramClient

async def interactive_dao_bro_auth():
    """Интерактивная авторизация promotion_dao_bro"""
    print("🔐 Интерактивная авторизация promotion_dao_bro...")
    print("📱 Номер: +447822028178")
    
    # Данные аккаунта
    phone = "+447822028178"
    api_id = 18837962
    api_hash = "9be03fb41eea0e14119fe4f908d6e741"
    
    # Удаляем старый файл сессии
    import os
    session_file = "sessions/promotion_dao_bro.session"
    if os.path.exists(session_file):
        os.remove(session_file)
        print("✅ Старый файл сессии удален")
    
    # Создаем клиент
    client = TelegramClient("sessions/promotion_dao_bro", api_id, api_hash)
    
    try:
        await client.connect()
        print("✅ Подключение установлено")
        
        # Отправляем код
        print("📲 Отправляем код на номер +447822028178...")
        sent_code = await client.send_code_request(phone)
        phone_code_hash = sent_code.phone_code_hash
        print(f"✅ Код отправлен! Ожидайте SMS...")
        
        # Запрашиваем код у пользователя
        print("\n" + "="*50)
        print("📱 ВВЕДИТЕ КОД ИЗ SMS")
        print("="*50)
        code = input("Код из SMS (5 цифр): ").strip()
        
        if not code or len(code) != 5 or not code.isdigit():
            print("❌ Неверный формат кода")
            return
        
        print(f"📝 Введен код: {code}")
        
        # Пробуем авторизоваться с кодом
        try:
            await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
            print("✅ Авторизация с кодом успешна!")
        except Exception as e:
            if "PASSWORD_HASH_INVALID" in str(e) or "two-step" in str(e).lower():
                print("🔐 Требуется пароль 2FA")
                print("\n" + "="*50)
                print("🔑 ВВЕДИТЕ ПАРОЛЬ 2FA")
                print("="*50)
                password = input("Пароль 2FA: ").strip()
                
                if not password:
                    print("❌ Пароль не может быть пустым")
                    return
                
                print(f"📝 Введен пароль: {password}")
                
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
        if session_string:
            print(f"✅ String session создан (длина: {len(session_string)})")
        else:
            print("✅ Файловая сессия сохранена (string session недоступен для файловых сессий)")
        
        # Обновляем конфигурацию
        with open('accounts_config.json', 'r', encoding='utf-8') as f:
            accounts = json.load(f)
        
        # Находим и обновляем аккаунт promotion_dao_bro
        for account in accounts:
            if account['session_name'] == 'promotion_dao_bro':
                if session_string:
                    account['string_session'] = session_string
                account['nickname'] = first_name
                break
        
        # Сохраняем обновленную конфигурацию
        with open('accounts_config.json', 'w', encoding='utf-8') as f:
            json.dump(accounts, f, indent=2, ensure_ascii=False)
        
        print("✅ Конфигурация обновлена!")
        print("✅ Файловая сессия сохранена")
        
        await client.disconnect()
        print("🎉 Авторизация promotion_dao_bro завершена!")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(interactive_dao_bro_auth())
