#!/usr/bin/env python3
import asyncio
import json
from telethon import TelegramClient

async def manual_reauthorize_dao_bro():
    """Ручная переавторизация promotion_dao_bro"""
    print("🔐 Ручная переавторизация promotion_dao_bro...")
    print("📱 Номер: +447822028178")
    print("🔑 API ID: 18837962")
    print("🔑 API Hash: 9be03fb41eea0e14119fe4f908d6e741")
    
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
        sent_code = await client.send_code_request(phone)
        print(f"✅ Код отправлен! Тип: {sent_code.type}")
        
        print("\n" + "="*50)
        print("📱 КОД ОТПРАВЛЕН НА НОМЕР +447822028178")
        print("="*50)
        print("\nТеперь нужно:")
        print("1. Проверить SMS на телефоне +447822028178")
        print("2. Запустить команду:")
        print(f"   python3 complete_dao_bro_auth.py [КОД_ИЗ_SMS]")
        print("\nИли если нужен пароль 2FA:")
        print(f"   python3 complete_dao_bro_auth.py [КОД_ИЗ_SMS] [ПАРОЛЬ_2FA]")
        print("="*50)
        
        await client.disconnect()
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(manual_reauthorize_dao_bro())
