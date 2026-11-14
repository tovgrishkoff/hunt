#!/usr/bin/env python3
"""Напоминания пользователям с истекшей платной подпиской Lead Hunter."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timedelta, timezone

import asyncpg
import requests
from dotenv import load_dotenv

load_dotenv(".env.docker")
load_dotenv(".env")
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("subscription_reminders.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("subscription_reminders")

DB_HOST = os.getenv("DB_HOST", "localhost")
if DB_HOST == "postgres" and not os.path.exists("/.dockerenv"):
    DB_HOST = "localhost"
DB_PORT = os.getenv("DB_PORT", "5434")
if DB_PORT == "5432" and DB_HOST == "localhost":
    DB_PORT = "5434"
DB_NAME = os.getenv("DB_NAME", "bali_bot")
DB_USER = os.getenv("DB_USER", "grishkoff")
DB_PASSWORD = os.getenv("DB_PASSWORD", "testpass")
BOT_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("MAIN_BOT_TOKEN")
MANAGER_USERNAME = os.getenv("MANAGER_USERNAME", "huansya0").lstrip("@")
MANAGER_URL = f"https://t.me/{MANAGER_USERNAME}"

# Не спамим чаще раза в N дней
REMINDER_INTERVAL_DAYS = int(os.getenv("SUB_REMINDER_INTERVAL_DAYS", "3"))
MAX_REMINDERS = int(os.getenv("SUB_REMINDER_MAX", "5"))

MESSAGE = f"""👋 Привет!

Срок платной подписки Lead Hunter закончился — заявки больше не приходят.

Чтобы снова получать лиды по вашим нишам, продлите подписку:
• /subscribe — оплата Stars
• или напишите менеджеру @{MANAGER_USERNAME} (укажите ваш ID)

Если ниши уже выбраны, после оплаты всё продолжится автоматически.
"""


async def ensure_tracking(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reminder_tracking (
            user_id BIGINT PRIMARY KEY,
            last_reminder_sent TIMESTAMPTZ,
            reminder_count INTEGER DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )


async def fetch_expired_subscribers(conn: asyncpg.Connection) -> list:
    now = datetime.now(timezone.utc)
    min_gap = now - timedelta(days=REMINDER_INTERVAL_DAYS)
    return await conn.fetch(
        """
        SELECT s.user_id, s.subscription_until, s.categories,
               COALESCE(rt.reminder_count, 0) AS reminder_count,
               rt.last_reminder_sent
        FROM subscribers s
        LEFT JOIN reminder_tracking rt ON rt.user_id = s.user_id
        WHERE s.subscription_until IS NOT NULL
          AND s.subscription_until < $1
          AND COALESCE(s.bot_blocked, false) = false
          AND (
                s.subscription_active IS TRUE
                OR s.subscription IS TRUE
                OR s.last_payment_at IS NOT NULL
              )
          AND COALESCE(rt.reminder_count, 0) < $2
          AND (rt.last_reminder_sent IS NULL OR rt.last_reminder_sent < $3)
        ORDER BY s.subscription_until ASC
        LIMIT 100
        """,
        now,
        MAX_REMINDERS,
        min_gap,
    )


def send_message(user_id: int) -> bool:
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN missing")
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": user_id,
        "text": MESSAGE.strip(),
        "reply_markup": {
            "inline_keyboard": [
                [{"text": "⭐ Продлить подписку", "callback_data": "pay_subscribe"}],
                [{"text": "💬 Написать менеджеру", "url": MANAGER_URL}],
            ]
        },
    }
    try:
        r = requests.post(url, json=payload, timeout=20)
        data = r.json() if r.content else {}
        if r.status_code == 200 and data.get("ok"):
            return True
        desc = data.get("description") or r.text
        if "blocked" in str(desc).lower() or "deactivated" in str(desc).lower():
            logger.warning("User %s blocked bot: %s", user_id, desc)
        else:
            logger.error("Send fail %s: %s", user_id, desc)
        return False
    except Exception as e:
        logger.error("Send exception %s: %s", user_id, e)
        return False


async def mark_sent(conn: asyncpg.Connection, user_id: int) -> None:
    await conn.execute(
        """
        INSERT INTO reminder_tracking (user_id, last_reminder_sent, reminder_count, created_at)
        VALUES ($1, NOW(), 1, NOW())
        ON CONFLICT (user_id) DO UPDATE
        SET last_reminder_sent = NOW(),
            reminder_count = COALESCE(reminder_tracking.reminder_count, 0) + 1
        """,
        user_id,
    )


async def mark_blocked(conn: asyncpg.Connection, user_id: int) -> None:
    await conn.execute(
        "UPDATE subscribers SET bot_blocked = TRUE WHERE user_id = $1",
        user_id,
    )


async def run_subscription_reminders() -> None:
    logger.info("🚀 Запуск сервиса напоминаний по истекшим подпискам")
    dsn = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    conn = await asyncpg.connect(dsn, timeout=15)
    try:
        logger.info("✅ Подключено к базе данных")
        await ensure_tracking(conn)
        users = await fetch_expired_subscribers(conn)
        logger.info("📊 Найдено %s пользователей с истекшей подпиской", len(users))
        sent = 0
        for row in users:
            uid = int(row["user_id"])
            ok = send_message(uid)
            if ok:
                await mark_sent(conn, uid)
                sent += 1
            else:
                # soft: if clearly blocked, flag
                pass
            time.sleep(0.4)
        logger.info("✅ Отправлено напоминаний: %s / %s", sent, len(users))
    finally:
        await conn.close()


async def main() -> None:
    try:
        await run_subscription_reminders()
    except Exception as e:
        logger.error("❌ Критическая ошибка в subscription_reminders: %s", e)
        raise


if __name__ == "__main__":
    asyncio.run(main())
