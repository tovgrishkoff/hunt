#!/usr/bin/env python3
"""
Простая переавторизация promotion_anna_truncher
Использует проверенный метод из authorize_new_account.py
"""
import asyncio
import json
from pathlib import Path
from telethon import TelegramClient
from telethon.sessions import StringSession
from urllib.parse import urlparse

# Данные аккаунта promotion_anna_truncher (из accounts_config.json)
ACCOUNT = {
    "phone": "+380935173511",
    "api_id": 37120288,
    "api_hash": "e576f165ace9ea847633a136dc521062",
    "session_name": "promotion_anna_truncher",
    "nickname": "Anna Truncher",
    "proxy": "http://Vu9TDx:0zumuH@178.171.42.229:9540"  # Новый прокси
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
        except Exception as e:
            print(f"⚠️ Ошибка парсинга прокси: {e}")
            return None
    
    return None

async def reauthorize_anna():
    """Переавторизация promotion_anna_truncher"""
    phone = ACCOUNT["phone"]
    api_id = ACCOUNT["api_id"]
    api_hash = ACCOUNT["api_hash"]
    session_name = ACCOUNT["session_name"]
    proxy_config = ACCOUNT["proxy"]
    
    print("\n" + "="*80)
    print("🔐 ПЕРЕАВТОРИЗАЦИЯ: promotion_anna_truncher")
    print("="*80)
    print(f"📱 Телефон: {phone}")
    print(f"🔑 API ID: {api_id}")
    print(f"🔗 Прокси: {proxy_config[:50]}...")
    print("="*80)
    print()
    
    # Парсим прокси
    proxy = parse_proxy(proxy_config)
    if proxy:
        print(f"🔗 Используем прокси: {proxy['addr']}:{proxy['port']}")
    else:
        print("⚠️ Прокси не используется")
    
    # Создаем клиент с новой StringSession
    string_session_obj = StringSession()
    client = TelegramClient(string_session_obj, api_id, api_hash, proxy=proxy)
    
    try:
        print("🔌 Подключение к Telegram...")
        print("   (это может занять до 30 секунд)")
        
        try:
            await asyncio.wait_for(client.connect(), timeout=30.0)
            print("✅ Подключение установлено")
        except asyncio.TimeoutError:
            print("❌ Таймаут подключения (30 секунд)")
            await client.disconnect()
            return None
        except Exception as e:
            print(f"❌ Ошибка подключения: {e}")
            await client.disconnect()
            return None
        
        # Запрашиваем код
        print(f"\n📲 Отправляю код на {phone}...")
        result = await client.send_code_request(phone)
        
        print("="*80)
        print("✅ Код отправлен!")
        print("="*80)
        print(f"Тип доставки: {result.type}")
        print("="*80)
        print()
        
        # Проверяем, куда отправлен код
        result_type_str = str(result.type).lower()
        if 'telegram' in result_type_str or 'app' in result_type_str:
            print("⚠️ ВАЖНО: Код отправлен в Telegram на уже авторизованное устройство!")
            print("   Проверьте Telegram на телефоне/компьютере с этим номером")
            print("   Код должен прийти в уведомлениях Telegram (не SMS!)")
        elif 'sms' in result_type_str:
            print("📱 Код отправлен по SMS")
            print(f"   Проверьте SMS на номер {phone}")
        else:
            print(f"📱 Проверьте Telegram/SMS на номер {phone}")
        
        print("   Код должен прийти в течение 1-2 минут")
        print()
        
        # Запрашиваем код
        code = input("✉️ Введите код из Telegram/SMS: ").strip()
        
        if not code:
            print("❌ Код не введен!")
            await client.disconnect()
            return None
        
        try:
            await client.sign_in(phone, code)
            print("✅ Код подтвержден!")
        except Exception as e:
            error_str = str(e)
            if "PASSWORD_HASH_INVALID" in error_str or "two-step" in error_str.lower() or "password" in error_str.lower():
                print("🔐 Требуется пароль 2FA:")
                password = input("🔐 Введите пароль 2FA: ").strip()
                if password:
                    await client.sign_in(password=password)
                    print("✅ Авторизация с 2FA успешна!")
                else:
                    print("❌ Пароль 2FA не введен!")
                    await client.disconnect()
                    return None
            else:
                raise
        
        # Получаем информацию о пользователе
        me = await client.get_me()
        username = getattr(me, 'username', 'No username')
        first_name = getattr(me, 'first_name', 'No name')
        
        print(f"✅ Авторизован как: {first_name} (@{username})")
        
        # Получаем string_session
        string_session = client.session.save()
        
        print(f"\n📝 String Session (длина: {len(string_session)} символов):")
        print("="*80)
        print(string_session)
        print("="*80)
        
        # Сохраняем в файл
        output_file = Path(f"new_session_{session_name}.txt")
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"Phone: {phone}\n")
            f.write(f"API ID: {api_id}\n")
            f.write(f"API Hash: {api_hash}\n")
            f.write(f"Session Name: {session_name}\n")
            f.write(f"Nickname: {first_name}\n")
            f.write(f"Username: @{username}\n")
            f.write(f"\nString Session:\n{string_session}\n")
        
        print(f"\n✅ Сессия сохранена в файл: {output_file}")
        
        # Обновляем accounts_config.json
        config_file = Path('accounts_config.json')
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                accounts = json.load(f)
            
            updated = False
            for account in accounts:
                if account['session_name'] == session_name:
                    account['string_session'] = string_session
                    updated = True
                    print(f"✅ Обновлен accounts_config.json для {session_name}")
                    break
            
            if updated:
                with open(config_file, 'w', encoding='utf-8') as f:
                    json.dump(accounts, f, ensure_ascii=False, indent=2)
                print("✅ accounts_config.json сохранен!")
            else:
                print(f"⚠️ Аккаунт {session_name} не найден в accounts_config.json")
        
        await client.disconnect()
        
        print("\n" + "="*80)
        print("✅ ПЕРЕАВТОРИЗАЦИЯ ЗАВЕРШЕНА!")
        print("="*80)
        print("\nТеперь можно перезапустить контейнеры:")
        print("  docker-compose restart account-manager marketer")
        print("="*80)
        
        return string_session
        
    except Exception as e:
        print(f"\n❌ Ошибка при переавторизации: {e}")
        import traceback
        traceback.print_exc()
        try:
            await client.disconnect()
        except:
            pass
        return None

if __name__ == "__main__":
    try:
        asyncio.run(reauthorize_anna())
    except KeyboardInterrupt:
        print("\n\n⚠️ Прервано пользователем")
    except Exception as e:
        print(f"\n\n❌ Критическая ошибка: {e}")
