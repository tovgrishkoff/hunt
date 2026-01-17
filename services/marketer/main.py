#!/usr/bin/env python3
"""
Маркетолог: Постинг объявлений по расписанию
"""
import asyncio
import sys
import os
import logging
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from services.marketer.scheduler import MarketerScheduler
from services.marketer.poster import SmartPoster

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/logs/marketer.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


async def main():
    """
    Основной режим: планировщик постинга.

    Разовый режим (ручной запуск):
      python3 main.py <ниша> <размер_батча>
    пример:
      python3 main.py bali 20
    """
    logger.info("=" * 80)
    logger.info("🚀 MARKETER - Постинг объявлений")
    logger.info("=" * 80)

    # Разовый запуск: python3 main.py bali 20
    if len(sys.argv) >= 3:
        niche = sys.argv[1]
        batch_size = int(sys.argv[2])
        logger.info(f"🟡 One-shot mode: niche={niche}, batch_size={batch_size}")
        poster = SmartPoster(niche=niche)
        await poster.run_batch(batch_size=batch_size)
        logger.info("✅ One-shot mode completed")
        return

    scheduler = MarketerScheduler()
    try:
        await scheduler.run()
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down...")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())

