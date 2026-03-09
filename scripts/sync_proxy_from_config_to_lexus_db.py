#!/usr/bin/env python3
"""
Синхронизация прокси из accounts_config.json в таблицу accounts БД Lexus.

Обновляет поле proxy у аккаунтов в БД значениями из конфига (по session_name).
Запуск:
  - из хоста (БД на порту 5440):
    POSTGRES_PORT=5440 POSTGRES_DB=telegram_promotion_lexus python3 scripts/sync_proxy_from_config_to_lexus_db.py
  - из контейнера lexus-marketer:
    docker exec lexus-marketer python3 /app/scripts/sync_proxy_from_config_to_lexus_db.py
"""
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# Корень проекта для импорта lexus_db
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

# Для запуска с хоста: подставить БД Lexus (порт 5440)
if not os.getenv('DATABASE_URL') and not os.getenv('POSTGRES_DB'):
    os.environ.setdefault('POSTGRES_PORT', '5440')
    os.environ.setdefault('POSTGRES_DB', 'telegram_promotion_lexus')

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def load_accounts_config() -> list:
    """Загружает accounts_config.json из стандартных путей."""
    for path in [
        project_root / "accounts_config.json",
        Path("/app/accounts_config.json"),
        Path("accounts_config.json"),
    ]:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    raise FileNotFoundError("accounts_config.json не найден")


async def main() -> None:
    """Синхронизирует proxy из конфига в БД Lexus."""
    logger.info("Синхронизация proxy из accounts_config.json в БД Lexus")
    logger.info("")

    try:
        accounts_config = load_accounts_config()
    except FileNotFoundError as e:
        logger.error("❌ %s", e)
        sys.exit(1)

    # Только аккаунты с указанным proxy
    with_proxy = [
        acc for acc in accounts_config
        if acc.get("proxy")
    ]
    if not with_proxy:
        logger.info("В конфиге нет аккаунтов с proxy. Нечего синхронизировать.")
        return

    from lexus_db.session import AsyncSessionLocal
    from lexus_db.models import Account
    from sqlalchemy import select, update

    updated = 0
    not_found = []

    async with AsyncSessionLocal() as session:
        for acc in with_proxy:
            session_name = acc.get("session_name")
            proxy = (acc.get("proxy") or "").strip()
            if not session_name:
                continue

            result = await session.execute(
                select(Account).where(Account.session_name == session_name)
            )
            account = result.scalar_one_or_none()

            if account is None:
                not_found.append(session_name)
                continue

            if account.proxy != proxy:
                account.proxy = proxy
                updated += 1
                logger.info("  ✅ %s → proxy обновлён", session_name)
            else:
                logger.info("  ⏭️ %s — proxy уже совпадает", session_name)

        await session.commit()

    logger.info("")
    logger.info("Итого: обновлено %s, в БД не найдено: %s", updated, len(not_found))
    if not_found:
        logger.info("Не найдены в БД (добавьте через migrate_lexus_accounts_to_db.py): %s", not_found)
    logger.info("Готово.")


if __name__ == "__main__":
    asyncio.run(main())
