import asyncio
import random
import json
import logging
from datetime import datetime, timedelta, time as dtime
from pathlib import Path
from telethon import TelegramClient
from telethon.errors import RPCError

class SmartScheduler:
    def __init__(self):
        self.accounts = []
        self.clients = {}
        self.targets = []
        self.niche_messages = {}
        self.group_niches = {}
        
        # Умное расписание
        self.schedule_history = {}  # История выполнения расписания
        self.account_schedule = {}  # Расписание для каждого аккаунта
        self.group_schedule = {}    # Расписание для каждой группы
        self.message_schedule = {}  # Расписание сообщений
        
        # Настройки умного расписания
        self.slots_per_day = 6
        self.min_interval_between_slots = 3 * 60 * 60  # 3 часа
        self.max_interval_between_slots = 4 * 60 * 60  # 4 часа
        self.randomization_window = 30 * 60  # 30 минут случайности
        
        # Анти-детекция
        self.human_like_delays = True
        self.variable_posting_times = True
        self.weekend_behavior = True
        
        self.setup_logging()
        
    def setup_logging(self):
        """Настройка логирования"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('smart_scheduler.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def load_accounts(self, config_file='accounts_config.json'):
        """Загрузка конфигурации аккаунтов"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                self.accounts = json.load(f)
            
            # Инициализация расписания для каждого аккаунта
            for account in self.accounts:
                session_name = account['session_name']
                self.account_schedule[session_name] = {
                    'last_post_time': None,
                    'next_available_time': None,
                    'daily_posts': 0,
                    'weekly_posts': 0,
                    'preferred_times': [],
                    'avoid_times': [],
                    'cooldown_until': None
                }
                
            self.logger.info(f"Loaded {len(self.accounts)} accounts with smart scheduling")
            
        except FileNotFoundError:
            self.logger.error(f"Config file {config_file} not found")
            return
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in {config_file}: {e}")

    def load_targets(self, targets_file='targets.txt'):
        """Загрузка списка целей из файла"""
        path = Path(targets_file)
        if not path.exists():
            self.logger.warning(f"Targets file {targets_file} not found")
            self.targets = []
            return
        with path.open('r', encoding='utf-8') as f:
            lines = [line.strip() for line in f.readlines()]
        self.targets = [line for line in lines if line]
        
        # Инициализация расписания для каждой группы
        for target in self.targets:
            self.group_schedule[target] = {
                'last_post_time': None,
                'next_available_time': None,
                'daily_posts': 0,
                'weekly_posts': 0,
                'preferred_times': [],
                'avoid_times': [],
                'cooldown_until': None,
                'activity_level': random.uniform(0.3, 0.9)  # Уровень активности группы
            }
            
        self.logger.info(f"Loaded {len(self.targets)} targets with smart scheduling")

    def load_niche_messages(self, niche_files=None):
        """Загрузка сообщений по нишам из отдельных файлов"""
        if niche_files is None:
            niche_files = {
                'morning': 'messages_photo.txt',
                'late_morning': 'messages_housing.txt',
                'noon': 'messages_video.txt',
                'afternoon': 'messages_currency.txt',
                'evening': 'messages_hookah.txt',
                'night': 'messages_manicure.txt',
                'eyebrows': 'messages_eyebrows.txt',
                'eyelashes': 'messages_eyelashes.txt',
                'hair': 'messages_hair.txt',
                'makeup': 'messages_makeup.txt',
                'photographer': 'messages_photographer.txt',
                'cosmetology': 'messages_cosmetology.txt',
                'bike_rental': 'messages_bike_rental.txt',
                'playstation': 'messages_playstation.txt',
                'videographer': 'messages_videographer.txt',
                'transport': 'messages_transport.txt',
                'car_rental': 'messages_car_rental.txt',
                'tourism': 'messages_tourism.txt',
                'media_studio': 'messages_media_studio.txt',
                'rental_property': 'messages_rental_property.txt',
                'sale_property': 'messages_sale_property.txt',
                'designer': 'messages_designer.txt',
            }
            
        self.niche_messages = {}
        for niche, filename in niche_files.items():
            path = Path(filename)
            if not path.exists():
                self.logger.warning(f"Niche file {filename} not found for {niche}")
                continue
            with path.open('r', encoding='utf-8') as f:
                lines = [line.strip() for line in f.readlines()]
            msgs = [line for line in lines if line]
            if msgs:
                self.niche_messages[niche] = msgs
                self.logger.info(f"Loaded {len(msgs)} messages for {niche}")

    def load_group_niches(self):
        """Загрузка сопоставления групп с нишами"""
        try:
            with open('group_niches.json', 'r', encoding='utf-8') as f:
                self.group_niches = json.load(f)
            self.logger.info(f"Loaded {len(self.group_niches)} group-niche mappings")
        except FileNotFoundError:
            self.logger.warning("group_niches.json not found, creating default mapping")
            self.create_default_group_niches()

    def create_default_group_niches(self):
        """Создание сопоставления групп с нишами по умолчанию"""
        niches = list(self.niche_messages.keys())
        self.group_niches = {}
        
        for i, target in enumerate(self.targets):
            # Распределяем ниши равномерно по группам
            niche = niches[i % len(niches)]
            self.group_niches[target] = niche
            
        # Сохраняем в файл
        with open('group_niches.json', 'w', encoding='utf-8') as f:
            json.dump(self.group_niches, f, indent=2, ensure_ascii=False)
            
        self.logger.info(f"Created default group-niche mapping for {len(self.targets)} groups")

    def generate_human_like_schedule(self, date):
        """Генерация человеческого расписания на день"""
        # Базовые временные слоты
        base_slots = [
            (6, 0),   # Утро
            (9, 30),  # Позднее утро
            (12, 0),  # Обед
            (15, 30), # Послеобеденное время
            (18, 0),  # Вечер
            (21, 0),  # Ночь
        ]
        
        # Добавляем случайность к времени
        human_slots = []
        for hour, minute in base_slots:
            # Случайное отклонение ±30 минут
            random_offset = random.randint(-30, 30)
            new_minute = minute + random_offset
            
            # Корректируем если вышли за границы
            if new_minute < 0:
                new_minute += 60
                hour -= 1
            elif new_minute >= 60:
                new_minute -= 60
                hour += 1
                
            # Проверяем границы дня
            if 0 <= hour < 24:
                human_slots.append((hour, new_minute))
        
        # Сортируем по времени
        human_slots.sort()
        
        # Создаем расписание
        schedule = []
        for i, (hour, minute) in enumerate(human_slots):
            slot_time = datetime.combine(date, dtime(hour, minute))
            
            # Выбираем случайную нишу
            niche = random.choice(list(self.niche_messages.keys()))
            
            schedule.append({
                'time': slot_time,
                'niche': niche,
                'slot_id': i,
                'executed': False
            })
        
        return schedule

    def get_optimal_posting_time(self, account_name, group):
        """Получение оптимального времени для постинга"""
        now = datetime.now()
        
        # Базовые предпочтения по времени
        time_preferences = {
            'morning': (6, 12),    # 6:00 - 12:00
            'afternoon': (12, 18), # 12:00 - 18:00
            'evening': (18, 22),   # 18:00 - 22:00
            'night': (22, 6)       # 22:00 - 6:00
        }
        
        # Выбираем случайное время в предпочтительном диапазоне
        period = random.choice(list(time_preferences.keys()))
        start_hour, end_hour = time_preferences[period]
        
        if start_hour < end_hour:
            # Обычный случай (например, 6-12)
            hour = random.randint(start_hour, end_hour - 1)
        else:
            # Переход через полночь (например, 22-6)
            hour = random.randint(start_hour, 23) if random.random() < 0.5 else random.randint(0, end_hour - 1)
        
        minute = random.randint(0, 59)
        
        # Создаем время
        optimal_time = datetime.combine(now.date(), dtime(hour, minute))
        
        # Если время уже прошло, переносим на завтра
        if optimal_time <= now:
            optimal_time += timedelta(days=1)
        
        return optimal_time

    def calculate_group_activity_score(self, group, time):
        """Расчет уровня активности группы в данное время"""
        hour = time.hour
        weekday = time.weekday()
        
        # Базовый уровень активности
        base_activity = self.group_schedule[group]['activity_level']
        
        # Модификаторы по времени
        time_modifiers = {
            'morning': 0.8,    # 6-12
            'afternoon': 1.0,  # 12-18
            'evening': 1.2,    # 18-22
            'night': 0.6       # 22-6
        }
        
        if 6 <= hour < 12:
            time_period = 'morning'
        elif 12 <= hour < 18:
            time_period = 'afternoon'
        elif 18 <= hour < 22:
            time_period = 'evening'
        else:
            time_period = 'night'
        
        time_modifier = time_modifiers[time_period]
        
        # Модификатор по дню недели
        if weekday < 5:  # Будни
            day_modifier = 1.0
        else:  # Выходные
            day_modifier = 1.1
        
        # Итоговый уровень активности
        activity_score = base_activity * time_modifier * day_modifier
        
        return min(activity_score, 1.0)

    def select_best_account_for_time(self, time, exclude_accounts=None):
        """Выбор лучшего аккаунта для данного времени"""
        if exclude_accounts is None:
            exclude_accounts = set()
        
        available_accounts = []
        
        for account_name, schedule in self.account_schedule.items():
            if account_name in exclude_accounts:
                continue
                
            # Проверяем доступность
            if schedule['cooldown_until'] and time < schedule['cooldown_until']:
                continue
                
            # Проверяем лимиты
            if schedule['daily_posts'] >= 3:  # Максимум 3 поста в день
                continue
                
            # Рассчитываем приоритет
            priority = self.calculate_account_priority(account_name, time)
            available_accounts.append((account_name, priority))
        
        if not available_accounts:
            return None
        
        # Сортируем по приоритету
        available_accounts.sort(key=lambda x: x[1], reverse=True)
        
        return available_accounts[0][0]

    def calculate_account_priority(self, account_name, time):
        """Расчет приоритета аккаунта для данного времени"""
        schedule = self.account_schedule[account_name]
        
        # Базовый приоритет
        priority = 1.0
        
        # Модификатор по времени с последнего поста
        if schedule['last_post_time']:
            time_since_last = (time - schedule['last_post_time']).total_seconds()
            if time_since_last > 6 * 60 * 60:  # Больше 6 часов
                priority += 0.5
            elif time_since_last < 2 * 60 * 60:  # Меньше 2 часов
                priority -= 0.3
        
        # Модификатор по количеству постов
        if schedule['daily_posts'] == 0:
            priority += 0.3
        elif schedule['daily_posts'] >= 2:
            priority -= 0.2
        
        # Случайный модификатор
        priority += random.uniform(-0.1, 0.1)
        
        return max(priority, 0.1)

    def select_best_group_for_time(self, time, exclude_groups=None):
        """Выбор лучшей группы для данного времени"""
        if exclude_groups is None:
            exclude_groups = set()
        
        available_groups = []
        
        for group, schedule in self.group_schedule.items():
            if group in exclude_groups:
                continue
                
            # Проверяем доступность
            if schedule['cooldown_until'] and time < schedule['cooldown_until']:
                continue
                
            # Рассчитываем приоритет
            priority = self.calculate_group_priority(group, time)
            available_groups.append((group, priority))
        
        if not available_groups:
            return None
        
        # Сортируем по приоритету
        available_groups.sort(key=lambda x: x[1], reverse=True)
        
        return available_groups[0][0]

    def calculate_group_priority(self, group, time):
        """Расчет приоритета группы для данного времени"""
        schedule = self.group_schedule[group]
        
        # Базовый приоритет
        priority = 1.0
        
        # Модификатор по активности группы
        activity_score = self.calculate_group_activity_score(group, time)
        priority *= activity_score
        
        # Модификатор по времени с последнего поста
        if schedule['last_post_time']:
            time_since_last = (time - schedule['last_post_time']).total_seconds()
            if time_since_last > 24 * 60 * 60:  # Больше 24 часов
                priority += 0.5
            elif time_since_last < 6 * 60 * 60:  # Меньше 6 часов
                priority -= 0.3
        
        # Модификатор по количеству постов
        if schedule['daily_posts'] == 0:
            priority += 0.3
        elif schedule['daily_posts'] >= 2:
            priority -= 0.2
        
        # Случайный модификатор
        priority += random.uniform(-0.1, 0.1)
        
        return max(priority, 0.1)

    def update_schedule_after_post(self, account_name, group, time):
        """Обновление расписания после поста"""
        # Обновляем расписание аккаунта
        account_schedule = self.account_schedule[account_name]
        account_schedule['last_post_time'] = time
        account_schedule['daily_posts'] += 1
        account_schedule['cooldown_until'] = time + timedelta(hours=6)
        
        # Обновляем расписание группы
        group_schedule = self.group_schedule[group]
        group_schedule['last_post_time'] = time
        group_schedule['daily_posts'] += 1
        group_schedule['cooldown_until'] = time + timedelta(hours=24)
        
        self.logger.info(f"Updated schedule: {account_name} -> {group} at {time}")

    def reset_daily_schedules(self):
        """Сброс дневных расписаний"""
        for account_name in self.account_schedule:
            self.account_schedule[account_name]['daily_posts'] = 0
            
        for group in self.group_schedule:
            self.group_schedule[group]['daily_posts'] = 0
            
        self.logger.info("Daily schedules reset")

    async def initialize_clients(self):
        """Инициализация всех клиентов"""
        for account in self.accounts:
            try:
                api_id = int(account['api_id'])
                
                string_session = account.get('string_session')
                if string_session:
                    from telethon.sessions import StringSession
                    client = TelegramClient(
                        StringSession(string_session),
                        api_id,
                        account['api_hash']
                    )
                else:
                    client = TelegramClient(
                        f"sessions/{account['session_name']}", 
                        api_id, 
                        account['api_hash']
                    )
                await client.connect()
                
                if await client.is_user_authorized():
                    self.clients[account['session_name']] = client
                    me = await client.get_me()
                    username = getattr(me, 'username', 'No username')
                    self.logger.info(f"✅ Initialized client for {account['session_name']} (@{username})")
                else:
                    self.logger.info(f"❌ Skipping unauthorized client {account['session_name']}")
                    await client.disconnect()
                    
            except Exception as e:
                self.logger.error(f"❌ Failed to initialize {account['session_name']}: {e}")

    async def resolve_target(self, client, target):
        """Разрешение цели: username/link/ID -> entity"""
        try:
            if target.isdigit():
                target_id = int(target)
                try:
                    return await client.get_entity(target_id)
                except Exception:
                    pass
                # Поиск среди диалогов
                dialogs = [d async for d in client.iter_dialogs()]
                for dialog in dialogs:
                    entity = dialog.entity
                    try:
                        if getattr(entity, 'id', None) == target_id:
                            return entity
                    except Exception:
                        continue
                raise ValueError(f"Entity with id {target_id} not found")
            else:
                return await client.get_entity(target)
        except Exception as e:
            self.logger.error(f"Failed to resolve target {target}: {e}")
            return None

    async def execute_smart_post(self, account_name, group, niche, message, dry_run=True):
        """Выполнение умного поста"""
        client = self.clients.get(account_name)
        if not client:
            self.logger.error(f"Client not found for account {account_name}")
            return False
            
        entity = await self.resolve_target(client, group)
        if not entity:
            self.logger.error(f"Failed to resolve target {group}")
            return False
            
        if dry_run:
            self.logger.info(f"[DRY-RUN] Would send to {group} via {account_name}: {message}")
            return True
        else:
            try:
                await client.send_message(entity, message)
                self.logger.info(f"✅ SENT to {group} via {account_name}: {message}")
                self.update_schedule_after_post(account_name, group, datetime.now())
                return True
            except RPCError as e:
                self.logger.error(f"RPCError sending to {group} via {account_name}: {e}")
                return False
            except Exception as e:
                self.logger.error(f"Failed to send to {group} via {account_name}: {e}")
                return False

    async def run_smart_scheduler(self, dry_run=True):
        """Запуск умного планировщика"""
        self.logger.info("🧠 Starting Smart Scheduler...")
        
        while True:
            now = datetime.now()
            today = now.date()
            
            # Сброс дневных расписаний в полночь
            if now.hour == 0 and now.minute == 0:
                self.reset_daily_schedules()
            
            # Генерируем расписание на день
            daily_schedule = self.generate_human_like_schedule(today)
            
            # Находим следующий слот
            next_slot = None
            for slot in daily_schedule:
                if slot['time'] > now and not slot['executed']:
                    next_slot = slot
                    break
            
            if not next_slot:
                # Если слотов на сегодня нет, ждем до завтра
                tomorrow = today + timedelta(days=1)
                next_day_schedule = self.generate_human_like_schedule(tomorrow)
                if next_day_schedule:
                    next_slot = next_day_schedule[0]
            
            if not next_slot:
                self.logger.warning("No available slots found")
                await asyncio.sleep(3600)  # Ждем час
                continue
            
            # Ждем до времени слота
            wait_seconds = max(1, int((next_slot['time'] - now).total_seconds()))
            self.logger.info(f"Next slot: {next_slot['time'].strftime('%Y-%m-%d %H:%M:%S')} (in {wait_seconds}s)")
            await asyncio.sleep(wait_seconds)
            
            # Выполняем пост
            self.logger.info(f"🧠 Executing smart post for niche: {next_slot['niche']}")
            
            # Выбираем лучший аккаунт и группу
            account_name = self.select_best_account_for_time(now)
            group = self.select_best_group_for_time(now)
            
            if account_name and group:
                # Получаем сообщение
                niche = next_slot['niche']
                if niche in self.niche_messages:
                    message = random.choice(self.niche_messages[niche])
                else:
                    message = "Ищу специалиста на Бали"
                
                # Выполняем пост
                success = await self.execute_smart_post(account_name, group, niche, message, dry_run)
                if success:
                    next_slot['executed'] = True
            else:
                self.logger.warning("No available account or group for posting")

    async def run(self, dry_run=True, schedule=False):
        """Запуск системы"""
        self.logger.info("🚀 Starting Smart Scheduler System...")
        
        # Загружаем конфигурацию
        self.load_accounts()
        self.load_targets()
        self.load_niche_messages()
        self.load_group_niches()
        
        # Инициализируем клиенты
        await self.initialize_clients()
        
        if not self.clients:
            self.logger.error("❌ No authorized clients available")
            return
            
        self.logger.info(f"🎉 System ready with {len(self.clients)} accounts!")
        
        if schedule:
            await self.run_smart_scheduler(dry_run=dry_run)
        else:
            # Одноразовый запуск
            now = datetime.now()
            account_name = self.select_best_account_for_time(now)
            group = self.select_best_group_for_time(now)
            
            if account_name and group:
                niche = self.group_niches.get(group, 'morning')
                if niche in self.niche_messages:
                    message = random.choice(self.niche_messages[niche])
                else:
                    message = "Ищу специалиста на Бали"
                
                await self.execute_smart_post(account_name, group, niche, message, dry_run)

# Функция для запуска
async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Smart Telegram PR promotion system')
    parser.add_argument('--post', action='store_true', help='Отправлять сообщения (иначе dry-run)')
    parser.add_argument('--schedule', action='store_true', help='Режим планировщика')
    args = parser.parse_args()

    system = SmartScheduler()
    await system.run(dry_run=not args.post, schedule=args.schedule)

if __name__ == "__main__":
    asyncio.run(main())



