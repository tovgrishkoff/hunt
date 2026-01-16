#!/usr/bin/env python3
"""
Скрипт для создания новых сессий для автоответчика
"""

import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
import json

async def create_session(phone, api_id, api_hash, session_name):
    """Создание новой сессии"""
    print(f"\n{'='*60}")
    print(f"🔐 Создание сессии для {session_name}")
    print(f"📱 Телефон: {phone}")
    print(f"{'='*60}\n")
    
    client = TelegramClient(f'sessions/{session_name}', api_id, api_hash)
    
    await client.start(phone=phone)
    
    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"✅ Авторизация успешна!")
        print(f"👤 Имя: {me.first_name} {me.last_name or ''}")
        print(f"🆔 ID: {me.id}")
        print(f"📝 Username: @{me.username if me.username else 'не установлен'}")
        print(f"📁 Сессия сохранена: sessions/{session_name}.session")
    else:
        print(f"❌ Ошибка авторизации")
    
    await client.disconnect()
    return True

async def main():
    print("\n" + "="*60)
    print("🤖 СОЗДАНИЕ СЕССИЙ ДЛЯ АВТООТВЕТЧИКА")
    print("="*60)
    
    # Загружаем конфигурацию
    try:
        with open('accounts_config_autoresponder.json', 'r') as f:
            accounts = json.load(f)
    except FileNotFoundError:
        print("❌ Файл accounts_config_autoresponder.json не найден!")
        return
    
    print(f"\n📋 Найдено аккаунтов: {len(accounts)}")
    print("\n⚠️  ВАЖНО:")
    print("   - Убедитесь, что у вас есть доступ к этим номерам телефонов")
    print("   - Вам нужно будет ввести код подтверждения из Telegram")
    print("   - Если включена 2FA, нужно будет ввести пароль")
    print("\n")
    
    input("Нажмите Enter для продолжения...")
    
    for idx, account in enumerate(accounts, 1):
        print(f"\n{'─'*60}")
        print(f"📱 Аккаунт {idx}/{len(accounts)}")
        print(f"{'─'*60}")
        
        try:
            await create_session(
                phone=account['phone'],
                api_id=account['api_id'],
                api_hash=account['api_hash'],
                session_name=account['session_name']
            )
        except Exception as e:
            print(f"❌ Ошибка при создании сессии: {e}")
            continue
    
    print("\n" + "="*60)
    print("✅ ПРОЦЕСС ЗАВЕРШЕН")
    print("="*60)
    print("\n📝 Следующие шаги:")
    print("   1. Проверьте, что все сессии созданы: ls -la sessions/")
    print("   2. Запустите автоответчик: docker-compose up -d autoresponder")
    print("   3. Проверьте логи: docker logs telegram-autoresponder -f")
    print("")

if __name__ == "__main__":
    asyncio.run(main())
















