#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка прав на постинг в группах Lexus и обновление БД.

Читает группы из таблицы groups (telegram_promotion_lexus),
проверяет через Telegram API, может ли хотя бы один Lexus-аккаунт
постить в каждой группе. Обновляет can_post в БД.

Запуск:
  docker exec lexus-marketer python3 /app/scripts/check_lexus_permissions_and_update_db.py
  docker exec lexus-marketer python3 /app/scripts/check_lexus_permissions_and_update_db.py --limit 20
  docker exec lexus-marketer python3 /app/scripts/check_lexus_permissions_and_update_db.py --dry-run
"""
import argparse
import asyncio
import json
import logging
import re
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from telethon.errors import FloodWaitError
except ImportError:
    FloodWaitError = None

from sqlalchemy import select, and_, or_
from sqlalchemy.orm import Session

# Используем sync session для совместимости с shared.database
from shared.database.session import SessionLocal, init_db
from shared.database.models import Account, Group
from shared.telegram.client_manager import TelegramClientManager

import os

log_dir = Path("/app/logs") if Path("/app/logs").exists() else Path(__file__).parent.parent / "logs"
log_dir.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_dir / "lexus_permissions_update.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# Макс. ожидание при FloodWait (сек). Больше — группу не обновляем, пропускаем.
FLOOD_WAIT_MAX_SLEEP = 600


def _extract_flood_wait_seconds(error: Exception) -> int | None:
    """Извлекает число секунд из FloodWait (FloodWaitError или текст 'A wait of N seconds')."""
    if FloodWaitError and isinstance(error, FloodWaitError):
        return getattr(error, "seconds", None)
    msg = str(error)
    m = re.search(r"wait of (\d+) seconds", msg, re.I)
    return int(m.group(1)) if m else None


def load_lexus_allowed_accounts() -> set:
    """Загружает whitelist аккаунтов Lexus из конфига."""
    paths = [
        Path("/app/lexus_accounts_config.json"),
        Path(__file__).parent.parent / "lexus_accounts_config.json",
    ]
    for p in paths:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                allowed = set(data.get("allowed_accounts", []) or [])
                if allowed:
                    logger.info(f"✅ Lexus accounts: {allowed}")
                    return allowed
            except Exception as e:
                logger.warning(f"⚠️ Failed to load {p}: {e}")
    return set()


async def check_can_post(client, entity, me) -> tuple[bool, str]:
    """
    Проверяет, может ли аккаунт постить в группе/канале.

    Returns:
        (can_post: bool, reason: str)
    """
    try:
        permissions = await client.get_permissions(entity, me)
        if not permissions:
            return False, "No permissions (not member?)"

        # Каналы (broadcast): только админы могут постить
        if getattr(entity, "broadcast", False):
            return False, "Channel: only admins can post"

        can_send = True
        if hasattr(permissions, "send_messages") and not permissions.send_messages:
            can_send = False
        elif (
            hasattr(permissions, "banned_rights")
            and permissions.banned_rights
            and hasattr(permissions.banned_rights, "send_messages")
            and permissions.banned_rights.send_messages
        ):
            can_send = False

        if can_send:
            return True, "OK"
        return False, "No send_messages permission"
    except Exception as e:
        return False, str(e)[:100]


async def main():
    parser = argparse.ArgumentParser(
        description="Проверка прав Lexus и обновление can_post в БД"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Лимит групп для проверки (0 = все)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Только проверить, не обновлять БД",
    )
    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("🔍 LEXUS: Проверка прав на постинг и обновление БД")
    logger.info("=" * 80)

    # Загружаем whitelist Lexus
    allowed_sessions = load_lexus_allowed_accounts()
    if not allowed_sessions:
        logger.error("❌ Не найден lexus_accounts_config.json или пустой allowed_accounts")
        return 1

    init_db()
    db: Session = SessionLocal()

    try:
        # Клиенты
        sessions_dir = Path("/app/sessions")
        if not sessions_dir.exists():
            sessions_dir = Path(__file__).parent.parent / "sessions_lexus"
        if not sessions_dir.exists():
            sessions_dir = Path(__file__).parent.parent / "sessions"

        client_manager = TelegramClientManager(sessions_dir=str(sessions_dir))
        # Загружаем ВСЕ аккаунты из БД, затем фильтруем по whitelist
        await client_manager.load_accounts_from_db(db, exclude_lexus_accounts=False)

        # Оставляем только Lexus-аккаунты
        client_manager.clients = {
            k: v
            for k, v in client_manager.clients.items()
            if k in allowed_sessions
        }

        if not client_manager.clients:
            logger.error(
                "❌ Нет загруженных Lexus-клиентов. "
                "Проверьте: аккаунты в БД, sessions_lexus, lexus_accounts_config.json"
            )
            return 1

        logger.info(f"✅ Аккаунтов для проверки: {len(client_manager.clients)}")

        # Группы: active или joined, niche ukraine_cars
        stmt = (
            select(Group)
            .where(
                and_(
                    Group.niche == "ukraine_cars",
                    Group.status.in_(["active", "joined"]),
                )
            )
            .order_by(Group.username)
        )
        if args.limit > 0:
            stmt = stmt.limit(args.limit)

        result = db.execute(stmt)
        groups = result.scalars().all()
        logger.info(f"📋 Групп для проверки: {len(groups)}")

        if not groups:
            logger.info("✅ Нет групп для проверки")
            return 0

        updated_can_post_false = 0
        kept_can_post_true = 0

        for idx, group in enumerate(groups, 1):
            logger.info(f"\n[{idx}/{len(groups)}] {group.username}")

            retries_left = 2  # обычная попытка + одна после короткого FloodWait
            done = False

            while retries_left > 0 and not done:
                can_post_any = False
                last_reason = ""
                min_flood_wait_sec: int | None = None

                for account_name, client in client_manager.clients.items():
                    if not client.is_connected():
                        client = await client_manager.ensure_client_connected(account_name)
                    if not client:
                        continue

                    try:
                        entity = await client.get_entity(group.username)
                        me = await client.get_me()
                        can_post, reason = await check_can_post(client, entity, me)

                        if can_post:
                            can_post_any = True
                            logger.info(f"   ✅ {account_name}: может постить")
                            break
                        last_reason = reason
                    except Exception as e:
                        wait_sec = _extract_flood_wait_seconds(e)
                        if wait_sec is not None:
                            if min_flood_wait_sec is None or wait_sec < min_flood_wait_sec:
                                min_flood_wait_sec = wait_sec
                            last_reason = f"FloodWait: {wait_sec} сек"
                            logger.warning(f"   ⏳ {account_name}: FloodWait {wait_sec} сек")
                        else:
                            last_reason = str(e)[:80]
                            logger.debug(f"   ⚠️ {account_name}: {last_reason}")

                    await asyncio.sleep(1)

                if can_post_any:
                    kept_can_post_true += 1
                    if not group.can_post:
                        if not args.dry_run:
                            group.can_post = True
                            db.commit()
                        logger.info(f"   🔄 Восстановлен can_post=True")
                    done = True
                    break

                if min_flood_wait_sec is not None:
                    if min_flood_wait_sec > FLOOD_WAIT_MAX_SLEEP:
                        logger.warning(
                            "   ⏳ Пропущено (FloodWait %s сек ≈ %s мин). БД не меняем. Запустите скрипт через ~1–2 ч.",
                            min_flood_wait_sec,
                            min_flood_wait_sec // 60,
                        )
                        done = True
                        break
                    logger.warning("   ⏳ FloodWait %s сек — ждём и повторяем проверку группы...", min_flood_wait_sec)
                    await asyncio.sleep(min_flood_wait_sec)
                    retries_left -= 1
                    continue

                logger.warning(f"   ❌ Ни один аккаунт не может постить: {last_reason}")
                if group.can_post or group.can_post is None:
                    if not args.dry_run:
                        group.can_post = False
                        db.commit()
                    updated_can_post_false += 1
                done = True
                break

            await asyncio.sleep(2)

        logger.info("")
        logger.info("=" * 80)
        logger.info("📊 ИТОГ")
        logger.info("=" * 80)
        logger.info(f"Групп, где можно постить: {kept_can_post_true}")
        logger.info(f"Групп, обновлено can_post=False: {updated_can_post_false}")
        if args.dry_run:
            logger.info("(dry-run: БД не изменена)")
        logger.info("=" * 80)

        return 0

    except Exception as e:
        logger.error(f"❌ Ошибка: {e}", exc_info=True)
        db.rollback()
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
