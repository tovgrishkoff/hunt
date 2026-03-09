#!/usr/bin/env python3
import asyncio
import json
import uuid
from pathlib import Path
from telethon import TelegramClient
from telethon.sessions import StringSession


# Глобальный список Lexus-аккаунтов (загружаем один раз)
LEXUS_ALLOWED_ACCOUNTS = set()

lexus_config_path = Path("lexus_accounts_config.json")
if lexus_config_path.exists():
    try:
        with lexus_config_path.open("r", encoding="utf-8") as f:
            _cfg = json.load(f)
        LEXUS_ALLOWED_ACCOUNTS = set(_cfg.get("allowed_accounts", []))
    except Exception as e:
        print(f"⚠️ Не удалось загрузить lexus_accounts_config.json: {e}")


def _get_session_dir_for_account(session_name: str) -> Path:
    """
    Определяем, куда сохранять файловую сессию:
    - Lexus-аккаунты -> sessions_lexus/
    - остальные -> sessions/
    """
    if session_name in LEXUS_ALLOWED_ACCOUNTS:
        return Path("sessions_lexus")
    return Path("sessions")


async def create_new_session(phone, api_id, api_hash, session_name):
    """Создание новой сессии для аккаунта"""
    print(f"\n📱 Создаем сессию для {session_name} ({phone})")

    # Определяем директорию для сохранения сессии
    session_dir = _get_session_dir_for_account(session_name)
    session_dir.mkdir(exist_ok=True)
    
    # Используем временное имя для авторизации, чтобы избежать блокировок
    temp_session_path = session_dir / f"{session_name}_temp_{uuid.uuid4().hex[:8]}"
    final_session_path = session_dir / session_name
    
    # Удаляем старую сессию, если есть (чтобы избежать блокировок)
    if final_session_path.exists():
        final_session_path.unlink()
    if (final_session_path.parent / f"{session_name}.session-journal").exists():
        (final_session_path.parent / f"{session_name}.session-journal").unlink()

    # Создаем временный клиент для авторизации (используем StringSession в памяти)
    from telethon.sessions import StringSession
    client = TelegramClient(StringSession(), api_id, api_hash)
    
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
        user_id = me.id
        
        print(f"✅ Пользователь: {first_name} (@{username})")
        
        # Получаем string session
        session_string = client.session.save()
        print(f"✅ String session создан")
        
        # Получаем данные авторизации из текущей сессии
        auth_key = getattr(client.session, 'auth_key', None)
        dc_id = getattr(client.session, 'dc_id', None) or 2
        server_address = getattr(client.session, 'server_address', None) or '149.154.167.50'
        port = getattr(client.session, 'port', None) or 443
        
        if not auth_key:
            raise Exception("Не удалось получить auth_key из сессии")
        
        # Закрываем StringSession клиент
        await client.disconnect()
        
        # Создаем SQLiteSession и устанавливаем данные напрямую
        from telethon.sessions import SQLiteSession
        sqlite_session = SQLiteSession(str(final_session_path))
        sqlite_session.set_dc(dc_id, server_address, port)
        sqlite_session.auth_key = auth_key
        
        # Устанавливаем ID пользователя (из me.id)
        sqlite_session._self_id = user_id
        
        # Сохраняем файловую сессию
        sqlite_session.save()
        
        print(f"✅ Файловая сессия сохранена в {final_session_path}")
        
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
        try:
            await client.disconnect()
        except:
            pass
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



