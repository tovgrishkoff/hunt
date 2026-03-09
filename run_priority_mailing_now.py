#!/usr/bin/env python3
"""
Немедленная рассылка приоритетных сообщений во все чаты, куда вступили аккаунты и могут писать.

Для каждого аккаунта собираются из диалогов все группы/супергруппы с правом отправки сообщений
(не только балийские) — рассылка идёт по этому списку.

Сообщения: messages_bali_retreat.txt, messages_tibet_kailash.txt,
messages_wellness_dreamland_6march.txt из bali_assets/messages.json.
С фото, если в сообщении указано photo.

Запуск: из корня проекта
  cd /home/tovgrishkoff/PIAR/telegram_promotion_system_bali
  python3 run_priority_mailing_now.py

Аккаунты загружаются из БД (niche=bali, status=active), как и остальные сервисы.
"""
import asyncio
import json
import logging
import random
import sys
from pathlib import Path
from typing import List, Optional, Dict, Any

# Корень проекта для импорта shared (БД)
_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import Channel, Chat
from telethon.errors import (
    FloodWaitError,
    RPCError,
    ChatWriteForbiddenError,
    UserBannedInChannelError,
    ChatSendMediaForbiddenError,
)

# source_file из блока 3284–3546 (ретрит Бали, Тибет/Кайлас, wellness Дримленд)
PRIORITY_SOURCE_FILES = [
    "messages_bali_retreat.txt",
    "messages_tibet_kailash.txt",
    "messages_wellness_dreamland_6march.txt",
]

DELAY_BETWEEN_POSTS = (45, 90)  # секунды между постами
DELAY_BETWEEN_ACCOUNTS = (180, 360)  # 3–6 минут между аккаунтами

PROJECT_ROOT = _PROJECT_ROOT


def setup_logging() -> logging.Logger:
    """Настройка логирования."""
    logs_dir = PROJECT_ROOT / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "priority_mailing_now.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    return logging.getLogger(__name__)


def parse_proxy(proxy_config: Optional[str]) -> Optional[dict]:
    """Парсинг прокси из строки."""
    if not proxy_config:
        return None
    if isinstance(proxy_config, dict):
        return proxy_config
    try:
        from urllib.parse import urlparse
        parsed = urlparse(proxy_config)
        proxy_type = (parsed.scheme or "http").lower()
        host = parsed.hostname
        port = parsed.port or (8080 if proxy_type in ("http", "https") else 1080)
        if not host or not port:
            return None
        out: dict = {"proxy_type": "http", "addr": host, "port": port}
        if parsed.username:
            out["username"] = parsed.username
        if parsed.password:
            out["password"] = parsed.password
        return out
    except Exception:
        return None


def load_priority_messages() -> List[Dict[str, Any]]:
    """Загрузить из bali_assets/messages.json только приоритетные сообщения."""
    for path in [
        PROJECT_ROOT / "bali_assets" / "messages.json",
        Path("bali_assets/messages.json"),
    ]:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                all_msgs = json.load(f)
            out = [
                m for m in all_msgs
                if m.get("source_file") in PRIORITY_SOURCE_FILES
            ]
            return out
    raise FileNotFoundError("Не найден bali_assets/messages.json")


def resolve_photo_path(photo: Optional[str], logger: logging.Logger) -> Optional[Path]:
    """Найти файл фото на диске (локально или /app в Docker)."""
    if not photo or not str(photo).strip():
        return None
    photo = str(photo).strip()
    candidates = [
        PROJECT_ROOT / photo,
        PROJECT_ROOT / "bali_assets" / Path(photo).name,
        Path(photo),
        Path("/app") / photo,
        Path("/app/bali_assets") / Path(photo).name,
    ]
    for p in candidates:
        if p.exists():
            return p
    logger.warning(f"  ⚠️ Фото не найдено: {photo}, отправляю только текст")
    return None


def _is_group_or_megagroup(entity) -> bool:
    """Только группы и супергруппы; не каналы (broadcast), не личка."""
    if isinstance(entity, Chat):
        return True
    if isinstance(entity, Channel):
        if getattr(entity, "broadcast", False):
            return False
        return bool(getattr(entity, "megagroup", False))
    return False


async def _can_send_messages(client: TelegramClient, entity) -> bool:
    """Проверка права на отправку сообщений в чате."""
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
    except Exception:
        return False


async def get_postable_groups_from_dialogs(
    client: TelegramClient,
    logger: logging.Logger,
    limit: Optional[int] = None,
) -> List[str]:
    """
    Собрать из диалогов аккаунта все группы/супергруппы, где можно писать.
    Возвращает список username (без @) для отправки.
    """
    result = []
    count = 0
    async for dialog in client.iter_dialogs():
        if limit and count >= limit:
            break
        entity = dialog.entity
        if not _is_group_or_megagroup(entity):
            continue
        if getattr(entity, "left", False) or getattr(entity, "kicked", False):
            continue
        username = getattr(entity, "username", None)
        if not username:
            continue
        username = username.lstrip("@")
        if not await _can_send_messages(client, entity):
            continue
        result.append(username)
        count += 1
    return result


def load_accounts_from_db() -> List[dict]:
    """
    Загрузить Bali-аккаунты из БД (как marketer, activity, daily_check).
    Возвращает список словарей: session_name, api_id, api_hash, string_session, proxy, nickname.
    Аккаунты без string_session пропускаются.
    """
    from shared.database.session import SessionLocal
    from shared.database.models import Account

    db = SessionLocal()
    try:
        rows = (
            db.query(Account)
            .filter(Account.status == "active", Account.niche == "bali")
            .all()
        )
        out = []
        for a in rows:
            ss = (a.string_session or "").strip()
            if not ss or ss in ("", "null", "TO_BE_CREATED"):
                continue
            out.append({
                "session_name": a.session_name,
                "api_id": a.api_id,
                "api_hash": a.api_hash,
                "string_session": ss,
                "proxy": a.proxy,
                "nickname": getattr(a, "nickname", None),
            })
        return out
    finally:
        db.close()


async def send_post_to_group(
    client: TelegramClient,
    account_name: str,
    group_username: str,
    text: str,
    photo_path: Optional[Path],
    logger: logging.Logger,
) -> bool:
    """Отправить пост в группу (с фото или только текст)."""
    try:
        entity = await client.get_entity(group_username)
        if photo_path:
            try:
                await client.send_file(entity, str(photo_path), caption=text)
                logger.info(f"  ✅ Отправлено (с фото) в @{group_username}")
                return True
            except ChatSendMediaForbiddenError:
                logger.warning(f"  ⚠️ В группе нельзя медиа, отправляю текст в @{group_username}")
                await client.send_message(entity, text)
                logger.info(f"  ✅ Отправлено (только текст) в @{group_username}")
                return True
        else:
            await client.send_message(entity, text)
            logger.info(f"  ✅ Отправлено в @{group_username}")
            return True
    except ChatWriteForbiddenError:
        logger.warning(f"  ⚠️ Нет прав на отправку в @{group_username}")
        return False
    except UserBannedInChannelError:
        logger.warning(f"  ⚠️ Забанен в @{group_username}")
        return False
    except FloodWaitError as e:
        logger.warning(f"  ⚠️ FloodWait: {e.seconds} сек")
        await asyncio.sleep(e.seconds)
        return False
    except RPCError as e:
        logger.error(f"  ❌ Ошибка: {e}")
        return False
    except Exception as e:
        logger.error(f"  ❌ Неожиданная ошибка: {e}")
        return False


async def run_mailing_for_account(
    account: dict,
    messages: List[Dict[str, Any]],
    logger: logging.Logger,
) -> None:
    """Рассылка для одного аккаунта: собираем все чаты из диалогов, где можно писать, и постим в каждый."""
    account_name = account["session_name"]
    logger.info("\n" + "=" * 80)
    logger.info(f"📱 АККАУНТ: {account_name}")
    logger.info("=" * 80)

    proxy = parse_proxy(account.get("proxy"))
    string_session = (account.get("string_session") or "").strip()
    if not string_session or string_session in ("", "null", "TO_BE_CREATED"):
        logger.error(f"❌ Нет string_session для {account_name}")
        return

    client = TelegramClient(
        StringSession(string_session),
        int(account["api_id"]),
        account["api_hash"],
        proxy=proxy,
    )

    try:
        await client.connect()
        if not await client.is_user_authorized():
            logger.error(f"❌ {account_name} не авторизован")
            return
        me = await client.get_me()
        logger.info(f"👤 Авторизован как: @{getattr(me, 'username', '?')}")

        logger.info("📂 Собираю список чатов из диалогов (группы, где можно писать)...")
        groups = await get_postable_groups_from_dialogs(client, logger)
        logger.info(f"📋 Найдено групп для рассылки: {len(groups)}")

        if not groups:
            logger.warning(f"  ⚠️ У {account_name} нет групп с правом отправки. Пропуск.")
            return

        sent_count = 0
        failed_count = 0

        for i, group_username in enumerate(groups, 1):
            # group_username уже без @, get_entity принимает и так и так
            msg = random.choice(messages)
            text = (msg.get("text") or "").strip()
            if not text:
                continue
            photo = msg.get("photo") or msg.get("image")
            photo_path = resolve_photo_path(photo, logger)

            logger.info(f"\n[{i}/{len(groups)}] @{group_username} ({msg.get('source_file', '?')})")

            ok = await send_post_to_group(
                client, account_name, group_username, text, photo_path, logger
            )
            if ok:
                sent_count += 1
            else:
                failed_count += 1

            if i < len(groups):
                delay = random.randint(*DELAY_BETWEEN_POSTS)
                await asyncio.sleep(delay)

        logger.info("\n" + "=" * 80)
        logger.info(f"📊 ИТОГИ {account_name}: ✅ {sent_count}  ❌ {failed_count}")
        logger.info("=" * 80)
    except Exception as e:
        logger.error(f"❌ Ошибка для {account_name}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.disconnect()
        logger.info(f"🔌 Отключен {account_name}")


async def main() -> None:
    logger = setup_logging()
    logger.info("\n" + "=" * 80)
    logger.info("📨 НЕМЕДЛЕННАЯ РАССЫЛКА: ретрит Бали 8 марта, Тибет/Кайлас, wellness Дримленд")
    logger.info("=" * 80)

    messages = load_priority_messages()
    logger.info(f"📝 Сообщений в пуле: {len(messages)}")

    accounts_to_use = load_accounts_from_db()
    if not accounts_to_use:
        logger.error(
            "❌ Нет аккаунтов с string_session в БД (niche=bali, status=active). "
            "Синхронизируйте конфиг с БД: python3 scripts/update_all_accounts_from_config.py"
        )
        return
    if not messages:
        logger.error("❌ Нет приоритетных сообщений в messages.json")
        return

    logger.info("📋 Для каждого аккаунта группы берутся из диалогов (все чаты, где можно писать)")
    logger.info(f"👤 Аккаунтов: {len(accounts_to_use)}")
    logger.info("=" * 80)

    for i, account in enumerate(accounts_to_use, 1):
        await run_mailing_for_account(account, messages, logger)
        if i < len(accounts_to_use):
            delay = random.randint(*DELAY_BETWEEN_ACCOUNTS)
            logger.info(f"\n⏸️ Пауза {delay // 60} мин до следующего аккаунта...")
            await asyncio.sleep(delay)

    logger.info("\n" + "=" * 80)
    logger.info("✅ РАССЫЛКА ЗАВЕРШЕНА")
    logger.info("=" * 80)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️ Прервано пользователем")
    except Exception as e:
        print(f"\n\n❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
