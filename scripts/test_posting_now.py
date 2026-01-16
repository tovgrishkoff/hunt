#!/usr/bin/env python3
"""
Быстрый тест постинга прямо сейчас
Имитирует работу слота для проверки на боевой рассылке
"""
import asyncio
import logging
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config.loader import ConfigLoader
from shared.telegram.client_manager import TelegramClientManager
from shared.database.session import SessionLocal, init_db
from services.marketer.poster import Poster

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_posting_now():
    """Тестовый постинг прямо сейчас"""
    logger.info("=" * 80)
    logger.info("🧪 ТЕСТОВЫЙ ПОСТИНГ - ПРЯМО СЕЙЧАС")
    logger.info("=" * 80)
    
    # Инициализация БД
    try:
        init_db()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.warning(f"⚠️ Database already initialized: {e}")
    
    # Загрузка конфигурации
    config_dir = Path(__file__).parent.parent / "config"
    if not config_dir.exists():
        config_dir = Path("/app/config")
    
    config_loader = ConfigLoader(config_dir=str(config_dir))
    niche_config = config_loader.load_niche_config()
    
    logger.info(f"📋 Active niche: {niche_config['display_name']} ({niche_config['name']})")
    
    # Инициализация клиентов
    sessions_dir = Path(__file__).parent.parent / "sessions"
    if not sessions_dir.exists():
        sessions_dir = Path("/app/sessions")
    
    client_manager = TelegramClientManager(sessions_dir=str(sessions_dir))
    db = SessionLocal()
    
    try:
        # Загрузка аккаунтов
        await client_manager.load_accounts_from_db(db)
        if not client_manager.clients:
            logger.error("❌ No active accounts")
            return
        
        logger.info(f"✅ Loaded {len(client_manager.clients)} accounts")
        
    finally:
        db.close()
    
    # Инициализация Poster
    poster = Poster(client_manager, config_loader, niche_config)
    await poster.initialize()
    
    # Запуск постинга для слота "morning" (имитация)
    logger.info("")
    logger.info("=" * 80)
    logger.info("🚀 ЗАПУСК ПОСТИНГА")
    logger.info("=" * 80)
    logger.info(f"⏰ Время: {datetime.now()}")
    logger.info("=" * 80)
    
    try:
        await poster.post_for_slot("morning", niche_config)
        logger.info("")
        logger.info("=" * 80)
        logger.info("✅ ПОСТИНГ ЗАВЕРШЕН")
        logger.info("=" * 80)
    except Exception as e:
        logger.error(f"❌ Ошибка при постинге: {e}", exc_info=True)
        logger.info("")
        logger.info("=" * 80)
        logger.info("❌ ПОСТИНГ ЗАВЕРШИЛСЯ С ОШИБКОЙ")
        logger.info("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_posting_now())
