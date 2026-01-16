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

# Добавляем путь к shared модулям
sys.path.insert(0, '/app')

from shared.database.session import get_db, init_db
from shared.config.loader import ConfigLoader
from shared.telegram.client_manager import TelegramClientManager
from services.account_manager.joiner import GroupJoiner

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/logs/account-manager.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


async def main():
    """Основной цикл работы менеджера аккаунтов"""
    logger.info("=" * 80)
    logger.info("🚀 ACCOUNT MANAGER - Поиск и вступление в группы")
    logger.info("=" * 80)
    
    # Инициализация БД
    try:
        init_db()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize database: {e}")
        return
    
    # Загрузка конфигурации
    config_loader = ConfigLoader()
    niche_config = config_loader.load_niche_config()
    logger.info(f"📋 Active niche: {niche_config['display_name']} ({niche_config['name']})")
    
    # Инициализация клиентов
    client_manager = TelegramClientManager()
    db_gen = get_db()
    db = next(db_gen)
    try:
        await client_manager.load_accounts_from_db(db)
        logger.info(f"✅ Loaded {len(client_manager.clients)} accounts")
    except Exception as e:
        logger.error(f"❌ Failed to load accounts: {e}")
        return
    finally:
        db.close()
    
    # Инициализация джойнера
    joiner = GroupJoiner(client_manager, config_loader, niche_config)
    
    # Запуск цикла поиска и вступления
    try:
        await joiner.run()
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down...")
    finally:
        await client_manager.disconnect_all()


if __name__ == "__main__":
    asyncio.run(main())

