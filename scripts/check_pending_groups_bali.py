#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка групп Bali со статусом 'pending'.

Логика:
- Берём groups WHERE niche='bali' AND status='pending'
- Для каждой группы проверяем, стал ли хоть один Bali‑аккаунт участником
- Если да:
    - проверяем, можно ли постить
    - обновляем группу в БД: assigned_account_id, joined_at, warm_up_until,
      can_post, status ('active' или 'read_only')
- Если username не существует / канал приватный — помечаем как 'inaccessible'

Запуск из хоста:
  cd PIAR/telegram_promotion_system_bali
  python3 scripts/check_pending_groups_bali.py --limit 50

Запуск в контейнере:
  docker exec telegram-bali-account-manager python3 /app/scripts/check_pending_groups_bali.py --limit 50
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

from telethon.errors import (
    UsernameNotOccupiedError,
    ChannelPrivateError,
    FloodWaitError,
)
from telethon.tl.functions.channels import GetFullChannelRequest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shared.database.session import SessionLocal, init_db  # noqa: E402
from shared.database.models import Account, Group  # noqa: E402
from shared.telegram.client_manager import TelegramClientManager  # noqa: E402

import logging  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def check_can_post(client, entity) -> bool:
    """Проверить, может ли аккаунт писать в чат."""
    try:
        me = await client.get_me()
        perms = await client.get_permissions(entity, me)

        # Явное право send_messages
        if perms and getattr(perms, "send_messages", None) is not None:
            return bool(perms.send_messages)

        # banned_rights.send_messages
        banned_rights = getattr(perms, "banned_rights", None) if perms else None
        if banned_rights and hasattr(banned_rights, "send_messages"):
            return not bool(banned_rights.send_messages)

        # Доп. проверка default_banned_rights
        try:
            full = await client(GetFullChannelRequest(entity))
            full_chat = getattr(full, "full_chat", None)
            if full_chat and getattr(full_chat, "default_banned_rights", None):
                br = full_chat.default_banned_rights
                if getattr(br, "send_messages", False):
                    return False
                return True
        except Exception:
            # Не критично, проваливаемся к дефолту
            pass

        # Если ничего не знаем — считаем, что можно (для обычных групп)
        return True
    except Exception as e:  # noqa: BLE001
        logger.debug("check_can_post error: %s", e)
        return False


async def is_member(client, username: str) -> Tuple[bool, Optional[str]]:
    """Проверить, является ли клиент участником @username."""
    try:
        entity = await client.get_entity(username)
    except UsernameNotOccupiedError:
        return False, "username_not_occupied"
    except ChannelPrivateError:
        return False, "channel_private"
    except Exception as e:  # noqa: BLE001
        return False, str(e)

    try:
        await client.get_participants(entity, limit=1)
        return True, None
    except Exception as e:  # noqa: BLE001
        err = str(e).lower()
        if "not a member" in err or "participant" in err or "user not found" in err:
            return False, "not_member"
        return False, str(e)


def get_pending(limit: int):
    """Получить pending‑группы Bali из БД."""
    init_db()
    db = SessionLocal()
    try:
        return (
            db.query(Group)
            .filter(Group.niche == "bali", Group.status == "pending")
            .order_by(Group.updated_at.asc().nullslast())
            .limit(limit)
            .all()
        )
    finally:
        db.close()


def set_joined(
    group_id: int,
    account_id: int,
    can_post: bool,
    title: Optional[str] = None,
    members_count: Optional[int] = None,
) -> None:
    """Обновить группу после подтверждения вступления."""
    now = datetime.utcnow()
    db = SessionLocal()
    try:
        g = db.query(Group).filter(Group.id == group_id).first()
        if not g:
            return
        g.assigned_account_id = account_id
        g.joined_at = now
        g.warm_up_until = now + timedelta(hours=24)
        g.can_post = can_post
        g.status = "active" if can_post else "read_only"
        g.updated_at = now
        if title is not None:
            g.title = title
        if members_count is not None:
            g.members_count = members_count
        db.commit()
        logger.info("✅ group id=%s → status=%s (account_id=%s)", group_id, g.status, account_id)
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.error("❌ Error updating group id=%s: %s", group_id, e)
    finally:
        db.close()


def set_inaccessible(group_id: int) -> None:
    """Пометить группу как недоступную."""
    db = SessionLocal()
    try:
        g = db.query(Group).filter(Group.id == group_id).first()
        if not g:
            return
        g.status = "inaccessible"
        g.updated_at = datetime.utcnow()
        db.commit()
        logger.info("📛 group id=%s → status=inaccessible", group_id)
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.error("❌ Error marking inaccessible id=%s: %s", group_id, e)
    finally:
        db.close()


async def process_pending(limit: int, dry_run: bool, delay: int) -> None:
    """Основной цикл обработки pending‑групп."""
    logger.info("🔍 Checking pending Bali groups (limit=%s, dry_run=%s)", limit, dry_run)
    pending = get_pending(limit)
    if not pending:
        logger.info("✅ No pending groups.")
        return

    logger.info("📋 Pending groups: %s", len(pending))

    sessions_dir = os.getenv("SESSIONS_DIR", "/app/sessions")
    if not Path(sessions_dir).exists() and (ROOT / "sessions").exists():
        sessions_dir = str(ROOT / "sessions")

    client_manager = TelegramClientManager(sessions_dir=sessions_dir)

    db = SessionLocal()
    try:
        await client_manager.load_accounts_from_db(db, exclude_lexus_accounts=True)
    finally:
        db.close()

    if not client_manager.clients:
        logger.warning("⚠️ No Telegram clients loaded. Check accounts in DB / config.")
        return

    # Карту session_name → account_id берём из БД
    db = SessionLocal()
    try:
        account_ids = {
            row.session_name: row.id
            for row in db.query(Account.id, Account.session_name).filter(
                Account.session_name.in_(list(client_manager.clients.keys()))
            )
        }
    finally:
        db.close()

    promoted = 0
    inaccessible = 0
    still_pending = 0

    for group in pending:
        username = group.username
        if not username.startswith("@"):
            username = "@" + username
        logger.info("➡️  Group %s (id=%s)", username, group.id)

        if dry_run:
            still_pending += 1
            await asyncio.sleep(1)
            continue

        # Сначала пробуем разрешить entity хоть одним клиентом (для быстрой проверки существования)
        try:
            first_client = list(client_manager.clients.values())[0]
            entity = await first_client.get_entity(username)
        except UsernameNotOccupiedError:
            logger.info("  username not occupied → mark inaccessible")
            set_inaccessible(group.id)
            inaccessible += 1
            await asyncio.sleep(delay)
            continue
        except ChannelPrivateError:
            logger.info("  channel private → mark inaccessible")
            set_inaccessible(group.id)
            inaccessible += 1
            await asyncio.sleep(delay)
            continue
        except FloodWaitError as e:
            logger.warning("  FloodWait %s sec on get_entity, skipping for now", e.seconds)
            still_pending += 1
            await asyncio.sleep(min(e.seconds, 60))
            continue
        except Exception as e:  # noqa: BLE001
            logger.warning("  get_entity error: %s", e)
            still_pending += 1
            await asyncio.sleep(delay)
            continue

        # Ищем аккаунт, который уже участник группы
        found_session: Optional[str] = None
        found_client = None
        for session_name, client in client_manager.clients.items():
            try:
                member, _ = await is_member(client, username)
                if member:
                    found_session = session_name
                    found_client = client
                    break
            except FloodWaitError as e:
                logger.warning("  FloodWait %s sec for %s", e.seconds, session_name)
                await asyncio.sleep(min(e.seconds, 60))
            except Exception:
                # Просто пробуем следующего
                continue

        if not found_session or not found_client:
            logger.info("  No accounts are members yet → still pending")
            still_pending += 1
            await asyncio.sleep(delay)
            continue

        account_id = account_ids.get(found_session)
        if not account_id:
            logger.warning("  Account %s not found in DB", found_session)
            still_pending += 1
            await asyncio.sleep(delay)
            continue

        # Проверяем, можно ли постить
        can_post = await check_can_post(found_client, entity)

        title: Optional[str] = None
        members_count: Optional[int] = None
        try:
            full = await found_client(GetFullChannelRequest(entity))
            full_chat = getattr(full, "full_chat", None)
            if full_chat is not None:
                title = getattr(full_chat, "title", None)
                members_count = getattr(full_chat, "participants_count", None)
        except Exception:
            pass

        set_joined(
            group_id=group.id,
            account_id=account_id,
            can_post=can_post,
            title=title,
            members_count=members_count,
        )
        promoted += 1
        await asyncio.sleep(delay)

    await client_manager.disconnect_all()
    logger.info(
        "✅ Done: promoted=%s, inaccessible=%s, still_pending=%s",
        promoted,
        inaccessible,
        still_pending,
    )


def parse_args() -> argparse.Namespace:
    """Разбор аргументов командной строки."""
    parser = argparse.ArgumentParser(
        description="Check Bali pending groups: promote to active/read_only if join approved.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=30,
        help="Макс. число групп за запуск (default: 30)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Не изменять БД, только логировать.",
    )
    parser.add_argument(
        "--delay",
        type=int,
        default=15,
        help="Пауза между группами в секундах (default: 15)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(
        process_pending(
            limit=args.limit,
            dry_run=args.dry_run,
            delay=args.delay,
        ),
    )

