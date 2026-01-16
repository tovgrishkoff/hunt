#!/usr/bin/env python3
"""
Авторизация promotion_alex_ever с созданием новой сессии
"""

import asyncio
import json
from telethon import TelegramClient
from telethon.sessions import StringSession

async def authorize_alex_ever():
    with open('accounts_config.json', 'r', encoding='utf-8') as f:
        accounts = json.load(f)
    
    # Находим аккаунт
    account = None
    for acc in accounts:
        if acc['session_name'] == 'promotion_alex_ever':
            account = acc
            break
    
    if not account:
        print("❌ Аккаунт promotion_alex_ever не найден")
        return
    
    session_name = account['session_name']
    phone = account['phone']
    api_id = int(account['api_id'])
    api_hash = account['api_hash']
    string_session = account.get('string_session', '')
    
    print(f"\n{'='*60}")
    print(f"📱 Авторизация: {session_name}")
    print(f"   Телефон: {phone}")
    print(f"{'='*60}\n")
    
    # Сначала пробуем использовать string_session для создания новой сессии
    if string_session:
        try:
            print("🔄 Пробуем использовать string_session...")
            string_client = TelegramClient(StringSession(string_session), api_id, api_hash)
            await string_client.connect()
            
            if await string_client.is_user_authorized():
                me = await string_client.get_me()
                username = getattr(me, 'username', 'No username')
                print(f"✅ String session валиден (@{username})")
                
                # Создаем новую файловую сессию из string_session
                print("💾 Создаем файловую сессию...")
                file_client = TelegramClient(f'sessions/{session_name}', api_id, api_hash)
                await file_client.connect()
                
                # Копируем auth_key
                auth_key = string_client.session.auth_key
                if auth_key:
                    file_client.session.auth_key = auth_key
                    file_client.session.save()
                    print("✅ Auth key скопирован")
                
                await string_client.disconnect()
                await file_client.disconnect()
                
                # Проверяем новую сессию
                check_client = TelegramClient(f'sessions/{session_name}', api_id, api_hash)
                await check_client.connect()
                
                if await check_client.is_user_authorized():
                    me = await check_client.get_me()
                    print(f"✅ Файловая сессия создана! (@{me.username})")
                    await check_client.disconnect()
                    return True
                else:
                    print("⚠️ Файловая сессия не авторизована, переходим к обычной авторизации...")
                    await check_client.disconnect()
        except Exception as e:
            print(f"⚠️ Ошибка с string_session: {e}")
            print("📲 Переходим к обычной авторизации...")
    
    # Обычная авторизация
    print("\n📲 Создаем новую сессию...")
    client = TelegramClient(f'sessions/{session_name}', api_id, api_hash)
    
    try:
        print("🔌 Подключение...")
        await asyncio.wait_for(client.connect(), timeout=20.0)
        print("✅ Подключено")
        
        if await client.is_user_authorized():
            me = await client.get_me()
            print(f"✅ Уже авторизован как @{me.username}")
            await client.disconnect()
            return True
        
        print("📨 Отправляем код...")
        await client.send_code_request(phone)
        print(f"✅ Код отправлен на {phone}")
        
        code = input("\n📱 Введите код из SMS/Telegram: ").strip()
        
        try:
            await client.sign_in(phone, code)
            print("✅ Авторизация успешна!")
        except Exception as e:
            error_str = str(e).lower()
            if "password" in error_str or "two-step" in error_str or "2fa" in error_str:
                print("🔐 Требуется пароль 2FA:")
                password = input("Пароль 2FA: ").strip()
                await client.sign_in(password=password)
                print("✅ Авторизация с 2FA успешна!")
            else:
                raise
        
        me = await client.get_me()
        username = getattr(me, 'username', 'No username')
        first_name = getattr(me, 'first_name', 'No name')
        print(f"✅ Авторизован как {first_name} (@{username})")
        
        # Обновляем string_session
        try:
            session_string = client.session.save()
            account['string_session'] = session_string
            account['nickname'] = first_name
            
            with open('accounts_config.json', 'w', encoding='utf-8') as f:
                json.dump(accounts, f, indent=2, ensure_ascii=False)
            print("✅ Конфигурация обновлена!")
        except:
            pass
        
        await client.disconnect()
        return True
        
    except asyncio.TimeoutError:
        print("❌ Таймаут подключения")
        try:
            await client.disconnect()
        except:
            pass
        return False
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        try:
            await client.disconnect()
        except:
            pass
        return False

if __name__ == "__main__":
    asyncio.run(authorize_alex_ever())
