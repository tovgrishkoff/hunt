#!/usr/bin/env python3
"""
Переавторизация аккаунта promotion_Masha Sinugina через QR-код
"""
import asyncio
import sys
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

# Данные аккаунта
ACCOUNT = {
    "phone": "+380731888518",
    "api_id": 34835411,
    "api_hash": "e3599e26b8f121230825b78136b795e3",
    "session_name": "promotion_Masha Sinugina",
    "nickname": "Masha Sinugina"
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
                
                # Проверяем, требуется ли пароль 2FA после сканирования QR
                if not await client.is_user_authorized():
                    print("\n🔐 Включена двухфакторная аутентификация (2FA)")
                    print("="*80)
                    print("После сканирования QR-кода требуется ввести пароль 2FA")
                    print("="*80)
                    
                    password = input("\n🔐 Введите пароль 2FA: ").strip()
                    
                    if not password:
                        print("❌ Пароль не введен. Отмена.")
                        await client.disconnect()
                        return None
                    
                    try:
                        await client.sign_in(password=password)
                        print("✅ Пароль 2FA принят! Авторизация успешна.")
                    except Exception as e:
                        print(f"❌ Ошибка при вводе пароля 2FA: {e}")
                        print("   Проверьте правильность пароля и попробуйте снова.")
                        await client.disconnect()
                        return None
                        
            except SessionPasswordNeededError:
                # Требуется пароль 2FA (если ошибка выброшена напрямую)
                print("\n🔐 Требуется пароль 2FA (двухфакторная аутентификация)")
                print("="*80)
                password = input("Введите пароль 2FA: ").strip()
                
                if not password:
                    print("❌ Пароль не введен. Отмена.")
                    await client.disconnect()
                    return None
                
                try:
                    await client.sign_in(password=password)
                    print("✅ Пароль 2FA принят!")
                except Exception as e:
                    print(f"❌ Ошибка при вводе пароля 2FA: {e}")
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
            await client.send_message('me', 'Новая сессия создана через QR! 🚀')
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

async def main():
    print("🚀 Переавторизация аккаунта promotion_Masha Sinugina")
    print("="*80)
    print("\n📋 Данные аккаунта:")
    print(f"   Телефон: {ACCOUNT['phone']}")
    print(f"   Nickname: {ACCOUNT['nickname']}")
    print(f"   Session: {ACCOUNT['session_name']}")
    print()
    print("="*80)
    print("\n⚠️  ВАЖНО: Убедитесь, что аккаунт не используется в других контейнерах!")
    print()
    input("Нажмите Enter для продолжения...")
    print()
    
    result = await authorize_via_qr(ACCOUNT)
    
    if result:
        print("\n" + "="*80)
        print("✅ АВТОРИЗАЦИЯ УСПЕШНА!")
        print("="*80)
        print("\n📝 Следующие шаги:")
        print("   1. Обновить accounts_config.json с новой String Session")
        print("   2. Обновить БД через скрипт update_all_accounts_from_config.py")
        print("   3. Перезапустить контейнер секретаря: docker restart telegram-bali-secretary")
        print("\n💡 Для обновления запустите:")
        print("   python3 update_sessions_from_files.py")
        print("   python3 scripts/update_all_accounts_from_config.py")
    else:
        print("\n" + "="*80)
        print("❌ АВТОРИЗАЦИЯ НЕ УДАЛАСЬ")
        print("="*80)
        print("\nПопробуйте запустить скрипт снова.")

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
