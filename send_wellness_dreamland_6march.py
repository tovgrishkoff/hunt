#!/usr/bin/env python3
"""
Рассылка в чаты Бали: wellness-съёмка на пляже Дримленд, 6 марта.
Контакт: @sofyasvetlaya

Аккаунты: из config/bali_accounts_config.json (allowed_accounts).
Группы: config/bali_mailing_groups.json.
Данные аккаунтов: accounts_config.json.
"""
import asyncio
import json
import logging
import random
from pathlib import Path
from typing import List, Optional

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    FloodWaitError,
    RPCError,
    ChatWriteForbiddenError,
    UserBannedInChannelError,
)

# Варианты сообщения про wellness-фото 6 марта
WELLNESS_MESSAGES: List[str] = [
    """Ищем девушек, кто хотел получить красивые фото в wellness-тематике) Создаём контент для сайта и ищем тех, кто хотел бы поучаствовать и получить классный контент для себя.

С вас — присутствие, с нас — красивые фото и видео, в том числе на коптер.

Локация: пляж Дримленд, 6 марта.
Референсы прикрепляем.
Чтобы попасть, напишите нашему арт-директору @sofyasvetlaya""",
    """Девушки, кто хочет красивые фото в wellness-тематике? Делаем контент для сайта и ищем участниц — с вас присутствие, с нас фото и видео (в т.ч. на коптер).

Пляж Дримленд, 6 марта. Референсы прикрепляем.
Записаться: @sofyasvetlaya""",
]

DELAY_BETWEEN_POSTS = (60, 120)  # 1–2 минуты между постами
DELAY_BETWEEN_ACCOUNTS = (300, 600)  # 5–10 минут между аккаунтами

PROJECT_ROOT = Path(__file__).resolve().parent


def setup_logging() -> logging.Logger:
    """Настройка логирования."""
    logs_dir = PROJECT_ROOT / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "wellness_dreamland_6march.log"

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
    """Парсинг прокси из строки (http/socks5)."""
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


def load_mailing_groups() -> List[str]:
    """Загрузить список групп из config/bali_mailing_groups.json."""
    for path in [
        PROJECT_ROOT / "config" / "bali_mailing_groups.json",
        Path("config/bali_mailing_groups.json"),
    ]:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("groups", [])
    raise FileNotFoundError(
        "Не найден config/bali_mailing_groups.json. Создайте файл со списком groups."
    )


def load_bali_allowed_accounts() -> List[str]:
    """Загрузить allowed_accounts из config/bali_accounts_config.json."""
    for path in [
        PROJECT_ROOT / "config" / "bali_accounts_config.json",
        PROJECT_ROOT / "bali_accounts_config.json",
        Path("config/bali_accounts_config.json"),
        Path("bali_accounts_config.json"),
    ]:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("allowed_accounts", [])
    return []


def load_accounts_config() -> List[dict]:
    """Загрузить accounts_config.json (все аккаунты с api_id, api_hash, string_session)."""
    for path in [
        PROJECT_ROOT / "accounts_config.json",
        Path("accounts_config.json"),
    ]:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    raise FileNotFoundError("Не найден accounts_config.json")


async def send_message_to_group(
    client: TelegramClient,
    account_name: str,
    group_username: str,
    message: str,
    logger: logging.Logger,
) -> bool:
    """Отправить сообщение в группу."""
    try:
        entity = await client.get_entity(group_username)
        await client.send_message(entity, message)
        logger.info(f"  ✅ Отправлено в @{group_username}")
        return True
    except ChatWriteForbiddenError:
        logger.warning(f"  ⚠️ Нет прав на отправку в @{group_username}")
        return False
    except UserBannedInChannelError:
        logger.warning(f"  ⚠️ Забанен в @{group_username}")
        return False
    except FloodWaitError as e:
        logger.warning(f"  ⚠️ FloodWait: {e.seconds} секунд")
        await asyncio.sleep(e.seconds)
        return False
    except RPCError as e:
        logger.error(f"  ❌ Ошибка: {e}")
        return False
    except Exception as e:
        logger.error(f"  ❌ Неожиданная ошибка: {e}")
        return False


async def send_messages_for_account(
    account: dict,
    groups: List[str],
    logger: logging.Logger,
) -> None:
    """Отправка сообщений для одного аккаунта."""
    account_name = account["session_name"]
    logger.info("\n" + "=" * 80)
    logger.info(f"📱 АККАУНТ: {account_name} ({account.get('nickname', 'N/A')})")
    logger.info("=" * 80)

    proxy = parse_proxy(account.get("proxy"))
    string_session = (account.get("string_session") or "").strip()
    if not string_session or string_session in ("", "null", "TO_BE_CREATED"):
        logger.error(f"❌ Нет валидной string_session для {account_name}")
        return

    client = TelegramClient(
        StringSession(string_session),
        int(account["api_id"]),
        account["api_hash"],
        proxy=proxy,
    )

    try:
        await client.connect()
        logger.info(f"✅ Подключен {account_name}")

        if not await client.is_user_authorized():
            logger.error(f"❌ {account_name} не авторизован")
            return

        me = await client.get_me()
        username = getattr(me, "username", "No username")
        logger.info(f"👤 Авторизован как: @{username}")

        message = random.choice(WELLNESS_MESSAGES)
        logger.info(f"📝 Сообщение выбрано (длина: {len(message)} символов)")

        sent_count = 0
        failed_count = 0

        for i, group_link in enumerate(groups, 1):
            group_username = (
                group_link.replace("https://t.me/", "")
                .replace("http://t.me/", "")
                .strip("/")
            )
            if group_username.startswith("+"):
                logger.warning(f"  ⚠️ Пропускаю invite link: {group_link}")
                continue

            logger.info(f"\n[{i}/{len(groups)}] @{group_username}")

            success = await send_message_to_group(
                client, account_name, group_username, message, logger
            )
            if success:
                sent_count += 1
            else:
                failed_count += 1

            if i < len(groups):
                delay = random.randint(*DELAY_BETWEEN_POSTS)
                logger.info(f"⏸️ Пауза {delay} секунд перед следующим постом...")
                await asyncio.sleep(delay)

        logger.info("\n" + "=" * 80)
        logger.info(f"📊 ИТОГИ для {account_name}:")
        logger.info(f"  ✅ Отправлено: {sent_count}")
        logger.info(f"  ❌ Не удалось: {failed_count}")
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"❌ Критическая ошибка для {account_name}: {e}")
        import traceback

        traceback.print_exc()
    finally:
        await client.disconnect()
        logger.info(f"🔌 Отключен {account_name}")


async def main() -> None:
    """Основная функция: загрузка конфигов и рассылка по аккаунтам."""
    logger = setup_logging()

    logger.info("\n" + "=" * 80)
    logger.info("📨 РАССЫЛКА: Wellness-фото пляж Дримленд, 6 марта (@sofyasvetlaya)")
    logger.info("=" * 80)

    groups = load_mailing_groups()
    allowed = load_bali_allowed_accounts()
    all_accounts = load_accounts_config()

    accounts_to_use = [
        acc for acc in all_accounts if acc.get("session_name") in allowed
    ]

    if not accounts_to_use:
        logger.error(
            "❌ Нет аккаунтов для рассылки. Проверьте config/bali_accounts_config.json "
            "и accounts_config.json."
        )
        return

    logger.info(f"📋 Групп для рассылки: {len(groups)}")
    logger.info(f"👤 Аккаунтов: {len(accounts_to_use)}")
    logger.info("=" * 80)

    for i, account in enumerate(accounts_to_use, 1):
        await send_messages_for_account(account, groups, logger)
        if i < len(accounts_to_use):
            delay = random.randint(*DELAY_BETWEEN_ACCOUNTS)
            logger.info(
                f"\n⏸️ Пауза {delay // 60} мин перед следующим аккаунтом..."
            )
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
