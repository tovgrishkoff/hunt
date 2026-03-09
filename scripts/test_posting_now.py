#!/usr/bin/env python3
"""
Быстрый тест постинга прямо сейчас
Имитирует работу слота для проверки на боевой рассылке.
Использует SmartPoster (как marketer в Docker).
"""
import asyncio
import logging
import os
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def test_posting_now():
    """Тестовый постинг прямо сейчас"""
    logger.info("=" * 80)
    logger.info("🧪 ТЕСТОВЫЙ ПОСТИНГ - ПРЯМО СЕЙЧАС")
    logger.info("=" * 80)

    niche = os.getenv("NICHE", "bali")
    logger.info(f"📋 Ниша: {niche}")
    logger.info(f"⏰ Время: {datetime.now()}")

    from services.marketer.poster import SmartPoster

    poster = SmartPoster(niche=niche)
    batch_size = 30

    logger.info("")
    logger.info("=" * 80)
    logger.info("🚀 ЗАПУСК ПОСТИНГА")
    logger.info("=" * 80)

    try:
        await poster.run_batch(batch_size=batch_size)
        logger.info("")
        logger.info("=" * 80)
        logger.info("✅ ПОСТИНГ ЗАВЕРШЕН")
        logger.info("=" * 80)
    except Exception as e:
        logger.error(f"❌ Ошибка при постинге: {e}", exc_info=True)
        logger.info("=" * 80)
        logger.info("❌ ПОСТИНГ ЗАВЕРШИЛСЯ С ОШИБКОЙ")
        logger.info("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_posting_now())
