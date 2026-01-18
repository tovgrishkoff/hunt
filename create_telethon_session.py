#!/usr/bin/env python3
"""
Скрипт для создания Telethon сессии
Запускать ВРУЧНУЮ на сервере (не в Docker!)
"""

from telethon import TelegramClient
import asyncio

# Прямые значения из config.py
API_ID = 14402545
API_HASH = '9b5c94fcbaafb98d0862714bbba83d10'
PHONE_NUMBER = '+380630632244'

async def create_session():
    print("🔐 Создание Telethon сессии...")
    print(f"📱 Телефон: {PHONE_NUMBER}")
    print()
    
    # Создаем клиент
    client = TelegramClient('monitor_session', API_ID, API_HASH)
    
    # Подключаемся и авторизуемся
    await client.start(phone=PHONE_NUMBER)
    
    # Проверяем авторизацию
    if await client.is_user_authorized():
        me = await client.get_me()
        print()
        print("✅ Авторизация успешна!")
        print(f"👤 Пользователь: {me.first_name} {me.last_name or ''}")
        print(f"📞 Телефон: {me.phone}")
        print()
        print("📁 Файл сессии создан: monitor_session.session")
        print()
        print("💡 Теперь можно запустить Docker контейнер:")
        print("   cd /home/tovgrishkoff/mvp2105")
        print("   docker-compose up -d user-monitor")
    else:
        print("❌ Ошибка авторизации")
    
    await client.disconnect()

if __name__ == "__main__":
    print("=" * 60)
    print("🤖 Создание Telethon сессии для мониторинга чатов")
    print("=" * 60)
    print()
    print("⚠️  ВАЖНО: Этот скрипт нужно запускать ВРУЧНУЮ!")
    print("⚠️  Потребуется ввести код из Telegram!")
    print()
    
    try:
        asyncio.run(create_session())
    except KeyboardInterrupt:
        print("\n❌ Отменено пользователем")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")

