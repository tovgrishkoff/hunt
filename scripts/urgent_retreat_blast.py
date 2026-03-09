#!/usr/bin/env python3
"""
Срочная рассылка сообщения про ретритный тур по списку групп / инвайтов.

Использует ОДИН из bali‑аккаунтов из config/bali_accounts_config.json
и данные аккаунта (api_id, api_hash, string_session, proxy) из БД.
"""
import asyncio
import os
import json
import sys
from pathlib import Path
from typing import List, Optional

from telethon import TelegramClient
from telethon.errors import FloodWaitError, UserAlreadyParticipantError
from telethon.sessions import StringSession
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from sqlalchemy.orm import Session

# Гарантируем, что корень проекта в PYTHONPATH (для shared.*)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.database.session import get_db
from shared.database.models import Account

# Список чатов / инвайтов
RAW_LINKS: List[str] = [
    "https://t.me/joinchat/ysYeLNQm4bY0MGZi",
    "https://t.me/travelfriendschat/1",
    "https://t.me/+_KKBalrgAEA3YTUy",
    "https://t.me/mytbilisi_chat",
    "https://t.me/EduVKrym",
    "https://t.me/KrymskiiMost",
    "https://t.me/turkey_hotels_travelask",
    "https://t.me/gofortravel_chat",
    "https://t.me/wrenjapanchat",
    "https://t.me/krasnaya_polyana",
    "https://t.me/Dombay7/1",
    "https://t.me/cyprus_f0rum",
    "https://t.me/dubai_topchat",
    "https://t.me/batumi_group",
    "https://t.me/Phuket",
    "https://t.me/teriberka51",
    "https://t.me/travelchat24",
    "https://t.me/trvlclick_chat",
    "https://t.me/armeniarus_chat",
    "https://t.me/+Bv4qcirDgakxYmUy",
    "https://t.me/travelask_all_chats",
]


def _load_india_retreat_texts() -> List[str]:
    """
    Берём тексты, которые вы уже использовали для набора группы в Индию:
    блоки messages_india_holi.txt и messages_india_retreat.txt из
    config/messages/bali/messages.json.
    """
    messages_path = (
        PROJECT_ROOT / "config" / "messages" / "bali" / "messages.json"
    )
    if not messages_path.exists():
        raise RuntimeError(f"Не найден файл с сообщениями: {messages_path}")

    with messages_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    india_texts: List[str] = []
    for item in data:
        src = item.get("source_file") or ""
        if src in ("messages_india_holi.txt", "messages_india_retreat.txt"):
            text = (item.get("text") or "").strip()
            if text:
                india_texts.append(text)

    if not india_texts:
        raise RuntimeError("В messages.json не найдено текстов для Индии (india_holi / india_retreat)")

    return india_texts


def normalize_link(link: str) -> str:
    link = link.strip()
    if link.startswith("http"):
        link = link.split("?", 1)[0]
    return link


def is_invite_link(link: str) -> bool:
    """joinchat или t.me/+...."""
    return "joinchat" in link or "/+" in link


def extract_invite_hash(link: str) -> str:
    """t.me/+Bv4qcirDgakxYmUy -> Bv4qcirDgakxYmUy"""
    part = link.rsplit("/", 1)[-1]
    return part.lstrip("+")


def extract_username(link: str) -> str:
    """t.me/mytbilisi_chat -> @mytbilisi_chat (обрезаем /1 в конце)"""
    part = link.rsplit("/", 1)[-1]
    if not part:
        raise ValueError(f"Не удалось вытащить username из {link}")
    if "/" in part:
        part = part.split("/", 1)[0]
    if not part.startswith("@"):
        part = "@" + part
    return part


def _parse_proxy(proxy_string: Optional[str]) -> Optional[dict]:
    """Простой разбор строки прокси из БД (socks5/http)."""
    if not proxy_string:
        return None
    try:
        from urllib.parse import urlparse

        parsed = urlparse(proxy_string)
        if not parsed.scheme or not parsed.hostname or not parsed.port:
            return None

        if parsed.scheme == "socks5":
            return {
                "proxy_type": "socks5",
                "addr": parsed.hostname,
                "port": parsed.port,
                "username": parsed.username,
                "password": parsed.password,
            }
        if parsed.scheme in ("http", "https"):
            return {
                "proxy_type": "http",
                "addr": parsed.hostname,
                "port": parsed.port,
                "username": parsed.username,
                "password": parsed.password,
            }
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️ Не удалось распарсить proxy '{proxy_string}': {exc}")
    return None


def _load_bali_accounts_from_db() -> Account:
    """
    Берём список session_name из config/bali_accounts_config.json
    и находим первый активный аккаунт в БД с заполненным string_session.
    """
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "config",
        "bali_accounts_config.json",
    )
    if not os.path.exists(config_path):
        raise RuntimeError(f"Не найден {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    allowed: List[str] = cfg.get("allowed_accounts") or []
    if not allowed:
        raise RuntimeError("В bali_accounts_config.json нет allowed_accounts")

    db_gen = get_db()
    db: Session = next(db_gen)
    try:
        acc: Optional[Account] = (
            db.query(Account)
            .filter(
                Account.session_name.in_(allowed),
                Account.status == "active",
                Account.string_session.isnot(None),
            )
            .order_by(Account.id.asc())
            .first()
        )
    finally:
        db.close()

    if not acc:
        raise RuntimeError(
            "Не найден ни один активный Bali‑аккаунт в БД "
            "из списка allowed_accounts"
        )

    if not acc.api_id or not acc.api_hash or not acc.string_session:
        raise RuntimeError(
            f"У аккаунта {acc.session_name} не заполнены api_id/api_hash/string_session"
        )

    return acc


async def join_and_send() -> None:
    # Берём первый подходящий Bali‑аккаунт из конфига/БД
    account = _load_bali_accounts_from_db()
    proxy_config = _parse_proxy(account.proxy)

    # Готовим пул текстов для Индии (Холи + ретрит)
    india_texts = _load_india_retreat_texts()

    client = TelegramClient(
        StringSession(account.string_session.strip()),
        int(account.api_id),
        account.api_hash,
        proxy=proxy_config,
    )
    await client.start()
    me = await client.get_me()
    print(f"✅ Запускаю рассылку от аккаунта: {getattr(me, 'username', None) or me.id}")

    for raw in RAW_LINKS:
        link = normalize_link(raw)
        try:
            print(f"\n=== Обрабатываю: {link}")

            # 1) Вступаем в чат
            if is_invite_link(link):
                invite_hash = extract_invite_hash(link)
                try:
                    await client(ImportChatInviteRequest(invite_hash))
                    print(f"  ✅ Вступил по инвайту: {link}")
                except UserAlreadyParticipantError:
                    print("  ℹ️ Уже участник (invite)")
            else:
                username = extract_username(link)
                try:
                    await client(JoinChannelRequest(username))
                    print(f"  ✅ Вступил в {username}")
                except UserAlreadyParticipantError:
                    print("  ℹ️ Уже участник (username)")

            # 2) Отправляем сообщение
            try:
                # Берём один из индийских текстов (чтобы в разных чатах чуть различалось)
                import random

                text_to_send = random.choice(india_texts)

                if is_invite_link(link):
                    # После ImportChatInviteRequest entity можно получить по самой ссылке
                    entity = await client.get_entity(link)
                else:
                    username = extract_username(link)
                    entity = await client.get_entity(username)

                await client.send_message(entity, text_to_send)
                print("  ✅ Сообщение отправлено")
            except FloodWaitError as fw:
                print(f"  ⏳ FloodWait {fw.seconds} сек, пропускаю чат")
            except Exception as send_err:  # noqa: BLE001
                print(f"  ❌ Ошибка отправки сообщения: {send_err}")

            # Антиспам‑пауза
            await asyncio.sleep(30)

        except FloodWaitError as fw:
            print(f"⏳ Глобальный FloodWait: {fw.seconds} сек, сплю...")
            await asyncio.sleep(fw.seconds + 5)
        except Exception as err:  # noqa: BLE001
            print(f"❌ Ошибка при обработке {link}: {err}")
            await asyncio.sleep(5)

    await client.disconnect()
    print("\n✅ Скрипт завершил работу")


if __name__ == "__main__":
    asyncio.run(join_and_send())

