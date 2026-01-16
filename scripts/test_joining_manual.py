#!/usr/bin/env python3
"""
Ручной запуск процесса вступления в группы
Позволяет проверить вступление без ожидания расписания
"""
import asyncio
import sys
import logging
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.database.session import SessionLocal
from shared.config.loader import ConfigLoader
from shared.telegram.client_manager import TelegramClientManager

# Импорт joiner
import importlib.util
joiner_path = Path(__file__).parent.parent / "services" / "account-manager" / "joiner.py"
joiner_spec = importlib.util.spec_from_file_location("joiner", joiner_path)
joiner_module = importlib.util.module_from_spec(joiner_spec)
joiner_spec.loader.exec_module(joiner_module)
GroupJoiner = joiner_module.GroupJoiner

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Ручной запуск вступления в группы"""
    logger.info("=" * 80)
    logger.info("🧪 РУЧНОЙ ЗАПУСК ВСТУПЛЕНИЯ В ГРУППЫ")
    logger.info("=" * 80)
    
    # Загрузка конфигурации
    config_loader = ConfigLoader()
    niche_config = config_loader.load_niche_config()
    niche = niche_config['name']
    
    logger.info(f"📋 Ниша: {niche_config['display_name']} ({niche})")
    
    # Инициализация клиентов
    client_manager = TelegramClientManager()
    db = SessionLocal()
    try:
        await client_manager.load_accounts_from_db(db)
        logger.info(f"✅ Загружено {len(client_manager.clients)} клиентов")
    finally:
        db.close()
    
    if not client_manager.clients:
        logger.error("❌ Нет загруженных клиентов! Проверьте аккаунты в БД.")
        return
    
    # Создание joiner
    joiner = GroupJoiner(client_manager, niche_config)
    
    # Запуск процесса вступления
    logger.info("")
    logger.info("🚪 Запуск процесса вступления...")
    logger.info("")
    
    joined, failed = await joiner.process_new_groups(niche)
    
    logger.info("")
    logger.info("=" * 80)
    logger.info(f"✅ РЕЗУЛЬТАТ: {joined} вступило, {failed} неудач")
    logger.info("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
