#!/usr/bin/env python3
"""
Проверка статуса всех аккаунтов в accounts_config_stories.json
"""

import asyncio
import json
from pathlib import Path
from telethon import TelegramClient
from telethon.sessions import StringSession


async def check_account_status(account):
    """Проверка статуса одного аккаунта"""
    session_name = account.get('session_name', 'N/A')
    phone = account.get('phone', 'N/A')
    api_id = account.get('api_id')
    api_hash = account.get('api_hash')
    string_session = account.get('string_session', '')
    nickname = account.get('nickname', 'N/A')
    
    print(f"\n{'='*80}")
    print(f"📱 {session_name}")
    print('='*80)
    print(f"   Телефон: {phone}")
    print(f"   API ID: {api_id}")
    print(f"   Nickname: {nickname}")
    
    if not string_session:
        print("   ❌ String Session отсутствует!")
        return False
    
    print(f"   ✅ String Session присутствует (длина: {len(string_session)} символов)")
    
    try:
        client = TelegramClient(StringSession(string_session), api_id, api_hash)
        await client.connect()
        
        if await client.is_user_authorized():
            me = await client.get_me()
            username = getattr(me, 'username', 'No username')
            first_name = getattr(me, 'first_name', 'No name')
            last_name = getattr(me, 'last_name', '') or ''
            
            print(f"   ✅ АВТОРИЗОВАН И РАБОТАЕТ")
            print(f"      👤 Username: @{username}")
            print(f"      📛 Имя: {first_name} {last_name}".strip())
            print(f"      🆔 ID: {me.id}")
            
            await client.disconnect()
            return True
        else:
            print("   ❌ НЕ авторизован (String Session недействителен)")
            await client.disconnect()
            return False
            
    except Exception as e:
        print(f"   ❌ Ошибка: {str(e)[:100]}")
        try:
            await client.disconnect()
        except:
            pass
        return False


async def check_all_accounts():
    """Проверка всех аккаунтов"""
    print("\n" + "="*80)
    print("🔍 ПРОВЕРКА СТАТУСА ВСЕХ АККАУНТОВ")
    print("="*80)
    
    config_file = "accounts_config_stories.json"
    
    # Загружаем конфигурацию
    config_path = Path(config_file)
    if not config_path.exists():
        print(f"❌ Файл {config_file} не найден!")
        return
    
    with open(config_file, 'r', encoding='utf-8') as f:
        accounts = json.load(f)
    
    print(f"\n📋 Найдено аккаунтов: {len(accounts)}\n")
    
    results = []
    for account in accounts:
        status = await check_account_status(account)
        results.append({
            'session_name': account.get('session_name'),
            'status': status
        })
        # Небольшая задержка между проверками
        await asyncio.sleep(1)
    
    # Итоговая статистика
    print("\n" + "="*80)
    print("📊 ИТОГОВАЯ СТАТИСТИКА")
    print("="*80)
    
    active_count = sum(1 for r in results if r['status'])
    inactive_count = len(results) - active_count
    
    print(f"\n✅ Активных аккаунтов: {active_count}/{len(results)}")
    print(f"❌ Неактивных аккаунтов: {inactive_count}/{len(results)}\n")
    
    print("Детали:")
    for result in results:
        status_icon = "✅" if result['status'] else "❌"
        print(f"   {status_icon} {result['session_name']}")
    
    print("\n" + "="*80 + "\n")


if __name__ == "__main__":
    asyncio.run(check_all_accounts())








