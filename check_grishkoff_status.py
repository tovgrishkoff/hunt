#!/usr/bin/env python3
"""
Проверка статуса авторизации аккаунта @grishkoff (promotion_new_account)
"""

import asyncio
import json
from pathlib import Path
from telethon import TelegramClient
from telethon.sessions import StringSession


async def check_grishkoff_status():
    """Проверка статуса аккаунта @grishkoff"""
    print("\n" + "="*80)
    print("🔍 ПРОВЕРКА СТАТУСА АККАУНТА @grishkoff (promotion_new_account)")
    print("="*80 + "\n")
    
    config_file = "accounts_config_stories.json"
    session_name = "promotion_new_account"
    
    # Загружаем конфигурацию
    config_path = Path(config_file)
    if not config_path.exists():
        print(f"❌ Файл {config_file} не найден!")
        return
    
    with open(config_file, 'r', encoding='utf-8') as f:
        accounts = json.load(f)
    
    # Ищем аккаунт
    account = None
    for acc in accounts:
        if acc.get('session_name') == session_name:
            account = acc
            break
    
    if not account:
        print(f"❌ Аккаунт {session_name} не найден в конфигурации!")
        return
    
    phone = account.get('phone', 'N/A')
    api_id = account.get('api_id')
    api_hash = account.get('api_hash')
    string_session = account.get('string_session', '')
    nickname = account.get('nickname', 'N/A')
    
    print(f"📱 Телефон: {phone}")
    print(f"📋 Session name: {session_name}")
    print(f"🔑 API ID: {api_id}")
    print(f"👤 Nickname: {nickname}")
    
    if not string_session:
        print("\n❌ String Session отсутствует в конфигурации!")
        print("   Нужно авторизовать аккаунт.")
        return
    
    print(f"✅ String Session присутствует (длина: {len(string_session)} символов)")
    
    # Проверяем подключение
    print("\n🔌 Проверка подключения к Telegram...")
    
    try:
        client = TelegramClient(StringSession(string_session), api_id, api_hash)
        await client.connect()
        
        if await client.is_user_authorized():
            me = await client.get_me()
            username = getattr(me, 'username', 'No username')
            first_name = getattr(me, 'first_name', 'No name')
            last_name = getattr(me, 'last_name', '') or ''
            
            print("\n" + "="*80)
            print("✅ АККАУНТ АВТОРИЗОВАН И РАБОТАЕТ:")
            print("="*80)
            print(f"   👤 Username: @{username}")
            print(f"   📛 Имя: {first_name} {last_name}".strip())
            print(f"   🆔 ID: {me.id}")
            print(f"   📱 Телефон: {phone}")
            print("="*80)
            
            # Проверяем, совпадает ли username
            if username.lower() == 'grishkoff':
                print("\n✅ Username совпадает: @grishkoff")
            else:
                print(f"\n⚠️  Username в Telegram: @{username}")
                print("   (Ожидался @grishkoff)")
            
            await client.disconnect()
            print("\n✅ Проверка завершена успешно!\n")
            
        else:
            print("\n❌ Аккаунт НЕ авторизован!")
            print("   String Session недействителен или истек.")
            print("   Нужно переавторизовать аккаунт.")
            await client.disconnect()
            
    except Exception as e:
        print(f"\n❌ Ошибка при проверке: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(check_grishkoff_status())








