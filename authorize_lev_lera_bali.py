#!/usr/bin/env python3
"""
Авторизация аккаунтов Lev Moiseev и Lera Katina для системы Bali (БЕЗ прокси).

Перед запуском добавьте аккаунты в БД:
  python3 scripts/add_lev_lera_bali_accounts.py

Запуск из корня проекта:
  python3 authorize_lev_lera_bali.py

После ввода кода из Telegram/SMS сессия сохраняется в файл и в БД.
"""
import asyncio
import os
import sys
from pathlib import Path

# Корень проекта для shared
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from telethon import TelegramClient
from telethon.sessions import StringSession

# Lev Moiseev @levmoives, Lera Katina @lerakatina
ACCOUNTS = {
    "1": {
        "phone": "+380639597698",
        "api_id": 33654773,
        "api_hash": "5698a681018432cb744a204f41ef5182",
        "session_name": "promotion_lev_moiseev",
        "nickname": "Lev Moiseev",
    },
    "2": {
        "phone": "+380937392435",
        "api_id": 30513372,
        "api_hash": "1d275ee48d6e35ed6fa9df5b0d642769",
        "session_name": "promotion_lera_katina",
        "nickname": "Lera Katina",
    },
}


def update_db_string_session(session_name: str, string_session: str) -> bool:
    """Записать string_session в БД для аккаунта."""
    try:
        from shared.database.session import SessionLocal, init_db
        from shared.database.models import Account

        init_db()
        db = SessionLocal()
        try:
            account = db.query(Account).filter(
                Account.session_name == session_name
            ).first()
            if not account:
                print(f"⚠️ Аккаунт {session_name} не найден в БД. Добавьте его: python3 scripts/add_lev_lera_bali_accounts.py")
                return False
            account.string_session = string_session
            account.status = "active"
            db.commit()
            print(f"✅ БД обновлена: {session_name} (string_session записан)")
            return True
        finally:
            db.close()
    except Exception as e:
        print(f"❌ Ошибка обновления БД: {e}")
        return False


async def authorize_account(account_data: dict) -> str | None:
    """Авторизация одного аккаунта (без прокси). Возвращает string_session или None."""
    phone = account_data["phone"]
    api_id = account_data["api_id"]
    api_hash = account_data["api_hash"]
    session_name = account_data["session_name"]

    print(f"\n{'='*80}")
    print(f"📱 Авторизация: {account_data['nickname']} ({phone})")
    print(f"{'='*80}")
    print(f"Session: {session_name}")
    print("⚠️ БЕЗ ПРОКСИ")
    print()

    os.makedirs("sessions", exist_ok=True)
    # Используем StringSession, чтобы session.save() вернул строку для БД (файловая сессия возвращает None)
    session_obj = StringSession()
    client = TelegramClient(session_obj, api_id, api_hash)

    try:
        print("🔐 Подключение к Telegram...")
        try:
            await asyncio.wait_for(client.connect(), timeout=30.0)
            print("✅ Подключение установлено")
        except asyncio.TimeoutError:
            print("❌ Таймаут подключения (30 сек)")
            await client.disconnect()
            return None
        except Exception as e:
            print(f"❌ Ошибка подключения: {e}")
            await client.disconnect()
            return None

        if await client.is_user_authorized():
            print("✅ Уже авторизован!")
            me = await client.get_me()
            username = getattr(me, "username", "No username")
            print(f"   Пользователь: @{username}")
        else:
            print("📲 Отправляем код...")
            result = await client.send_code_request(phone)
            print("=" * 80)
            print("✅ Код отправлен!")
            print(f"Тип доставки: {result.type}")
            print("=" * 80)
            result_type_str = str(result.type).lower()
            if "telegram" in result_type_str or "app" in result_type_str:
                print("⚠️ Код в Telegram на уже авторизованное устройство!")
            elif "sms" in result_type_str:
                print("📱 Код отправлен по SMS")
            print("   Введите код в течение минуты")
            print()

            code = input("✉️ Введите код из Telegram/SMS: ").strip()
            if not code:
                print("❌ Код не введен!")
                await client.disconnect()
                return None

            try:
                await client.sign_in(phone, code)
                print("✅ Код подтверждён!")
            except Exception as e:
                error_str = str(e)
                if "PASSWORD_HASH_INVALID" in error_str or "two-step" in error_str.lower():
                    password = input("🔐 Введите пароль 2FA: ").strip()
                    if password:
                        await client.sign_in(password=password)
                        print("✅ Авторизация с 2FA успешна!")
                    else:
                        print("❌ Пароль не введён!")
                        await client.disconnect()
                        return None
                else:
                    print(f"❌ Ошибка: {e}")
                    await client.disconnect()
                    return None

        me = await client.get_me()
        username = getattr(me, "username", "No username")
        first_name = getattr(me, "first_name", "No name")
        print(f"\n✅ Пользователь: {first_name} (@{username}), ID: {me.id}")

        session_string = client.session.save()  # StringSession.save() возвращает строку

        filename = f"new_account_{session_name}_session.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"Phone: {phone}\n")
            f.write(f"API ID: {api_id}\n")
            f.write(f"Session Name: {session_name}\n")
            f.write(f"Username: @{username}\n")
            f.write(f"User ID: {me.id}\n")
            f.write(f"\nString Session:\n{session_string}\n")
        print(f"✅ Сессия сохранена в файл: {filename}")
        print(f"✅ Файловая сессия: sessions/{session_name}.session")

        await client.disconnect()
        return session_string

    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        try:
            await client.disconnect()
        except Exception:
            pass
        return None


def main() -> None:
    print("🚀 Авторизация Lev Moiseev и Lera Katina для Bali")
    print("=" * 80)
    print("\nВыберите аккаунт:")
    for key, acc in ACCOUNTS.items():
        print(f"  {key}. {acc['nickname']} ({acc['phone']})")
    print()
    choice = input("Введите номер (1 или 2): ").strip()

    if choice not in ACCOUNTS:
        print(f"❌ Неверный выбор: {choice}")
        return

    account = ACCOUNTS[choice]
    print(f"\n✅ Выбран: {account['nickname']}")

    session_string = asyncio.run(authorize_account(account))

    if session_string:
        print(f"\n{'='*80}")
        print(f"✅ Сессия создана для {account['nickname']}!")
        print("=" * 80)
        if update_db_string_session(account["session_name"], session_string):
            print("✅ Аккаунт готов к использованию в системе Bali.")
        else:
            print("⚠️ Сессия сохранена в файл. Добавьте string_session в БД вручную.")
    else:
        print(f"\n❌ Не удалось авторизовать {account['nickname']}")


if __name__ == "__main__":
    main()
