#!/usr/bin/env python3
"""
Быстрый тест отправки SMS для аккаунтов 4 и 5
"""
import asyncio
import json
from urllib.parse import urlparse
from telethon import TelegramClient
from telethon.sessions import StringSession

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


async def test_send_code(session_name: str, account_data: dict, use_proxy: bool = True):
    """Тест отправки кода"""
    phone = account_data["phone"]
    api_id = account_data["api_id"]
    api_hash = account_data["api_hash"]
    nickname = account_data["nickname"]
    proxy_config = account_data.get("proxy") if use_proxy else None
    
    print(f"\n{'='*80}")
    print(f"🔐 Тест отправки кода для: {session_name}")
    print(f"👤 Никнейм: {nickname}")
    print(f"📞 Телефон: {phone}")
    print(f"🔑 API ID: {api_id}")
    
    proxy = None
    if proxy_config:
        proxy = parse_proxy(proxy_config)
        if proxy:
            print(f"🌐 Прокси: {proxy['addr']}:{proxy['port']}")
        else:
            print("⚠️ Прокси указан, но не удалось распарсить")
    else:
        print("⚠️ Прокси не используется")
    
    print(f"{'='*80}\n")
    
    client = TelegramClient(StringSession(), api_id, api_hash, proxy=proxy)
    
    try:
        print("📡 Подключение к Telegram...")
        await client.connect()
        print("✅ Подключение установлено\n")
        
        if await client.is_user_authorized():
            print("⚠️ Аккаунт уже авторизован! Создаем новую сессию...")
            await client.disconnect()
            client = TelegramClient(StringSession(), api_id, api_hash, proxy=proxy)
            await client.connect()
        
        print("📲 Отправка запроса на код...")
        print("   ⏳ Подождите, это может занять до 2 минут...\n")
        
        try:
            result = await client.send_code_request(phone)
            
            print(f"{'='*80}")
            print("✅ КОД ОТПРАВЛЕН!")
            print(f"{'='*80}")
            print(f"Тип доставки: {result.type}")
            if hasattr(result, 'next_type'):
                print(f"Следующий тип: {result.next_type}")
            print(f"Phone code hash: {result.phone_code_hash[:20]}...")
            print(f"{'='*80}\n")
            
            # Проверяем, куда отправлен код
            result_type_str = str(result.type).lower()
            if 'telegram' in result_type_str or 'app' in result_type_str:
                print("⚠️ ВАЖНО: Код отправлен в Telegram на уже авторизованное устройство!")
                print("   📱 Проверьте Telegram на телефоне/компьютере с этим номером")
                print("   Код должен прийти в уведомлениях Telegram (не SMS!)")
                print("   Или может появиться запрос на подтверждение новой авторизации")
            elif 'sms' in result_type_str:
                print("📱 Код отправлен по SMS")
                print(f"   Проверьте SMS на номер {phone}")
            else:
                print(f"📱 Проверьте Telegram/SMS на номер {phone}")
            
            print("\n   Код должен прийти в течение 1-2 минут")
            print("\n💡 Если аккаунт уже залогинен на другом устройстве:")
            print("   - Код может прийти в Telegram на это устройство")
            print("   - Или может потребоваться подтверждение с устройства")
            print()
            
            return True
            
        except Exception as e:
            error_str = str(e)
            print(f"\n❌ Ошибка при отправке кода: {error_str}")
            print("\nВозможные причины:")
            print("1. API_ID/API_HASH неверные или заблокированы Telegram")
            print("2. Номер телефона не зарегистрирован в Telegram")
            print("3. Слишком много попыток - нужно подождать (FloodWait)")
            print("4. Проблемы с сетью или прокси")
            print("5. Аккаунт заблокирован или ограничен")
            
            # Проверяем FloodWait
            if "wait" in error_str.lower() or "flood" in error_str.lower():
                import re
                wait_match = re.search(r'(\d+)', error_str)
                if wait_match:
                    wait_seconds = int(wait_match.group(1))
                    wait_minutes = wait_seconds // 60
                    print(f"\n⏰ Нужно подождать: {wait_seconds} секунд (~{wait_minutes} минут)")
            
            return False
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        try:
            await client.disconnect()
        except:
            pass


async def main():
    """Основная функция"""
    print("🚀 Тест отправки SMS для аккаунтов 4 и 5")
    print("=" * 80)
    
    # Загружаем аккаунты
    try:
        with open('accounts_config.json', 'r', encoding='utf-8') as f:
            accounts = json.load(f)
    except Exception as e:
        print(f"❌ Ошибка загрузки конфига: {e}")
        return
    
    # Аккаунты 4 и 5 (индексы 3 и 4 в списке)
    if len(accounts) < 5:
        print("❌ Недостаточно аккаунтов в конфиге!")
        return
    
    account_4 = accounts[3]  # promotion_oleg_petrov
    account_5 = accounts[4]  # promotion_anna_truncher
    
    accounts_to_test = [
        ("promotion_oleg_petrov", account_4),
        ("promotion_anna_truncher", account_5)
    ]
    
    print(f"\n📋 Будем тестировать:")
    for name, acc in accounts_to_test:
        print(f"   - {name} ({acc.get('nickname', name)}) - {acc.get('phone')}")
    
    # Спрашиваем про прокси
    print("\n" + "="*80)
    use_proxy_input = input("Использовать прокси? (y/n, по умолчанию y): ").strip().lower()
    use_proxy = use_proxy_input != 'n'
    print("="*80 + "\n")
    
    results = {}
    
    for session_name, account_data in accounts_to_test:
        account_info = {
            "phone": account_data.get('phone'),
            "api_id": account_data.get('api_id'),
            "api_hash": account_data.get('api_hash'),
            "nickname": account_data.get('nickname', session_name),
            "proxy": account_data.get('proxy')
        }
        
        success = await test_send_code(session_name, account_info, use_proxy)
        results[session_name] = success
        
        if not success and use_proxy:
            print("\n⚠️ Не получилось с прокси, пробуем без прокси...")
            success = await test_send_code(session_name, account_info, use_proxy=False)
            results[session_name] = success
        
        # Пауза между аккаунтами
        if session_name != accounts_to_test[-1][0]:
            input("\n⏸️  Нажмите Enter для перехода к следующему аккаунту...")
    
    # Итоговый отчет
    print("\n" + "=" * 80)
    print("📊 ИТОГОВЫЙ ОТЧЕТ")
    print("=" * 80)
    
    for session_name, success in results.items():
        status = "✅ Успешно" if success else "❌ Не удалось"
        print(f"{session_name}: {status}")
    
    print("=" * 80)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️ Прервано пользователем")
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
