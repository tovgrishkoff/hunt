#!/usr/bin/env python3
"""
Универсальная авторизация через QR-код для всех аккаунтов
"""
import asyncio
import sys
import json
from pathlib import Path
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError

# Пытаемся импортировать qrcode
try:
    import qrcode
    QR_AVAILABLE = True
except ImportError:
    QR_AVAILABLE = False
    print("⚠️ Библиотека qrcode не установлена. Будет показан только URL для сканирования.")

# Список аккаунтов для авторизации
ACCOUNTS_TO_AUTH = {
    "1": {
        "phone": "+380937392431",
        "api_id": 36665934,
        "api_hash": "0ac3c86e68a3e4eac13bb7c2ab2dff3d",
        "session_name": "promotion_lisa_soak",
        "nickname": "Lisa Soak"
    },
    "2": {
        "phone": "+380731888518",
        "api_id": 34835411,
        "api_hash": "e3599e26b8f121230825b78136b795e3",
        "session_name": "promotion_new_account_2",
        "nickname": "New Account 2"
    },
    "3": {
        "phone": "+380931849825",
        "api_id": 34601626,
        "api_hash": "eba8c7b793884b92a65c48436b646600",
        "session_name": "promotion_artur_biggest",
        "nickname": "Artur Biggest"
    },
    "4": {
        "phone": "+380935173511",
        "api_id": 37120288,
        "api_hash": "e576f165ace9ea847633a136dc521062",
        "session_name": "promotion_anna_truncher",
        "nickname": "Anna Truncher"
    },
    "5": {
        "phone": "+380731005075",
        "api_id": 38166279,
        "api_hash": "5326e0a7fb4803c973bc0b7025eb65af",
        "session_name": "promotion_oleg_petrov",
        "nickname": "Oleg Petrov"
    },
    "6": {
        "phone": "+380930734685",
        "api_id": 25586686,
        "api_hash": "9ccad646ca28f63e7e9f0c2ea0e5f1c2",
        "session_name": "promotion_alex_ever",
        "nickname": "Alex Ever"
    },
    "7": {
        "phone": "+380934672230",
        "api_id": 27971326,
        "api_hash": "3e9d2b22e6ad33f1da1df8d2a1a4e2b3",
        "session_name": "promotion_dao_bro",
        "nickname": "Dao Bro"
    },
    "8": {
        "phone": "+380935173511",
        "api_id": 37120288,
        "api_hash": "e576f165ace9ea847633a136dc521062",
        "session_name": "promotion_rod_shaihutdinov",
        "nickname": "Rod Shaihutdinov"
    }
}

# Если есть accounts_config.json — подтягиваем реальные данные (API_ID/API_HASH/phone)
def _sync_accounts_from_config(accounts_map: dict) -> dict:
    config_path = Path(__file__).parent / "accounts_config.json"
    if not config_path.exists():
        return accounts_map
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config_accounts = json.load(f)
    except Exception:
        return accounts_map

    by_session = {
        acc.get("session_name"): acc
        for acc in config_accounts
        if acc.get("session_name")
    }
    for key, acc in accounts_map.items():
        session_name = acc.get("session_name")
        if not session_name:
            continue
        cfg = by_session.get(session_name)
        if not cfg:
            continue
        # Обновляем только если в конфиге есть значения
        acc["phone"] = cfg.get("phone", acc.get("phone"))
        acc["api_id"] = cfg.get("api_id", acc.get("api_id"))
        acc["api_hash"] = cfg.get("api_hash", acc.get("api_hash"))
        acc["nickname"] = cfg.get("nickname", acc.get("nickname"))
    return accounts_map

ACCOUNTS_TO_AUTH = _sync_accounts_from_config(ACCOUNTS_TO_AUTH)

def display_url_as_qr(url):
    """Отображение QR-кода в терминале"""
    if QR_AVAILABLE:
        try:
            qr = qrcode.QRCode()
            qr.add_data(url)
            qr.print_ascii(invert=True)
        except Exception as e:
            print(f"⚠️ Ошибка отображения QR: {e}")
            print(f"\n📱 URL для сканирования: {url}")
    else:
        print(f"\n📱 URL для сканирования:")
        print("="*80)
        print(url)
        print("="*80)
        print("\n💡 Скопируйте этот URL и откройте в браузере, или используйте:")
        print("   Telegram на телефоне -> Настройки -> Устройства -> Подключить устройство")

async def authorize_via_qr(account_data):
    """Авторизация через QR-код"""
    api_id = account_data["api_id"]
    api_hash = account_data["api_hash"]
    session_name = account_data["session_name"]
    nickname = account_data["nickname"]
    phone = account_data["phone"]
    
    print(f"\n{'='*80}")
    print(f"📱 Авторизация через QR-код: {nickname}")
    print(f"{'='*80}")
    print(f"Телефон: {phone}")
    print(f"API ID: {api_id}")
    print(f"Session: {session_name}")
    print()
    
    # Создаем клиент с StringSession
    client = TelegramClient(StringSession(), api_id, api_hash)
    
    try:
        print("🔐 Подключение к Telegram...")
        await client.connect()
        print("✅ Подключение установлено\n")
        
        # Проверяем, авторизован ли уже
        if await client.is_user_authorized():
            print("✅ Аккаунт уже авторизован!")
            me = await client.get_me()
            username = getattr(me, 'username', 'No username')
            first_name = getattr(me, 'first_name', 'No name')
            print(f"   Пользователь: {first_name} (@{username})")
        else:
            print("📱 Запуск авторизации через QR-код...")
            print("="*80)
            print("📲 ИНСТРУКЦИЯ:")
            print("   1. Откройте Telegram на телефоне")
            print("   2. Перейдите: Настройки -> Устройства -> Подключить устройство")
            print("   3. Отсканируйте QR-код ниже камерой телефона")
            print("="*80)
            print()
            
            try:
                # Запускаем процедуру QR-логина
                qr_login = await client.qr_login()
                
                print("🔲 QR-КОД (отсканируйте его в Telegram):")
                print("="*80)
                display_url_as_qr(qr_login.url)
                print("="*80)
                print()
                print("⏳ Ожидание сканирования QR-кода...")
                print("   (У вас есть ограниченное время, обычно 1-2 минуты)")
                print()
                
                # Ждем, пока пользователь отсканирует
                try:
                    await qr_login.wait()
                    print("✅ QR-код успешно отсканирован!")
                except SessionPasswordNeededError:
                    print("🔐 Включена двухфакторная защита. Нужен пароль 2FA.")
                    password = input("🔐 Пароль 2FA: ").strip()
                    if not password:
                        print("❌ Пароль 2FA не введен")
                        await client.disconnect()
                        return None
                    try:
                        await client.sign_in(password=password)
                        print("✅ Авторизация с 2FA успешна!")
                    except Exception as e:
                        print(f"❌ Ошибка 2FA: {e}")
                        await client.disconnect()
                        return None
                except asyncio.TimeoutError:
                    print("❌ Время ожидания истекло. QR-код устарел.")
                    print("   Перезапустите скрипт для получения нового QR-кода.")
                    await client.disconnect()
                    return None
                except Exception as e:
                    print(f"❌ Ошибка при ожидании сканирования: {e}")
                    await client.disconnect()
                    return None
                    
            except Exception as e:
                print(f"❌ Ошибка при запуске QR-логина: {e}")
                print("\nВозможные причины:")
                print("1. API_ID/API_HASH неверные")
                print("2. Проблемы с сетью")
                print("3. Telegram временно недоступен")
                await client.disconnect()
                return None
        
        # Получаем информацию о пользователе
        me = await client.get_me()
        username = getattr(me, 'username', 'No username')
        first_name = getattr(me, 'first_name', 'No name')
        last_name = getattr(me, 'last_name', '')
        
        print(f"\n✅ Авторизация успешна!")
        print(f"   Пользователь: {first_name} {last_name} (@{username})")
        print(f"   ID: {me.id}")
        
        # Получаем String Session
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
        
        # Отправляем тестовое сообщение себе (опционально)
        try:
            await client.send_message('me', 'Авторизация через QR успешна! 🚀')
            print("✅ Тестовое сообщение отправлено")
        except:
            pass
        
        await client.disconnect()
        return {
            'session_string': session_string,
            'account_data': account_data,
            'user_info': {
                'username': username,
                'first_name': first_name,
                'last_name': last_name,
                'user_id': me.id
            }
        }
        
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
    print("🚀 Универсальная авторизация через QR-код")
    print("="*80)
    print("\n📋 Доступные аккаунты для авторизации:")
    print()
    
    for key, account in ACCOUNTS_TO_AUTH.items():
        print(f"  {key}. {account['nickname']} ({account['phone']})")
        print(f"     Session: {account['session_name']}")
    
    print()
    print("  n. Ввести данные нового аккаунта вручную")
    print()
    print("="*80)
    
    choice = input("👉 Выберите номер аккаунта (или 'n' для нового): ").strip().lower()
    
    if choice == 'n':
        # Ручной ввод данных
        print("\n📝 Введите данные нового аккаунта:")
        phone = input("Телефон (с +): ").strip()
        api_id = input("API ID: ").strip()
        api_hash = input("API Hash: ").strip()
        session_name = input("Session Name (например, promotion_new_account): ").strip()
        nickname = input("Nickname (необязательно): ").strip() or session_name
        
        account_data = {
            "phone": phone,
            "api_id": int(api_id),
            "api_hash": api_hash,
            "session_name": session_name,
            "nickname": nickname
        }
    elif choice in ACCOUNTS_TO_AUTH:
        account_data = ACCOUNTS_TO_AUTH[choice]
    else:
        print(f"❌ Неверный выбор: {choice}")
        return
    
    print(f"\n✅ Выбран: {account_data['nickname']} ({account_data['phone']})")
    print("="*80)
    
    # Запускаем асинхронную функцию
    result = asyncio.run(authorize_via_qr(account_data))
    
    if result:
        session_string = result['session_string']
        account_data = result['account_data']
        user_info = result['user_info']
        
        print(f"\n{'='*80}")
        print(f"✅ УСПЕШНО! Сессия создана для {account_data['nickname']}!")
        print(f"{'='*80}")
        print(f"\n📋 Следующие шаги:")
        print(f"   1. Скопируйте String Session из файла: new_session_{account_data['session_name']}.txt")
        print(f"   2. Откройте accounts_config.json")
        print(f"   3. Добавьте новый аккаунт с этой String Session")
        print(f"   4. Добавьте в bali_accounts_config.json если нужно использовать для Бали")
        print(f"\nПример записи для accounts_config.json:")
        print(f"  {{")
        print(f"    \"phone\": \"{account_data['phone']}\",")
        print(f"    \"api_id\": {account_data['api_id']},")
        print(f"    \"api_hash\": \"{account_data['api_hash']}\",")
        print(f"    \"session_name\": \"{account_data['session_name']}\",")
        print(f"    \"nickname\": \"{account_data['nickname']}\",")
        print(f"    \"string_session\": \"{session_string[:50]}...\"")
        print(f"  }}")
        
        # Предлагаем продолжить с другими аккаунтами
        print("\n" + "="*80)
        continue_choice = input("Продолжить с другим аккаунтом? (y/n): ").strip().lower()
        if continue_choice == 'y':
            main()  # Рекурсивный вызов для следующего аккаунта
    else:
        print(f"\n❌ Не удалось создать сессию для {account_data['nickname']}")
        print("\n" + "="*80)
        retry_choice = input("Попробовать еще раз? (y/n): ").strip().lower()
        if retry_choice == 'y':
            result = asyncio.run(authorize_via_qr(account_data))
            if result:
                print(f"\n✅ Успешно после повторной попытки!")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️ Прервано пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
