#!/usr/bin/env python3
"""
Скрипт для переавторизации новых аккаунтов и получения новых string_session
"""
import asyncio
import json
from pathlib import Path
from telethon import TelegramClient
from telethon.sessions import StringSession

# Аккаунты для переавторизации (только проблемные - с заблокированными сессиями)
ACCOUNTS_TO_REAUTHORIZE = [
    {
        "phone": "+380731005075",
        "api_id": 38166279,
        "api_hash": "5326e0a7fb4803c973bc0b7025eb65af",
        "session_name": "promotion_oleg_petrov",
        "nickname": "Oleg Petrov",
        "proxy": "http://nqzMyT:A2FFuy@181.177.86.184:9185"  # Новый прокси
    },
    {
        "phone": "+380935173511",
        "api_id": 37120288,
        "api_hash": "e576f165ace9ea847633a136dc521062",
        "session_name": "promotion_anna_truncher",
        "nickname": "Anna Truncher",
        "proxy": "http://Vu9TDx:0zumuH@178.171.42.229:9540"  # Новый прокси
    }
]

def parse_proxy(proxy_config):
    """Парсинг прокси в формат для Telethon"""
    if not proxy_config:
        return None
    
    if isinstance(proxy_config, str):
        try:
            from urllib.parse import urlparse
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

async def reauthorize_account(account_data):
    """Переавторизация одного аккаунта"""
    print("\n" + "="*80)
    print(f"🔐 ПЕРЕАВТОРИЗАЦИЯ: {account_data['nickname']}")
    print(f"📱 Телефон: {account_data['phone']}")
    print("="*80)
    
    api_id = int(account_data['api_id'])
    api_hash = account_data['api_hash']
    phone = account_data['phone']
    proxy_config = account_data.get('proxy')
    
    # Парсим прокси
    proxy = None
    if proxy_config:
        proxy = parse_proxy(proxy_config)
        if proxy:
            print(f"🔗 Используем прокси: {proxy['addr']}:{proxy['port']}")
    
    # Создаем клиент с новой StringSession
    string_session_obj = StringSession()
    client = TelegramClient(string_session_obj, api_id, api_hash, proxy=proxy)
    
    try:
        await client.connect()
        print("✅ Подключение установлено")
        
        # Проверяем, авторизован ли уже
        if await client.is_user_authorized():
            print("⚠️ Аккаунт уже авторизован. Создаем новую сессию...")
            # Отключаемся и создаем новый клиент
            await client.disconnect()
            string_session_obj = StringSession()
            client = TelegramClient(string_session_obj, api_id, api_hash, proxy=proxy)
            await client.connect()
        
        # Запрашиваем код
        print(f"\n📨 Отправка кода на {phone}...")
        result = await client.send_code_request(phone)
        
        # Показываем, куда отправлен код
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
        
        # Запрашиваем код у пользователя
        code = input("✉️ Введите код из Telegram/SMS: ").strip()
        
        if not code:
            print("❌ Код не введен!")
            await client.disconnect()
            return None
        
        # Авторизуемся
        try:
            await client.sign_in(phone, code)
        except Exception as e:
            # Если требуется пароль 2FA
            if "password" in str(e).lower() or "two" in str(e).lower():
                password = input("🔒 Введите пароль 2FA: ").strip()
                await client.sign_in(password=password)
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
        output_file = Path(f"new_session_{account_data['session_name']}.txt")
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"Phone: {phone}\n")
            f.write(f"API ID: {api_id}\n")
            f.write(f"API Hash: {api_hash}\n")
            f.write(f"Session Name: {account_data['session_name']}\n")
            f.write(f"Nickname: {account_data['nickname']}\n")
            f.write(f"Username: @{username}\n")
            f.write(f"\nString Session:\n{string_session}\n")
        
        print(f"\n✅ Сессия сохранена в файл: {output_file}")
        
        await client.disconnect()
        
        return {
            'session_name': account_data['session_name'],
            'string_session': string_session,
            'username': username,
            'first_name': first_name
        }
        
    except Exception as e:
        print(f"❌ Ошибка при переавторизации: {e}")
        try:
            await client.disconnect()
        except:
            pass
        return None

async def main():
    """Основная функция"""
    print("\n" + "="*80)
    print("🔄 ПЕРЕАВТОРИЗАЦИЯ НОВЫХ АККАУНТОВ")
    print("="*80)
    print("\nЭтот скрипт переавторизует 2 аккаунта (promotion_oleg_petrov, promotion_anna_truncher)")
    print("для каждого аккаунта.\n")
    
    results = []
    
    for account in ACCOUNTS_TO_REAUTHORIZE:
        result = await reauthorize_account(account)
        if result:
            results.append(result)
        
        # Небольшая пауза между аккаунтами
        if account != ACCOUNTS_TO_REAUTHORIZE[-1]:
            print("\n⏸️ Пауза 3 секунды перед следующим аккаунтом...")
            await asyncio.sleep(3)
    
    # Выводим итоговую информацию
    print("\n" + "="*80)
    print("📊 ИТОГИ ПЕРЕАВТОРИЗАЦИИ")
    print("="*80)
    
    if results:
        print(f"\n✅ Успешно переавторизовано: {len(results)} аккаунтов")
        print("\nНовые string_session:")
        for result in results:
            print(f"\n  {result['session_name']} (@{result['username']}):")
            print(f"    {result['string_session'][:50]}...")
    else:
        print("\n❌ Не удалось переавторизовать ни одного аккаунта")
    
    print("\n" + "="*80)
    print("✅ ГОТОВО! Теперь обновите accounts_config.json с новыми string_session")
    print("="*80)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️ Прервано пользователем")
    except Exception as e:
        print(f"\n\n❌ Критическая ошибка: {e}")




