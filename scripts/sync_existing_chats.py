#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sync Dialogs to DB — двусторонняя синхронизация групп из Telegram в PostgreSQL.

Собирает все группы/супергруппы, в которых уже состоят Bali-аккаунты,
проверяет право на отправку сообщений и делает upsert в таблицу groups:
- новых записей (niche='bali', status='active') с привязкой к аккаунту;
- обновление статуса у существующих (active, сброс pending/inaccessible/no_accounts_left).

Запуск:
  cd PIAR/telegram_promotion_system_bali
  python3 scripts/sync_existing_chats.py

В Docker:
  docker exec telegram-bali-account-manager python3 /app/scripts/sync_existing_chats.py
"""
import asyncio
import sys
import logging
from pathlib import Path
from datetime import datetime, timedelta

# Корень проекта в PYTHONPATH
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from telethon import TelegramClient
from telethon.tl.types import Channel, Chat

from shared.database.session import SessionLocal
from shared.database.models import Group, Account
from shared.telegram.client_manager import TelegramClientManager

# Логирование
log_dir = project_root / "logs"
log_dir.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_dir / "sync_existing_chats.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

NICHE = "bali"


def _is_group_or_megagroup(entity) -> bool:
    """Только группы и супергруппы; исключаем каналы (broadcast), личку, ботов."""
    if isinstance(entity, Chat):
        return True
    if isinstance(entity, Channel):
        if getattr(entity, "broadcast", False):
            return False
        return bool(getattr(entity, "megagroup", False))
    return False


async def _can_send_messages(client: TelegramClient, entity) -> bool:
    """Проверка права на отправку сообщений в чате (не read-only)."""
    try:
        me = await client.get_me()
        permissions = await client.get_permissions(entity, me)
        if not permissions:
            return False
        if hasattr(permissions, "send_messages"):
            return bool(permissions.send_messages)
        if hasattr(permissions, "banned_rights") and permissions.banned_rights:
            if hasattr(permissions.banned_rights, "send_messages"):
                return not bool(permissions.banned_rights.send_messages)
        return True
    except Exception as e:
        logger.debug("  get_permissions failed for entity %s: %s", entity, e)
        return False


async def _collect_postable_groups(client: TelegramClient, session_name: str) -> list:
    """
    Собрать из диалогов только группы/супергруппы, где можно писать.
    Возвращает список словарей: username, title, entity, members_count.
    """
    result = []
    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        if not _is_group_or_megagroup(entity):
            continue
        if getattr(entity, "left", False) or getattr(entity, "kicked", False):
            continue
        username = getattr(entity, "username", None)
        if not username:
            continue
        if not username.startswith("@"):
            username = f"@{username}"
        title = getattr(entity, "title", "") or "Unknown"
        members_count = getattr(entity, "participants_count", None)
        if not await _can_send_messages(client, entity):
            logger.debug("  Skip read-only: %s", username)
            continue
        result.append({
            "username": username,
            "title": title,
            "entity": entity,
            "members_count": members_count,
        })
    return result


async def sync_existing_chats() -> None:
    """Синхронизация диалогов Bali-аккаунтов с таблицей groups."""
    db = SessionLocal()
    client_manager = TelegramClientManager()

    try:
        logger.info("Загружаю Bali-аккаунты из БД...")
        await client_manager.load_accounts_from_db(db, exclude_lexus_accounts=True)
        clients = client_manager.clients
        if not clients:
            logger.error("Нет доступных Bali-аккаунтов для синхронизации")
            return

        logger.info("Загружено аккаунтов: %s", len(clients))
        logger.info("=" * 80)

        grand_added = 0
        grand_updated = 0
        past_date = datetime.utcnow() - timedelta(days=3)

        for session_name, client in clients.items():
            try:
                if not client.is_connected():
                    await client.connect()
                me = await client.get_me()
                account_name = me.username or me.first_name or session_name
            except Exception as e:
                logger.warning("Аккаунт %s: не удалось подключиться — %s", session_name, e)
                continue

            db_account = db.query(Account).filter(Account.session_name == session_name).first()
            if not db_account:
                logger.warning("Аккаунт %s не найден в БД, пропускаю", session_name)
                continue

            logger.info("Сканирую диалоги: %s (%s)", account_name, session_name)
            try:
                groups_data = await _collect_postable_groups(client, session_name)
            except Exception as e:
                logger.error("Ошибка при сборе диалогов %s: %s", session_name, e, exc_info=True)
                continue

            added = 0
            updated = 0

            for g in groups_data:
                username = g["username"]
                title = g["title"]
                members_count = g["members_count"]
                db_group = db.query(Group).filter(Group.username == username).first()

                if not db_group:
                    try:
                        new_group = Group(
                            username=username,
                            title=title,
                            niche=NICHE,
                            status="active",
                            assigned_account_id=db_account.id,
                            joined_at=past_date,
                            warm_up_until=past_date,
                            can_post=True,
                            members_count=members_count,
                        )
                        db.add(new_group)
                        db.commit()
                        added += 1
                        logger.info("  Добавлена: %s (%s)", username, title[:50])
                    except Exception as e:
                        db.rollback()
                        logger.error("  Ошибка добавления %s: %s", username, e)
                else:
                    changed = False
                    if db_group.status != "active":
                        db_group.status = "active"
                        changed = True
                    if db_group.assigned_account_id != db_account.id:
                        db_group.assigned_account_id = db_account.id
                        changed = True
                    if db_group.niche != NICHE:
                        db_group.niche = NICHE
                        changed = True
                    if db_group.can_post is not True:
                        db_group.can_post = True
                        changed = True
                    if db_group.title != title:
                        db_group.title = title
                        changed = True
                    if members_count is not None and db_group.members_count != members_count:
                        db_group.members_count = members_count
                        changed = True
                    if not db_group.joined_at:
                        db_group.joined_at = past_date
                        db_group.warm_up_until = past_date
                        changed = True
                    if changed:
                        try:
                            db.commit()
                            updated += 1
                            logger.info("  Обновлена: %s", username)
                        except Exception as e:
                            db.rollback()
                            logger.error("  Ошибка обновления %s: %s", username, e)

            grand_added += added
            grand_updated += updated
            total = len(groups_data)
            logger.info(
                "Аккаунт %s: найдено групп %s. Добавлено новых: %s, Обновлено: %s.",
                session_name,
                total,
                added,
                updated,
            )
            logger.info("-" * 60)

        logger.info("")
        logger.info("=" * 80)
        logger.info("ИТОГ СИНХРОНИЗАЦИИ (Sync Dialogs to DB)")
        logger.info("  Добавлено новых групп: %s", grand_added)
        logger.info("  Обновлено групп: %s", grand_updated)
        logger.info("  Всего обработано: %s", grand_added + grand_updated)
        logger.info("=" * 80)

    except Exception as e:
        logger.error("Критическая ошибка: %s", e, exc_info=True)
    finally:
        db.close()
        try:
            await client_manager.disconnect_all()
        except Exception as e:
            logger.debug("disconnect_all: %s", e)


if __name__ == "__main__":
    try:
        asyncio.run(sync_existing_chats())
    except KeyboardInterrupt:
        logger.info("Синхронизация прервана пользователем")
        sys.exit(0)
    except Exception as e:
        logger.error("Фатальная ошибка: %s", e, exc_info=True)
        sys.exit(1)
