#!/usr/bin/env python3
"""
Умный автоответчик с анализом контекста сообщений
"""

import asyncio
import random
import json
import logging
import os
from pathlib import Path
from datetime import datetime, timedelta
from telethon import TelegramClient, events
from telethon.errors import RPCError
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker

# Загружаем .env файл, если существует
def load_env_file():
    """Простая загрузка .env файла"""
    env_file = Path(__file__).parent / '.env'
    if env_file.exists():
        try:
            with open(env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        os.environ[key.strip()] = value.strip()
        except Exception as e:
            logging.warning(f"Не удалось загрузить .env файл: {e}")

# Загружаем .env при импорте модуля
load_env_file()

# Импортируем наш умный анализатор
from smart_response_analyzer import SmartResponseAnalyzer

# Настройка базы данных PostgreSQL
# По умолчанию БД включена, для отключения установите USE_DATABASE=false
USE_DATABASE = os.getenv('USE_DATABASE', 'true').lower() == 'true'
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://dm_user:dm_password@localhost:5436/dm_responses')

# По умолчанию используем файловый режим (без БД)
DB_AVAILABLE = False
engine = None
SessionLocal = None
Base = None

# Пробуем подключиться к БД только если явно указано
if USE_DATABASE:
    try:
        engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        # Проверяем подключение
        with engine.connect() as conn:
            pass
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        Base = declarative_base()
        DB_AVAILABLE = True
        logging.info("✅ Подключение к БД успешно")
        
        class DMResponse(Base):
            __tablename__ = "dm_responses"
            
            id = Column(Integer, primary_key=True, index=True)
            user_id = Column(String, index=True)
            username = Column(String)
            response_sent = Column(Boolean, default=False)
            response_text = Column(String)
            message_text = Column(String)
            service_type = Column(String)
            sent_at = Column(DateTime, default=datetime.utcnow)
            created_at = Column(DateTime, default=datetime.utcnow)

        # Создаем таблицы
        try:
            Base.metadata.create_all(bind=engine)
        except Exception as e:
            logging.warning(f"⚠️ Не удалось создать таблицы в БД: {e}")
            DB_AVAILABLE = False
    except Exception as e:
        logging.warning(f"⚠️ Не удалось подключиться к БД: {e}. Будет использован файловый режим.")
        DB_AVAILABLE = False
else:
    logging.info("ℹ️ Режим работы: файловый (без БД). Для использования БД установите USE_DATABASE=true")

class SmartPostgresDMResponder:
    def __init__(self):
        self.accounts = []
        self.clients = {}
        self.responses = []
        self.blacklist = set()
        self.smart_analyzer = SmartResponseAnalyzer()
        self.db_available = DB_AVAILABLE  # Используем глобальную переменную
        self.responses_file = Path('sent_responses.txt')  # Файл для отслеживания ответов
        self.setup_logging()
        if not self.db_available:
            self.logger.info("ℹ️ Работа в файловом режиме (без БД). Ответы будут сохраняться в sent_responses.txt")
        
    def setup_logging(self):
        """Настройка логирования"""
        from pathlib import Path
        import sys
        
        logs_dir = Path("logs")
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_file = logs_dir / "smart_autoresponder.log"
        
        # Создаем логгер
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        
        # Формат логов
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', 
                                     datefmt='%Y-%m-%d %H:%M:%S')
        
        # Вывод в консоль (stdout)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        
        # Вывод в файл
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)
        
        # Предотвращаем дублирование
        self.logger.propagate = False
        
        # Принудительно выводим первое сообщение
        print("=" * 60, flush=True)
        self.logger.info("🚀 Инициализация Smart DM Responder...")
        print("=" * 60, flush=True)
        
    def load_accounts(self, config_file=None):
        """Загрузка аккаунтов из конфигурации"""
        # Пробуем разные варианты конфигов (приоритет accounts_config.json)
        config_files = [
            config_file,
            os.getenv('ACCOUNTS_CONFIG'),
            'accounts_config.json',  # Основной конфиг с promotion_* сессиями
            'accounts_config_autoresponder.json'
        ]
        
        for config_path in config_files:
            if not config_path:
                continue
            try:
                if Path(config_path).exists():
                    with open(config_path, 'r', encoding='utf-8') as f:
                        self.accounts = json.load(f)
                    self.logger.info(f"✅ Загружено {len(self.accounts)} аккаунтов из {config_path}")
                    # Выводим имена сессий для отладки
                    session_names = [acc.get('session_name', 'unknown') for acc in self.accounts]
                    self.logger.info(f"   Сессии: {', '.join(session_names)}")
                    return
            except Exception as e:
                self.logger.warning(f"Не удалось загрузить {config_path}: {e}")
                continue
        
        self.logger.error("❌ Не удалось загрузить конфигурацию аккаунтов")
            
    def load_responses(self):
        """Загрузка базовых ответов (fallback)"""
        try:
            with open('dm_responses.txt', 'r', encoding='utf-8') as f:
                self.responses = [line.strip() for line in f if line.strip()]
            self.logger.info(f"Loaded {len(self.responses)} fallback responses")
        except Exception as e:
            self.logger.error(f"Error loading responses: {e}")
            
    def load_blacklist(self):
        """Загрузка черного списка"""
        try:
            with open('blacklist.txt', 'r', encoding='utf-8') as f:
                self.blacklist = set(line.strip() for line in f if line.strip())
            self.logger.info(f"Loaded {len(self.blacklist)} blacklisted users")
        except Exception as e:
            self.logger.warning(f"Could not load blacklist: {e}")
            
    def check_response_sent(self, user_id):
        """
        Проверка, отправляли ли уже ответ пользователю за последние 7 дней
        Если прошло больше недели - считаем, что можно отвечать снова
        """
        if self.db_available and SessionLocal:
            try:
                db = SessionLocal()
                try:
                    # Проверяем только ответы за последние 7 дней
                    week_ago = datetime.utcnow() - timedelta(days=7)
                    response = db.query(DMResponse).filter(
                        DMResponse.user_id == str(user_id),
                        DMResponse.response_sent == True,
                        DMResponse.created_at >= week_ago
                    ).first()
                    return response is not None
                finally:
                    db.close()
            except Exception as e:
                self.logger.warning(f"Ошибка проверки в БД, используем файл: {e}")
                self.db_available = False
        
        # Fallback на файловую систему (не проверяем дату, просто проверяем наличие)
        if self.responses_file.exists():
            try:
                with open(self.responses_file, 'r', encoding='utf-8') as f:
                    return str(user_id) in f.read()
            except Exception:
                return False
        return False
    
    def cleanup_old_responses(self, days=7):
        """
        Очистка старых записей из базы данных (старше указанного количества дней)
        """
        if not self.db_available or not SessionLocal:
            return 0
        
        try:
            db = SessionLocal()
            try:
                cutoff_date = datetime.utcnow() - timedelta(days=days)
                deleted_count = db.query(DMResponse).filter(
                    DMResponse.created_at < cutoff_date
                ).delete()
                db.commit()
                
                if deleted_count > 0:
                    self.logger.info(f"🧹 Очищено {deleted_count} старых записей (старше {days} дней)")
                
                return deleted_count
            except Exception as e:
                db.rollback()
                self.logger.error(f"❌ Ошибка при очистке старых записей: {e}")
                return 0
            finally:
                db.close()
        except Exception as e:
            self.logger.error(f"❌ Ошибка подключения к БД при очистке: {e}")
            return 0
            
    def mark_response_sent(self, user_id, username, response_text, message_text="", service_type=""):
        """Отметка отправленного ответа"""
        if self.db_available and SessionLocal:
            try:
                db = SessionLocal()
                try:
                    dm_response = DMResponse(
                        user_id=str(user_id),
                        username=username,
                        response_sent=True,
                        response_text=response_text,
                        message_text=message_text,
                        service_type=service_type
                    )
                    db.add(dm_response)
                    db.commit()
                    return
                except Exception as e:
                    self.logger.warning(f"Ошибка записи в БД, используем файл: {e}")
                    db.rollback()
                    self.db_available = False
                finally:
                    db.close()
            except Exception as e:
                self.logger.warning(f"Ошибка подключения к БД, используем файл: {e}")
                self.db_available = False
        
        # Fallback на файловую систему
        try:
            with open(self.responses_file, 'a', encoding='utf-8') as f:
                f.write(f"{user_id}\n")
        except Exception as e:
            self.logger.error(f"Ошибка записи в файл: {e}")

    async def handle_new_message(self, event, client_name):
        """Обработка нового сообщения с умным анализом"""
        try:
            # Логируем входящее сообщение сразу
            self.logger.info(f"📨 Входящее сообщение в {client_name}")
            
            sender = await event.get_sender()
            if not sender:
                self.logger.warning("⚠️ Не удалось получить информацию об отправителе")
                return

            user_id = sender.id
            username = getattr(sender, 'username', 'No username')
            message_text = event.message.text or ""
            
            self.logger.info(f"📨 Новое сообщение от @{username} ({user_id}) в {client_name}: {message_text[:100] if message_text else '(пустое)'}")
            
            # Проверяем черный список
            if username in self.blacklist or str(user_id) in self.blacklist:
                self.logger.info(f"🚫 Skipping blacklisted user: {username} ({user_id})")
                return

            # Проверяем, не отправляли ли уже ответ за последние 7 дней
            # Если прошло больше недели - отвечаем снова
            if self.check_response_sent(user_id):
                self.logger.info(f"⏭️ Already responded to {username} ({user_id}) in the last 7 days, skipping")
                return

            # Умный анализ сообщения и выбор ответа
            if message_text.strip():
                # Анализируем сообщение и получаем умный ответ (используем асинхронную версию с ChatGPT)
                service_type = self.smart_analyzer._detect_service_type(message_text.lower())
                
                # Пытаемся получить ответ от ChatGPT (если доступен)
                response_text = None
                if self.smart_analyzer.use_chatgpt and self.smart_analyzer.chatgpt_generator and self.smart_analyzer.chatgpt_generator.enabled:
                    try:
                        self.logger.info(f"🤖 [CHATGPT] Пытаюсь сгенерировать ответ через ChatGPT для типа '{service_type}'...")
                        response_text = await self.smart_analyzer.chatgpt_generator.generate_selling_response(
                            message_text, 
                            service_type
                        )
                        if response_text:
                            self.logger.info(f"✅ [CHATGPT] Ответ сгенерирован через ChatGPT: {response_text[:100]}...")
                        else:
                            self.logger.warning(f"⚠️ [CHATGPT] ChatGPT вернул None, используем fallback")
                    except Exception as e:
                        self.logger.warning(f"⚠️ [CHATGPT] Ошибка при генерации ChatGPT ответа: {e}, используем fallback")
                
                # Если ChatGPT не вернул ответ, используем fallback
                if not response_text:
                    responses = self.smart_analyzer.responses.get(service_type, self.smart_analyzer.responses['default'])
                    response_text = random.choice(responses)
                    self.logger.info(f"📋 [FALLBACK] Использован шаблонный ответ для типа '{service_type}': {response_text[:100]}...")
                
                self.logger.info(f"🧠 Smart analysis: service_type='{service_type}', message='{message_text[:50]}...'")
            else:
                # Если сообщение пустое, используем случайный fallback ответ
                if not self.responses:
                    self.logger.warning("No fallback responses available")
                    return
                response_text = random.choice(self.responses)
                service_type = "unknown"
            
            # Отправляем ОДИН ответ (либо от ChatGPT, либо из заготовок)
            await event.respond(response_text)
            
            # Отмечаем, что ответ отправлен
            self.mark_response_sent(user_id, username, response_text, message_text, service_type)
            
            self.logger.info(f"✅ Smart response sent to {username} ({user_id}) via {client_name}")
            self.logger.info(f"   Service type: {service_type}")
            self.logger.info(f"   Response: {response_text[:100]}...")
            
        except RPCError as e:
            self.logger.error(f"RPCError responding to {username}: {e}")
        except Exception as e:
            self.logger.error(f"Error handling message from {username}: {e}")

    async def initialize_clients(self):
        """Инициализация всех клиентов"""
        import sys
        total = len(self.accounts)
        for i, account in enumerate(self.accounts, 1):
            session_name = account['session_name']
            print(f"[{i}/{total}] Инициализация {session_name}...", file=sys.stdout, flush=True)
            self.logger.info(f"[{i}/{total}] Инициализация {session_name}...")
            
            client = None
            try:
                api_id = int(account['api_id'])
                
                client = TelegramClient(
                    f"sessions/{session_name}", 
                    api_id, 
                    account['api_hash']
                )
                
                print(f"   Подключение...", file=sys.stdout, flush=True)
                # Подключаемся с таймаутом
                try:
                    await asyncio.wait_for(client.connect(), timeout=15.0)
                except asyncio.TimeoutError:
                    print(f"   ⚠️ Таймаут подключения (15 сек) - пропускаем", file=sys.stdout, flush=True)
                    self.logger.warning(f"⚠️ Timeout connecting to {session_name}, skipping...")
                    if client:
                        try:
                            await client.disconnect()
                        except:
                            pass
                    continue  # Пропускаем этот клиент и переходим к следующему
                
                # Проверяем авторизацию
                print(f"   Проверка авторизации...", file=sys.stdout, flush=True)
                if await client.is_user_authorized():
                    self.clients[session_name] = client
                    me = await client.get_me()
                    username = getattr(me, 'username', 'No username')
                    print(f"   ✅ Авторизован как @{username}", file=sys.stdout, flush=True)
                    self.logger.info(f"✅ Initialized AUTHORIZED client for {session_name} (@{username})")
                    
                    # Регистрируем обработчик новых сообщений
                    client_name = session_name  # Сохраняем имя в локальной переменной
                    
                    @client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
                    async def handler(event):
                        await self.handle_new_message(event, client_name)
                    
                    # Проверяем, что обработчик зарегистрирован
                    handlers_count = len(client.list_event_handlers())
                    self.logger.info(f"📝 Обработчиков событий зарегистрировано: {handlers_count}")
                    print(f"   ✅ Обработчик событий зарегистрирован ({handlers_count} обработчиков)", file=sys.stdout, flush=True)
                else:
                    print(f"   ❌ Не авторизован", file=sys.stdout, flush=True)
                    self.logger.info(f"❌ Skipping UNAUTHORIZED client {session_name}")
                    await client.disconnect()
                    
            except Exception as e:
                print(f"   ❌ Ошибка: {str(e)[:50]}", file=sys.stdout, flush=True)
                self.logger.error(f"❌ Failed to initialize {session_name}: {e}")
                if client:
                    try:
                        await client.disconnect()
                    except:
                        pass

    async def run(self):
        """Запуск автоответчика"""
        import sys
        print("\n" + "=" * 60, file=sys.stdout, flush=True)
        self.logger.info("🤖 Starting Smart PostgreSQL DM Responder...")
        print("=" * 60 + "\n", file=sys.stdout, flush=True)
        
        # Загружаем конфигурацию
        self.load_accounts()
        self.load_responses()
        self.load_blacklist()
        
        # Инициализируем клиенты
        print("📡 Инициализация клиентов...\n", file=sys.stdout, flush=True)
        try:
            await asyncio.wait_for(self.initialize_clients(), timeout=60.0)
        except asyncio.TimeoutError:
            print("\n⚠️ Таймаут инициализации клиентов (60 сек)", file=sys.stdout, flush=True)
            self.logger.warning("⚠️ Timeout during client initialization")
        
        if not self.clients:
            print("\n❌ ОШИБКА: Нет авторизованных клиентов!\n", file=sys.stdout, flush=True)
            self.logger.error("❌ No authorized clients available")
            return
        
        # Очищаем старые записи при запуске
        self.cleanup_old_responses(days=7)
        
        # Запускаем периодическую очистку старых записей (каждые 24 часа)
        async def periodic_cleanup():
            """Периодическая очистка старых записей"""
            while True:
                await asyncio.sleep(24 * 60 * 60)  # 24 часа
                self.cleanup_old_responses(days=7)
        
        # Запускаем задачу очистки в фоне
        asyncio.create_task(periodic_cleanup())
        
        print("\n" + "=" * 60, file=sys.stdout, flush=True)
        print(f"✅ ГОТОВО! Автоответчик работает с {len(self.clients)} аккаунтами", file=sys.stdout, flush=True)
        print("=" * 60, file=sys.stdout, flush=True)
        self.logger.info(f"🎉 Smart DM Responder ready with {len(self.clients)} authorized accounts!")
        self.logger.info("👂 Listening for new DMs with smart analysis...")
        self.logger.info("🧹 Автоматическая очистка старых записей (старше 7 дней) каждые 24 часа")
        print("\n👂 Ожидание входящих сообщений...", file=sys.stdout, flush=True)
        print("   (Нажмите Ctrl+C для остановки)\n", file=sys.stdout, flush=True)
        
        # Держим бота запущенным
        try:
            # Запускаем все клиенты параллельно
            tasks = [client.run_until_disconnected() for client in self.clients.values()]
            await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            self.logger.info("🛑 Shutting down...")
        finally:
            for client in self.clients.values():
                await client.disconnect()

if __name__ == "__main__":
    import sys
    # Принудительно отключаем буферизацию
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
    
    print("\n" + "=" * 60, flush=True)
    print("🚀 ЗАПУСК SMART DM RESPONDER", flush=True)
    print("=" * 60 + "\n", flush=True)
    
    responder = SmartPostgresDMResponder()
    asyncio.run(responder.run())



