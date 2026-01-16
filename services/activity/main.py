#!/usr/bin/env python3
"""
Activity Service: Просмотр Stories участников групп
Работает в фоновом режиме, параллельно с постингом
"""
import asyncio
import sys
import logging
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.telegram.client_manager import TelegramClientManager
from shared.database.session import SessionLocal
from shared.config.loader import ConfigLoader

# Импортируем модули из той же директории
import importlib.util
story_viewer_spec = importlib.util.spec_from_file_location("story_viewer", Path(__file__).parent / "story_viewer.py")
story_viewer_module = importlib.util.module_from_spec(story_viewer_spec)
story_viewer_spec.loader.exec_module(story_viewer_module)
StoryViewer = story_viewer_module.StoryViewer

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/logs/activity.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ActivityService:
    """Сервис просмотра Stories"""
    
    def __init__(self):
        self.config_loader = ConfigLoader()
        self.client_manager = TelegramClientManager()
        self.story_viewer = None
        self.interval_hours = 6  # Интервал между циклами (часов)
    
    async def initialize(self):
        """Инициализация компонентов"""
        # Загрузка конфигурации ниши
        niche_config = self.config_loader.load_niche_config()
        logger.info(f"📋 Active niche: {niche_config['display_name']} ({niche_config['name']})")
        
        # Инициализация клиентов
        db = SessionLocal()
        try:
            await self.client_manager.load_accounts_from_db(db)
            logger.info(f"✅ Loaded {len(self.client_manager.clients)} accounts")
        except Exception as e:
            logger.error(f"❌ Failed to load accounts: {e}")
            raise
        finally:
            db.close()
        
        # Инициализация story viewer с конфигом ниши
        self.story_viewer = StoryViewer(self.client_manager, niche_config)
        
        logger.info("✅ Activity Service initialized")
    
    async def run_cycle(self):
        """Один цикл просмотра Stories"""
        logger.info("=" * 80)
        logger.info("🔄 ACTIVITY CYCLE - Просмотр Stories участников групп")
        logger.info("=" * 80)
        
        try:
            total_viewed, total_reactions = await self.story_viewer.process_all_accounts()
            
            logger.info("=" * 80)
            logger.info(f"✅ Cycle completed: {total_viewed} views, {total_reactions} reactions")
            logger.info("=" * 80)
            
            return {
                'viewed': total_viewed,
                'reactions': total_reactions
            }
            
        except Exception as e:
            logger.error(f"❌ Error in cycle: {e}", exc_info=True)
            return {'viewed': 0, 'reactions': 0}
    
    async def run(self):
        """Основной цикл работы сервиса"""
        await self.initialize()
        
        logger.info("=" * 80)
        logger.info("🚀 ACTIVITY SERVICE - Просмотр Stories")
        logger.info("=" * 80)
        logger.info(f"⏰ Interval: {self.interval_hours} hours")
        logger.info("=" * 80)
        
        while True:
            try:
                result = await self.run_cycle()
                logger.info(f"📊 Cycle statistics: {result}")
                
                # Ждем до следующего цикла
                wait_seconds = self.interval_hours * 3600
                wait_hours = wait_seconds // 3600
                logger.info(f"😴 Next cycle in {wait_hours} hours")
                await asyncio.sleep(wait_seconds)
                
            except KeyboardInterrupt:
                logger.info("🛑 Shutting down...")
                break
            except Exception as e:
                logger.error(f"❌ Error in main loop: {e}", exc_info=True)
                await asyncio.sleep(600)  # Ждем 10 минут при ошибке


async def main():
    """Основная функция запуска"""
    service = ActivityService()
    
    try:
        await service.run()
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down...")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())

