#!/usr/bin/env python3
"""
Скрипт для авторизации Telethon с кодом
"""

from telethon import TelegramClient
import asyncio
import sys

# Прямые значения из config.py
API_ID = 14402545
API_HASH = '9b5c94fcbaafb98d0862714bbba83d10'
PHONE_NUMBER = '+380630632244'

async def auth_with_code(code):
    print("🔐 Авторизация Telethon...")
    print(f"📱 Телефон: {PHONE_NUMBER}")
    print(f"🔢 Код: {code}")
    print()
    
    # Создаем клиент
    client = TelegramClient('monitor_session', API_ID, API_HASH)
    
    await client.connect()
    
    # Если не авторизован, отправляем запрос кода
    if not await client.is_user_authorized():
        print("📨 Отправка запроса кода...")
        await client.send_code_request(PHONE_NUMBER)
        
        print("🔐 Ввод кода...")
        try:
            # Авторизуемся с кодом
            await client.sign_in(PHONE_NUMBER, code)
            print("✅ Код принят!")
        except Exception as e:
            if 'password' in str(e).lower():
                print("🔒 Требуется пароль 2FA")
                password = input("Введите пароль 2FA: ")
                await client.sign_in(password=password)
            else:
                print(f"❌ Ошибка при вводе кода: {e}")
                await client.disconnect()
                return False
    
    # Проверяем авторизацию
    if await client.is_user_authorized():
        me = await client.get_me()
        print()
        print("✅ Авторизация успешна!")
        print(f"👤 Пользователь: {me.first_name} {me.last_name or ''}")
        print(f"📞 Телефон: {me.phone}")
        print(f"🆔 ID: {me.id}")
        print()
        print("📁 Файл сессии сохранен: monitor_session.session")
        print()
        print("💡 Теперь можно запустить Docker контейнер:")
        print("   docker-compose up -d user-monitor")
        await client.disconnect()
        return True
    else:
        print("❌ Ошибка авторизации")
        await client.disconnect()
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("❌ Использование: python3 auth_telethon.py <код>")
        print("Пример: python3 auth_telethon.py 12345")
        sys.exit(1)
    
    code = sys.argv[1]
    
    print("=" * 60)
    print("🤖 Авторизация Telethon")
    print("=" * 60)
    print()
    
    try:
        success = asyncio.run(auth_with_code(code))
        if success:
            print("\n✅ Готово!")
        else:
            print("\n❌ Не удалось авторизоваться")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n❌ Отменено пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

