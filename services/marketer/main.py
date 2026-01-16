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
    """Основной цикл работы маркетолога"""
    logger.info("=" * 80)
    logger.info("🚀 MARKETER - Постинг объявлений")
    logger.info("=" * 80)
    
    scheduler = MarketerScheduler()
    
    try:
        await scheduler.run()
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down...")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())

