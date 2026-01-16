#!/usr/bin/env python3
import asyncio
import json
from telethon import TelegramClient

async def final_dao_bro_auth():
    """Финальная авторизация promotion_dao_bro"""
    print("🔐 Финальная авторизация promotion_dao_bro...")
    
    # Данные аккаунта
    phone = "+447822028178"
    api_id = 18837962
    api_hash = "9be03fb41eea0e14119fe4f908d6e741"
    code = "21932"  # Код из SMS
    
    # Создаем клиент
    client = TelegramClient("sessions/promotion_dao_bro", api_id, api_hash)
    
    try:
        await client.connect()
        print("✅ Подключение установлено")
        
        # Отправляем код и получаем phone_code_hash
        print("📲 Отправляем код...")
        sent_code = await client.send_code_request(phone)
        phone_code_hash = sent_code.phone_code_hash
        print(f"✅ Получен phone_code_hash: {phone_code_hash}")
        
        # Авторизуемся с кодом
        try:
            await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
            print("✅ Авторизация с кодом успешна!")
        except Exception as e:
            if "PASSWORD_HASH_INVALID" in str(e) or "two-step" in str(e).lower():
                print("🔐 Требуется пароль 2FA")
                password = "Nt5%cF7kM3$aX9pR"  # Пароль 2FA
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
        print(f"✅ String session создан (длина: {len(session_string)})")
        
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
        print("✅ Файловая сессия сохранена")
        
        await client.disconnect()
        print("🎉 Авторизация promotion_dao_bro завершена!")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(final_dao_bro_auth())
