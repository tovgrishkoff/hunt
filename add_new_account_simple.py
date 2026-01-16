#!/usr/bin/env python3
"""
Простой скрипт для добавления нового аккаунта
Использует интерактивный ввод данных
"""
import asyncio
import json
from pathlib import Path
from telethon import TelegramClient
from telethon.sessions import StringSession

async def authorize_new_account():
    """Интерактивная авторизация нового аккаунта"""
    print("\n" + "="*80)
    print("🔐 ДОБАВЛЕНИЕ НОВОГО TELEGRAM АККАУНТА")
    print("="*80)
    print()
    
    # Запрашиваем данные аккаунта
    print("📋 Введите данные нового аккаунта:")
    print()
    
    phone = input("📱 Номер телефона (с +): ").strip()
    if not phone:
        print("❌ Номер телефона обязателен!")
        return None
    
    api_id_str = input("🔑 API ID: ").strip()
    if not api_id_str:
        print("❌ API ID обязателен!")
        return None
    
    try:
        api_id = int(api_id_str)
    except ValueError:
        print("❌ API ID должен быть числом!")
        return None
    
    api_hash = input("🔑 API Hash: ").strip()
    if not api_hash:
        print("❌ API Hash обязателен!")
        return None
    
    session_name = input("📝 Session name (например, promotion_new_user): ").strip()
    if not session_name:
        print("❌ Session name обязателен!")
        return None
    
    nickname = input("👤 Nickname (необязательно): ").strip() or session_name
    
    print()
    print("="*80)
    print(f"📱 Телефон: {phone}")
    print(f"👤 Имя: {nickname}")
    print(f"📝 Session: {session_name}")
    print(f"🔑 API ID: {api_id}")
    print("="*80)
    print()
    
    confirm = input("✅ Все верно? (y/n): ").strip().lower()
    if confirm != 'y':
        print("❌ Отменено")
        return None
    
    # Создаем директорию для сессий
    Path("sessions").mkdir(exist_ok=True)
    
    # Создаем клиент с StringSession
    session = StringSession()
    client = TelegramClient(session, api_id, api_hash)
    
    try:
        print("\n🔌 Подключение к Telegram...")
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
        
        # Проверяем авторизацию
        if await client.is_user_authorized():
            print("✅ Аккаунт уже авторизован!")
            me = await client.get_me()
            username = getattr(me, 'username', 'No username')
            print(f"   Пользователь: @{username}")
        else:
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
                print("   Проверьте Telegram на Android устройстве")
            elif 'sms' in result_type_str:
                print("📱 Код отправлен по SMS")
                print(f"   Проверьте SMS на номер {phone}")
            else:
                print(f"📱 Проверьте Telegram/SMS на номер {phone}")
            
            print("   Код должен прийти в течение минуты")
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
        
        print("\n" + "="*80)
        print("✅ АВТОРИЗАЦИЯ УСПЕШНА!")
        print("="*80)
        print(f"👤 Имя: {first_name} {last_name}".strip())
        print(f"📱 Телефон: {me.phone}")
        print(f"🆔 Username: @{username}" if username != 'No username' else "🆔 Username: не установлен")
        print(f"🆔 User ID: {me.id}")
        print("="*80)
        
        # Получаем string_session
        string_session = client.session.save()
        
        print("\n" + "="*80)
        print("📋 STRING SESSION (скопируйте это):")
        print("="*80)
        print(string_session)
        print("="*80)
        
        # Сохраняем в файл
        filename = f'new_account_{session_name}_session.txt'
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"Phone: {phone}\n")
            f.write(f"API ID: {api_id}\n")
            f.write(f"API Hash: {api_hash}\n")
            f.write(f"Session Name: {session_name}\n")
            f.write(f"Nickname: {nickname}\n")
            f.write(f"Username: @{username}\n")
            f.write(f"Full Name: {first_name} {last_name}".strip() + "\n")
            f.write(f"User ID: {me.id}\n")
            f.write(f"\nString Session:\n{string_session}\n")
        
        print(f"\n✅ Сессия сохранена в файл: {filename}")
        
        # Создаем JSON конфиг для добавления в accounts_config.json
        account_data = {
            "phone": phone,
            "api_id": api_id,
            "api_hash": api_hash,
            "session_name": session_name,
            "nickname": nickname,
            "bio": "Ищу профессионалов для сотрудничества",
            "string_session": string_session
        }
        
        if username != 'No username':
            account_data["username"] = username
        
        json_filename = f'new_account_{session_name}_config.json'
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(account_data, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Конфиг сохранен в файл: {json_filename}")
        print()
        print("="*80)
        print("📋 СЛЕДУЮЩИЕ ШАГИ:")
        print("="*80)
        print(f"1. Скопируйте String Session из файла: {filename}")
        print(f"2. Или используйте готовый JSON конфиг: {json_filename}")
        print(f"3. Добавьте аккаунт в accounts_config.json")
        print(f"4. Добавьте аккаунт в accounts_config_stories.json (если нужен просмотр Stories)")
        print("="*80)
        
        await client.disconnect()
        return account_data
        
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        try:
            await client.disconnect()
        except:
            pass
        return None

if __name__ == "__main__":
    print("\n🚀 Запуск скрипта добавления нового аккаунта")
    print("   Убедитесь, что у вас есть:")
    print("   - Номер телефона аккаунта")
    print("   - API ID и API Hash (получить на https://my.telegram.org/apps)")
    print()
    
    result = asyncio.run(authorize_new_account())
    if result:
        print("\n✅ Готово! Аккаунт успешно авторизован!")
        print("   Теперь добавьте его в конфигурационные файлы.")
    else:
        print("\n❌ Не удалось авторизовать аккаунт")




