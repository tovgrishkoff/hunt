"""
Планировщик для Lexus Account Manager
Работает с lexus_db (Async SQLAlchemy) для поиска и вступления в группы
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, time as dtime
from pathlib import Path
from typing import Optional, List
import pytz

from lexus_db.session import AsyncSessionLocal, init_db
from lexus_db.models import Account, Target
from sqlalchemy import select, func

# Импорт scout и smart_joiner
import importlib.util
from pathlib import Path

# Импорт scout
scout_spec = importlib.util.spec_from_file_location("scout", Path(__file__).parent / "scout.py")
scout_module = importlib.util.module_from_spec(scout_spec)
scout_spec.loader.exec_module(scout_module)
Scout = scout_module.Scout

# Импорт smart_joiner
smart_joiner_spec = importlib.util.spec_from_file_location("smart_joiner", Path(__file__).parent / "smart_joiner.py")
smart_joiner_module = importlib.util.module_from_spec(smart_joiner_spec)
smart_joiner_spec.loader.exec_module(smart_joiner_module)
SmartJoiner = smart_joiner_module.SmartJoiner

# Импорт ConfigLoader
from shared.config.loader import ConfigLoader

# Импорт client_manager для поиска групп
from shared.telegram.client_manager import TelegramClientManager

logger = logging.getLogger(__name__)


class LexusAccountManagerScheduler:
    """Планировщик для Lexus Account Manager"""
    
    def __init__(self):
        self.config_loader = ConfigLoader()
        self.scout = None
        self.smart_joiner = None
        self.client_manager = None
        self.niche: Optional[str] = None
        self.allowed_sessions: Optional[List[str]] = None
        self._last_reset_date = None
    
    def _load_lexus_accounts(self) -> Optional[List[str]]:
        """Загрузка списка разрешенных аккаунтов для Lexus"""
        possible_paths = [
            Path("/app/lexus_accounts_config.json"),
            Path("lexus_accounts_config.json"),
            Path("../lexus_accounts_config.json"),
        ]
        
        for path in possible_paths:
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    allowed = data.get("allowed_accounts") or []
                    allowed = [s for s in allowed if s]
                    if allowed:
                        logger.info(
                            f"✅ Loaded {len(allowed)} Lexus sessions from {path}: "
                            f"{', '.join(allowed)}"
                        )
                        return allowed
                except Exception as e:
                    logger.warning(f"⚠️ Failed to load lexus_accounts_config.json from {path}: {e}")
        
        logger.warning("⚠️ lexus_accounts_config.json not found or empty, using all active accounts")
        return None
    
    async def initialize(self):
        """Инициализация компонентов"""
        # Инициализация БД
        try:
            await init_db()
            logger.info("✅ Database initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize database: {e}")
            raise
        
        # Загрузка конфигурации ниши
        niche_name = os.getenv('NICHE', 'ukraine_cars')
        if niche_name:
            logger.info(f"📋 Using niche from environment: {niche_name}")
            niche_config = self.config_loader.load_niche_config(niche_name)
        else:
            niche_config = self.config_loader.load_niche_config()
        
        self.niche = niche_config.get('name', 'ukraine_cars')
        logger.info(f"📋 Active niche: {niche_config.get('display_name', '')} ({self.niche})")
        
        # Загружаем allowed_sessions для Lexus
        self.allowed_sessions = self._load_lexus_accounts()
        
        # Инициализация smart_joiner с фильтрацией по allowed_sessions
        # Используем абсолютный путь к accounts_config.json в контейнере
        accounts_config_path = '/app/accounts_config.json'
        self.smart_joiner = SmartJoiner(
            accounts_config_path=accounts_config_path,
            allowed_sessions=self.allowed_sessions
        )
        
        # Инициализация client_manager для поиска групп (опционально, можем создавать клиенты напрямую)
        self.client_manager = None  # Будем создавать клиенты напрямую из БД
        
        # Загружаем аккаунты из БД для проверки
        async with AsyncSessionLocal() as session:
            # Получаем только Lexus аккаунты из БД
            if self.allowed_sessions:
                stmt = select(Account).where(
                    Account.status == 'active',
                    Account.session_name.in_(self.allowed_sessions)
                )
            else:
                stmt = select(Account).where(Account.status == 'active')
            
            result = await session.execute(stmt)
            accounts = result.scalars().all()
            logger.info(f"✅ Found {len(accounts)} Lexus accounts in DB")
    
    async def get_new_groups_count(self) -> int:
        """Получить количество групп со статусом 'new' в очереди"""
        async with AsyncSessionLocal() as session:
            stmt = select(func.count(Target.id)).where(
                Target.niche == self.niche,
                Target.status == 'new'
            )
            result = await session.execute(stmt)
            count = result.scalar_one() or 0
            return count
    
    async def search_groups(self, niche_config: dict):
        """Поиск новых групп. Scout ищет по ключевым словам и сохраняет в БД со статусом 'new'; Joiner потом вступает в них."""
        logger.info("=" * 80)
        logger.info("🔍 STEP 1: SEARCHING FOR NEW GROUPS (Scout → status='new')")
        logger.info("=" * 80)
        
        # Получаем ключевые слова из секции manager
        manager_config = niche_config.get('manager', {})
        search_keywords = manager_config.get('search_keywords', []) or []
        
        if not search_keywords:
            logger.warning("⚠️ No search keywords available, skipping search")
            return 0
        
        logger.info(f"🔎 Search keywords: {len(search_keywords)} total")
        
        # Используем scout для поиска групп
        try:
            scout = Scout(niche=self.niche)
            # Используем метод search_and_save_groups, который сам создает клиент и сохраняет в БД
            saved_count = await scout.search_and_save_groups(
                keywords=search_keywords,
                niche=self.niche,
                allowed_sessions=list(self.allowed_sessions) if self.allowed_sessions else None,
                client_manager=self.client_manager
            )
            logger.info(f"✅ Scout: добавлено в БД со статусом 'new': {saved_count} групп (Joiner подхватит в STEP 2)")
            return saved_count
        except Exception as e:
            logger.error(f"❌ Error during group search: {e}", exc_info=True)
            return 0
    
    async def join_groups(self, niche_config: dict):
        """Вступление в группы со статусом 'new' (добавленные Scout в STEP 1)."""
        logger.info("")
        logger.info("=" * 80)
        logger.info("🚪 STEP 2: JOINING NEW GROUPS (status='new' → вступление)")
        logger.info("=" * 80)
        
        # Получаем лимиты из конфига
        limits_config = niche_config.get('limits', {})
        batch_size = limits_config.get('join_batch_size', 20)
        
        try:
            # Используем smart_joiner для вступления
            await self.smart_joiner.run_batch(niche=self.niche, batch_size=batch_size)
            logger.info("✅ Join batch completed")
        except Exception as e:
            logger.error(f"❌ Error during group joining: {e}", exc_info=True)
    
    async def run(self):
        """Основной цикл планировщика"""
        await self.initialize()
        
        niche_config = self.config_loader.load_niche_config(self.niche)
        
        # Получаем расписание для вступления
        joining_schedule = niche_config.get('joining_schedule', {})
        timezone_str = joining_schedule.get('timezone', 'Europe/Kiev')
        timezone = pytz.timezone(timezone_str)
        
        # Получаем слоты для вступления
        slots = joining_schedule.get('slots', [
            {"name": "morning_1", "time": "08:00"},
            {"name": "noon_1", "time": "12:00"},
            {"name": "afternoon_1", "time": "15:00"},
            {"name": "evening_1", "time": "18:00"},
            {"name": "night_1", "time": "20:00"}
        ])
        
        logger.info("=" * 80)
        logger.info(f"📅 LEXUS ACCOUNT MANAGER SCHEDULER - {timezone_str}")
        logger.info("=" * 80)
        logger.info(f"Schedule: {len(slots)} slots per day")
        for slot in slots:
            logger.info(f"  - {slot['time']} ({slot['name']})")
        logger.info("=" * 80)
        
        # Преобразуем слоты в формат (name, time)
        slots_list = [
            (slot['name'], datetime.strptime(slot['time'], '%H:%M').time())
            for slot in slots
        ]
        
        processed_slots_today = {name: None for name, _ in slots_list}
        
        # Интервалы ожидания
        FAST_PROCESSING_INTERVAL = 60  # 60 секунд при наличии очереди
        
        while True:
            now = datetime.now(timezone)
            today = now.date()
            
            # АДАПТИВНАЯ ЛОГИКА: Проверяем размер очереди ПЕРЕД ожиданием
            new_groups_count = await self.get_new_groups_count()
            
            if new_groups_count > 0:
                # Режим 'первичной обработки': есть группы в очереди
                logger.info(f"⚡ Режим первичной обработки: в очереди {new_groups_count} групп (статус 'new')")
                logger.info("🚀 Запускаем обработку немедленно...")
                slot_name = "fast_processing"
            else:
                # Режим 'поддержки': очередь пуста - используем стандартное расписание
                # Находим следующий слот
                next_slot_name = None
                next_slot_dt = None
                
                for name, t in slots_list:
                    slot_dt = timezone.localize(datetime.combine(today, t))
                    if slot_dt <= now:
                        slot_dt = slot_dt + timedelta(days=1)
                    if next_slot_dt is None or slot_dt < next_slot_dt:
                        next_slot_dt = slot_dt
                        next_slot_name = name
                
                # Ждем до следующего слота
                wait_seconds = max(1, int((next_slot_dt - now).total_seconds()))
                wait_hours = wait_seconds // 3600
                wait_minutes = (wait_seconds % 3600) // 60
                logger.info(
                    f"⏰ Next slot: {next_slot_name} at {next_slot_dt.strftime('%Y-%m-%d %H:%M:%S')} "
                    f"(in {wait_hours}h {wait_minutes}m)"
                )
                await asyncio.sleep(wait_seconds)
                
                slot_name = next_slot_name
                run_day = datetime.now(timezone).date()
                logger.info(f"⏰ Woke up for slot: {slot_name}, date: {run_day}")
                
                if processed_slots_today.get(slot_name) == run_day:
                    logger.info(f"  Slot {slot_name}: already processed today, skipping")
                    continue
            
            # Запускаем обработку
            try:
                # 1. Поиск новых групп
                await self.search_groups(niche_config)
                
                # 2. Вступление в найденные группы
                await self.join_groups(niche_config)
                
                logger.info(f"✅ Slot {slot_name} completed")
                processed_slots_today[slot_name] = datetime.now(timezone).date()
                
            except Exception as e:
                logger.error(f"❌ Error in slot {slot_name}: {e}", exc_info=True)
            
            # АДАПТИВНАЯ ЛОГИКА: Проверяем размер очереди после обработки
            new_groups_count_after = await self.get_new_groups_count()
            
            if new_groups_count_after > 0:
                logger.info(f"📊 В очереди осталось: {new_groups_count_after} групп (статус 'new')")
                logger.info(f"⚡ Режим первичной обработки: следующий запуск через {FAST_PROCESSING_INTERVAL} секунд")
                await asyncio.sleep(FAST_PROCESSING_INTERVAL)
            else:
                logger.info(f"✅ Очередь пуста (new == 0), переключаемся на режим поддержки (стандартное расписание)")
