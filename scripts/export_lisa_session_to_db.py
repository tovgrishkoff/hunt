#!/usr/bin/env python3
"""
Однократный скрипт: экспорт file-сессии promotion_lisa_soak в StringSession
и запись в БД (accounts.string_session). После этого секретарь подхватит @soakqt.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from telethon import TelegramClient
from telethon.sessions import StringSession
from shared.database.session import SessionLocal, init_db
from shared.database.models import Account

SESSION_NAME = "promotion_lisa_soak"
API_ID = 36665934
API_HASH = "0ac3c86e68a3e4eac13bb7c2ab2dff3d"


async def export_file_to_string() -> str | None:
    """Экспорт sessions/promotion_lisa_soak.session в строку."""
    base = Path(__file__).parent.parent
    session_file = base / "sessions" / f"{SESSION_NAME}.session"
    if not session_file.exists():
        print(f"Файл сессии не найден: {session_file}")
        return None
    client = TelegramClient(str(session_file), API_ID, API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        print("Сессия не авторизована.")
        await client.disconnect()
        return None
    s = StringSession()
    port = getattr(client.session, "port", 443)
    s.set_dc(client.session.dc_id, client.session.server_address, port)
    s.auth_key = client.session.auth_key
    out = s.save()
    await client.disconnect()
    return out if out else None


def update_db(string_session: str) -> bool:
    """Обновить string_session в БД для promotion_lisa_soak."""
    init_db()
    db = SessionLocal()
    try:
        account = db.query(Account).filter(Account.session_name == SESSION_NAME).first()
        if not account:
            print(f"Аккаунт {SESSION_NAME} не найден в БД.")
            return False
        account.string_session = string_session
        account.api_id = API_ID
        account.api_hash = API_HASH
        db.commit()
        print(f"БД обновлена: {SESSION_NAME} (string_session записан).")
        return True
    finally:
        db.close()


def update_config_json(string_session: str) -> None:
    """Обновить string_session в accounts_config.json для Lisa."""
    base = Path(__file__).parent.parent
    config_file = base / "accounts_config.json"
    with open(config_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    for acc in data:
        if acc.get("session_name") == SESSION_NAME:
            acc["string_session"] = string_session
            break
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("accounts_config.json обновлён для promotion_lisa_soak.")


def main():
    print("Экспорт file-сессии в строку...")
    string_session = asyncio.run(export_file_to_string())
    if not string_session:
        sys.exit(1)
    print(f"StringSession получен (длина {len(string_session)}).")
    if not update_db(string_session):
        sys.exit(2)
    update_config_json(string_session)
    print("Готово. Перезапустите секретаря: docker-compose restart secretary")


if __name__ == "__main__":
    main()
