#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Создание новых StringSession для аккаунтов Lexus с обновлением конфига и БД.

Делает:
1. Интерактивную переавторизацию (код из Telegram/SMS, при необходимости 2FA).
2. Обновление string_session в accounts_config.json (по session_name).
3. Обновление lexus_accounts_config.json (last_updated).
4. Обновление таблицы accounts в БД Lexus (string_session, status=active).

Запуск из корня проекта:
  cd PIAR/telegram_promotion_system_bali
  python3 scripts/create_lexus_sessions.py

С указанием БД Lexus (если не в Docker):
  POSTGRES_HOST=localhost POSTGRES_PORT=5440 python3 scripts/create_lexus_sessions.py
"""
import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError


def load_lexus_allowed() -> set:
    """Загрузить allowed_accounts из lexus_accounts_config.json."""
    for p in [project_root / "lexus_accounts_config.json", Path("/app/lexus_accounts_config.json")]:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    allowed = set(data.get("allowed_accounts", []))
                    if allowed:
                        return allowed
            except Exception as e:
                print(f"⚠️ Ошибка чтения {p}: {e}")
    return set()


def load_accounts_config() -> list:
    """Загрузить accounts_config.json (список аккаунтов с phone, api_id, api_hash, string_session)."""
    for p in [project_root / "accounts_config.json", Path("/app/accounts_config.json")]:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data if isinstance(data, list) else data.get("accounts", [])
            except Exception as e:
                print(f"⚠️ Ошибка чтения {p}: {e}")
    return []


async def get_lexus_accounts_from_db():
    """Загрузить аккаунты Lexus из БД (phone, api_id, api_hash, session_name) для тех, кого нет в конфиге."""
    try:
        from lexus_db.session import AsyncSessionLocal
        from lexus_db.models import Account
        from sqlalchemy import select, and_
    except ImportError as e:
        print(f"⚠️ lexus_db недоступен: {e}")
        return []
    allowed = load_lexus_allowed()
    if not allowed:
        return []
    async with AsyncSessionLocal() as session:
        stmt = select(Account).where(
            and_(Account.session_name.in_(allowed))
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()
        return [
            {
                "session_name": a.session_name,
                "phone": (a.phone or "").strip(),
                "api_id": a.api_id,
                "api_hash": a.api_hash or "",
                "proxy": a.proxy,
                "nickname": getattr(a, "nickname", None) or a.session_name,
            }
            for a in rows
        ]


def parse_proxy(proxy_string):
    if not proxy_string or not isinstance(proxy_string, str):
        return None
    try:
        from urllib.parse import urlparse
        p = urlparse(proxy_string)
        if p.scheme == "socks5":
            return {"proxy_type": "socks5", "addr": p.hostname, "port": p.port, "username": p.username, "password": p.password}
        if p.scheme in ("http", "https"):
            return {"proxy_type": "http", "addr": p.hostname, "port": p.port, "username": p.username, "password": p.password}
    except Exception:
        pass
    return None


async def create_session_for_account(acc: dict) -> dict | None:
    """
    Интерактивная авторизация одного аккаунта.
    Возвращает {"session_name", "string_session", "username", "first_name"} или None.
    """
    session_name = acc.get("session_name", "")
    phone = (acc.get("phone") or "").strip()
    api_id = acc.get("api_id")
    api_hash = (acc.get("api_hash") or "").strip()
    nickname = acc.get("nickname", session_name)
    proxy = parse_proxy(acc.get("proxy"))

    if not phone or not api_id or not api_hash:
        print(f"⚠️ У {session_name} нет phone/api_id/api_hash. Пропуск.")
        return None

    print(f"\n{'='*60}")
    print(f"📱 {nickname} ({session_name}) — {phone}")
    print("=" * 60)

    client = TelegramClient(StringSession(), int(api_id), api_hash, proxy=proxy)
    try:
        await client.connect()
        if await client.is_user_authorized():
            print("✅ Уже авторизован, сохраняем текущую сессию.")
        else:
            print("📲 Отправка кода...")
            await client.send_code_request(phone)
            code = input("✉️ Введите код из Telegram/SMS: ").strip()
            if not code:
                print("❌ Код не введён.")
                await client.disconnect()
                return None
            try:
                await client.sign_in(phone, code)
                print("✅ Код принят.")
            except SessionPasswordNeededError:
                pwd = input("🔒 Введите пароль 2FA: ").strip()
                await client.sign_in(password=pwd)
                print("✅ 2FA успешно.")
            except Exception as e:
                if "password" in str(e).lower() or "two" in str(e).lower():
                    pwd = input("🔒 Введите пароль 2FA: ").strip()
                    await client.sign_in(password=pwd)
                    print("✅ 2FA успешно.")
                else:
                    raise

        me = await client.get_me()
        username = getattr(me, "username", "") or "—"
        first_name = getattr(me, "first_name", "") or "—"
        print(f"   Пользователь: {first_name} (@{username})")

        string_session = client.session.save()
        if not string_session:
            print("❌ Не удалось получить string_session.")
            await client.disconnect()
            return None
        await client.disconnect()
        return {
            "session_name": session_name,
            "string_session": string_session,
            "username": username,
            "first_name": first_name,
        }
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        try:
            await client.disconnect()
        except Exception:
            pass
        return None


def update_accounts_config(session_name: str, string_session: str) -> bool:
    """Обновить string_session в accounts_config.json по session_name."""
    path = project_root / "accounts_config.json"
    if not path.exists():
        print("⚠️ accounts_config.json не найден, пропуск обновления конфига.")
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            print("⚠️ accounts_config.json не список, пропуск.")
            return False
        updated = False
        for item in data:
            if item.get("session_name") == session_name:
                item["string_session"] = string_session
                updated = True
                break
        if updated:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"   ✅ accounts_config.json обновлён для {session_name}")
        else:
            print(f"   ⚠️ {session_name} не найден в accounts_config.json (только БД обновлена)")
        return updated
    except Exception as e:
        print(f"   ❌ Ошибка записи accounts_config.json: {e}")
        return False


def update_lexus_config_file() -> bool:
    """Обновить last_updated в lexus_accounts_config.json."""
    path = project_root / "lexus_accounts_config.json"
    if not path.exists():
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["last_updated"] = datetime.utcnow().strftime("%Y-%m-%d")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print("   ✅ lexus_accounts_config.json обновлён (last_updated)")
        return True
    except Exception as e:
        print(f"   ❌ Ошибка lexus_accounts_config.json: {e}")
        return False


async def update_lexus_db(session_name: str, string_session: str) -> bool:
    """Записать string_session в таблицу accounts БД Lexus."""
    try:
        from lexus_db.session import AsyncSessionLocal
        from lexus_db.models import Account
        from sqlalchemy import select
    except ImportError as e:
        print(f"   ⚠️ lexus_db: {e}")
        return False
    try:
        async with AsyncSessionLocal() as session:
            stmt = select(Account).where(Account.session_name == session_name)
            result = await session.execute(stmt)
            acc = result.scalar_one_or_none()
            if not acc:
                print(f"   ⚠️ Аккаунт {session_name} не найден в БД Lexus.")
                return False
            acc.string_session = string_session
            acc.status = "active"
            await session.commit()
        print(f"   ✅ БД Lexus обновлена для {session_name}")
        return True
    except Exception as e:
        print(f"   ❌ Ошибка БД Lexus: {e}")
        return False


async def main():
    allowed = load_lexus_allowed()
    if not allowed:
        print("❌ В lexus_accounts_config.json нет allowed_accounts.")
        sys.exit(1)

    config_list = load_accounts_config()
    config_by_name = {a["session_name"]: a for a in config_list if isinstance(a, dict) and a.get("session_name")}
    db_accounts = await get_lexus_accounts_from_db()
    db_by_name = {a["session_name"]: a for a in db_accounts}
    accounts = []
    for name in sorted(allowed):
        acc = config_by_name.get(name) or db_by_name.get(name)
        if acc:
            accounts.append(acc)

    if not accounts:
        print("❌ Нет данных об аккаунтах (ни в accounts_config.json, ни в БД Lexus).")
        sys.exit(1)

    print("🔄 Создание новых сессий Lexus")
    print("=" * 60)
    for i, a in enumerate(accounts, 1):
        print(f"  {i}. {a.get('nickname', a.get('session_name'))} ({a.get('session_name')})")
    print("  0. Выход")
    choice = input("\nНомер аккаунта (или несколько через запятую, например 1,2,3): ").strip()
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

    lexus_config_updated = False
    for idx in indices:
        acc = accounts[idx]
        result = await create_session_for_account(acc)
        if not result:
            continue
        session_name = result["session_name"]
        string_session = result["string_session"]
        update_accounts_config(session_name, string_session)
        await update_lexus_db(session_name, string_session)
        lexus_config_updated = True

    if lexus_config_updated:
        update_lexus_config_file()

    print("\n" + "=" * 60)
    print("✅ Готово. Перезапустите контейнеры (lexus-account-manager, lexus-marketer), чтобы подхватить сессии.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
