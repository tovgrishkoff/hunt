#!/usr/bin/env python3
"""Напоминания за 2/1/0 день до конца триала + счётчик лидов."""

import asyncio
import logging
import os
from datetime import datetime, timezone

import asyncpg
import requests
from dotenv import load_dotenv

load_dotenv(".env.docker")
load_dotenv(".env")

logger = logging.getLogger(__name__)

DB_HOST = os.getenv("DB_HOST", "localhost")
if DB_HOST == "postgres" and not os.path.exists("/.dockerenv"):
    DB_HOST = "localhost"
DB_PORT = os.getenv("DB_PORT", "5434")
if DB_PORT == "5432" and DB_HOST == "localhost":
    DB_PORT = "5434"
DB_NAME = os.getenv("DB_NAME", "bali_bot")
DB_USER = os.getenv("DB_USER", "grishkoff")
DB_PASSWORD = os.getenv("DB_PASSWORD", "testpass")
BOT_TOKEN = os.getenv("BOT_TOKEN")

REMINDER_COLUMNS = {
    2: "trial_reminder_d2_sent",
    1: "trial_reminder_d1_sent",
    0: "trial_reminder_d0_sent",
}


def _send(user_id: int, text: str, bot_token: str) -> bool:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    keyboard = {
        "inline_keyboard": [
            [{"text": "⭐ Оформить подписку", "callback_data": "pay_subscribe"}],
        ]
    }
    r = requests.post(
        url,
        json={
            "chat_id": user_id,
            "text": text,
            "parse_mode": "HTML",
            "reply_markup": keyboard,
        },
        timeout=15,
    )
    if r.status_code == 200:
        return True
    if "403" in r.text or "blocked" in r.text.lower():
        return False
    logger.error("send failed %s: %s", user_id, r.text)
    return False


async def send_trial_pre_expiry_reminders():
    bot_token = BOT_TOKEN or os.getenv("BOT_TOKEN")
    if not bot_token:
        logger.error("BOT_TOKEN missing")
        return

    dsn = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    conn = await asyncpg.connect(dsn, timeout=10)
    try:
        await conn.execute(
            """
            ALTER TABLE subscribers
            ADD COLUMN IF NOT EXISTS trial_reminder_d2_sent BOOLEAN DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS trial_reminder_d1_sent BOOLEAN DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS trial_reminder_d0_sent BOOLEAN DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS trial_leads_count INTEGER DEFAULT 0,
            ADD COLUMN IF NOT EXISTS bot_blocked BOOLEAN DEFAULT FALSE
            """
        )
        now = datetime.now(timezone.utc)
        rows = await conn.fetch(
            """
            SELECT user_id, trial_until, trial_leads_count, bot_blocked,
                   trial_reminder_d2_sent, trial_reminder_d1_sent, trial_reminder_d0_sent
            FROM subscribers
            WHERE subscription_active IS NOT TRUE
              AND trial_until IS NOT NULL
              AND trial_until > $1
              AND COALESCE(bot_blocked, FALSE) = FALSE
            """,
            now,
        )
        sent = 0
        for row in rows:
            uid = row["user_id"]
            trial_until = row["trial_until"]
            if trial_until.tzinfo is None:
                trial_until = trial_until.replace(tzinfo=timezone.utc)
            days_left = (trial_until.date() - now.date()).days
            if days_left not in REMINDER_COLUMNS:
                continue
            col = REMINDER_COLUMNS[days_left]
            if row.get(col):
                continue
            leads = int(row["trial_leads_count"] or 0)
            if days_left == 0:
                day_word = "Сегодня"
            else:
                day_word = f"Через {days_left} дн."
            text = (
                f"⏳ <b>{day_word} заканчивается триал</b>\n\n"
                f"За триал вы получили <b>{leads}</b> лид(ов).\n"
                "Оформите подписку, чтобы не потерять поток заявок."
            )
            ok = await asyncio.to_thread(_send, uid, text, bot_token)
            if ok:
                await conn.execute(
                    f"UPDATE subscribers SET {col} = TRUE WHERE user_id = $1", uid
                )
                sent += 1
            else:
                await conn.execute(
                    "UPDATE subscribers SET bot_blocked = TRUE WHERE user_id = $1", uid
                )
            await asyncio.sleep(0.4)
        logger.info("Pre-expiry trial reminders sent: %s", sent)
    finally:
        await conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(send_trial_pre_expiry_reminders())
