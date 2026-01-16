#!/usr/bin/env python3
"""
Скрипт для создания String Session для нового аккаунта
"""
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

async def create_string_session():
    phone = "+380930734685"
    api_id = 25586686
    api_hash = "2b8c229a66202daa2d2b560f969f78a1"
    
    print(f"📱 Создание String Session для {phone}")
    print(f"API ID: {api_id}")
    
    client = TelegramClient(StringSession(), api_id, api_hash)
    
    await client.start(phone=phone)
    
    print("\n✅ Авторизация успешна!")
    
    # Получаем String Session
    string_session = client.session.save()
    
    print("\n" + "="*80)
    print("📋 String Session (скопируйте это):")
    print("="*80)
    print(string_session)
    print("="*80)
    
    # Получаем информацию о пользователе
    me = await client.get_me()
    print(f"\n👤 Аккаунт: @{me.username or 'no_username'}")
    print(f"   Имя: {me.first_name or ''} {me.last_name or ''}")
    print(f"   ID: {me.id}")
    
    # Сохраняем в файл
    with open('new_account_session.txt', 'w') as f:
        f.write(f"Phone: {phone}\n")
        f.write(f"API ID: {api_id}\n")
        f.write(f"API Hash: {api_hash}\n")
        f.write(f"Username: @{me.username or 'no_username'}\n")
        f.write(f"String Session:\n{string_session}\n")
    
    print("\n✅ Сессия сохранена в файл: new_account_session.txt")
    
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(create_string_session())

