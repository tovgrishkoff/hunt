#!/usr/bin/env python3
"""
Авторизация аккаунта Lisa Soak
На основе рабочего кода authorize_other_accounts.py
"""
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from urllib.parse import urlparse

# Данные аккаунта Lisa Soak
ACCOUNT = {
    "phone": "+380937392431",  # Исправлено: убрана лишняя 1 в конце
    "api_id": 36665934,
    "api_hash": "0ac3c86e68a3e4eac13bb7c2ab2dff3d",
    "session_name": "promotion_lisa_soak",
    "nickname": "Lisa Soak"
}

# Новый прокси для перелогина (HTTPS)
PROXY_URL = "https://FATKWa:bsJ7rQ@193.32.153.87:9526"

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

async def authorize_account(account_data, use_proxy=False):
    """Авторизация аккаунта"""
    phone = account_data["phone"]
    api_id = account_data["api_id"]
    api_hash = account_data["api_hash"]
    session_name = account_data["session_name"]
    nickname = account_data["nickname"]
    
    print(f"\n{'='*80}")
    print(f"📱 Авторизация: {nickname} ({phone})")
    print(f"{'='*80}")
    print(f"API ID: {api_id}")
    print(f"Session: {session_name}")
    print()
    
    # Парсим прокси если указан
    proxy = None
    if use_proxy:
        proxy = parse_proxy(PROXY_URL)
        if proxy:
            print(f"✅ Прокси включен: {PROXY_URL}")
        else:
            print("⚠️ Не удалось распарсить прокси, работаем без прокси")
            proxy = None
    else:
        print("⚠️ Работаем без прокси")
    
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
                
                # Проверяем, куда отправлен код
                result_type_str = str(result.type).lower()
                if 'telegram' in result_type_str or 'app' in result_type_str:
                    print("⚠️ ВАЖНО: Код отправлен в Telegram на уже авторизованное устройство!")
                    print("   📱 Проверьте Telegram на телефоне/компьютере с этим номером")
                    print("   Код должен прийти в уведомлениях Telegram (не SMS!)")
                elif 'sms' in result_type_str:
                    print("📱 Код отправлен по SMS")
                    print(f"   Проверьте SMS на номер {phone}")
                else:
                    print(f"📱 Проверьте Telegram/SMS на номер {phone}")
                
                print("   Код должен прийти в течение минуты")
            except Exception as e:
                print(f"❌ Ошибка при отправке кода: {e}")
                print("\nВозможные причины:")
                print("1. API_ID/API_HASH неверные")
                print("2. Номер телефона не зарегистрирован в Telegram")
                print("3. Слишком много попыток - нужно подождать")
                print("4. Проблемы с сетью")
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
                if "PASSWORD_HASH_INVALID" in error_str or "two-step" in error_str.lower() or "SessionPasswordNeeded" in error_str:
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
        last_name = getattr(me, 'last_name', '')
        
        print(f"\n✅ Пользователь: {first_name} {last_name} (@{username})")
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
            f.write(f"Full Name: {first_name} {last_name}\n")
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
    print("🚀 Авторизация аккаунта Lisa Soak")
    print("="*80)
    print(f"\n📱 Телефон: {ACCOUNT['phone']}")
    print(f"🔑 API ID: {ACCOUNT['api_id']}")
    print(f"📝 Session: {ACCOUNT['session_name']}")
    print("="*80)
    
    # Спрашиваем про прокси
    print("\n" + "="*80)
    use_proxy_input = input("Использовать прокси? (y/n, по умолчанию n): ").strip().lower()
    use_proxy = use_proxy_input == 'y'
    print("="*80 + "\n")
    
    # Запускаем асинхронную функцию
    session = asyncio.run(authorize_account(ACCOUNT, use_proxy=use_proxy))
    
    if session:
        print(f"\n{'='*80}")
        print(f"✅ УСПЕШНО! Сессия создана для {ACCOUNT['nickname']}!")
        print(f"{'='*80}")
        print(f"\n📋 Следующие шаги:")
        print(f"   1. Скопируйте String Session из файла: new_session_{ACCOUNT['session_name']}.txt")
        print(f"   2. Откройте accounts_config.json")
        print(f"   3. Добавьте новый аккаунт с этой String Session")
        print(f"   4. Добавьте в bali_accounts_config.json если нужно использовать для Бали")
    else:
        print(f"\n❌ Не удалось создать сессию для {ACCOUNT['nickname']}")

if __name__ == "__main__":
    main()
