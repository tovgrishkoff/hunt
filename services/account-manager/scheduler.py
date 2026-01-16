"""
Планировщик для Account Manager
Работает по расписанию Asia/Jakarta (ночью по Киеву)
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict
import pytz

from shared.config.loader import ConfigLoader
from shared.telegram.client_manager import TelegramClientManager
from shared.database.session import SessionLocal
from shared.database.models import Group
from sqlalchemy import func

# Импортируем модули из той же директории
import importlib.util
from pathlib import Path

# Импорт finder
finder_spec = importlib.util.spec_from_file_location("finder", Path(__file__).parent / "finder.py")
finder_module = importlib.util.module_from_spec(finder_spec)
finder_spec.loader.exec_module(finder_module)
GroupFinder = finder_module.GroupFinder

# Импорт joiner
joiner_spec = importlib.util.spec_from_file_location("joiner", Path(__file__).parent / "joiner.py")
joiner_module = importlib.util.module_from_spec(joiner_spec)
joiner_spec.loader.exec_module(joiner_module)
GroupJoiner = joiner_module.GroupJoiner

logger = logging.getLogger(__name__)


class AccountManagerScheduler:
    """Планировщик для Account Manager"""
    
    def __init__(self):
        self.config_loader = ConfigLoader()
        self.client_manager = TelegramClientManager()
        self.finder = None
        self.joiner = None
        self._last_reset_date = None
    
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
        
        # Инициализация finder и joiner
        self.finder = GroupFinder(self.client_manager)
        self.joiner = GroupJoiner(self.client_manager, niche_config)
    
    def reset_daily_counters_if_needed(self, today):
        """Сброс дневных счетчиков в полночь"""
        if self._last_reset_date != today:
            logger.info(f"🔄 New day: {today}, counters will be reset on next join")
            self._last_reset_date = today
    
    def get_new_groups_count(self, niche: str) -> int:
        """
        Получить количество групп со статусом 'new' в очереди
        
        Args:
            niche: Ниша групп
        
        Returns:
            Количество групп в очереди
        """
        db = SessionLocal()
        try:
            count = db.query(func.count(Group.id)).filter(
                Group.niche == niche,
                Group.status == 'new'
            ).scalar()
            return count or 0
        except Exception as e:
            logger.error(f"❌ Error getting new groups count: {e}")
            return 0
        finally:
            db.close()
    
    async def run(self):
        """Основной цикл планировщика"""
        await self.initialize()
        
        niche_config = self.config_loader.load_niche_config()
        niche = niche_config['name']
        
        # Получаем расписание для вступления (Asia/Jakarta)
        joining_schedule = niche_config.get('joining_schedule', {})
        timezone_str = joining_schedule.get('timezone', 'Asia/Jakarta')
        timezone = pytz.timezone(timezone_str)
        
        # Получаем слоты для вступления (по умолчанию из конфига)
        slots = joining_schedule.get('slots', [
            {"name": "early_morning_1", "time": "05:00"},
            {"name": "early_morning_2", "time": "07:00"},
            {"name": "morning_1", "time": "09:00"},
            {"name": "morning_2", "time": "11:00"}
        ])
        
        logger.info("=" * 80)
        logger.info(f"📅 ACCOUNT MANAGER SCHEDULER - {timezone_str}")
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
            
            # Сброс счетчиков в полночь
            self.reset_daily_counters_if_needed(today)
            
            # АДАПТИВНАЯ ЛОГИКА: Проверяем размер очереди ПЕРЕД ожиданием
            new_groups_count = self.get_new_groups_count(niche)
            
            if new_groups_count > 0:
                # Режим 'первичной обработки': есть группы в очереди
                # Запускаем обработку сразу, без ожидания слота
                logger.info(f"⚡ Режим первичной обработки: в очереди {new_groups_count} групп (статус 'new')")
                logger.info("🚀 Запускаем обработку немедленно...")
                
                slot_name = "fast_processing"  # Виртуальный слот для быстрой обработки
                run_day = today
                
                # Пропускаем проверку processed_slots_today - в быстром режиме обрабатываем всегда
            else:
                # Режим 'поддержки': очередь пуста
                # Используем стандартное расписание (slots)
                if self._slot_processing_mode:
                    logger.info(f"✅ Очередь пуста (new == 0), режим поддержки (стандартное расписание)")
                else:
                    self._slot_processing_mode = True  # Возвращаемся к режиму поддержки
                    logger.info(f"🔄 Переключаемся на режим поддержки (стандартное расписание)")
                
                # Находим следующий слот
                next_slot_name = None
                next_slot_dt = None
                
                for name, t in slots_list:
                    slot_dt = timezone.localize(datetime.combine(today, t))
                    if slot_dt <= now:
                        # Если время слота прошло, переносим на завтра
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
                
                # Время слота наступило
                slot_name = next_slot_name
                run_day = datetime.now(timezone).date()
                logger.info(f"⏰ Woke up for slot: {slot_name}, date: {run_day}")
                
                if processed_slots_today.get(slot_name) == run_day:
                    logger.info(f"  Slot {slot_name}: already processed today, skipping")
                    continue
            
            # Запускаем обработку
            try:
                # 1. Поиск новых групп
                logger.info("=" * 80)
                logger.info("🔍 STEP 1: SEARCHING FOR NEW GROUPS")
                logger.info("=" * 80)
                
                # Получаем ключевые слова из секции manager
                manager_config = niche_config.get('manager', {})
                search_keywords = manager_config.get('search_keywords', [])
                if not search_keywords:
                    logger.warning("⚠️ No search keywords in config, skipping search")
                else:
                    # Используем первый доступный клиент для поиска
                    if not self.client_manager.clients:
                        logger.error("❌ No clients available for search")
                    else:
                        client_name = list(self.client_manager.clients.keys())[0]
                        
                        # Проверяем и переподключаем клиент при необходимости
                        client = await self.client_manager.ensure_client_connected(client_name)
                        if not client:
                            logger.error(f"❌ Failed to connect client {client_name} for search")
                        else:
                            logger.info(f"👤 Using account for search: {client_name}")
                            
                            try:
                                found_groups = await self.finder.search_groups(client, search_keywords)
                                
                                if found_groups:
                                    saved = self.finder.save_groups_to_db(found_groups, niche)
                                    logger.info(f"✅ Saved {saved} new groups to DB")
                                else:
                                    logger.info("ℹ️ No new groups found")
                            except Exception as e:
                                logger.error(f"❌ Error during group search: {e}", exc_info=True)
                
                # 2. Вступление в найденные группы
                logger.info("")
                logger.info("=" * 80)
                logger.info("🚪 STEP 2: JOINING NEW GROUPS")
                logger.info("=" * 80)
                
                joined, failed = await self.joiner.process_new_groups(niche)
                logger.info(f"✅ Slot {slot_name} completed: {joined} joined, {failed} failed")
                
                processed_slots_today[slot_name] = run_day
                
            except Exception as e:
                logger.error(f"❌ Error in slot {slot_name}: {e}", exc_info=True)
            
            # После обработки проверяем очередь снова
            if slot_name != "fast_processing":
                # Обычный слот - помечаем как обработанный
                processed_slots_today[slot_name] = run_day
            
            # АДАПТИВНАЯ ЛОГИКА: Проверяем размер очереди после обработки
            new_groups_count_after = self.get_new_groups_count(niche)
            
            if new_groups_count_after > 0:
                # Режим 'первичной обработки': есть группы в очереди
                # Используем короткий интервал (60 секунд) для быстрой обработки
                logger.info(f"📊 В очереди осталось: {new_groups_count_after} групп (статус 'new')")
                logger.info(f"⚡ Режим первичной обработки: следующий запуск через {FAST_PROCESSING_INTERVAL} секунд")
                self._slot_processing_mode = False  # Отключаем режим поддержки
                await asyncio.sleep(FAST_PROCESSING_INTERVAL)
                # Продолжаем цикл - на следующей итерации проверим очередь снова
            else:
                # Режим 'поддержки': очередь пуста
                # Используем стандартное расписание (slots)
                logger.info(f"✅ Очередь пуста (new == 0), переключаемся на режим поддержки (стандартное расписание)")
                self._slot_processing_mode = True  # Включаем режим поддержки
                # Продолжаем основной цикл (while True) - будет ждать следующего слота

