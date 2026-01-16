#!/usr/bin/env python3
"""
Переавторизация аккаунта promotion_new_account для системы просмотра Stories

Использование:
    python3 reauthorize_new_account.py              # Интерактивный режим
    python3 reauthorize_new_account.py <код>        # С кодом из SMS
    python3 reauthorize_new_account.py <код> <2fa>   # С кодом и паролем 2FA
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from telethon import TelegramClient
from telethon.sessions import StringSession

async def reauthorize_new_account(code=None, password_2fa=None):
    """Переавторизация promotion_new_account"""
    print("="*70)
    print("🔐 ПЕРЕАВТОРИЗАЦИЯ promotion_new_account")
    print("="*70)
    
    # Загружаем конфигурацию stories
    config_file = 'accounts_config_stories.json'
    
    if not os.path.exists(config_file):
        print(f"❌ Файл {config_file} не найден!")
        return
    
    with open(config_file, 'r', encoding='utf-8') as f:
        accounts = json.load(f)
    
    # Находим аккаунт promotion_new_account
    account = None
    for acc in accounts:
        if acc['session_name'] == 'promotion_new_account':
            account = acc
            break
    
    if not account:
        print("❌ Аккаунт promotion_new_account не найден в конфигурации!")
        return
    
    phone = account['phone']
    api_id = int(account['api_id'])
    api_hash = account['api_hash']
    session_name = account['session_name']
    
    print(f"\n📱 Аккаунт: {session_name}")
    print(f"📞 Телефон: {phone}")
    print(f"🔑 API ID: {api_id}")
    print()
    
    # Удаляем старую сессию (если есть)
    session_file = f"sessions_stories/stories_{session_name}.session"
    if os.path.exists(session_file):
        os.remove(session_file)
        print(f"✅ Старый файл сессии удален: {session_file}")
    
    # Создаем папку для сессий
    Path("sessions_stories").mkdir(exist_ok=True)
    
    # Создаем клиент
    client = TelegramClient(
        f"sessions_stories/stories_{session_name}",
        api_id,
        api_hash
    )
    
    try:
        await client.connect()
        print("✅ Подключение к Telegram установлено")
        
        if await client.is_user_authorized():
            print("✅ Уже авторизован!")
            me = await client.get_me()
            username = getattr(me, 'username', 'No username')
            first_name = getattr(me, 'first_name', 'No name')
            print(f"   Пользователь: {first_name} (@{username})")
        else:
            if code is None:
                print("\n📲 Отправляем код авторизации...")
                await client.send_code_request(phone)
                print(f"✅ Код отправлен на {phone}")
                
                # Запрашиваем код
                code = input("\nВведите код из SMS/Telegram: ").strip()
            else:
                print(f"\n📲 Используем код из аргументов: {code}")
            
            try:
                await client.sign_in(phone, code)
                print("✅ Авторизация успешна!")
            except Exception as e:
                error_str = str(e).lower()
                if "password" in error_str or "two-step" in error_str or "2fa" in error_str:
                    if password_2fa is None:
                        print("\n🔐 Требуется пароль 2FA:")
                        password_2fa = input("Введите пароль 2FA: ").strip()
                    else:
                        print(f"\n🔐 Используем пароль 2FA из аргументов")
                    await client.sign_in(password=password_2fa)
                    print("✅ Авторизация с 2FA успешна!")
                else:
                    raise e
        
        # Получаем информацию о пользователе
        me = await client.get_me()
        username = getattr(me, 'username', 'No username')
        first_name = getattr(me, 'first_name', 'No name')
        
        print(f"\n✅ Авторизован как: {first_name} (@{username})")
        
        # Создаем string session
        string_session = client.session.save()
        
        # Обновляем конфигурацию
        account['string_session'] = string_session
        account['nickname'] = first_name
        
        # Сохраняем обновленную конфигурацию
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(accounts, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Конфигурация обновлена в {config_file}")
        print("✅ String session сохранен")
        
        await client.disconnect()
        
        print("\n" + "="*70)
        print("✅ ПЕРЕАВТОРИЗАЦИЯ ЗАВЕРШЕНА")
        print("="*70)
        print("\n📋 Следующие шаги:")
        print("   1. Перезапустите контейнер stories-viewer:")
        print("      cd /home/tovgrishkoff/PIAR/telegram_promotion_system")
        print("      docker-compose restart stories-viewer")
        print("   2. Проверьте логи:")
        print("      docker logs telegram-stories-viewer --tail 50")
        print()
        
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        await client.disconnect()


if __name__ == "__main__":
    # Парсим аргументы командной строки
    code_arg = sys.argv[1] if len(sys.argv) > 1 else None
    password_2fa_arg = sys.argv[2] if len(sys.argv) > 2 else None
    
    asyncio.run(reauthorize_new_account(code=code_arg, password_2fa=password_2fa_arg))

