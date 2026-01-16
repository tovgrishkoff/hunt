#!/usr/bin/env python3
"""
Скрипт для поиска украинских групп по всем ключевым словам из конфига cars.json
"""
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config.loader import ConfigLoader
from shared.telegram.client_manager import TelegramClientManager
from shared.database.session import SessionLocal, init_db
from shared.database.models import Account
import importlib.util
from pathlib import Path

# Импорт finder из account-manager (с дефисом)
finder_spec = importlib.util.spec_from_file_location(
    "finder",
    Path(__file__).parent.parent / "services" / "account-manager" / "finder.py"
)
finder_module = importlib.util.module_from_spec(finder_spec)
finder_spec.loader.exec_module(finder_module)
GroupFinder = finder_module.GroupFinder

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def search_ukraine_groups():
    """Поиск украинских групп по всем ключевым словам"""
    logger.info("=" * 80)
    logger.info("🔍 ПОИСК УКРАИНСКИХ ГРУПП")
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
    
    # Получаем ключевые слова
    manager_config = niche_config.get('manager', {})
    search_keywords = manager_config.get('search_keywords', [])
    
    if not search_keywords:
        logger.error("❌ No search keywords in config")
        return
    
    logger.info(f"📝 Ключевых слов для поиска: {len(search_keywords)}")
    for kw in search_keywords:
        logger.info(f"  • {kw}")
    
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
        
        # Выбираем первый активный аккаунт
        account = db.query(Account).filter(Account.status == 'active').first()
        if not account:
            logger.error("❌ No active accounts")
            return
        
        logger.info(f"👤 Using account: {account.session_name}")
        
        # Получаем клиент и проверяем подключение
        client = client_manager.clients.get(account.session_name)
        if not client:
            logger.error(f"❌ Client {account.session_name} not found")
            return
        
        # Проверяем и переподключаем при необходимости
        if not client.is_connected():
            logger.info("🔄 Client disconnected, reconnecting...")
            client = await client_manager.ensure_client_connected(account.session_name)
            if not client:
                logger.error(f"❌ Failed to connect client {account.session_name}")
                return
        
        logger.info("✅ Client connected and ready")
        
        # Инициализация Finder
        finder = GroupFinder(client_manager)
        
        # Выполняем поиск
        logger.info("")
        logger.info("=" * 80)
        logger.info("🔍 НАЧАЛО ПОИСКА")
        logger.info("=" * 80)
        
        found_groups = await finder.search_groups(client, search_keywords, limit_per_keyword=20)
        
        logger.info("")
        logger.info("=" * 80)
        logger.info("📊 РЕЗУЛЬТАТЫ ПОИСКА")
        logger.info("=" * 80)
        
        if found_groups:
            logger.info(f"✅ Найдено групп: {len(found_groups)}")
            
            # Сохраняем в БД
            niche = niche_config['name']
            saved = finder.save_groups_to_db(found_groups, niche)
            logger.info(f"💾 Сохранено в БД: {saved} новых групп")
            
            # Выводим список найденных групп
            logger.info("")
            logger.info("📋 Найденные группы:")
            for group_info in found_groups:
                logger.info(f"  • {group_info.get('username')} - {group_info.get('title', 'No title')} "
                          f"(найдено по: {group_info.get('found_by', 'unknown')})")
        else:
            logger.warning("⚠️ Группы не найдены")
        
        logger.info("=" * 80)
        logger.info("✅ ПОИСК ЗАВЕРШЕН")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"❌ Ошибка при поиске: {e}", exc_info=True)
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(search_ukraine_groups())
