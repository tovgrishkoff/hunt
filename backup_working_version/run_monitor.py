import asyncio
import logging
from aiogram import Bot
from database import Database
from config import TELEGRAM_BOT_TOKEN, DB_DSN
from monitor import MessageMonitor

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    try:
        # Инициализация компонентов
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        db = Database(DB_DSN)
        monitor = MessageMonitor(bot, db)
        
        # Подключаемся к базе
        await db.connect()
        logger.info("Database connected successfully")
        
        # Инициализируем монитор
        await monitor.initialize()
        logger.info("Monitor initialized successfully")
        
        # Запускаем монитор
        await monitor.start()
        logger.info("Monitor started successfully")
        
        # Держим скрипт запущенным
        while True:
            await asyncio.sleep(1)
            
    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        await db.close()
        await bot.close()

async def test_monitor(monitor):
    await monitor.process_message_from_subscriber(
        message_text="Тестовое сообщение для проверки ниши Фотограф",
        chat_title="Тестовый чат",
        message_link="https://t.me/test/1"
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Monitor stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")

# После инициализации монитора:
asyncio.create_task(test_monitor(monitor)) 