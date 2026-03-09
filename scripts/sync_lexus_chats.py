#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sync Dialogs для Lexus — синхронизация групп из Telegram в БД telegram_promotion_lexus.

Собирает все группы/супергруппы, в которых уже состоят Lexus-аккаунты
(promotion_alex_ever, promotion_dao_bro, promotion_rod_shaihutdinov и др. из lexus_accounts_config),
проверяет право на отправку сообщений и делает upsert в таблицу groups:
- новых записей (niche='ukraine_cars', status='active') с привязкой к аккаунту;
- обновление статуса у существующих (active, can_post=True, warm_up_until в прошлом).

Запуск с хоста (из корня проекта, БД Lexus на порту 5440 или в docker):
  cd PIAR/telegram_promotion_system_bali
  POSTGRES_PORT=5440 POSTGRES_DB=telegram_promotion_lexus python3 scripts/sync_lexus_chats.py

В Docker (из контейнера lexus-account-manager или lexus-marketer):
  docker exec lexus-account-manager python3 /app/scripts/sync_lexus_chats.py
"""
import asyncio
import json
import sys
import logging
from pathlib import Path
from datetime import datetime, timedelta

# Корень проекта в PYTHONPATH
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import Channel, Chat

from lexus_db.session import AsyncSessionLocal
from lexus_db.models import Target, Account
from sqlalchemy import select, and_

# Логирование
log_dir = project_root / "logs"
log_dir.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_dir / "sync_lexus_chats.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

NICHE = "ukraine_cars"


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


def _load_lexus_allowed_accounts() -> set:
    """Загрузить список разрешённых аккаунтов из lexus_accounts_config.json."""
    for path in [
        project_root / "lexus_accounts_config.json",
        Path("/app/lexus_accounts_config.json"),
        Path("lexus_accounts_config.json"),
    ]:
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    allowed = set(data.get("allowed_accounts", []))
                    if allowed:
                        return allowed
            except Exception as e:
                logger.warning("Failed to load %s: %s", path, e)
    return set()


async def _create_client(account: Account, accounts_config: dict) -> TelegramClient | None:
    """Создать Telethon-клиент для аккаунта (api_id, api_hash, string_session из БД или конфига)."""
    cfg = accounts_config.get(account.session_name, {})
    api_id = account.api_id or cfg.get("api_id")
    api_hash = account.api_hash or cfg.get("api_hash")
    string_session = (account.string_session or cfg.get("string_session") or "").strip()
    if not all([api_id, api_hash, string_session]):
        logger.warning("  Skip %s: missing api_id/api_hash/string_session", account.session_name)
        return None
    proxy = account.proxy or cfg.get("proxy")
    proxy_config = None
    if proxy and isinstance(proxy, str):
        try:
            from urllib.parse import urlparse
            p = urlparse(proxy)
            if p.scheme == "socks5":
                proxy_config = {"proxy_type": "socks5", "addr": p.hostname, "port": p.port, "username": p.username, "password": p.password}
            elif p.scheme in ("http", "https"):
                proxy_config = {"proxy_type": "http", "addr": p.hostname, "port": p.port, "username": p.username, "password": p.password}
        except Exception:
            pass
    try:
        client = TelegramClient(StringSession(string_session), int(api_id), api_hash, proxy=proxy_config)
        await client.connect()
        if not await client.is_user_authorized():
            logger.warning("  Skip %s: not authorized", account.session_name)
            await client.disconnect()
            return None
        return client
    except Exception as e:
        logger.warning("  Failed to create client for %s: %s", account.session_name, e)
        return None


async def sync_lexus_chats() -> None:
    """Синхронизация диалогов Lexus-аккаунтов с таблицей groups (lexus_db)."""
    allowed = _load_lexus_allowed_accounts()
    if not allowed:
        logger.error("Нет allowed_accounts в lexus_accounts_config.json")
        return

    # Загружаем конфиг аккаунтов (api_id, api_hash, string_session для создания клиентов)
    # Сначала lexus_accounts_config (если там есть массив accounts), иначе accounts_config.json
    accounts_config = {}
    for path in [
        project_root / "lexus_accounts_config.json",
        Path("/app/lexus_accounts_config.json"),
        project_root / "accounts_config.json",
        Path("/app/accounts_config.json"),
    ]:
        if not path.exists():
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
                if isinstance(raw, list):
                    accounts_config = {a["session_name"]: a for a in raw if isinstance(a, dict) and a.get("session_name")}
                elif isinstance(raw, dict):
                    lst = raw.get("accounts")
                    if isinstance(lst, list):
                        accounts_config = {a["session_name"]: a for a in lst if isinstance(a, dict) and a.get("session_name")}
                if accounts_config:
                    break
        except Exception as e:
            logger.warning("Load config %s: %s", path, e)

    # Загружаем аккаунты и сразу выгружаем в список dict (чтобы не держать сессию и не иметь detached-объектов)
    async with AsyncSessionLocal() as session:
        stmt = select(Account).where(
            and_(Account.status == "active", Account.session_name.in_(allowed))
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()
        accounts_data = [
            {
                "id": a.id,
                "session_name": a.session_name,
                "api_id": a.api_id,
                "api_hash": a.api_hash,
                "string_session": a.string_session,
                "proxy": a.proxy,
            }
            for a in rows
        ]

    if not accounts_data:
        logger.error("В БД Lexus нет активных аккаунтов из allowed_accounts. Проверьте lexus_accounts_config.json и таблицу accounts.")
        return

    logger.info("Загружено Lexus-аккаунтов из БД: %s", len(accounts_data))
    logger.info("=%s", "=" * 79)

    grand_added = 0
    grand_updated = 0
    past_date = datetime.utcnow() - timedelta(days=3)

    for acc in accounts_data:
        account_id = acc["id"]
        session_name = acc["session_name"]
        # Объект-подделку с полями для _create_client
        class _Acc:
            pass
        account = _Acc()
        account.session_name = session_name
        account.api_id = acc["api_id"]
        account.api_hash = acc["api_hash"]
        account.string_session = acc["string_session"]
        account.proxy = acc["proxy"]

        client = None
        try:
            client = await _create_client(account, accounts_config)
            if not client:
                continue
            me = await client.get_me()
            account_name = me.username or me.first_name or session_name
        except Exception as e:
            logger.warning("Аккаунт %s: не удалось подключиться — %s", session_name, e)
            continue

        logger.info("Сканирую диалоги: %s (%s)", account_name, session_name)
        try:
            groups_data = await _collect_postable_groups(client, session_name)
        except Exception as e:
            logger.error("Ошибка при сборе диалогов %s: %s", session_name, e, exc_info=True)
            if client and client.is_connected():
                await client.disconnect()
            continue

        added = 0
        updated = 0

        async with AsyncSessionLocal() as session:
            for g in groups_data:
                username = g["username"]
                title = g["title"]
                members_count = g["members_count"]
                stmt = select(Target).where(Target.username == username)
                result = await session.execute(stmt)
                db_group = result.scalar_one_or_none()

                if not db_group:
                    try:
                        new_group = Target(
                            username=username,
                            title=title,
                            niche=NICHE,
                            status="active",
                            assigned_account_id=account_id,
                            joined_at=past_date,
                            warm_up_until=past_date,
                            can_post=True,
                            members_count=members_count,
                        )
                        session.add(new_group)
                        await session.commit()
                        added += 1
                        logger.info("  Добавлена: %s (%s)", username, (title or "")[:50])
                    except Exception as e:
                        await session.rollback()
                        logger.error("  Ошибка добавления %s: %s", username, e)
                else:
                    changed = False
                    if db_group.status != "active":
                        db_group.status = "active"
                        changed = True
                    if db_group.assigned_account_id != account_id:
                        db_group.assigned_account_id = account_id
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
                            await session.commit()
                            updated += 1
                            logger.info("  Обновлена: %s", username)
                        except Exception as e:
                            await session.rollback()
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

        if client and client.is_connected():
            await client.disconnect()

    logger.info("")
    logger.info("=%s", "=" * 79)
    logger.info("ИТОГ СИНХРОНИЗАЦИИ LEXUS (Sync Dialogs to DB)")
    logger.info("  Добавлено новых групп: %s", grand_added)
    logger.info("  Обновлено групп: %s", grand_updated)
    logger.info("  Всего обработано: %s", grand_added + grand_updated)
    logger.info("=%s", "=" * 79)


if __name__ == "__main__":
    try:
        asyncio.run(sync_lexus_chats())
    except KeyboardInterrupt:
        logger.info("Синхронизация прервана пользователем")
        sys.exit(0)
    except Exception as e:
        logger.error("Фатальная ошибка: %s", e, exc_info=True)
        sys.exit(1)
