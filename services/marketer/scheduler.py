"""
Планировщик для постинга по расписанию
"""
import asyncio
import os
import random
import json
import logging
from datetime import datetime, timedelta, time as dtime
from pathlib import Path
import pytz
from typing import Optional

from shared.database.session import get_db, init_db
from shared.config.loader import ConfigLoader
from shared.telegram.client_manager import TelegramClientManager
from sqlalchemy import text
from services.marketer.poster import SmartPoster as Poster

logger = logging.getLogger(__name__)


class MarketerScheduler:
    """Планировщик постинга"""
    
    def __init__(self):
        self.config_loader = ConfigLoader()
        self.client_manager = TelegramClientManager()
        self.poster = None
        self.niche: Optional[str] = None
        self._last_reset_date = None
    
    async def initialize(self):
        """Инициализация компонентов"""
        # Инициализация БД
        try:
            init_db()
            logger.info("✅ Database initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize database: {e}")
            raise
        
        # Загрузка конфигурации ниши
        # Используем переменную окружения NICHE, если установлена (для Ukraine проекта)
        niche_name = os.getenv('NICHE')
        if niche_name:
            logger.info(f"📋 Using niche from environment: {niche_name}")
            niche_config = self.config_loader.load_niche_config(niche_name)
        else:
            niche_config = self.config_loader.load_niche_config()
        logger.info(f"📋 Active niche: {niche_config.get('display_name', niche_config.get('name', 'unknown'))} ({niche_config.get('name', 'unknown')})")
        
        # Инициализация клиентов
        db_gen = get_db()
        db = next(db_gen)
        try:
            # Для Lexus используем exclude_lexus_accounts=False чтобы использовать whitelist
            project_name = os.getenv('PROJECT_NAME', '').lower()
            exclude_lexus = project_name != 'lexus'
            await self.client_manager.load_accounts_from_db(db, exclude_lexus_accounts=exclude_lexus)
            logger.info(f"✅ Loaded {len(self.client_manager.clients)} accounts")
        except Exception as e:
            logger.error(f"❌ Failed to load accounts: {e}")
            raise
        finally:
            db.close()
        
        # Инициализация постера
        # Используем переменную окружения NICHE или имя из конфига
        poster_niche = os.getenv('NICHE') or niche_config.get('name', 'bali')
        self.poster = Poster(poster_niche)
        self.niche = poster_niche
        logger.info(f"📝 Poster initialized for niche: {poster_niche}")
        # await self.poster.initialize()  # SmartPoster не имеет метода initialize
    
    def reset_daily_counters_if_needed(self, today):
        """Сброс дневных счетчиков в полночь"""
        if self._last_reset_date != today:
            # В БД Bali дневной лимит хранится в groups.daily_posts_count.
            # Без сброса этот счетчик "накапливается навсегда", из-за чего постинг
            # со временем прекращается (get_groups_ready_for_posting фильтрует < 2).
            try:
                niche = self.niche or "bali"
                db_gen = get_db()
                db = next(db_gen)
                try:
                    result = db.execute(
                        text(
                            "UPDATE groups "
                            "SET daily_posts_count = 0 "
                            "WHERE niche = :niche AND COALESCE(daily_posts_count, 0) <> 0"
                        ),
                        {"niche": niche},
                    )
                    db.commit()
                    updated = getattr(result, "rowcount", None)
                    logger.info(
                        f"🔄 New day: {today}. Reset daily_posts_count for niche '{niche}' "
                        f"(updated={updated})"
                    )
                finally:
                    db.close()
            except Exception as e:
                logger.error(f"❌ Failed to reset daily counters for {today}: {e}", exc_info=True)

            self._last_reset_date = today
    
    async def run(self):
        """Основной цикл планировщика"""
        await self.initialize()
        
        # Используем переменную окружения NICHE, если установлена (для Ukraine проекта)
        niche_name = os.getenv('NICHE')
        if niche_name:
            niche_config = self.config_loader.load_niche_config(niche_name)
        else:
            niche_config = self.config_loader.load_niche_config()
        # Получаем расписание из секции marketer
        marketer_config = niche_config.get('marketer', {})
        schedule = marketer_config.get('posting_schedule', {})
        
        # Проверяем наличие необходимых полей
        if not schedule or 'timezone' not in schedule:
            logger.error("❌ 'posting_schedule' not found in niche config or missing 'timezone'")
            logger.error(f"Available keys in marketer_config: {list(marketer_config.keys())}")
            logger.error(f"Available keys in niche_config: {list(niche_config.keys())}")
            raise ValueError("posting_schedule configuration is missing or invalid")
        
        if 'slots' not in schedule or not schedule['slots']:
            logger.error("❌ 'slots' not found in posting_schedule or empty")
            raise ValueError("posting_schedule.slots configuration is missing or empty")
        
        timezone = pytz.timezone(schedule['timezone'])
        
        logger.info("=" * 80)
        logger.info(f"📅 MARKETER SCHEDULER - {schedule['timezone']}")
        logger.info("=" * 80)
        logger.info(f"Schedule: {len(schedule['slots'])} slots per day")
        for slot in schedule['slots']:
            logger.info(f"  - {slot['time']} ({slot['name']})")
        logger.info("=" * 80)
        
        slots = [
            (slot['name'], datetime.strptime(slot['time'], '%H:%M').time())
            for slot in schedule['slots']
        ]
        
        posted_slots_today = {name: None for name, _ in slots}
        
        while True:
            now = datetime.now(timezone)
            today = now.date()
            
            # Сброс счетчиков в полночь (чтобы ready_count был корректен с начала дня)
            self.reset_daily_counters_if_needed(today)
            
            # Находим следующий слот
            next_slot_name = None
            next_slot_dt = None
            
            for name, t in slots:
                slot_dt = timezone.localize(datetime.combine(today, t))
                if slot_dt <= now:
                    # Если время слота прошло, переносим на завтра
                    slot_dt = slot_dt + timedelta(days=1)
                if next_slot_dt is None or slot_dt < next_slot_dt:
                    next_slot_dt = slot_dt
                    next_slot_name = name
            
            # Пробуждение в 00:01 по Jakarta только для сброса daily_posts_count (чтобы daily_check и постер видели готовые группы с начала дня)
            midnight_dt = timezone.localize(datetime.combine(today, datetime.strptime("00:01", "%H:%M").time()))
            if now < midnight_dt:
                next_wake_dt = min(next_slot_dt, midnight_dt)
            else:
                next_midnight = timezone.localize(datetime.combine(today + timedelta(days=1), datetime.strptime("00:01", "%H:%M").time()))
                next_wake_dt = min(next_slot_dt, next_midnight)
            
            # Ждем до следующего события (слот или полночь)
            wait_seconds = max(1, int((next_wake_dt - now).total_seconds()))
            wait_hours = wait_seconds // 3600
            wait_minutes = (wait_seconds % 3600) // 60
            logger.info(
                f"⏰ Next: {next_slot_name} at {next_slot_dt.strftime('%Y-%m-%d %H:%M:%S')} "
                f"(in {wait_hours}h {wait_minutes}m)" + (" [сначала сброс в 00:01]" if (next_wake_dt.hour == 0 and next_wake_dt.minute == 1) else "")
            )
            await asyncio.sleep(wait_seconds)
            
            run_day = datetime.now(timezone).date()
            now_after = datetime.now(timezone)
            # Проснулись в 00:01 только для сброса счётчиков — не постим
            if (now_after.hour == 0 and now_after.minute <= 2) and next_wake_dt != next_slot_dt:
                logger.info(f"🔄 Midnight reset wake: date={run_day}, counters reset at start of loop")
                continue
            
            # Время слота наступило
            slot_name = next_slot_name
            logger.info(f"⏰ Woke up for slot: {slot_name}, date: {run_day}")
            
            if posted_slots_today.get(slot_name) == run_day:
                logger.info(f"Slot {slot_name}: already posted today, skipping")
                continue
            
            # Сброс дневных счётчиков ПЕРЕД постингом, чтобы группы снова стали "готовы"
            # (иначе при первом проходе за день daily_posts_count ещё от вчера и постер видит 0 групп)
            self.reset_daily_counters_if_needed(run_day)
            
            # Запускаем постинг
            try:
                batch_size = marketer_config.get('batch_size', 5)
                await self.poster.run_batch(batch_size=batch_size)
                posted_slots_today[slot_name] = run_day
                logger.info(f"✅ Completed slot {slot_name}")
            except Exception as e:
                logger.error(f"❌ Error in slot {slot_name}: {e}", exc_info=True)

