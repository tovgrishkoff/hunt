"""
Планировщик для Account Manager
Работает по расписанию Asia/Jakarta (ночью по Киеву)
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import pytz
from telethon.errors import FloodWaitError

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

# Импорт keywords
keywords_spec = importlib.util.spec_from_file_location(
    "keywords", Path(__file__).parent / "keywords.py"
)
keywords_module = importlib.util.module_from_spec(keywords_spec)
keywords_spec.loader.exec_module(keywords_module)
build_search_keywords_from_messages = keywords_module.build_search_keywords_from_messages
SearchKeywordsConfig = keywords_module.SearchKeywordsConfig

logger = logging.getLogger(__name__)


class AccountManagerScheduler:
    """Планировщик для Account Manager"""
    
    def __init__(self):
        self.config_loader = ConfigLoader()
        self.client_manager = TelegramClientManager()
        self.finder = None
        self.joiner = None
        self._last_reset_date = None
        # True = режим "поддержки" (работаем по слотам), False = "быстрая обработка" (есть очередь new)
        self._slot_processing_mode = True
        # Первый запуск: позволяем один форс-слот без ожидания расписания
        self._first_run = True
        # Опциональный список session_name аккаунтов, которые должны
        # использоваться для поиска / вступления (например, Bali love-аккаунты)
        self.allowed_sessions: Optional[List[str]] = None
        # Локальный cooldown для аккаунтов поиска (по FloodWait), ключ — session_name
        self._search_cooldowns: Dict[str, datetime] = {}
        # Порядок обхода аккаунтов при поиске (round-robin)
        self._search_order: List[str] = []
        self._search_index: int = 0
    
    def _load_allowed_sessions_for_niche(self, niche_name: str) -> Optional[List[str]]:
        """
        Загрузка списка разрешённых аккаунтов для ниши.
        
        Для ниши 'bali' используем bali_accounts_config.json, чтобы
        те же love-аккаунты, которые постят, также искали и вступали в новые группы.
        
        Для ниши 'ukraine_cars' или 'cars' используем lexus_accounts_config.json.
        """
        if niche_name == "bali":
            possible_paths = [
                Path("/app/bali_accounts_config.json"),
                Path("bali_accounts_config.json"),
                Path("../bali_accounts_config.json"),
            ]
            config_key = "allowed_accounts"
            config_name = "bali_accounts_config.json"
        elif niche_name in ["ukraine_cars", "cars"]:
            possible_paths = [
                Path("/app/lexus_accounts_config.json"),
                Path("lexus_accounts_config.json"),
                Path("../lexus_accounts_config.json"),
            ]
            config_key = "allowed_accounts"
            config_name = "lexus_accounts_config.json"
        else:
            return None
        
        for path in possible_paths:
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    allowed = data.get(config_key) or []
                    allowed = [s for s in allowed if s]
                    if allowed:
                        logger.info(
                            f"✅ Loaded {len(allowed)} allowed {niche_name} sessions from {path}: "
                            f"{', '.join(allowed)}"
                        )
                        return allowed
                except Exception as e:
                    logger.warning(f"⚠️ Failed to load {config_name} from {path}: {e}")
        
        logger.warning(f"⚠️ {config_name} not found or empty, using all active accounts")
        return None
    
    async def initialize(self):
        """Инициализация компонентов"""
        # Загрузка конфигурации ниши
        # Используем переменную окружения NICHE, если установлена (для Ukraine/Lexus проекта)
        niche_name = os.getenv('NICHE')
        if niche_name:
            logger.info(f"📋 Using niche from environment: {niche_name}")
            niche_config = self.config_loader.load_niche_config(niche_name)
        else:
            niche_config = self.config_loader.load_niche_config()
        logger.info(f"📋 Active niche: {niche_config['display_name']} ({niche_config['name']})")
        
        # Загружаем allowed_sessions для ниши (для Bali - love-аккаунты)
        self.allowed_sessions = self._load_allowed_sessions_for_niche(niche_config.get("name"))
        
        # Инициализация клиентов
        db = SessionLocal()
        try:
            await self.client_manager.load_accounts_from_db(db)
            logger.info(f"✅ Loaded {len(self.client_manager.clients)} accounts")
            
            # Если заданы allowed_sessions (Bali), фильтруем клиентов:
            # и поиск, и вступление будут использовать только эти аккаунты.
            if self.allowed_sessions:
                before = len(self.client_manager.clients)
                self.client_manager.clients = {
                    name: client
                    for name, client in self.client_manager.clients.items()
                    if name in self.allowed_sessions
                }
                after = len(self.client_manager.clients)
                logger.info(
                    f"✅ Restricted clients to allowed_sessions for niche {niche_config.get('name')}: "
                    f"{after}/{before} clients kept"
                )
        except Exception as e:
            logger.error(f"❌ Failed to load accounts: {e}")
            raise
        finally:
            db.close()
        
        # Инициализируем порядок обхода аккаунтов для поиска (round-robin)
        self._search_order = list(self.client_manager.clients.keys())
        
        # Инициализация finder и joiner
        self.finder = GroupFinder(self.client_manager)
        # Для joiner передаём allowed_sessions, чтобы он выбирал аккаунт
        # только из списка Bali love-аккаунтов при вступлении.
        self.joiner = GroupJoiner(
            self.client_manager,
            niche_config,
            allowed_sessions=self.allowed_sessions,
        )
    
    def _get_next_search_client_name(self) -> Optional[str]:
        """
        Выбрать следующий аккаунт для поиска с учётом локального cooldown.
        
        Аккаунты, попавшие в FloodWait на долгий срок, временно исключаются
        из использования для STEP 1 (поиска новых групп), но продолжают
        участвовать в других процессах после истечения cooldown.
        """
        if not self.client_manager.clients:
            return None
        
        now_utc = datetime.utcnow()
        total = len(self._search_order)
        if total == 0:
            self._search_order = list(self.client_manager.clients.keys())
            total = len(self._search_order)
            if total == 0:
                return None
        
        # Очищаем истёкшие cooldown'ы
        to_delete = [name for name, until in self._search_cooldowns.items() if until <= now_utc]
        for name in to_delete:
            self._search_cooldowns.pop(name, None)
        
        # Round-robin по доступным аккаунтам
        for _ in range(total):
            name = self._search_order[self._search_index % total]
            self._search_index = (self._search_index + 1) % total
            if name not in self.client_manager.clients:
                continue
            cooldown_until = self._search_cooldowns.get(name)
            if cooldown_until and cooldown_until > now_utc:
                continue
            return name
        
        logger.warning("⚠️ Нет доступных аккаунтов для поиска (все в cooldown по FloodWait)")
        return None
    
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
        
        # Используем переменную окружения NICHE, если установлена (для Ukraine/Lexus проекта)
        niche_name = os.getenv('NICHE')
        if niche_name:
            niche_config = self.config_loader.load_niche_config(niche_name)
        else:
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
                # Если это самый первый запуск — делаем форс-обработку без ожидания слота
                if self._first_run:
                    logger.info("⚡ First run with empty queue (new == 0) — forcing immediate slot")
                    slot_name = "forced_start"
                    run_day = today
                    # После первой форс-обработки переходим к обычному режиму
                    self._first_run = False
                else:
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
                # Если очередь new большая — пропускаем поиск (STEP 1), сразу идём во вступления (STEP 2).
                # Так не упираемся в FloodWait по поиску и быстрее разгребаем очередь.
                new_groups_count = self.get_new_groups_count(niche)
                skip_search_when_queue_ge = 80  # порог: при new >= 80 поиск не делаем
                do_search = new_groups_count < skip_search_when_queue_ge

                # 1. Поиск новых групп (пропускаем, если очередь уже большая)
                if do_search:
                    logger.info("=" * 80)
                    logger.info("🔍 STEP 1: SEARCHING FOR NEW GROUPS")
                    logger.info("=" * 80)
                else:
                    logger.info("=" * 80)
                    logger.info("🔍 STEP 1: SKIP (очередь new = %s >= %s, сразу переходим к вступлениям)", new_groups_count, skip_search_when_queue_ge)
                    logger.info("=" * 80)

                manager_config = niche_config.get('manager', {})

                if do_search:
                    config_keywords = manager_config.get('search_keywords', []) or []
                    messages = self.config_loader.load_messages(niche)
                    auto_keywords = build_search_keywords_from_messages(
                        messages=messages,
                        cfg=SearchKeywordsConfig(),
                    )
                    search_keywords = []
                    for kw in [*config_keywords, *auto_keywords]:
                        kw = (kw or "").strip()
                        if kw and kw not in search_keywords:
                            search_keywords.append(kw)
                    if not search_keywords:
                        logger.warning("⚠️ No search keywords available (config + auto), skipping search")
                    else:
                        logger.info(
                            f"🔎 Search keywords: {len(search_keywords)} total "
                            f"(config={len(config_keywords)}, auto={len(auto_keywords)})"
                        )
                        if not self.client_manager.clients:
                            logger.error("❌ No clients available for search")
                        else:
                            client_name = self._get_next_search_client_name()
                            if not client_name:
                                logger.error("❌ No search accounts available (all in cooldown or not loaded)")
                            else:
                                client = await self.client_manager.ensure_client_connected(client_name)
                                if not client:
                                    logger.error(f"❌ Failed to connect client {client_name} for search")
                                else:
                                    logger.info(f"👤 Using account for search: {client_name}")
                                    limit_per_keyword = manager_config.get("limit_per_keyword", 40)
                                    try:
                                        found_groups = await self.finder.search_groups(
                                            client, search_keywords, limit_per_keyword=limit_per_keyword
                                        )
                                        if found_groups:
                                            keyword_to_sub_niche = (manager_config.get('keyword_to_sub_niche') or {})
                                            saved = self.finder.save_groups_to_db(
                                                found_groups, niche,
                                                keyword_to_sub_niche=keyword_to_sub_niche,
                                            )
                                            logger.info(f"✅ Saved {saved} new groups to DB")
                                        else:
                                            logger.info("ℹ️ No new groups found")
                                    except FloodWaitError as e:
                                        wait_seconds = int(getattr(e, "seconds", 0) or 0)
                                        if wait_seconds <= 0:
                                            wait_seconds = 600
                                        cooldown_seconds = max(wait_seconds, 600)
                                        cooldown_seconds = min(cooldown_seconds, 3600)
                                        until = datetime.utcnow() + timedelta(seconds=cooldown_seconds)
                                        self._search_cooldowns[client_name] = until
                                        logger.warning(
                                            "  ⏳ FloodWait %s сек для поиска (%s), cooldown до %s",
                                            wait_seconds, client_name, until.isoformat(timespec="seconds"),
                                        )
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

