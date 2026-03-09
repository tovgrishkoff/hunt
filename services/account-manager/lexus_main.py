#!/usr/bin/env python3
"""
Lexus Account Manager: Поиск и вступление в группы для ukraine_cars
Работает с lexus_db (Async SQLAlchemy)
"""
import asyncio
import sys
import os
import logging
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Импорт scheduler из той же директории
import importlib.util
from pathlib import Path
scheduler_spec = importlib.util.spec_from_file_location("lexus_scheduler", Path(__file__).parent / "lexus_scheduler.py")
lexus_scheduler = importlib.util.module_from_spec(scheduler_spec)
scheduler_spec.loader.exec_module(lexus_scheduler)
LexusAccountManagerScheduler = lexus_scheduler.LexusAccountManagerScheduler

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/logs/lexus_account_manager.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


async def main():
    """Основной цикл работы Lexus Account Manager"""
    logger.info("=" * 80)
    logger.info("🚀 LEXUS ACCOUNT MANAGER - Поиск и вступление в группы")
    logger.info("=" * 80)
    
    scheduler = LexusAccountManagerScheduler()
    
    try:
        await scheduler.run()
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down...")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
