#!/usr/bin/env python3
"""
Авторизация через QR-код (обход проблемы с недоставкой SMS)
"""
import asyncio
import sys
from telethon import TelegramClient
from telethon.sessions import StringSession

# Пытаемся импортировать qrcode, если не установлен - используем текстовый вывод
try:
    import qrcode
    QR_AVAILABLE = True
except ImportError:
    QR_AVAILABLE = False
    print("⚠️ Библиотека qrcode не установлена. Будет показан только URL для сканирования.")

# Данные аккаунта
ACCOUNT = {
    "phone": "+380731888518",
    "api_id": 34835411,
    "api_hash": "e3599e26b8f121230825b78136b795e3",
    "session_name": "promotion_new_account_2",
    "nickname": "New Account 2"
}

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
    
    print(f"\n{'='*80}")
    print(f"📱 Авторизация через QR-код: {nickname}")
    print(f"{'='*80}")
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
            f.write(f"Phone: {account_data['phone']}\n")
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
    print("🚀 Авторизация через QR-код")
    print("="*80)
    print(f"\n📱 Телефон: {ACCOUNT['phone']}")
    print(f"🔑 API ID: {ACCOUNT['api_id']}")
    print(f"📝 Session: {ACCOUNT['session_name']}")
    print("="*80)
    print("\n💡 Преимущества QR-авторизации:")
    print("   - Не нужен SMS код")
    print("   - Работает даже если SMS не приходит")
    print("   - Быстро и удобно")
    print()
    
    # Запускаем асинхронную функцию
    session = asyncio.run(authorize_via_qr(ACCOUNT))
    
    if session:
        print(f"\n{'='*80}")
        print(f"✅ УСПЕШНО! Сессия создана для {ACCOUNT['nickname']}!")
        print(f"{'='*80}")
        print(f"\n📋 Следующие шаги:")
        print(f"   1. Скопируйте String Session из файла: new_session_{ACCOUNT['session_name']}.txt")
        print(f"   2. Откройте accounts_config.json")
        print(f"   3. Добавьте новый аккаунт с этой String Session")
        print(f"   4. Добавьте в bali_accounts_config.json если нужно использовать для Бали")
        print(f"\nПример записи для accounts_config.json:")
        print(f"  {{")
        print(f"    \"phone\": \"{ACCOUNT['phone']}\",")
        print(f"    \"api_id\": {ACCOUNT['api_id']},")
        print(f"    \"api_hash\": \"{ACCOUNT['api_hash']}\",")
        print(f"    \"session_name\": \"{ACCOUNT['session_name']}\",")
        print(f"    \"nickname\": \"{ACCOUNT['nickname']}\",")
        print(f"    \"string_session\": \"{session[:50]}...\"")
        print(f"  }}")
    else:
        print(f"\n❌ Не удалось создать сессию для {ACCOUNT['nickname']}")

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
