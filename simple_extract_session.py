#!/usr/bin/env python3
"""
Простое извлечение string_session - создаем новый клиент с StringSession
и копируем данные авторизации
"""
import asyncio
import json
import os
from telethon import TelegramClient
from telethon.sessions import StringSession

async def extract_session():
    config_file = 'accounts_config_stories.json'
    session_file = 'sessions_stories/stories_promotion_new_account.session'
    
    with open(config_file, 'r', encoding='utf-8') as f:
        accounts = json.load(f)
    
    account = next((a for a in accounts if a['session_name'] == 'promotion_new_account'), None)
    if not account:
        print("❌ Аккаунт не найден")
        return
    
    api_id = int(account['api_id'])
    api_hash = account['api_hash']
    
    # Подключаемся через файловую сессию
    file_client = TelegramClient(session_file, api_id, api_hash)
    await file_client.connect()
    
    if not await file_client.is_user_authorized():
        print("❌ Сессия не авторизована")
        await file_client.disconnect()
        return
    
    me = await file_client.get_me()
    print(f"✅ Авторизован: {me.first_name} (@{getattr(me, 'username', 'No username')})")
    
    # Создаем клиент с StringSession
    string_session_obj = StringSession()
    string_client = TelegramClient(string_session_obj, api_id, api_hash)
    
    await string_client.connect()
    
    # Копируем auth_key из файловой сессии
    if hasattr(file_client.session, 'auth_key') and file_client.session.auth_key:
        string_session_obj.set_dc(
            file_client.session.dc_id,
            file_client.session.server_address,
            file_client.session.auth_key
        )
    
    # Авторизуем string_client используя существующую авторизацию
    # Просто делаем get_me чтобы активировать сессию
    await string_client.get_me()
    
    # Сохраняем string_session
    string_session = string_session_obj.save()
    
    print(f"📝 String session: {string_session[:50]}... (длина: {len(string_session)})")
    
    # Обновляем конфиг
    account['string_session'] = string_session
    account['nickname'] = me.first_name
    
    with open(config_file, 'w', encoding='utf-8') as f:
        json.dump(accounts, f, indent=2, ensure_ascii=False)
    
    print("✅ Конфигурация обновлена!")
    
    await file_client.disconnect()
    await string_client.disconnect()

if __name__ == "__main__":
    asyncio.run(extract_session())



