#!/usr/bin/env python3
"""
Простая авторизация Anna Truncher - с использованием прокси
Использует точно такой же метод, как для Oleg Petrov, но с прокси
"""
import asyncio
from telethon import TelegramClient
from urllib.parse import urlparse

# Данные аккаунта Anna Truncher
ACCOUNT = {
    "phone": "+380935173511",
    "api_id": 37120288,
    "api_hash": "e576f165ace9ea847633a136dc521062",
    "session_name": "promotion_anna_truncher",
    "nickname": "Anna Truncher",
    "proxy": "http://pG0d5c:8LcpzP@45.89.72.202:9136"  # Прокси из конфига
}

def parse_proxy(proxy_config):
    """Парсинг прокси в формат для Telethon (словарь, как в promotion_system.py)"""
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

async def authorize_anna():
    """Простая авторизация - точно как для Oleg Petrov"""
    phone = ACCOUNT["phone"]
    api_id = ACCOUNT["api_id"]
    api_hash = ACCOUNT["api_hash"]
    session_name = ACCOUNT["session_name"]
    
    print(f"\n{'='*80}")
    print(f"📱 Авторизация: {ACCOUNT['nickname']} ({phone})")
    print(f"{'='*80}")
    print(f"API ID: {api_id}")
    print(f"Session: {session_name}")
    print()
    
    import os
    os.makedirs("sessions", exist_ok=True)
    
    # Парсим прокси если указан
    proxy = parse_proxy(ACCOUNT.get('proxy'))
    if proxy:
        print(f"🌐 Используется прокси: {proxy['addr']}:{proxy['port']} ({proxy['proxy_type']})")
        print("   Это поможет избежать лимитов Telegram при множественных запросах")
        print("   Каждый аккаунт будет использовать свой IP адрес")
    else:
        print("⚠️ Прокси не указан - возможны проблемы с лимитами Telegram")
    
    # Создаем клиент с прокси если указан
    client = TelegramClient(
        f"sessions/{session_name}", 
        api_id, 
        api_hash,
        proxy=proxy  # Передаем прокси в клиент
    )
    
    try:
        await client.connect()
        print("✅ Подключение установлено")
        
        if await client.is_user_authorized():
            print("✅ Уже авторизован!")
            me = await client.get_me()
            username = getattr(me, 'username', 'No username')
            print(f"   Пользователь: @{username}")
        else:
            print("📲 Отправляем код...")
            result = await client.send_code_request(phone)
            print(f"✅ Код отправлен! Тип доставки: {result.type}")
            print("   Проверьте Telegram/SMS - код должен прийти в течение минуты")
            
            print("\n" + "="*80)
            code = input("✉️ Введите код из SMS/Telegram: ").strip()
            
            if not code:
                print("❌ Код не введен!")
                await client.disconnect()
                return None
            
            try:
                await client.sign_in(phone, code)
                print("✅ Авторизация успешна!")
            except Exception as e:
                error_str = str(e)
                if "PASSWORD_HASH_INVALID" in error_str or "two-step" in error_str.lower():
                    print("🔐 Требуется пароль 2FA:")
                    password = input("🔐 Пароль 2FA: ").strip()
                    if password:
                        await client.sign_in(password=password)
                        print("✅ Авторизация с 2FA успешна!")
                    else:
                        print("❌ Пароль не введен!")
                        await client.disconnect()
                        return None
                else:
                    print(f"❌ Ошибка: {e}")
                    await client.disconnect()
                    return None
        
        # Получаем информацию о пользователе
        me = await client.get_me()
        username = getattr(me, 'username', 'No username')
        first_name = getattr(me, 'first_name', 'No name')
        
        print(f"\n✅ Пользователь: {first_name} (@{username})")
        print(f"   ID: {me.id}")
        
        # Создаем string session
        session_string = client.session.save()
        
        print("\n" + "="*80)
        print("📋 String Session (скопируйте это):")
        print("="*80)
        print(session_string)
        print("="*80)
        
        # Сохраняем в файл
        filename = f'new_account_{session_name}_session.txt'
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"Phone: {phone}\n")
            f.write(f"API ID: {api_id}\n")
            f.write(f"API Hash: {api_hash}\n")
            f.write(f"Session Name: {session_name}\n")
            f.write(f"Username: @{username}\n")
            f.write(f"Full Name: {first_name} {me.last_name or ''}\n")
            f.write(f"User ID: {me.id}\n")
            f.write(f"\nString Session:\n{session_string}\n")
        
        print(f"\n✅ Сессия сохранена в файл: {filename}")
        print(f"✅ Файловая сессия: sessions/{session_name}.session")
        
        await client.disconnect()
        return session_string
        
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        try:
            await client.disconnect()
        except:
            pass
        return None

if __name__ == "__main__":
    print("🚀 Простая авторизация Anna Truncher")
    print("="*80)
    print("Используется точно такой же метод, как для Oleg Petrov")
    print("="*80)
    
    session = asyncio.run(authorize_anna())
    
    if session:
        print(f"\n{'='*80}")
        print(f"✅ УСПЕШНО! Сессия создана для {ACCOUNT['nickname']}!")
        print(f"{'='*80}")
        print(f"\n📋 Следующие шаги:")
        print(f"   1. Скопируйте String Session из файла: new_account_{ACCOUNT['session_name']}_session.txt")
        print(f"   2. Откройте accounts_config.json")
        print(f"   3. Найдите аккаунт {ACCOUNT['session_name']}")
        print(f"   4. Замените 'TO_BE_CREATED' на скопированную String Session")
    else:
        print(f"\n❌ Не удалось создать сессию для {ACCOUNT['nickname']}")

