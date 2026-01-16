#!/usr/bin/env python3
"""
Создание отдельных сессий для Stories Viewer
"""

import asyncio
import json
from telethon import TelegramClient
from telethon.sessions import StringSession

async def create_session(phone, api_id, api_hash, session_name):
    """Создать сессию для аккаунта"""
    print(f"\n{'='*60}")
    print(f"📱 Создание сессии для {phone}")
    print(f"Имя сессии: stories_{session_name}")
    print('='*60)
    
    client = TelegramClient(f"sessions/stories_{session_name}", api_id, api_hash)
    
    await client.connect()
    
    if not await client.is_user_authorized():
        print(f"\n🔐 Введите код для {phone}:")
        await client.send_code_request(phone)
        code = input('Код из SMS/Telegram: ')
        
        try:
            await client.sign_in(phone, code)
        except Exception as e:
            print(f"Ошибка: {e}")
            password = input('2FA пароль (если есть): ')
            if password:
                await client.sign_in(password=password)
    
    me = await client.get_me()
    print(f"✅ Успешно авторизован: @{me.username or phone}")
    print(f"   ID: {me.id}")
    print(f"   Имя: {me.first_name} {me.last_name or ''}")
    
    # Получаем StringSession для резервной копии
    string_session = client.session.save()
    print(f"\n💾 StringSession сохранена")
    
    await client.disconnect()
    
    return {
        'phone': phone,
        'session_name': f"stories_{session_name}",
        'string_session': string_session,
        'api_id': api_id,
        'api_hash': api_hash
    }


async def main():
    """Основная функция"""
    print("\n" + "="*60)
    print("🎯 СОЗДАНИЕ СЕССИЙ ДЛЯ STORIES VIEWER")
    print("="*60)
    
    # Загружаем текущую конфигурацию
    with open('accounts_config.json', 'r', encoding='utf-8') as f:
        accounts = json.load(f)
    
    print(f"\nНайдено {len(accounts)} аккаунтов")
    print("\nБудут созданы ОТДЕЛЬНЫЕ сессии с префиксом 'stories_'")
    print("Это не повлияет на текущие сессии для постинга!\n")
    
    input("Нажмите Enter для начала...")
    
    stories_config = []
    
    for account in accounts:
        try:
            session_data = await create_session(
                phone=account['phone'],
                api_id=account['api_id'],
                api_hash=account['api_hash'],
                session_name=account['session_name']
            )
            
            stories_config.append(session_data)
            
        except Exception as e:
            print(f"\n❌ Ошибка для {account['phone']}: {e}")
            import traceback
            traceback.print_exc()
    
    # Сохраняем конфигурацию для Stories
    if stories_config:
        with open('accounts_config_stories.json', 'w', encoding='utf-8') as f:
            json.dump(stories_config, f, indent=2, ensure_ascii=False)
        
        print("\n" + "="*60)
        print(f"✅ ГОТОВО! Создано {len(stories_config)} сессий")
        print(f"📁 Конфигурация сохранена: accounts_config_stories.json")
        print("="*60)
        
        print("\nСозданные файлы сессий:")
        for conf in stories_config:
            print(f"  ✓ sessions/{conf['session_name']}.session")
        
        print("\n🚀 Теперь можно запустить:")
        print("   python simple_stories_viewer.py")
    else:
        print("\n❌ Не удалось создать ни одной сессии")


if __name__ == '__main__':
    asyncio.run(main())

