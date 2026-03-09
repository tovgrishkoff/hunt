#!/usr/bin/env python3
"""
Менеджер аккаунтов: Поиск и вступление в группы
Работает по расписанию Джакартского времени
"""
import asyncio
import sys
import os
import logging
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Импортируем scheduler из той же директории
import importlib.util
scheduler_spec = importlib.util.spec_from_file_location("scheduler", Path(__file__).parent / "scheduler.py")
scheduler = importlib.util.module_from_spec(scheduler_spec)
scheduler_spec.loader.exec_module(scheduler)
AccountManagerScheduler = scheduler.AccountManagerScheduler

# Настройка логирования (подавляем шум Telethon "Got difference for channel")
logging.getLogger("telethon").setLevel(logging.WARNING)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/logs/account_manager.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


async def main():
    """Основной цикл работы Account Manager"""
    logger.info("=" * 80)
    logger.info("🚀 ACCOUNT MANAGER - Поиск и вступление в группы")
    logger.info("=" * 80)
    
    scheduler = AccountManagerScheduler()
    
    try:
        await scheduler.run()
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down...")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())

