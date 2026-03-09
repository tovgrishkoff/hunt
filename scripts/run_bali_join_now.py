#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Разовый запуск вступления в группы Bali (status='new').

Использует тот же GroupJoiner, что и account-manager: вступает в группы из очереди,
лимит за один запуск задаётся в config/niches/bali.json (join_batch_size, по умолчанию 20).

Запуск (из контейнера account-manager):
  docker exec telegram-bali-account-manager python3 /app/scripts/run_bali_join_now.py

С хоста (при наличии доступа к БД и sessions):
  cd PIAR/telegram_promotion_system_bali
  NICHE=bali python3 scripts/run_bali_join_now.py
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def load_allowed_sessions() -> list:
    """Список session_name для Bali (из bali_accounts_config.json)."""
    for path in [
        Path("/app/bali_accounts_config.json"),
        ROOT / "bali_accounts_config.json",
        ROOT / "config/bali_accounts_config.json",
    ]:
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                allowed = data.get("allowed_accounts") or []
                allowed = [s for s in allowed if s]
                if allowed:
                    return allowed
            except Exception as e:
                logger.warning("Failed to load %s: %s", path, e)
    return []


async def main():
    from shared.config.loader import ConfigLoader
    from shared.telegram.client_manager import TelegramClientManager
    from shared.database.session import SessionLocal

    import importlib.util
    joiner_spec = importlib.util.spec_from_file_location(
        "joiner", ROOT / "services/account-manager/joiner.py"
    )
    joiner_module = importlib.util.module_from_spec(joiner_spec)
    joiner_spec.loader.exec_module(joiner_module)
    GroupJoiner = joiner_module.GroupJoiner

    niche_name = os.getenv("NICHE", "bali")
    logger.info("📋 Ниша: %s", niche_name)

    config_loader = ConfigLoader()
    niche_config = config_loader.load_niche_config(niche_name)
    allowed_sessions = load_allowed_sessions()
    if allowed_sessions:
        logger.info("✅ Allowed sessions: %s", allowed_sessions)

    client_manager = TelegramClientManager(
        sessions_dir=os.getenv("SESSIONS_DIR", str(ROOT / "sessions"))
    )
    db = SessionLocal()
    try:
        await client_manager.load_accounts_from_db(db)
        if allowed_sessions:
            client_manager.clients = {
                k: v for k, v in client_manager.clients.items() if k in allowed_sessions
            }
        logger.info("✅ Загружено аккаунтов: %s", len(client_manager.clients))
    finally:
        db.close()

    if not client_manager.clients:
        logger.warning("⚠️ Нет аккаунтов для вступления. Проверьте БД и bali_accounts_config.json.")
        return

    joiner = GroupJoiner(
        client_manager,
        niche_config,
        allowed_sessions=allowed_sessions or None,
    )
    joined, failed = await joiner.process_new_groups(niche_name)
    logger.info("✅ Готово: вступили %s, неудач %s", joined, failed)

    # Отключаем клиенты
    for name, client in list(client_manager.clients.items()):
        try:
            if client.is_connected():
                await client.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
