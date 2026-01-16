#!/usr/bin/env python3
"""
Тестовый постинг для Ukraine проекта
"""
import sys
import os
import asyncio
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Устанавливаем переменные для Ukraine БД
os.environ['DATABASE_URL'] = 'postgresql://telegram_user_ukraine:telegram_password_ukraine@localhost:5439/ukraine_db'
os.environ['POSTGRES_HOST'] = 'localhost'
os.environ['POSTGRES_PORT'] = '5439'
os.environ['POSTGRES_USER'] = 'telegram_user_ukraine'
os.environ['POSTGRES_PASSWORD'] = 'telegram_password_ukraine'
os.environ['POSTGRES_DB'] = 'ukraine_db'
os.environ['NICHE'] = 'ukraine_cars'
os.environ['PROJECT_NAME'] = 'ukraine'

from services.marketer.poster import SmartPoster as Poster

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_posting():
    """Тестовый постинг для Ukraine"""
    logger.info("=" * 80)
    logger.info("🧪 ТЕСТОВЫЙ ПОСТИНГ UKRAINE")
    logger.info("=" * 80)
    
    poster = Poster('ukraine_cars')
    logger.info(f"✅ Poster создан для ниши: ukraine_cars")
    logger.info(f"✅ Загружено сообщений: {len(poster.posts_config)}")
    
    logger.info("\n📤 Запускаем тестовый постинг (batch_size=3)...")
    await poster.run_batch(batch_size=3)
    
    logger.info("\n✅ Тестовый постинг завершен!")


if __name__ == "__main__":
    try:
        asyncio.run(test_posting())
    except KeyboardInterrupt:
        logger.info("\n🛑 Прервано пользователем")
    except Exception as e:
        logger.error(f"\n❌ Ошибка: {e}", exc_info=True)
