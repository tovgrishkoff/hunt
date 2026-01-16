#!/usr/bin/env python3
"""
Скрипт для переавторизации аккаунтов с проблемой AuthKeyDuplicatedError
Генерирует новые String Session для убитых аккаунтов
"""
import asyncio
import json
import sys
from urllib.parse import urlparse
from telethon import TelegramClient
from telethon.sessions import StringSession

def load_accounts_from_config():
    """Загрузка аккаунтов из accounts_config.json"""
    try:
        with open('accounts_config.json', 'r', encoding='utf-8') as f:
            accounts = json.load(f)
        
        accounts_dict = {}
        for acc in accounts:
            session_name = acc.get('session_name')
            if session_name:
                accounts_dict[session_name] = {
                    "phone": acc.get('phone'),
                    "api_id": acc.get('api_id'),
                    "api_hash": acc.get('api_hash'),
                    "nickname": acc.get('nickname', session_name),
                    "proxy": acc.get('proxy')
                }
        return accounts_dict
    except FileNotFoundError:
        print("❌ Файл accounts_config.json не найден!")
        return {}
    except Exception as e:
        print(f"❌ Ошибка при загрузке конфигурации: {e}")
        return {}


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


async def generate_session(session_name: str, account_data: dict, use_proxy: bool = True):
    """
    Генерация новой String Session для аккаунта
    
    Args:
        session_name: Имя сессии (например, "promotion_artur_biggest")
        account_data: Словарь с данными аккаунта (phone, api_id, api_hash, nickname, proxy)
        use_proxy: Использовать ли прокси (по умолчанию True)
    """
    phone = account_data["phone"]
    api_id = account_data["api_id"]
    api_hash = account_data["api_hash"]
    nickname = account_data["nickname"]
    proxy_config = account_data.get("proxy") if use_proxy else None
    
    print(f"\n{'='*80}")
    print(f"🔐 Вход для аккаунта: {session_name}")
    print(f"👤 Никнейм: {nickname}")
    print(f"📞 Телефон: {phone}")
    print(f"🔑 API ID: {api_id}")
    
    # Парсим прокси если указан
    proxy = None
    if proxy_config:
        proxy = parse_proxy(proxy_config)
        if proxy:
            print(f"🌐 Прокси: {proxy['addr']}:{proxy['port']} ({proxy['proxy_type']})")
        else:
            print("⚠️ Прокси указан, но не удалось распарсить")
    else:
        print("⚠️ Прокси не используется")
    
    print(f"{'='*80}\n")
    
    # Создаем клиент с пустой StringSession
    client = TelegramClient(StringSession(), api_id, api_hash, proxy=proxy)
    
    try:
        # Подключаемся
        print("📡 Подключение к Telegram...")
        await client.connect()
        print("✅ Подключение установлено")
        
        # Проверяем авторизацию
        if not await client.is_user_authorized():
            print(f"📲 Отправка кода авторизации на {phone}...")
            print("   ⏳ Подождите, это может занять до 2 минут...")
            
            try:
                print("   ⏳ Отправка запроса на код... (это может занять до 2 минут)")
                result = await client.send_code_request(phone)
                
                print(f"\n{'='*80}")
                print("✅ Код отправлен!")
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
                
                print("   Код должен прийти в течение 1-2 минут")
                print("\n💡 Если аккаунт уже залогинен на другом устройстве:")
                print("   - Код может прийти в Telegram на это устройство")
                print("   - Или может потребоваться подтверждение с устройства")
                print()
                
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
                
                await client.disconnect()
                return None
            
            # Запрашиваем код
            print("\n" + "="*80)
            code = input("✉️ Введите код из SMS/Telegram: ").strip()
            
            if not code:
                print("❌ Код не введен!")
                await client.disconnect()
                return None
            
            try:
                await client.sign_in(phone, code)
                print("✅ Код принят!")
            except Exception as e:
                error_str = str(e)
                # Проверяем нужен ли 2FA пароль
                if "PASSWORD_HASH_INVALID" in error_str or "two-step" in error_str.lower() or "SessionPasswordNeeded" in error_str:
                    print("🔐 Требуется пароль двухфакторной аутентификации")
                    password = input("🔐 Введите пароль 2FA: ").strip()
                    if password:
                        await client.sign_in(password=password)
                        print("✅ Авторизация с 2FA успешна!")
                    else:
                        print("❌ Пароль не введен!")
                        await client.disconnect()
                        return None
                else:
                    print(f"❌ Ошибка при входе: {e}")
                    await client.disconnect()
                    return None
        else:
            print("✅ Аккаунт уже авторизован")
        
        # Получаем информацию о пользователе
        me = await client.get_me()
        username = me.username or "нет username"
        first_name = me.first_name or "Unknown"
        last_name = me.last_name or ""
        
        print(f"\n✅ Авторизован как: {first_name} {last_name} (@{username})")
        print(f"   ID: {me.id}")
        
        # Сохраняем сессию
        session_str = client.session.save()
        
        print(f"\n{'='*80}")
        print(f"✅ НОВАЯ СЕССИЯ ДЛЯ {session_name}")
        print(f"{'='*80}")
        print(f"\n{session_str}\n")
        print(f"{'='*80}\n")
        
        await client.disconnect()
        return session_str
            
    except Exception as e:
        print(f"❌ Ошибка при генерации сессии для {session_name}: {e}")
        import traceback
        traceback.print_exc()
        try:
            await client.disconnect()
        except:
            pass
        return None


async def main():
    """Основная функция"""
    print("🚀 Генерация новых сессий для аккаунтов")
    print("=" * 80)
    print("Этот скрипт поможет пересоздать сессии для аккаунтов")
    print("=" * 80)
    
    # Загружаем аккаунты из конфига
    all_accounts = load_accounts_from_config()
    
    if not all_accounts:
        print("❌ Не удалось загрузить аккаунты из accounts_config.json")
        return
    
    print(f"\n📋 Найдено аккаунтов: {len(all_accounts)}")
    print("\nДоступные аккаунты:")
    accounts_list = list(all_accounts.items())
    for i, (session_name, acc_data) in enumerate(accounts_list, 1):
        print(f"  {i}. {session_name} ({acc_data['nickname']}) - {acc_data['phone']}")
    
    # Выбор аккаунтов
    print("\n" + "="*80)
    print("Выберите аккаунты для переавторизации:")
    print("  - Введите номера через запятую (например: 1,3,5)")
    print("  - Или 'all' для всех аккаунтов")
    print("  - Или 'other' для аккаунтов кроме проблемных (artur, anna, oleg)")
    print("="*80)
    
    selection = input("\n👉 Ваш выбор: ").strip().lower()
    
    selected_accounts = {}
    if selection == 'all':
        selected_accounts = all_accounts
    elif selection == 'other':
        # Все кроме проблемных
        problematic = ['promotion_artur_biggest', 'promotion_anna_truncher', 'promotion_oleg_petrov']
        selected_accounts = {k: v for k, v in all_accounts.items() if k not in problematic}
    else:
        # Выбранные по номерам
        try:
            indices = [int(x.strip()) - 1 for x in selection.split(',')]
            for idx in indices:
                if 0 <= idx < len(accounts_list):
                    session_name, acc_data = accounts_list[idx]
                    selected_accounts[session_name] = acc_data
        except ValueError:
            print("❌ Неверный формат ввода!")
            return
    
    if not selected_accounts:
        print("❌ Не выбрано ни одного аккаунта!")
        return
    
    print(f"\n✅ Выбрано аккаунтов: {len(selected_accounts)}")
    for session_name in selected_accounts.keys():
        print(f"   - {session_name}")
    
    # Спрашиваем, использовать ли прокси
    print("\n" + "="*80)
    use_proxy_input = input("Использовать прокси? (y/n, по умолчанию y): ").strip().lower()
    use_proxy = use_proxy_input != 'n'
    print("="*80 + "\n")
    
    sessions = {}
    
    for session_name, account_data in selected_accounts.items():
        # Пробуем сначала с прокси, если не получится - без прокси
        session_str = await generate_session(session_name, account_data, use_proxy=use_proxy)
        
        # Если не получилось с прокси, пробуем без прокси
        if not session_str and use_proxy:
            print("\n⚠️ Не удалось с прокси, пробуем без прокси...")
            session_str = await generate_session(session_name, account_data, use_proxy=False)
        
        if session_str:
            sessions[session_name] = session_str
        else:
            print(f"⚠️ Не удалось создать сессию для {session_name}")
        
        # Пауза между аккаунтами
        remaining = list(selected_accounts.keys())
        if session_name != remaining[-1]:
            input("\n⏸️  Нажмите Enter для перехода к следующему аккаунту...")
    
    # Итоговый отчет
    print("\n" + "=" * 80)
    print("📊 ИТОГОВЫЙ ОТЧЕТ")
    print("=" * 80)
    
    if sessions:
        print(f"\n✅ Успешно создано сессий: {len(sessions)}")
        print("\n📋 Созданные сессии:")
        for session_name, session_str in sessions.items():
            print(f"\n{session_name}:")
            print(f"{session_str}")
    else:
        print("\n❌ Не удалось создать ни одной сессии")
    
    print("\n" + "=" * 80)
    print("💡 Следующие шаги:")
    print("1. Скопируйте созданные String Session")
    print("2. Обновите accounts_config.json, заменив старые string_session")
    print("3. Перезапустите контейнеры: docker-compose restart")
    print("=" * 80)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️ Прервано пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
