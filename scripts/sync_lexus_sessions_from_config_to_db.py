#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Синхронизация string_session из accounts_config.json в таблицу accounts БД Lexus.

Нужен после того, как вы создали новые сессии на хосте (create_lexus_sessions.py):
конфиг обновился на диске, но БД внутри Docker — другая. Запуск из контейнера
копирует string_session из смонтированного конфига в БД, которую использует Lexus.

Запуск из контейнера (обязательно — чтобы писать в ту же БД, что и сервисы):
  docker exec lexus-account-manager python3 /app/scripts/sync_lexus_sessions_from_config_to_db.py
"""
import asyncio
import json
import logging
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def load_lexus_allowed() -> set:
    for p in [project_root / "lexus_accounts_config.json", Path("/app/lexus_accounts_config.json")]:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return set(json.load(f).get("allowed_accounts", []))
            except Exception as e:
                logger.warning("Ошибка чтения %s: %s", p, e)
    return set()


def load_accounts_config() -> list:
    for p in [project_root / "accounts_config.json", Path("/app/accounts_config.json")]:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data if isinstance(data, list) else data.get("accounts", [])
            except Exception as e:
                logger.warning("Ошибка чтения %s: %s", p, e)
    return []


async def main() -> None:
    allowed = load_lexus_allowed()
    if not allowed:
        logger.error("Нет allowed_accounts в lexus_accounts_config.json")
        sys.exit(1)

    config = load_accounts_config()
    by_name = {a["session_name"]: a for a in config if isinstance(a, dict) and a.get("session_name")}

    to_sync = [(name, by_name.get(name)) for name in sorted(allowed)]
    to_sync = [(n, a) for n, a in to_sync if a and (a.get("string_session") or "").strip()]
    if not to_sync:
        logger.error("В accounts_config.json нет string_session для Lexus-аккаунтов: %s", sorted(allowed))
        sys.exit(1)

    from lexus_db.session import AsyncSessionLocal
    from lexus_db.models import Account
    from sqlalchemy import select

    updated = 0
    not_found = []

    async with AsyncSessionLocal() as session:
        for session_name, acc in to_sync:
            string_session = (acc.get("string_session") or "").strip()
            if len(string_session) < 50:
                logger.warning("  ⚠️ %s — string_session слишком короткий, пропуск", session_name)
                continue
            result = await session.execute(select(Account).where(Account.session_name == session_name))
            account = result.scalar_one_or_none()
            if not account:
                not_found.append(session_name)
                continue
            account.string_session = string_session
            account.status = "active"
            updated += 1
            logger.info("  ✅ %s → string_session обновлён в БД", session_name)
        await session.commit()

    logger.info("")
    logger.info("Итого: обновлено %s. В БД не найдено: %s", updated, not_found or "—")
    if not_found:
        logger.info("Добавьте аккаунты в БД через migrate_lexus_accounts_to_db.py (с хоста с подключением к БД Lexus).")


if __name__ == "__main__":
    asyncio.run(main())
