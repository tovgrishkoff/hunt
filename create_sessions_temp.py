#!/usr/bin/env python3
"""
Создание сессий во временной директории
"""

import asyncio
import json
import os
import shutil
from telethon import TelegramClient

async def create_single_session(phone, api_id, api_hash, session_name):
    """Создание одной сессии"""
    
    # Используем временную директорию
    session_path = f'temp_sessions/{session_name}'
    
    print(f"\n{'='*70}")
    print(f"🔐 Создание сессии: {session_name}")
    print(f"📱 Телефон: {phone}")
    print(f"{'='*70}\n")
    
    try:
        # Создаем клиент
        client = TelegramClient(session_path, api_id, api_hash)
        
        # Подключаемся и авторизуемся
        await client.connect()
        
        if not await client.is_user_authorized():
            print(f"📞 Запрашиваем код для {phone}...")
            await client.send_code_request(phone)
            
            # Просим пользователя ввести код
            code = input(f"💬 Введите код из Telegram для {phone}: ").strip()
            
            try:
                await client.sign_in(phone, code)
            except Exception as e:
                error_str = str(e).lower()
                if 'password' in error_str or '2fa' in error_str or 'two' in error_str:
                    # Нужен пароль 2FA
                    password = input(f"🔒 Введите пароль 2FA: ").strip()
                    await client.sign_in(password=password)
                else:
                    raise
        
        # Проверяем авторизацию
        if await client.is_user_authorized():
            me = await client.get_me()
            print(f"\n✅ УСПЕШНО!")
            print(f"   Имя: {me.first_name} {me.last_name or ''}")
            print(f"   ID: {me.id}")
            print(f"   Username: @{me.username if me.username else 'не установлен'}")
        else:
            print(f"❌ Не удалось авторизоваться")
            await client.disconnect()
            return False
        
        await client.disconnect()
        
        # Копируем сессию в основную директорию
        temp_file = f'{session_path}.session'
        final_file = f'sessions/{session_name}.session'
        
        if os.path.exists(temp_file):
            shutil.copy2(temp_file, final_file)
            print(f"   📁 Скопирована в: {final_file}")
        
        return True
        
    except Exception as e:
        print(f"❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    print("\n" + "="*70)
    print("🤖 СОЗДАНИЕ СЕССИЙ ДЛЯ АВТООТВЕТЧИКА")
    print("="*70)
    
    # Проверяем и создаем директории
    for dir_name in ['temp_sessions', 'sessions']:
        if not os.path.exists(dir_name):
            os.makedirs(dir_name, mode=0o777)
            print(f"✅ Создана директория {dir_name}/")
    
    # Загружаем конфигурацию
    with open('accounts_config_autoresponder.json', 'r') as f:
        accounts = json.load(f)
    
    print(f"\n📋 Найдено аккаунтов: {len(accounts)}")
    print("\n⚠️  ВАЖНО:")
    print("   • Убедитесь, что у вас есть доступ к этим номерам")
    print("   • Telegram отправит 5-значный код на каждый номер")
    print("   • Если включена 2FA, потребуется пароль\n")
    
    input("Нажмите Enter для начала...")
    
    success_count = 0
    
    for idx, account in enumerate(accounts, 1):
        print(f"\n{'─'*70}")
        print(f"📱 АККАУНТ {idx}/{len(accounts)}")
        print(f"{'─'*70}")
        
        result = await create_single_session(
            phone=account['phone'],
            api_id=account['api_id'],
            api_hash=account['api_hash'],
            session_name=account['session_name']
        )
        
        if result:
            success_count += 1
        
        # Небольшая пауза между аккаунтами
        if idx < len(accounts):
            await asyncio.sleep(2)
    
    print("\n" + "="*70)
    print(f"{'✅' if success_count == len(accounts) else '⚠️'} ЗАВЕРШЕНО")
    print(f"   Успешно: {success_count}/{len(accounts)}")
    print("="*70)
    
    if success_count == len(accounts):
        print("\n🎉 Все сессии созданы успешно!")
        print("\n📝 Следующие шаги:")
        print("   1. Запустите: docker-compose up -d autoresponder")
        print("   2. Проверьте: docker logs telegram-autoresponder -f")
        
        # Очищаем временную директорию
        print("\n🧹 Очистка временных файлов...")
        if os.path.exists('temp_sessions'):
            shutil.rmtree('temp_sessions')
            print("   ✅ Временные файлы удалены")
    else:
        print("\n⚠️  Не все сессии созданы. Проверьте ошибки выше.")
    
    print("")

if __name__ == "__main__":
    asyncio.run(main())
















