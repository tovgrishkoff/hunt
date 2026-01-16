#!/usr/bin/env python3
"""
Скрипт для авторизации promotion_new_account для просмотра сторис
"""
import asyncio
import json
from pathlib import Path
from telethon import TelegramClient
from telethon.sessions import StringSession

async def authorize_promotion_new_account():
    """Авторизация promotion_new_account"""
    print("🔐 Авторизация promotion_new_account для просмотра сторис")
    
    # Загружаем конфигурацию
    config_file = 'accounts_config_stories.json'
    with open(config_file, 'r', encoding='utf-8') as f:
        accounts = json.load(f)
    
    # Находим promotion_new_account
    account = None
    for acc in accounts:
        if acc['session_name'] == 'promotion_new_account':
            account = acc
            break
    
    if not account:
        print("❌ Аккаунт promotion_new_account не найден в конфигурации")
        return
    
    phone = account['phone']
    api_id = account['api_id']
    api_hash = account['api_hash']
    session_name = account['session_name']
    
    print(f"📱 Авторизуем: {session_name} ({phone})")
    print(f"🔑 API ID: {api_id}")
    
    # Создаем клиент с StringSession
    session = StringSession()
    client = TelegramClient(session, api_id, api_hash)
    
    try:
        await client.connect()
        print("✅ Подключение установлено")
        
        if await client.is_user_authorized():
            print("✅ Аккаунт уже авторизован")
            me = await client.get_me()
            print(f"👤 Авторизован как: {me.first_name} (@{me.username})")
            
            # Получаем string_session
            string_session = client.session.save()
            print(f"\n✅ String Session получен:")
            print(f"{string_session}")
            
            # Сохраняем в файл
            output_file = f"new_session_{session_name}.txt"
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(string_session)
            print(f"\n💾 String Session сохранен в: {output_file}")
            
            # Обновляем конфиг
            account['string_session'] = string_session
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(accounts, f, ensure_ascii=False, indent=2)
            print(f"✅ Конфиг {config_file} обновлен")
            
        else:
            print("📲 Отправка кода авторизации...")
            await client.send_code_request(phone)
            
            code = input("📝 Введите код из Telegram: ").strip()
            
            try:
                await client.sign_in(phone, code)
                print("✅ Авторизация успешна!")
                
                me = await client.get_me()
                print(f"👤 Авторизован как: {me.first_name} (@{me.username})")
                
                # Получаем string_session
                string_session = client.session.save()
                print(f"\n✅ String Session получен:")
                print(f"{string_session}")
                
                # Сохраняем в файл
                output_file = f"new_session_{session_name}.txt"
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(string_session)
                print(f"\n💾 String Session сохранен в: {output_file}")
                
                # Обновляем конфиг
                account['string_session'] = string_session
                with open(config_file, 'w', encoding='utf-8') as f:
                    json.dump(accounts, f, ensure_ascii=False, indent=2)
                print(f"✅ Конфиг {config_file} обновлен")
                
            except Exception as e:
                if "PASSWORD_HASH_INVALID" in str(e) or "password" in str(e).lower():
                    password = input("🔒 Введите пароль 2FA: ").strip()
                    await client.sign_in(password=password)
                    print("✅ Авторизация с 2FA успешна!")
                    
                    me = await client.get_me()
                    print(f"👤 Авторизован как: {me.first_name} (@{me.username})")
                    
                    # Получаем string_session
                    string_session = client.session.save()
                    print(f"\n✅ String Session получен:")
                    print(f"{string_session}")
                    
                    # Сохраняем в файл
                    output_file = f"new_session_{session_name}.txt"
                    with open(output_file, 'w', encoding='utf-8') as f:
                        f.write(string_session)
                    print(f"\n💾 String Session сохранен в: {output_file}")
                    
                    # Обновляем конфиг
                    account['string_session'] = string_session
                    with open(config_file, 'w', encoding='utf-8') as f:
                        json.dump(accounts, f, ensure_ascii=False, indent=2)
                    print(f"✅ Конфиг {config_file} обновлен")
                else:
                    print(f"❌ Ошибка авторизации: {e}")
                    raise
    
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.disconnect()
        print("\n🔌 Отключено")

if __name__ == "__main__":
    asyncio.run(authorize_promotion_new_account())

