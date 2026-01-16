#!/usr/bin/env python3
import asyncio
import json
from telethon import TelegramClient
from telethon.sessions import StringSession

async def create_new_session(phone, api_id, api_hash, session_name):
    """Создание новой сессии для аккаунта"""
    print(f"\n📱 Создаем сессию для {session_name} ({phone})")
    
    # Создаем временный клиент для авторизации
    client = TelegramClient(session_name, api_id, api_hash)
    
    try:
        await client.connect()
        print("✅ Подключение установлено")
        
        # Проверяем, авторизован ли уже
        if await client.is_user_authorized():
            print("✅ Аккаунт уже авторизован")
            me = await client.get_me()
            username = getattr(me, 'username', 'No username')
            print(f"   Пользователь: {username}")
        else:
            print("📲 Отправляем код авторизации...")
            await client.send_code_request(phone)
            
            # Запрашиваем код у пользователя
            code = input("Введите код из SMS/Telegram: ")
            
            try:
                await client.sign_in(phone, code)
                print("✅ Авторизация успешна!")
            except Exception as e:
                print(f"❌ Ошибка авторизации: {e}")
                # Попробуем с паролем 2FA
                if "PASSWORD_HASH_INVALID" in str(e) or "two-step" in str(e).lower():
                    password = input("Введите пароль 2FA: ")
                    await client.sign_in(password=password)
                    print("✅ Авторизация с 2FA успешна!")
        
        # Получаем информацию о пользователе
        me = await client.get_me()
        username = getattr(me, 'username', 'No username')
        first_name = getattr(me, 'first_name', 'No name')
        
        print(f"✅ Пользователь: {first_name} (@{username})")
        
        # Создаем string session
        session_string = client.session.save()
        print(f"✅ String session создан")
        
        # Сохраняем сессию в файл
        client.session.save(f"sessions/{session_name}")
        print(f"✅ Файловая сессия сохранена в sessions/{session_name}")
        
        await client.disconnect()
        
        return {
            'phone': phone,
            'api_id': api_id,
            'api_hash': api_hash,
            'session_name': session_name,
            'nickname': first_name,
            'bio': f"Пользователь {session_name}",
            'string_session': session_string
        }
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        await client.disconnect()
        return None

async def main():
    """Основная функция для создания сессий"""
    print("🚀 Создание новых сессий для аккаунтов")
    
    # Загружаем существующую конфигурацию
    try:
        with open('accounts_config.json', 'r', encoding='utf-8') as f:
            accounts = json.load(f)
    except FileNotFoundError:
        print("❌ Файл accounts_config.json не найден")
        return
    
    new_accounts = []
    
    for account in accounts:
        print(f"\n{'='*50}")
        print(f"Аккаунт: {account['session_name']}")
        print(f"Телефон: {account['phone']}")
        
        choice = input("Создать новую сессию для этого аккаунта? (y/n/s - skip): ").lower()
        
        if choice == 'y':
            new_session = await create_new_session(
                account['phone'],
                account['api_id'],
                account['api_hash'],
                account['session_name']
            )
            
            if new_session:
                new_accounts.append(new_session)
                print("✅ Сессия успешно создана!")
            else:
                print("❌ Не удалось создать сессию")
                # Добавляем старую конфигурацию
                new_accounts.append(account)
        elif choice == 's':
            print("⏭️ Пропускаем аккаунт")
            continue
        else:
            print("⏭️ Используем старую сессию")
            new_accounts.append(account)
    
    # Сохраняем обновленную конфигурацию
    if new_accounts:
        with open('accounts_config.json', 'w', encoding='utf-8') as f:
            json.dump(new_accounts, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Конфигурация сохранена: {len(new_accounts)} аккаунтов")
        print("🎉 Готово! Теперь можно запускать систему")
    else:
        print("\n❌ Не создано ни одной новой сессии")

if __name__ == "__main__":
    asyncio.run(main())



