#!/usr/bin/env python3
import asyncio
import json
import os
from telethon import TelegramClient
from telethon.sessions import StringSession

async def test_and_fix_session(account):
    """Тестирует сессию и пытается исправить если нужно"""
    session_name = account['session_name']
    phone = account['phone']
    api_id = account['api_id']
    api_hash = account['api_hash']
    
    print(f"\n📱 Тестируем {session_name} ({phone})")
    
    # Сначала пробуем string session
    if account.get('string_session'):
        try:
            client = TelegramClient(
                StringSession(account['string_session']),
                api_id,
                api_hash
            )
            await client.connect()
            
            if await client.is_user_authorized():
                me = await client.get_me()
                username = getattr(me, 'username', 'No username')
                print(f"   ✅ String session работает: @{username}")
                await client.disconnect()
                return account  # Сессия работает
            
            await client.disconnect()
            print("   ❌ String session не авторизован")
        except Exception as e:
            print(f"   ❌ String session ошибка: {e}")
    
    # Пробуем файловую сессию
    session_file = f"sessions/{session_name}.session"
    if os.path.exists(session_file):
        try:
            client = TelegramClient(session_file, api_id, api_hash)
            await client.connect()
            
            if await client.is_user_authorized():
                me = await client.get_me()
                username = getattr(me, 'username', 'No username')
                print(f"   ✅ Файловая сессия работает: @{username}")
                
                # Обновляем string session
                new_string_session = client.session.save()
                await client.disconnect()
                
                account['string_session'] = new_string_session
                return account
            
            await client.disconnect()
            print("   ❌ Файловая сессия не авторизована")
        except Exception as e:
            print(f"   ❌ Файловая сессия ошибка: {e}")
    
    # Если ничего не работает
    print(f"   ❌ Все сессии для {session_name} не работают")
    return None

async def main():
    """Основная функция"""
    print("🔍 Проверка и исправление сессий...")
    
    # Загружаем конфигурацию
    try:
        with open('accounts_config.json', 'r', encoding='utf-8') as f:
            accounts = json.load(f)
    except FileNotFoundError:
        print("❌ Файл accounts_config.json не найден")
        return
    
    working_accounts = []
    
    for account in accounts:
        fixed_account = await test_and_fix_session(account)
        if fixed_account:
            working_accounts.append(fixed_account)
    
    # Сохраняем только рабочие аккаунты
    if working_accounts:
        with open('accounts_config.json', 'w', encoding='utf-8') as f:
            json.dump(working_accounts, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Рабочие аккаунты: {len(working_accounts)}/{len(accounts)}")
        print("🎉 Конфигурация обновлена!")
        
        # Показываем какие аккаунты работают
        for account in working_accounts:
            print(f"   ✅ {account['session_name']} - {account['phone']}")
    else:
        print("\n❌ Ни один аккаунт не работает!")
        print("💡 Нужно создать новые сессии вручную")

if __name__ == "__main__":
    asyncio.run(main())



