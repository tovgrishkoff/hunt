#!/usr/bin/env python3
"""
Обновление string_session для аккаунтов Bali, у которых сессия инвалидирована
(ошибка "authorization key was used under two different IP addresses").

Использование:
  Из корня проекта (с настроенным .env или DATABASE_URL для Бали):
    python3 scripts/update_string_sessions_bali.py

  Или с явным URL БД:
    DATABASE_URL=postgresql://telegram_user_bali:telegram_password_bali@localhost:5438/telegram_promotion_bali \\
    python3 scripts/update_string_sessions_bali.py

По очереди запрашивает код из Telegram/SMS для каждого выбранного аккаунта,
создаёт новую StringSession и записывает её в accounts.string_session.
Авторизация выполняется БЕЗ прокси, чтобы избежать конфликта IP.
"""
import asyncio
import os
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from telethon import TelegramClient
from telethon.sessions import StringSession


# Аккаунты, у которых инвалидирована сессия (по логам account-manager)
DEFAULT_SESSION_NAMES = [
    "promotion_anna_truncher",
    "promotion_lev_moiseev",
    "promotion_lera_katina",
]


def get_accounts_from_db(session_names: list[str]):
    """Загрузить аккаунты из БД по session_name."""
    from shared.database.session import SessionLocal, init_db
    from shared.database.models import Account

    init_db()
    db = SessionLocal()
    try:
        accounts = (
            db.query(Account)
            .filter(Account.session_name.in_(session_names), Account.status == "active")
            .all()
        )
        return [
            {
                "session_name": a.session_name,
                "phone": a.phone or "",
                "api_id": a.api_id,
                "api_hash": a.api_hash or "",
                "nickname": a.nickname or a.session_name,
            }
            for a in accounts
        ]
    finally:
        db.close()


def update_db_string_session(session_name: str, string_session: str) -> bool:
    """Записать string_session в БД для аккаунта."""
    try:
        from shared.database.session import SessionLocal, init_db
        from shared.database.models import Account

        init_db()
        db = SessionLocal()
        try:
            account = db.query(Account).filter(Account.session_name == session_name).first()
            if not account:
                print(f"⚠️ Аккаунт {session_name} не найден в БД.")
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


async def authorize_account(account_data: dict) -> Optional[str]:
    """
    Переавторизация одного аккаунта (без прокси).
    Возвращает новую string_session или None.
    """
    phone = (account_data.get("phone") or "").strip()
    api_id = account_data.get("api_id")
    api_hash = account_data.get("api_hash") or ""
    session_name = account_data.get("session_name", "")
    nickname = account_data.get("nickname", session_name)

    if not phone or not api_id or not api_hash:
        print(f"⚠️ У аккаунта {session_name} в БД не заполнены phone/api_id/api_hash. Пропуск.")
        return None

    print(f"\n{'='*80}")
    print(f"📱 Переавторизация: {nickname} ({phone})")
    print(f"   Session: {session_name}")
    print("   ⚠️ Подключение БЕЗ прокси (чтобы не было конфликта IP)")
    print(f"{'='*80}\n")

    session_obj = StringSession()
    client = TelegramClient(session_obj, int(api_id), api_hash)

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
            print("✅ Уже авторизован (текущая сессия валидна). Сохраняем её в БД.")
        else:
            print("📲 Отправляем код на номер / в Telegram...")
            result = await client.send_code_request(phone)
            print("✅ Код отправлен!")
            result_type_str = str(result.type).lower()
            if "telegram" in result_type_str or "app" in result_type_str:
                print("   Код придёт в приложение Telegram на этом номере.")
            elif "sms" in result_type_str:
                print("   Код отправлен по SMS.")
            print()

            code = input("✉️ Введите код из Telegram/SMS: ").strip()
            if not code:
                print("❌ Код не введён.")
                await client.disconnect()
                return None

            try:
                await client.sign_in(phone, code)
                print("✅ Код подтверждён.")
            except Exception as e:
                error_str = str(e)
                if "PASSWORD_HASH_INVALID" in error_str or "two-step" in error_str.lower():
                    password = input("🔐 Введите пароль 2FA: ").strip()
                    if password:
                        await client.sign_in(password=password)
                        print("✅ Авторизация с 2FA успешна.")
                    else:
                        print("❌ Пароль не введён.")
                        await client.disconnect()
                        return None
                else:
                    print(f"❌ Ошибка входа: {e}")
                    await client.disconnect()
                    return None

        me = await client.get_me()
        username = getattr(me, "username", "") or "—"
        first_name = getattr(me, "first_name", "") or "—"
        print(f"   Пользователь: {first_name} (@{username}), ID: {me.id}")

        session_string = client.session.save()
        if not session_string:
            print("❌ Не удалось получить string_session.")
            await client.disconnect()
            return None

        out_file = PROJECT_ROOT / f"new_session_{session_name}.txt"
        out_file.write_text(
            f"Session: {session_name}\n"
            f"Phone: {phone}\n"
            f"User: @{username}\n\n"
            f"String Session:\n{session_string}\n",
            encoding="utf-8",
        )
        print(f"✅ Сессия сохранена в файл: {out_file.name}")

        await client.disconnect()
        return session_string

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        try:
            await client.disconnect()
        except Exception:
            pass
        return None


def main() -> None:
    print("🔄 Обновление string_session для аккаунтов Bali (сессия с двух IP)")
    print("=" * 80)

    accounts = get_accounts_from_db(DEFAULT_SESSION_NAMES)
    if not accounts:
        print("⚠️ В БД не найдены активные аккаунты с session_name из списка:")
        print("   ", ", ".join(DEFAULT_SESSION_NAMES))
        print("\nПроверьте DATABASE_URL и наличие записей в accounts.")
        sys.exit(1)

    missing_phone = [a["session_name"] for a in accounts if not (a.get("phone") or "").strip()]
    if missing_phone:
        print("⚠️ У следующих аккаунтов в БД не заполнен phone (нужен для отправки кода):")
        for s in missing_phone:
            print(f"   - {s}")
        accounts = [a for a in accounts if (a.get("phone") or "").strip()]

    if not accounts:
        print("Заполните phone в таблице accounts и запустите скрипт снова.")
        sys.exit(1)

    print("\nВыберите аккаунт для переавторизации:")
    for i, acc in enumerate(accounts, 1):
        print(f"  {i}. {acc['nickname']} ({acc['session_name']}) — {acc['phone']}")
    print(f"  0. Выход")
    print()
    choice = input("Введите номер (или несколько через запятую, например 1,2,3): ").strip()

    if choice == "0" or not choice:
        print("Выход.")
        return

    indices = []
    for part in choice.replace(" ", "").split(","):
        if part.isdigit():
            idx = int(part)
            if 1 <= idx <= len(accounts):
                indices.append(idx - 1)
    if not indices:
        print("❌ Неверный ввод.")
        sys.exit(1)

    updated = 0
    for idx in indices:
        acc = accounts[idx]
        session_string = asyncio.run(authorize_account(acc))
        if session_string and update_db_string_session(acc["session_name"], session_string):
            updated += 1

    print("\n" + "=" * 80)
    print(f"✅ Обновлено аккаунтов: {updated} из {len(indices)}")
    print("После обновления перезапустите account-manager, чтобы подхватить новые сессии.")
    print("=" * 80)


if __name__ == "__main__":
    main()
