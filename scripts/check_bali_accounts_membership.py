#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка участия аккаунтов Bali в группах.

- Загружает группы из БД (niche='bali', status in ('active','joined')).
- Проверяет для каждой группы, является ли хотя бы один Bali-аккаунт участником
  и может ли постить.
- Опционально обновляет БД: группы, где ни один аккаунт не участник → can_post=False,
  status='new' (чтобы account-manager снова вступил).

Запуск с хоста:
  cd PIAR/telegram_promotion_system_bali
  python3 scripts/check_bali_accounts_membership.py [--limit N] [--update-db] [--dry-run]

Запуск в контейнере:
  docker exec telegram-bali-marketer python3 /app/scripts/check_bali_accounts_membership.py --limit 50 --update-db
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from telethon import TelegramClient
from telethon.errors import (
    ChannelPrivateError,
    FloodWaitError,
    UserBannedInChannelError,
    ChatWriteForbiddenError,
)
from shared.database.session import SessionLocal, init_db
from shared.database.models import Account, Group
from shared.telegram.client_manager import TelegramClientManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(ROOT / "logs" / "check_bali_membership.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


async def check_membership(
    client: TelegramClient,
    account_name: str,
    group_username: str,
) -> Tuple[str, Optional[str]]:
    """
    Проверка участия аккаунта в группе.

    Returns:
        (status, error_message): 'member_can_post' | 'member_cannot_post' | 'not_member' | ...
    """
    try:
        username = group_username.lstrip("@")
        entity = await client.get_entity(username)
    except Exception as e:
        err = str(e).lower()
        if "not found" in err or "username" in err:
            return "not_found", str(e)[:200]
        if "private" in err or "channel" in err:
            return "private", str(e)[:200]
        return "error", str(e)[:200]

    try:
        me = await client.get_me()
        permissions = await client.get_permissions(entity, me)
    except UserBannedInChannelError:
        return "banned", "Аккаунт забанен в группе"
    except ChatWriteForbiddenError:
        return "member_cannot_post", "Нет прав на постинг"
    except Exception as e:
        err = str(e).lower()
        if "not a member" in err or "participant" in err or "user not found" in err:
            return "not_member", "Аккаунт не является участником группы"
        if "private" in err:
            return "private", str(e)[:200]
        return "error", str(e)[:200]

    can_send = False
    if permissions:
        if getattr(permissions, "send_messages", None) is not None:
            can_send = bool(permissions.send_messages)
        elif getattr(permissions, "banned_rights", None) and permissions.banned_rights:
            if getattr(permissions.banned_rights, "send_messages", None) is not None:
                can_send = not bool(permissions.banned_rights.send_messages)
    if can_send:
        return "member_can_post", None
    return "member_cannot_post", "Нет прав на постинг"


def load_bali_groups(limit: Optional[int] = None) -> List[Group]:
    """Группы Bali со статусом active/joined."""
    init_db()
    db = SessionLocal()
    try:
        q = (
            db.query(Group)
            .filter(
                Group.niche == "bali",
                Group.status.in_(("active", "joined")),
            )
            .order_by(Group.updated_at.asc())
        )
        if limit:
            q = q.limit(limit)
        return q.all()
    finally:
        db.close()


def update_group_to_rejoin(db_session, group_id: int) -> None:
    """Пометить группу для повторного вступления: can_post=False, status='new'."""
    g = db_session.query(Group).filter(Group.id == group_id).first()
    if not g:
        return
    g.can_post = False
    g.status = "new"
    g.updated_at = datetime.utcnow()
    db_session.commit()
    logger.info("  📌 Группа id=%s → status=new, can_post=False (для повторного вступления)", group_id)


async def run_check(
    limit: Optional[int],
    update_db: bool,
    dry_run: bool,
) -> None:
    groups = load_bali_groups(limit=limit)
    if not groups:
        logger.info("✅ Нет групп Bali со статусом active/joined.")
        return

    logger.info("📋 Групп для проверки: %s", len(groups))

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
        logger.warning("⚠️ Нет загруженных Bali-аккаунтов. Проверьте БД и bali_accounts_config.json.")
        return

    logger.info("✅ Аккаунтов для проверки: %s", list(client_manager.clients.keys()))

    results: Dict[str, Dict[str, Dict[str, str]]] = {}
    for idx, group in enumerate(groups, 1):
        username = group.username if group.username.startswith("@") else f"@{group.username}"
        logger.info("[%s/%s] %s", idx, len(groups), username)
        results[username] = {}
        for account_name, client in client_manager.clients.items():
            try:
                status, err = await check_membership(client, account_name, username)
            except FloodWaitError as e:
                status, err = "flood_wait", f"FloodWait {e.seconds}s"
                logger.warning("  ⏳ %s: FloodWait %s sec", account_name, e.seconds)
                await asyncio.sleep(min(e.seconds + 1, 60))
            else:
                emoji = {"member_can_post": "✅", "member_cannot_post": "⚠️", "not_member": "❌"}.get(status, "❓")
                logger.info("  %s %s: %s", emoji, account_name, status + (f" — {err}" if err else ""))
            results[username][account_name] = {"status": status, "error": err or ""}
            await asyncio.sleep(0.3)
        await asyncio.sleep(0.5)

    # Группы, где ни один аккаунт не может постить (все not_member или member_cannot_post)
    need_rejoin: List[Tuple[str, int]] = []
    for group in groups:
        username = group.username if group.username.startswith("@") else f"@{group.username}"
        acc_results = results.get(username, {})
        if not acc_results:
            continue
        can_post_any = any(
            r.get("status") == "member_can_post" for r in acc_results.values()
        )
        if not can_post_any:
            need_rejoin.append((username, group.id))

    logger.info("")
    logger.info("📊 Группы, где ни один Bali-аккаунт не может постить (кандидаты на status=new): %s", len(need_rejoin))
    for username, gid in need_rejoin[:30]:
        logger.info("  • %s (id=%s)", username, gid)
    if len(need_rejoin) > 30:
        logger.info("  ... и ещё %s", len(need_rejoin) - 30)

    if update_db and need_rejoin and not dry_run:
        db = SessionLocal()
        try:
            for _username, group_id in need_rejoin:
                update_group_to_rejoin(db, group_id)
            logger.info("✅ Обновлено групп (status=new): %s. Account-manager подхватит их для вступления.", len(need_rejoin))
        except Exception as e:
            db.rollback()
            logger.error("❌ Ошибка обновления БД: %s", e)
        finally:
            db.close()
    elif update_db and dry_run:
        logger.info("🔸 Dry-run: обновление БД не выполнялось (запустите без --dry-run).")

    # Отчёт в файл
    report_lines = [
        "=" * 60,
        "Проверка участия Bali-аккаунтов в группах",
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "=" * 60,
        f"Групп проверено: {len(groups)}",
        f"Групп для повторного вступления (status=new): {len(need_rejoin)}",
        "",
    ]
    for username, gid in need_rejoin:
        report_lines.append(f"  {username} (id={gid})")
    report_path = ROOT / "logs" / f"bali_membership_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    logger.info("📄 Отчёт: %s", report_path)


def main():
    parser = argparse.ArgumentParser(description="Проверка участия Bali-аккаунтов в группах")
    parser.add_argument("--limit", type=int, default=None, help="Макс. число групп для проверки")
    parser.add_argument("--update-db", action="store_true", help="Обновить БД: группы без участников → status=new")
    parser.add_argument("--dry-run", action="store_true", help="С --update-db: только показать, не писать в БД")
    args = parser.parse_args()
    asyncio.run(run_check(limit=args.limit, update_db=args.update_db, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
