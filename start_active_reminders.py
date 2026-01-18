#!/usr/bin/env python3
"""
Сервис для периодической отправки активных напоминаний
Запускается каждые 6 часов
"""

import asyncio
import logging
from datetime import datetime
from active_reminders import send_active_reminders

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('active_reminders_service.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

async def reminder_service_loop():
    """Основной цикл сервиса напоминаний"""
    logger.info("🚀 Сервис активных напоминаний запущен")
    logger.info(f"📅 Первый запуск: {datetime.now()}")
    
    while True:
        try:
            # Запускаем отправку напоминаний
            await send_active_reminders()
            
            # Ждем 6 часов до следующего запуска
            wait_seconds = 6 * 60 * 60  # 6 часов
            logger.info(f"⏳ Следующая проверка через 6 часов...")
            await asyncio.sleep(wait_seconds)
            
        except KeyboardInterrupt:
            logger.info("🛑 Сервис остановлен пользователем")
            break
        except Exception as e:
            logger.error(f"❌ Ошибка в цикле сервиса: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # При ошибке ждем 1 час перед повтором
            logger.info("⏳ Повтор через 1 час...")
            await asyncio.sleep(60 * 60)

if __name__ == "__main__":
    asyncio.run(reminder_service_loop())





