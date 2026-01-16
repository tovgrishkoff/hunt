#!/usr/bin/env python3
import asyncio
import json
from telethon import TelegramClient

async def reauthorize_dao_bro():
    """Переавторизация promotion_dao_bro через SMS"""
    print("🔐 Переавторизация promotion_dao_bro...")
    
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
    
    # Создаем новый клиент
    client = TelegramClient("sessions/promotion_dao_bro", api_id, api_hash)
    
    try:
        await client.connect()
        print("✅ Подключение установлено")
        
        # Отправляем код
        print("📲 Отправляем код на номер +447822028178...")
        await client.send_code_request(phone)
        
        # Запрашиваем код у пользователя
        print("\nВведите код из SMS:")
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
        with open('accounts_config.json', 'r', encoding='utf-8') as f:
            accounts = json.load(f)
        
        # Находим и обновляем аккаунт promotion_dao_bro
        for account in accounts:
            if account['session_name'] == 'promotion_dao_bro':
                account['string_session'] = session_string
                account['nickname'] = first_name
                break
        
        # Сохраняем обновленную конфигурацию
        with open('accounts_config.json', 'w', encoding='utf-8') as f:
            json.dump(accounts, f, indent=2, ensure_ascii=False)
        
        print("✅ Конфигурация обновлена!")
        print("✅ String session сохранен")
        
        await client.disconnect()
        print("🎉 Переавторизация завершена!")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(reauthorize_dao_bro())



