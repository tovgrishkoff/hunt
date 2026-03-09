#!/usr/bin/env python3
"""
Пересоздание сессий для проблемных аккаунтов через QR-код
Аккаунты: artur_biggest, anna_truncher, oleg_petrov
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

# Проблемные аккаунты для пересоздания сессий
PROBLEMATIC_ACCOUNTS = [
    {
        "phone": "+380931849825",
        "api_id": 34601626,
        "api_hash": "eba8c7b793884b92a65c48436b646600",
        "session_name": "promotion_artur_biggest",
        "nickname": "Artur Biggest"
    },
    {
        "phone": "+380935173511",
        "api_id": 37120288,
        "api_hash": "e576f165ace9ea847633a136dc521062",
        "session_name": "promotion_anna_truncher",
        "nickname": "Anna Truncher"
    },
    {
        "phone": "+380731005075",
        "api_id": 38166279,
        "api_hash": "5326e0a7fb4803c973bc0b7025eb65af",
        "session_name": "promotion_oleg_petrov",
        "nickname": "Oleg Petrov"
    }
]

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
        
        # Всегда создаем новую сессию (не проверяем is_user_authorized)
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
                        
            except asyncio.TimeoutError:
                print("❌ Время ожидания истекло. QR-код устарел.")
                print("   Перезапустите скрипт для получения нового QR-кода.")
                await client.disconnect()
                return None
            except SessionPasswordNeededError:
                # Требуется пароль 2FA
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
    print("🚀 Пересоздание сессий для проблемных аккаунтов")
    print("="*80)
    print("\n📋 Аккаунты для пересоздания:")
    print()
    
    for i, account in enumerate(PROBLEMATIC_ACCOUNTS, 1):
        print(f"  {i}. {account['nickname']} ({account['phone']})")
        print(f"     Session: {account['session_name']}")
    
    print()
    print("="*80)
    print("\n⚠️  ВАЖНО: Система для Украины должна быть остановлена!")
    print("   Убедитесь, что контейнеры telegram-combine-* остановлены.")
    print()
    print("🚀 Начинаем авторизацию...")
    print()
    
    results = []
    
    for i, account_data in enumerate(PROBLEMATIC_ACCOUNTS, 1):
        print(f"\n{'='*80}")
        print(f"📱 Аккаунт {i}/{len(PROBLEMATIC_ACCOUNTS)}: {account_data['nickname']}")
        print(f"{'='*80}")
        
        result = await authorize_via_qr(account_data)
        
        if result:
            results.append(result)
            print(f"\n✅ Сессия успешно создана для {account_data['nickname']}!")
            
            if i < len(PROBLEMATIC_ACCOUNTS):
                print("\n" + "="*80)
                continue_choice = input("Продолжить со следующим аккаунтом? (y/n): ").strip().lower()
                if continue_choice != 'y':
                    print("⚠️ Прервано пользователем")
                    break
        else:
            print(f"\n❌ Не удалось создать сессию для {account_data['nickname']}")
            retry_choice = input("Попробовать еще раз? (y/n): ").strip().lower()
            if retry_choice == 'y':
                result = await authorize_via_qr(account_data)
                if result:
                    results.append(result)
                    print(f"\n✅ Успешно после повторной попытки!")
            else:
                print(f"⚠️ Пропускаем {account_data['nickname']}")
    
    # Итоговый отчет
    print("\n" + "="*80)
    print("📊 ИТОГОВЫЙ ОТЧЕТ")
    print("="*80)
    print(f"\n✅ Успешно создано сессий: {len(results)}/{len(PROBLEMATIC_ACCOUNTS)}")
    
    if results:
        print("\n📋 Созданные сессии:")
        for result in results:
            account = result['account_data']
            print(f"   ✅ {account['nickname']} -> new_session_{account['session_name']}.txt")
        
        print("\n📝 Следующие шаги:")
        print("   1. Обновить accounts_config.json с новыми String Session")
        print("   2. Обновить БД через скрипт update_all_accounts_from_config.py")
        print("   3. Перезапустить контейнеры: docker-compose restart marketer account-manager")
    else:
        print("\n❌ Не удалось создать ни одной сессии")

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
