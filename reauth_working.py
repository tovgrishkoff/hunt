#!/usr/bin/env python3
"""
Переавторизация аккаунтов на основе рабочего кода authorize_other_accounts.py
Для аккаунтов 4 и 5 (promotion_oleg_petrov и promotion_anna_truncher)
"""
import asyncio
import json
from telethon import TelegramClient
from telethon.sessions import StringSession
from urllib.parse import urlparse

# Загружаем аккаунты из конфига
def load_accounts():
    """Загрузка аккаунтов 4 и 5 из accounts_config.json"""
    try:
        with open('accounts_config.json', 'r', encoding='utf-8') as f:
            accounts = json.load(f)
        
        # Аккаунты 4 и 5 (индексы 3 и 4)
        account_4 = accounts[3]  # promotion_oleg_petrov
        account_5 = accounts[4]  # promotion_anna_truncher
        
        return {
            "4": account_4,
            "5": account_5
        }
    except Exception as e:
        print(f"❌ Ошибка загрузки конфига: {e}")
        return {}

def parse_proxy(proxy_config):
    """Парсинг прокси в формат для Telethon (из рабочего кода)"""
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

async def authorize_account(account_data):
    """Авторизация аккаунта (на основе рабочего кода)"""
    phone = account_data["phone"]
    api_id = account_data["api_id"]
    api_hash = account_data["api_hash"]
    session_name = account_data["session_name"]
    nickname = account_data.get("nickname", session_name)
    
    print(f"\n{'='*80}")
    print(f"📱 Авторизация: {nickname} ({phone})")
    print(f"{'='*80}")
    print(f"API ID: {api_id}")
    print(f"Session: {session_name}")
    print()
    
    # Парсим прокси если указан
    proxy = parse_proxy(account_data.get('proxy'))
    if proxy:
        print(f"🌐 Используется прокси: {proxy['addr']}:{proxy['port']} ({proxy['proxy_type']})")
        print("   Каждый аккаунт использует свой IP адрес")
    else:
        print("⚠️ Прокси не указан")
    
    # Создаем клиент с StringSession (не файловую сессию)
    client = TelegramClient(
        StringSession(), 
        api_id, 
        api_hash,
        proxy=proxy
    )
    
    try:
        print("🔐 Подключение к Telegram...")
        await client.connect()
        print("✅ Подключение установлено")
        
        if await client.is_user_authorized():
            print("✅ Уже авторизован!")
            me = await client.get_me()
            username = getattr(me, 'username', 'No username')
            print(f"   Пользователь: @{username}")
        else:
            print("📲 Отправляем код...")
            print("   Подождите, это может занять до 2 минут...")
            
            try:
                result = await client.send_code_request(phone)
                print(f"✅ Код отправлен! Тип доставки: {result.type}")
                print(f"   Phone code hash: {result.phone_code_hash[:20]}...")
                print("   Проверьте Telegram/SMS - код должен прийти в течение минуты")
            except Exception as e:
                print(f"❌ Ошибка при отправке кода: {e}")
                print("\nВозможные причины:")
                print("1. API_ID/API_HASH неверные")
                print("2. Номер телефона не зарегистрирован в Telegram")
                print("3. Слишком много попыток - нужно подождать")
                await client.disconnect()
                return None
            
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
        filename = f'new_session_{session_name}.txt'
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

def main():
    print("🚀 Переавторизация аккаунтов 4 и 5")
    print("="*80)
    print("\nВыберите аккаунт:")
    print()
    
    accounts = load_accounts()
    
    if not accounts:
        print("❌ Не удалось загрузить аккаунты!")
        return
    
    for key, account in accounts.items():
        nickname = account.get('nickname', account.get('session_name', 'Unknown'))
        phone = account.get('phone', 'N/A')
        proxy_info = account.get('proxy', '')
        proxy_display = proxy_info.split('@')[1] if '@' in proxy_info else 'N/A'
        print(f"  {key}. {nickname} ({phone})")
        print(f"     Прокси: {proxy_display}")
    
    print()
    choice = input("Введите номер аккаунта (4 или 5): ").strip()
    
    if choice not in accounts:
        print(f"❌ Неверный выбор: {choice}")
        return
    
    account = accounts[choice]
    nickname = account.get('nickname', account.get('session_name', 'Unknown'))
    phone = account.get('phone', 'N/A')
    print(f"\n✅ Выбран: {nickname} ({phone})")
    
    # Запускаем асинхронную функцию
    session = asyncio.run(authorize_account(account))
    
    if session:
        print(f"\n{'='*80}")
        print(f"✅ УСПЕШНО! Сессия создана для {nickname}!")
        print(f"{'='*80}")
        print(f"\n📋 Следующие шаги:")
        print(f"   1. Скопируйте String Session из файла: new_session_{account['session_name']}.txt")
        print(f"   2. Откройте accounts_config.json")
        print(f"   3. Найдите аккаунт {account['session_name']}")
        print(f"   4. Замените старую string_session на новую")
    else:
        print(f"\n❌ Не удалось создать сессию для {nickname}")

if __name__ == "__main__":
    main()
