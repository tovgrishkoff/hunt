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

from telethon import TelegramClient

from sqlalchemy import text

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

# Автопереподключение при падении клиента
RECONNECT_DELAY_SEC = 60
RECONNECT_DELAY_MAX_SEC = 600
RECONNECT_BACKOFF = 1.5

# Периодическая проверка flood_wait и рестарт при появлении новых активных аккаунтов
FLOOD_WAIT_CHECK_INTERVAL_SEC = 30 * 60  # каждые 30 минут


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
            # Автоочистка flood_wait: переводим в active, если next_allowed_action_time истёк
            try:
                result = db.execute(text(
                    "UPDATE accounts SET status = 'active', next_allowed_action_time = NULL, updated_at = NOW() "
                    "WHERE status IN ('flood_wait', 'cooldown') "
                    "AND (next_allowed_action_time IS NULL OR next_allowed_action_time <= NOW())"
                ))
                db.commit()
                if result.rowcount and result.rowcount > 0:
                    logger.info(f"✅ Автоочистка flood_wait: {result.rowcount} аккаунт(ов) переведены в active")
            except Exception as e:
                db.rollback()
                logger.debug(f"Автоочистка flood_wait (колонка может отсутствовать): {e}")

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

    async def _periodic_flood_wait_clear_and_restart(self) -> None:
        """
        Каждые 30 минут сбрасывает истёкшие flood_wait/cooldown в БД.
        Если хотя бы один аккаунт переведён в active — завершает процесс (exit 0),
        чтобы Docker (restart: unless-stopped) перезапустил секретарь и подхватил новые аккаунты.
        """
        while True:
            await asyncio.sleep(FLOOD_WAIT_CHECK_INTERVAL_SEC)
            try:
                db = SessionLocal()
                try:
                    result = db.execute(text(
                        "UPDATE accounts SET status = 'active', next_allowed_action_time = NULL, updated_at = NOW() "
                        "WHERE status IN ('flood_wait', 'cooldown') "
                        "AND (next_allowed_action_time IS NULL OR next_allowed_action_time <= NOW())"
                    ))
                    db.commit()
                    cleared = result.rowcount if result.rowcount else 0
                    if cleared > 0:
                        logger.info(
                            f"🔄 Автосброс flood_wait: {cleared} аккаунт(ов) переведены в active. "
                            "Рестарт секретаря для подхвата аккаунтов..."
                        )
                        sys.exit(0)
                except Exception as e:
                    db.rollback()
                    logger.debug(f"Периодическая очистка flood_wait: {e}")
                finally:
                    db.close()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"Ошибка периодической проверки flood_wait: {e}")

    async def _run_client_with_reconnect(
        self,
        account_name: str,
        client: TelegramClient,
    ) -> None:
        """
        Запуск клиента с автопереподключением при падении соединения.
        При отключении (Connection to Telegram failed и т.п.) ждёт с экспоненциальной
        задержкой и переподключает клиент без перезапуска контейнера.
        """
        delay_sec = RECONNECT_DELAY_SEC
        while True:
            try:
                if not client.is_connected():
                    logger.info(f"🔄 {account_name}: переподключение...")
                    await client.connect()
                if not await client.is_user_authorized():
                    logger.error(
                        f"❌ {account_name} не авторизован после переподключения, "
                        "прекращаем попытки для этого аккаунта"
                    )
                    return
                if not getattr(client, "_sender", None):
                    try:
                        await client.start()
                    except Exception as e:
                        logger.debug(f"  {account_name} start(): {e}")
                logger.info(f"✅ {account_name} подключён, запуск run_until_disconnected()")
                await client.run_until_disconnected()
                logger.warning(f"⚠️ {account_name} отключился от сервера (нормальный выход)")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"❌ Client {account_name} disconnected: {e}")
                logger.info(
                    f"🔄 {account_name}: переподключение через {delay_sec:.0f} с "
                    "(автопереподключение)"
                )
                await asyncio.sleep(delay_sec)
                delay_sec = min(
                    delay_sec * RECONNECT_BACKOFF,
                    RECONNECT_DELAY_MAX_SEC,
                )
                try:
                    if client.is_connected():
                        await asyncio.wait_for(client.disconnect(), timeout=5.0)
                except (asyncio.TimeoutError, Exception):
                    pass
    
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
                
                # 5. Задача с автопереподключением при падении клиента
                tasks.append(
                    asyncio.create_task(
                        self._run_client_with_reconnect(account_name, client)
                    )
                )

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
        logger.info(f"   Периодическая проверка flood_wait каждые {FLOOD_WAIT_CHECK_INTERVAL_SEC // 60} мин.")
        logger.info("   Press Ctrl+C to stop.")
        logger.info("=" * 80)

        # Задача автосброса flood_wait и рестарта при появлении новых активных аккаунтов
        tasks.append(asyncio.create_task(self._periodic_flood_wait_clear_and_restart()))
        
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

