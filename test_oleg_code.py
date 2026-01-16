#!/usr/bin/env python3
"""
Тест отправки кода для Oleg Petrov
Проверяем, приходит ли код для уже рабочего аккаунта
"""
import asyncio
from telethon import TelegramClient
from urllib.parse import urlparse

# Данные Oleg Petrov (уже работает)
ACCOUNT = {
    "phone": "+380731005075",
    "api_id": 38166279,
    "api_hash": "5326e0a7fb4803c973bc0b7025eb65af",
    "session_name": "promotion_oleg_petrov",
    "nickname": "Oleg Petrov",
    "username": "petrsoleg",
    "proxy": "http://pG0d5c:8LcpzP@45.89.75.94:9797"
}

def parse_proxy(proxy_config):
    """Парсинг прокси в формат для Telethon"""
    if not proxy_config:
        return None
    
    if isinstance(proxy_config, str):
        try:
            parsed = urlparse(proxy_config)
            proxy_type = parsed.scheme.lower()
            host = parsed.hostname
            port = parsed.port or (8080 if proxy_type in ['http', 'https'] else 1080)
            username = parsed.username
            password = parsed.password
            
            if not host or not port:
                return None
            
            if proxy_type in ['http', 'https']:
                proxy_dict = {
                    'proxy_type': 'http',
                    'addr': host,
                    'port': port
                }
                if username:
                    proxy_dict['username'] = username
                if password:
                    proxy_dict['password'] = password
                return proxy_dict
            elif proxy_type == 'socks5':
                proxy_dict = {
                    'proxy_type': 'socks5',
                    'addr': host,
                    'port': port
                }
                if username:
                    proxy_dict['username'] = username
                if password:
                    proxy_dict['password'] = password
                return proxy_dict
        except Exception as e:
            print(f"⚠️ Ошибка парсинга прокси: {e}")
            return None
    
    return None

async def test_send_code():
    """Тест отправки кода для Oleg Petrov"""
    phone = ACCOUNT["phone"]
    api_id = ACCOUNT["api_id"]
    api_hash = ACCOUNT["api_hash"]
    session_name = ACCOUNT["session_name"]
    
    print(f"\n{'='*80}")
    print(f"🧪 ТЕСТ: Отправка кода для {ACCOUNT['nickname']} ({phone})")
    print(f"{'='*80}")
    print(f"API ID: {api_id}")
    print(f"API Hash: {ACCOUNT['api_hash']}")
    print(f"Username: @{ACCOUNT['username']}")
    print()
    print("ℹ️  Этот аккаунт УЖЕ успешно залогинился ранее")
    print("   Проверяем, приходит ли код сейчас")
    print()
    
    import os
    os.makedirs("sessions", exist_ok=True)
    
    # Парсим прокси
    proxy = parse_proxy(ACCOUNT.get('proxy'))
    if proxy:
        print(f"🌐 Используется прокси: {proxy['addr']}:{proxy['port']} ({proxy['proxy_type']})")
    else:
        print("⚠️ Прокси не указан")
    
    # Создаем НОВУЮ сессию для теста (не используем существующую)
    test_session_name = f"test_{session_name}"
    client = TelegramClient(
        f"sessions/{test_session_name}", 
        api_id, 
        api_hash,
        proxy=proxy
    )
    
    try:
        print("\n🔐 Подключение к Telegram...")
        await client.connect()
        print("✅ Подключение установлено")
        
        print("\n📲 Отправляем код...")
        print("   Подождите, это может занять до 2 минут...")
        print()
        
        try:
            result = await client.send_code_request(phone)
            
            print("="*80)
            print("✅ КОД ОТПРАВЛЕН!")
            print("="*80)
            print(f"Тип доставки: {result.type}")
            print(f"Phone code hash: {result.phone_code_hash}")
            print(f"Next type: {getattr(result, 'next_type', 'N/A')}")
            print(f"Timeout: {getattr(result, 'timeout', 'N/A')} секунд")
            print("="*80)
            print()
            print("📱 Проверьте Telegram/SMS на номер", phone)
            print("   Код должен прийти в течение минуты")
            print()
            print("💡 Если код ПРИШЕЛ:")
            print("   - Значит метод работает правильно")
            print("   - Проблема была с конкретными аккаунтами (Anna, Artur, Andrey)")
            print()
            print("💡 Если код НЕ ПРИШЕЛ:")
            print("   - Возможно, Telegram блокирует частые запросы")
            print("   - Нужно подождать между попытками")
            print()
            
            # Спрашиваем, пришел ли код
            print("="*80)
            answer = input("✉️ Пришел ли код? (y/n): ").strip().lower()
            
            if answer == 'y':
                print("\n✅ Отлично! Метод работает!")
                print("   Проблема была с конкретными аккаунтами")
                print("   Попробуйте другие аккаунты позже или проверьте их номера")
            else:
                print("\n⚠️ Код не пришел")
                print("   Возможные причины:")
                print("   1. Telegram блокирует частые запросы")
                print("   2. Нужно подождать 10-15 минут между попытками")
                print("   3. Проблемы с сетью/прокси")
            
            # Не авторизуемся, просто тестируем отправку кода
            print("\n🧹 Закрываем тестовую сессию...")
            await client.disconnect()
            
            # Удаляем тестовую сессию
            try:
                import os
                session_file = f"sessions/{test_session_name}.session"
                if os.path.exists(session_file):
                    os.remove(session_file)
                    print(f"✅ Удалена тестовая сессия: {session_file}")
            except:
                pass
            
            return True
            
        except Exception as e:
            print(f"\n❌ Ошибка при отправке кода: {e}")
            print("\nВозможные причины:")
            print("1. API_ID/API_HASH неверные")
            print("2. Telegram блокирует запросы")
            print("3. Проблемы с прокси")
            await client.disconnect()
            return False
        
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        try:
            await client.disconnect()
        except:
            pass
        return False

if __name__ == "__main__":
    print("🧪 Тест отправки кода для Oleg Petrov")
    print("="*80)
    print("Проверяем, работает ли отправка кода для уже рабочего аккаунта")
    print("="*80)
    
    result = asyncio.run(test_send_code())
    
    if result:
        print("\n✅ Тест завершен")
    else:
        print("\n❌ Тест не удался")

