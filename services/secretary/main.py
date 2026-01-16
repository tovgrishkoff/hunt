#!/usr/bin/env python3
"""
Secretary Service: Автоответчик на личные сообщения с GPT-4o-mini
"""
import asyncio
import sys
import os
import logging
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.telegram.client_manager import TelegramClientManager
from shared.database.session import SessionLocal
from shared.config.loader import ConfigLoader
from services.secretary.gpt_handler import GPTHandler
from services.secretary.responder import MessageResponder

# Настройка логирования (DEBUG для отладки)
logging.basicConfig(
    level=logging.DEBUG,  # Увеличено до DEBUG для видимости всех логов
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/logs/secretary.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
# Устанавливаем уровень логирования для telethon (чтобы не было слишком много логов)
logging.getLogger('telethon').setLevel(logging.WARNING)


class SecretaryService:
    """Сервис автоответчика"""
    
    def __init__(self):
        self.config_loader = ConfigLoader()
        self.client_manager = TelegramClientManager()
        self.gpt_handler = None
        self.responder = None
    
    async def initialize(self):
        """Инициализация компонентов"""
        # Загрузка конфигурации ниши
        niche_config = self.config_loader.load_niche_config()
        logger.info(f"📋 Active niche: {niche_config['display_name']} ({niche_config['name']})")
        
        # Инициализация GPT обработчика
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            logger.error("❌ OPENAI_API_KEY not found in environment variables")
            logger.error("   Please set OPENAI_API_KEY in .env file or environment")
            raise ValueError("OPENAI_API_KEY is required")
        
        self.gpt_handler = GPTHandler(api_key=api_key, niche_config=niche_config)
        
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
        
        # Инициализация обработчика сообщений
        self.responder = MessageResponder(self.client_manager, self.gpt_handler)
        
        # УБРАНО: initialize_forward_target - теперь получаем entity для каждого клиента отдельно
        
        # ВАЖНО: setup_handlers() НЕ вызываем здесь, потому что клиенты еще не запущены
        # Обработчики нужно регистрировать ПОСЛЕ того, как клиенты запущены через start()
        
        logger.info("✅ Secretary Service initialized")
    
    async def run(self):
        """Основной цикл работы сервиса"""
        await self.initialize()
        
        logger.info("=" * 80)
        logger.info("🚀 ЗАПУСК СЕКРЕТАРЯ...")
        logger.info("=" * 80)
        
        tasks = []
        active_count = 0

        # Перебираем клиентов
        for account_name, client in self.client_manager.clients.items():
            logger.info(f"🔌 Подключение {account_name}...")
            
            try:
                # 1. Проверяем, подключен ли клиент (он уже подключен через load_accounts_from_db)
                if not client.is_connected():
                    logger.warning(f"⚠️ {account_name} не подключен, пытаемся подключить...")
                    await client.connect()
                
                # 2. Проверяем авторизацию
                if not await client.is_user_authorized():
                    logger.error(f"❌ {account_name} ТРЕБУЕТ АВТОРИЗАЦИИ! Пропускаем, чтобы не зависнуть.")
                    continue
                
                # 3. ВАЖНО: Для работы обработчиков событий нужно вызвать start()
                # Но только если клиент уже авторизован, иначе зависнет на вводе пароля
                try:
                    # Проверяем, запущен ли клиент (start() уже был вызван)
                    if not hasattr(client, '_sender') or client._sender is None:
                        # Клиент не запущен, но он уже авторизован, поэтому безопасно вызывать start()
                        await client.start()
                        logger.debug(f"  ✅ {account_name} start() вызван")
                except Exception as e:
                    logger.warning(f"⚠️ {account_name} start() не нужен или ошибка: {e}")
                
                # 4. Получаем инфо о себе, чтобы убедиться, что всё ок
                me = await client.get_me()
                logger.info(f"✅ {account_name} УСПЕШНО ЗАПУЩЕН как @{getattr(me, 'username', 'N/A')} (ID: {me.id})")
                active_count += 1
                
                # 5. Создаем задачу на вечное ожидание событий
                async def keep_alive(cli=client, name=account_name):
                    try:
                        logger.debug(f"  🔄 {name} запущен в run_until_disconnected()")
                        await cli.run_until_disconnected()
                        logger.warning(f"⚠️ {name} отключился от сервера")
                    except Exception as e:
                        logger.error(f"❌ Client {name} disconnected: {e}")
                        import traceback
                        logger.error(f"❌ Traceback:\n{traceback.format_exc()}")
                
                tasks.append(asyncio.create_task(keep_alive()))

            except Exception as e:
                logger.error(f"❌ Ошибка при запуске {account_name}: {e}")
                import traceback
                logger.error(f"❌ Traceback:\n{traceback.format_exc()}")

        logger.info("=" * 80)
        if active_count == 0:
            logger.error("🛑 НИ ОДИН АККАУНТ НЕ ЗАПУСТИЛСЯ КОРРЕКТНО!")
            return
        
        # КРИТИЧНО: Регистрируем обработчики ПОСЛЕ того, как все клиенты запущены
        logger.info("📝 Регистрация обработчиков событий...")
        self.responder.setup_handlers()
        logger.info("✅ Обработчики зарегистрированы для всех активных клиентов")
            
        logger.info(f"🟢 Система работает на {active_count} аккаунтах.")
        logger.info("   Press Ctrl+C to stop.")
        logger.info("=" * 80)
        
        # Ждем выполнения всех задач
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        except KeyboardInterrupt:
            logger.info("🛑 Shutting down...")
        except Exception as e:
            logger.error(f"❌ Error in main loop: {e}", exc_info=True)


async def main():
    """Основная функция запуска"""
    service = SecretaryService()
    
    try:
        await service.run()
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down...")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())

