#!/usr/bin/env python3
"""
Авторизация аккаунта @grishkoff (promotion_new_account)
Обновляет string_session в accounts_config_stories.json
"""

import asyncio
import json
from pathlib import Path
from telethon import TelegramClient
from telethon.sessions import StringSession


async def authorize_grishkoff():
    """Авторизация аккаунта @grishkoff"""
    print("\n" + "="*80)
    print("🔐 АВТОРИЗАЦИЯ АККАУНТА @grishkoff (promotion_new_account)")
    print("="*80 + "\n")
    
    # Данные аккаунта
    phone = "+380930734685"
    api_id = 25586686
    api_hash = "2b8c229a66202daa2d2b560f969f78a1"
    session_name = "promotion_new_account"
    config_file = "accounts_config_stories.json"
    
    print(f"📱 Телефон: {phone}")
    print(f"📋 Session name: {session_name}")
    print(f"🔑 API ID: {api_id}\n")
    
    # Загружаем конфигурацию
    config_path = Path(config_file)
    if not config_path.exists():
        print(f"❌ Файл {config_file} не найден!")
        return
    
    with open(config_file, 'r', encoding='utf-8') as f:
        accounts = json.load(f)
    
    # Ищем аккаунт в конфиге
    account = None
    for acc in accounts:
        if acc.get('session_name') == session_name:
            account = acc
            break
    
    if not account:
        print(f"❌ Аккаунт {session_name} не найден в конфигурации!")
        return
    
    # Создаем клиент с StringSession
    print("🔌 Подключение к Telegram...")
    client = TelegramClient(StringSession(), api_id, api_hash)
    
    try:
        await client.connect()
        print("✅ Подключение установлено\n")
        
        # Проверяем авторизацию
        if await client.is_user_authorized():
            print("✅ Уже авторизован!")
            me = await client.get_me()
            username = getattr(me, 'username', 'No username')
            print(f"   Пользователь: @{username}")
        else:
            print("📲 Отправляем код авторизации...")
            await client.send_code_request(phone)
            
            # Запрашиваем код
            print("\n" + "-"*80)
            code = input("📱 Введите код из SMS/Telegram: ").strip()
            print("-"*80 + "\n")
            
            try:
                await client.sign_in(phone, code)
                print("✅ Авторизация успешна!")
            except Exception as e:
                error_str = str(e).lower()
                if "password" in error_str or "2fa" in error_str or "two-step" in error_str:
                    print("🔐 Требуется пароль 2FA (двухфакторная аутентификация)")
                    password = input("🔑 Введите пароль 2FA: ").strip()
                    await client.sign_in(password=password)
                    print("✅ Авторизация с 2FA успешна!")
                else:
                    raise e
        
        # Получаем информацию о пользователе
        me = await client.get_me()
        username = getattr(me, 'username', 'No username')
        first_name = getattr(me, 'first_name', 'No name')
        last_name = getattr(me, 'last_name', '') or ''
        
        print("\n" + "="*80)
        print("✅ ИНФОРМАЦИЯ ОБ АККАУНТЕ:")
        print("="*80)
        print(f"   👤 Username: @{username}")
        print(f"   📛 Имя: {first_name} {last_name}".strip())
        print(f"   🆔 ID: {me.id}")
        print("="*80 + "\n")
        
        # Получаем String Session
        string_session = client.session.save()
        
        # Обновляем конфигурацию
        account['string_session'] = string_session
        account['nickname'] = first_name
        
        # Сохраняем обновленную конфигурацию
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(accounts, f, indent=2, ensure_ascii=False)
        
        print("✅ Конфигурация обновлена!")
        print(f"   📁 Файл: {config_file}")
        print(f"   🔑 String Session обновлен (длина: {len(string_session)} символов)")
        
        # Также сохраняем в отдельный файл для резервной копии
        backup_file = f"{session_name}_session_backup.txt"
        with open(backup_file, 'w', encoding='utf-8') as f:
            f.write(f"Phone: {phone}\n")
            f.write(f"API ID: {api_id}\n")
            f.write(f"API Hash: {api_hash}\n")
            f.write(f"Session Name: {session_name}\n")
            f.write(f"Username: @{username}\n")
            f.write(f"Name: {first_name} {last_name}\n".strip())
            f.write(f"ID: {me.id}\n")
            f.write(f"\nString Session:\n{string_session}\n")
        
        print(f"   💾 Резервная копия: {backup_file}\n")
        
        await client.disconnect()
        print("✅ Готово! Аккаунт успешно авторизован и обновлен в конфигурации.\n")
        
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        try:
            await client.disconnect()
        except:
            pass


if __name__ == "__main__":
    asyncio.run(authorize_grishkoff())








