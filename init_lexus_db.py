#!/usr/bin/env python3
"""
Скрипт инициализации БД для Lexus
Создает таблицы в отдельной БД telegram_promotion_lexus
"""
import asyncio
import sys
from pathlib import Path

# Добавляем корень проекта в путь
sys.path.insert(0, str(Path(__file__).parent))

from lexus_db.session import init_db, get_database_url
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Инициализация БД Lexus"""
    logger.info("=" * 80)
    logger.info("🚀 ИНИЦИАЛИЗАЦИЯ БД LEXUS")
    logger.info("=" * 80)
    
    db_url = get_database_url()
    # Скрываем пароль в логе
    safe_url = db_url.split('@')[0].split('//')[0] + '//***@' + '@'.join(db_url.split('@')[1:])
    logger.info(f"📊 Database URL: {safe_url}")
    
    try:
        await init_db()
        logger.info("✅ БД успешно инициализирована! Таблицы созданы.")
        logger.info("📋 Созданные таблицы:")
        logger.info("   - accounts (аккаунты)")
        logger.info("   - groups (группы/цели)")
        logger.info("   - posts (история постов)")
        logger.info("   - account_group_blocklist (блоклист)")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации БД: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
