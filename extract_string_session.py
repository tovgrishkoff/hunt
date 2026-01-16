#!/usr/bin/env python3
"""
Извлечение string_session из файла сессии и обновление конфига
"""
import asyncio
import json
import os
from telethon import TelegramClient
from telethon.sessions import StringSession

async def extract_string_session():
    """Извлечение string_session из существующего файла сессии"""
    print("="*70)
    print("🔐 ИЗВЛЕЧЕНИЕ STRING_SESSION ИЗ ФАЙЛА СЕССИИ")
    print("="*70)
    
    config_file = 'accounts_config_stories.json'
    session_file = 'sessions_stories/stories_promotion_new_account.session'
    
    if not os.path.exists(config_file):
        print(f"❌ Файл {config_file} не найден!")
        return
    
    if not os.path.exists(session_file):
        print(f"❌ Файл сессии {session_file} не найден!")
        return
    
    # Загружаем конфигурацию
    with open(config_file, 'r', encoding='utf-8') as f:
        accounts = json.load(f)
    
    # Находим аккаунт
    account = None
    for acc in accounts:
        if acc['session_name'] == 'promotion_new_account':
            account = acc
            break
    
    if not account:
        print("❌ Аккаунт promotion_new_account не найден!")
        return
    
    api_id = int(account['api_id'])
    api_hash = account['api_hash']
    
    print(f"\n📱 Аккаунт: promotion_new_account")
    print(f"🔑 API ID: {api_id}")
    print(f"📁 Файл сессии: {session_file}")
    print()
    
    # Создаем клиент из файла сессии
    client = TelegramClient(session_file, api_id, api_hash)
    
    try:
        await client.connect()
        print("✅ Подключение установлено")
        
        if not await client.is_user_authorized():
            print("❌ Сессия не авторизована! Нужна переавторизация.")
            await client.disconnect()
            return
        
        # Получаем информацию о пользователе
        me = await client.get_me()
        username = getattr(me, 'username', 'No username')
        first_name = getattr(me, 'first_name', 'No name')
        
        print(f"✅ Авторизован как: {first_name} (@{username})")
        
        # Извлекаем string_session - используем метод экспорта сессии
        # Создаем новый клиент с StringSession и авторизуем его используя существующую сессию
        from telethon.sessions import StringSession
        
        # Получаем данные из текущей сессии
        if not hasattr(client.session, 'auth_key') or not client.session.auth_key:
            print("❌ Не удалось получить auth_key из сессии!")
            await client.disconnect()
            return
        
        # Создаем StringSession и устанавливаем DC и auth_key
        string_session_obj = StringSession()
        string_session_obj.set_dc(
            client.session.dc_id,
            client.session.server_address,
            client.session.auth_key
        )
        
        # Получаем user_id и устанавливаем его напрямую в сессию
        me = await client.get_me()
        if me and hasattr(string_session_obj, '_dc_id'):
            # Устанавливаем user_id через внутренний атрибут
            string_session_obj._entities[me.id] = me
        
        # Сохраняем string_session
        try:
            string_session = string_session_obj.save()
        except Exception as e:
            print(f"⚠️ Ошибка при сохранении StringSession: {e}")
            # Пробуем альтернативный метод - используем встроенный экспорт
            string_session = client.session.save() if hasattr(client.session, 'save') else None
            if not string_session or len(string_session) == 0:
                # Последний вариант - создаем через новый клиент
                temp_client = TelegramClient(StringSession(), api_id, api_hash)
                await temp_client.connect()
                # Копируем auth_key
                if hasattr(temp_client.session, 'set_dc'):
                    temp_client.session.set_dc(client.session.dc_id, client.session.server_address, client.session.auth_key)
                string_session = temp_client.session.save()
                await temp_client.disconnect()
        
        print(f"📝 String session длина: {len(string_session)} символов")
        if len(string_session) > 0:
            print(f"📝 Первые 50 символов: {string_session[:50]}...")
        
        # Обновляем конфигурацию
        account['string_session'] = string_session
        account['nickname'] = first_name
        
        # Сохраняем обновленную конфигурацию
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(accounts, f, indent=2, ensure_ascii=False)
        
        # Проверяем, что сохранилось
        with open(config_file, 'r', encoding='utf-8') as f:
            saved_accounts = json.load(f)
            saved_account = next((a for a in saved_accounts if a['session_name'] == 'promotion_new_account'), None)
            if saved_account and saved_account.get('string_session') and saved_account['string_session'] != 'null':
                print(f"\n✅ Конфигурация обновлена в {config_file}")
                print("✅ String session извлечен и сохранен")
            else:
                print(f"\n❌ ОШИБКА: string_session не сохранился!")
                print(f"   Значение: {saved_account.get('string_session') if saved_account else 'аккаунт не найден'}")
        
        await client.disconnect()
        
        print("\n" + "="*70)
        print("✅ ГОТОВО!")
        print("="*70)
        print("\n📋 Перезапустите контейнер:")
        print("   docker-compose restart stories-viewer")
        print()
        
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(extract_string_session())

