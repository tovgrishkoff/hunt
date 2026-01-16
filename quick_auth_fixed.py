#!/usr/bin/env python3
"""
Быстрая авторизация БЕЗ файловых сессий (только StringSession)
"""
import asyncio
import json
import shutil
from datetime import datetime
from telethon import TelegramClient
from telethon.sessions import StringSession

async def authorize_account(account_info):
    """Авторизация одного аккаунта"""
    phone = account_info['phone']
    api_id = int(account_info['api_id'])
    api_hash = account_info['api_hash']
    session_name = account_info['session_name']
    
    print(f"\n{'='*60}")
    print(f"📱 Аккаунт: {session_name}")
    print(f"📞 Телефон: {phone}")
    print(f"{'='*60}\n")
    
    # Создаем клиент с пустой StringSession
    client = TelegramClient(StringSession(), api_id, api_hash)
    
    try:
        await client.connect()
        print("✅ Подключение к Telegram установлено")
        
        # Проверяем авторизацию
        if not await client.is_user_authorized():
            print("📲 Отправляем код авторизации на", phone)
            await client.send_code_request(phone)
            
            # Запрашиваем код
            code = input("👉 Введите код из SMS/Telegram (5 цифр): ").strip()
            
            try:
                await client.sign_in(phone, code)
                print("✅ Код принят!")
            except Exception as e:
                error_str = str(e)
                # Проверяем нужен ли 2FA пароль
                if "SessionPasswordNeeded" in error_str or "password" in error_str.lower():
                    print("🔐 Требуется пароль двухфакторной аутентификации")
                    password = input("👉 Введите пароль 2FA: ").strip()
                    await client.sign_in(password=password)
                    print("✅ Авторизация с 2FA успешна!")
                else:
                    raise
        else:
            print("✅ Аккаунт уже авторизован")
        
        # Получаем информацию о пользователе
        me = await client.get_me()
        username = me.username or "нет username"
        first_name = me.first_name or "Unknown"
        
        print(f"\n✅ Успешно авторизован!")
        print(f"   Имя: {first_name}")
        print(f"   Username: @{username}")
        print(f"   ID: {me.id}")
        
        # Получаем string session
        string_session = client.session.save()
        print(f"✅ String session создан (длина: {len(string_session)} символов)")
        
        await client.disconnect()
        
        # Обновляем конфиг
        account_info['string_session'] = string_session
        account_info['nickname'] = first_name
        
        return True
        
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        try:
            await client.disconnect()
        except:
            pass
        return False

async def main():
    """Основная функция"""
    print("\n🚀 АВТОРИЗАЦИЯ TELEGRAM АККАУНТОВ (упрощенная версия)")
    print("="*60)
    
    # Загружаем конфигурацию
    try:
        with open('accounts_config.json', 'r', encoding='utf-8') as f:
            accounts = json.load(f)
    except FileNotFoundError:
        print("❌ Файл accounts_config.json не найден!")
        return
    
    print(f"\n📋 Найдено аккаунтов: {len(accounts)}")
    for i, acc in enumerate(accounts, 1):
        print(f"   {i}. {acc['session_name']} ({acc['phone']})")
    
    print("\n" + "="*60)
    print("⚡ ВАЖНО: Подготовьте телефоны для получения кодов!")
    print("="*60)
    
    input("\nНажмите Enter чтобы начать... ")
    
    success_count = 0
    updated_accounts = []
    
    # Авторизуем каждый аккаунт
    for account in accounts:
        result = await authorize_account(account)
        if result:
            success_count += 1
            updated_accounts.append(account)
        else:
            # Даже если не удалось - добавляем старую версию
            updated_accounts.append(account)
        
        print("\n" + "-"*60)
    
    # Сохраняем обновленную конфигурацию
    if success_count > 0:
        # Backup старого конфига
        backup_name = f"accounts_config.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        shutil.copy('accounts_config.json', backup_name)
        print(f"\n💾 Backup создан: {backup_name}")
        
        # Сохраняем новый конфиг
        with open('accounts_config.json', 'w', encoding='utf-8') as f:
            json.dump(updated_accounts, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Конфигурация обновлена!")
        print(f"   Успешно авторизовано: {success_count}/{len(accounts)} аккаунтов")
        
        print("\n" + "="*60)
        print("🎉 ГОТОВО! Теперь перезапустите Docker контейнер:")
        print("="*60)
        print("\n  cd /home/tovgrishkoff/PIAR/telegram_promotion_system")
        print("  docker-compose down")
        print("  docker-compose up --build -d")
        print("  docker logs telegram-promotion-advanced -f")
        print()
    else:
        print("\n❌ Не удалось авторизовать ни один аккаунт")

if __name__ == "__main__":
    asyncio.run(main())


















