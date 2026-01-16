#!/usr/bin/env python3
"""
Скрипт для принудительного запуска постинга
Запускает цикл постинга независимо от расписания
"""
import asyncio
import sys
import os
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent))

from services.marketer.poster import SmartPoster as Poster
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


async def main():
    """Принудительный запуск постинга"""
    logger.info("=" * 80)
    logger.info("🚀 FORCE POSTING - Принудительный запуск постинга")
    logger.info("=" * 80)
    
    # Определяем нишу
    niche = os.getenv('NICHE', 'bali')
    logger.info(f"📋 Ниша: {niche}")
    
    # Создаем постер
    poster = Poster(niche)
    
    # Запускаем батч постинга (большой батч чтобы обработать все группы)
    batch_size = 50  # Большой батч для теста
    logger.info(f"📊 Размер батча: {batch_size}")
    
    try:
        await poster.run_batch(batch_size=batch_size)
        logger.info("✅ Постинг завершен")
    except Exception as e:
        logger.error(f"❌ Ошибка при постинге: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
