#!/usr/bin/env python3
"""Периодический запуск subscription_reminders (каждый час)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from subscription_reminders import run_subscription_reminders

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("subscription_reminders.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


async def reminder_service_loop() -> None:
    logger.info("🚀 Сервис subscription_reminders запущен")
    logger.info("📅 Первый запуск: %s", datetime.now())
    while True:
        try:
            await run_subscription_reminders()
            wait_seconds = 60 * 60
            logger.info("⏳ Следующая проверка через 1 час...")
            await asyncio.sleep(wait_seconds)
        except KeyboardInterrupt:
            logger.info("🛑 Сервис остановлен пользователем")
            break
        except Exception as e:
            logger.error("❌ Ошибка при запуске subscription_reminders: %s", e)
            import traceback

            logger.error(traceback.format_exc())
            logger.info("⏳ Повтор через 15 минут...")
            await asyncio.sleep(15 * 60)


if __name__ == "__main__":
    asyncio.run(reminder_service_loop())
