import asyncio
import random
import json
import logging
import argparse
from pathlib import Path
from datetime import datetime, timedelta, time as dtime
from telethon import TelegramClient
from telethon.errors import RPCError
from telethon.tl.functions.account import UpdateProfileRequest

class AuthorizedOnlyPromotionSystem:
    def __init__(self):
        self.accounts = []
        self.clients = {}
        self.account_usage = {}
        self.posted_messages = {}
        self.targets = []
        self.messages = []
        self.niche_messages = {}
        self.posted_slots_today = {}
        self.dialog_entities_cache = {}
        self.group_niches = {}
        self.daily_posts = {}  # Счетчик постов в день для каждого аккаунта
        self.max_daily_posts = 4  # Максимум постов в день с аккаунта
        self.setup_logging()
        
    def setup_logging(self):
        """Настройка логирования"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('promotion.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def load_accounts(self, config_file='accounts_config.json'):
        """Загрузка конфигурации аккаунтов"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                self.accounts = json.load(f)
            
            for account in self.accounts:
                self.account_usage[account['session_name']] = 0
                self.daily_posts[account['session_name']] = 0
                
            self.logger.info(f"Loaded {len(self.accounts)} accounts")
            
        except FileNotFoundError:
            self.logger.error(f"Config file {config_file} not found")
            return
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in {config_file}: {e}")
            return

    def load_targets(self, targets_file: str = 'targets.txt'):
        """Загрузка списка целей из файла"""
        path = Path(targets_file)
        if not path.exists():
            self.logger.warning(f"Targets file {targets_file} not found. Create it with chat usernames/links or IDs.")
            self.targets = []
            return
        with path.open('r', encoding='utf-8') as f:
            lines = [line.strip() for line in f.readlines()]
        self.targets = [line for line in lines if line]
        self.logger.info(f"Loaded {len(self.targets)} targets")

    def load_messages(self, messages_file: str = 'messages.txt'):
        """Загрузка сообщений для постинга"""
        path = Path(messages_file)
        if not path.exists():
            self.logger.warning(f"Messages file {messages_file} not found. Create it with one message per line.")
            self.messages = []
            return
        with path.open('r', encoding='utf-8') as f:
            lines = [line.strip() for line in f.readlines()]
        # Пустые строки игнорируем
        self.messages = [line for line in lines if line]
        self.logger.info(f"Loaded {len(self.messages)} messages")

    def load_niche_messages(self, niche_files: dict = None):
        """Загрузка сообщений по нишам из отдельных файлов"""
        if niche_files is None:
            niche_files = {
                'general': 'messages_general.txt',
                'morning': 'messages_photo.txt',
                'noon': 'messages_housing.txt',
                'evening': 'messages_video.txt',
                'currency': 'messages_currency.txt',
                'hookah': 'messages_hookah.txt',
                'manicure': 'messages_manicure.txt',
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
            self.logger.warning("group_niches.json not found, using general messages for all groups")
            self.group_niches = {}

    async def resolve_target(self, client: TelegramClient, target: str):
        """Разрешение цели: username/link/ID -> entity"""
        try:
            # Попытка как число (ID)
            if target.isdigit():
                target_id = int(target)
                # Сначала пробуем напрямую
                try:
                    return await client.get_entity(target_id)
                except Exception:
                    pass
                # Затем ищем среди диалогов
                if client not in self.dialog_entities_cache:
                    self.dialog_entities_cache[client] = [d async for d in client.iter_dialogs()]
                for dialog in self.dialog_entities_cache[client]:
                    entity = dialog.entity
                    try:
                        if getattr(entity, 'id', None) == target_id:
                            return entity
                        # Попытка сопоставить с полным ID каналов (-100prefix)
                        if isinstance(target_id, int) and getattr(entity, 'id', None) is not None:
                            full_id = int(f"100{entity.id}") if entity.id > 0 else abs(entity.id)
                            if full_id == target_id:
                                return entity
                    except Exception:
                        continue
                raise ValueError(f"Entity with id {target_id} not found in dialogs")
            # Иначе строка (@username или ссылка)
            return await client.get_entity(target)
        except Exception as e:
            self.logger.error(f"Failed to resolve target {target}: {e}")
            return None

    def get_next_authorized_client(self):
        """Получение следующего АВТОРИЗОВАННОГО клиента для ротации"""
        if not self.clients:
            return None, None
        
        # Фильтруем только авторизованные клиенты
        authorized_clients = {}
        for account_name, client in self.clients.items():
            if client.is_connected() and self.daily_posts.get(account_name, 0) < self.max_daily_posts:
                # Проверяем, что аккаунт авторизован
                try:
                    # Если можем получить информацию о пользователе, значит авторизован
                    me = asyncio.create_task(client.get_me())
                    if me:
                        authorized_clients[account_name] = client
                except:
                    continue
        
        if not authorized_clients:
            self.logger.warning("No authorized clients available")
            return None, None
        
        # Находим клиента с наименьшим использованием среди авторизованных
        min_usage = min(self.account_usage.get(name, 0) for name in authorized_clients.keys())
        for account_name in authorized_clients.keys():
            if self.account_usage.get(account_name, 0) == min_usage:
                return account_name, authorized_clients[account_name]
        
        # Fallback: первый авторизованный клиент
        first_account = list(authorized_clients.keys())[0]
        return first_account, authorized_clients[first_account]

    async def post_to_targets(self, dry_run: bool = True, interval_seconds: int = 60, max_posts: int = 1, niche: str = None):
        """Постинг по целям с указанным интервалом и ротацией АВТОРИЗОВАННЫХ аккаунтов"""
        if not self.targets:
            self.logger.warning("No targets to post to. Skipping posting.")
            return
        # Загружаем сопоставление групп с нишами
        self.load_group_niches()

        if not self.clients:
            self.logger.error("No initialized clients available")
            return

        sent_count = 0
        # Рандомизируем порядок групп
        random_targets = random.sample(self.targets, len(self.targets))
        
        for idx, target in enumerate(random_targets, start=1):
            # Определяем нишу для конкретной группы
            group_niche = self.group_niches.get(target, 'general')
            
            # Выбираем источник сообщений
            if group_niche in self.niche_messages:
                source_messages = self.niche_messages[group_niche]
                self.logger.info(f"Using {group_niche} messages for {target}")
            elif niche and niche in self.niche_messages:
                source_messages = self.niche_messages[niche]
                self.logger.info(f"Using {niche} messages for {target}")
            else:
                source_messages = self.messages
                self.logger.info(f"Using general messages for {target}")
                
            if not source_messages:
                self.logger.warning(f"No messages available for {target}")
                continue
                
            # Ротация АВТОРИЗОВАННЫХ аккаунтов
            client_name, client = self.get_next_authorized_client()
            if client is None:
                self.logger.error("No authorized clients available for posting")
                break
                
            self.logger.info(f"Using AUTHORIZED client {client_name} (usage: {self.account_usage[client_name]}). Dry-run={dry_run}. Group={target}, Niche={group_niche}")

            entity = await self.resolve_target(client, target)
            if entity is None:
                continue

            message = random.choice(source_messages)
            if dry_run:
                self.logger.info(f"[DRY-RUN] Would send to {target} via {client_name}: {message}")
            else:
                try:
                    await client.send_message(entity, message)
                    self.logger.info(f"✅ SENT to {target} via {client_name}: {message}")
                    sent_count += 1
                    # Увеличиваем счётчики использования аккаунта
                    self.account_usage[client_name] += 1
                    self.daily_posts[client_name] += 1
                    self.logger.info(f"Account {client_name} daily posts: {self.daily_posts[client_name]}/{self.max_daily_posts}")
                except RPCError as e:
                    self.logger.error(f"RPCError sending to {target} via {client_name}: {e}")
                except Exception as e:
                    self.logger.error(f"Failed to send to {target} via {client_name}: {e}")

            if sent_count >= max_posts and not dry_run:
                self.logger.info(f"Max posts reached ({max_posts}). Stopping posting.")
                break

            if idx < len(self.targets):
                await asyncio.sleep(interval_seconds)
    
    async def initialize_clients(self):
        """Инициализация всех клиентов"""
        for account in self.accounts:
            try:
                # Преобразуем api_id в int если он строка
                api_id = int(account['api_id'])
                
                # Если есть StringSession в конфиге — используем его, иначе файловую сессию
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
                
                # Проверяем авторизацию
                if await client.is_user_authorized():
                    self.clients[account['session_name']] = client
                    me = await client.get_me()
                    username = getattr(me, 'username', 'No username')
                    self.logger.info(f"✅ Initialized AUTHORIZED client for {account['session_name']} (@{username})")
                else:
                    self.logger.info(f"❌ Skipping UNAUTHORIZED client {account['session_name']}")
                    await client.disconnect()
                    
            except Exception as e:
                self.logger.error(f"❌ Failed to initialize {account['session_name']}: {e}")
    
    async def test_connection(self):
        """Тест подключения аккаунта"""
        try:
            success_count = 0
            for account_name, client in self.clients.items():
                if client.is_connected():
                    try:
                        me = await client.get_me()
                        username = getattr(me, 'username', 'No username')
                        self.logger.info(f"✅ Account {account_name} connected as @{username}")
                        success_count += 1
                    except Exception as e:
                        self.logger.error(f"❌ Failed to get user info for {account_name}: {e}")
            return success_count > 0
        except Exception as e:
            self.logger.error(f"❌ Connection test failed: {e}")
            return False
    
    async def run(self, do_post: bool = False, interval_seconds: int = 60, max_posts: int = 1, schedule: bool = False):
        """Запуск системы продвижения"""
        self.logger.info("🚀 Starting Authorized-Only Promotion System...")
        
        # Загружаем конфигурацию
        self.load_accounts()
        self.load_targets()
        self.load_messages()
        self.load_niche_messages()
        self.load_group_niches()
        
        # Инициализируем только авторизованные клиенты
        await self.initialize_clients()
        
        # Тестируем подключение
        if await self.test_connection():
            self.logger.info(f"🎉 System ready with {len(self.clients)} authorized accounts!")
            if schedule:
                await self.run_scheduler(do_post=do_post)
            else:
                if do_post:
                    await self.post_to_targets(dry_run=False, interval_seconds=interval_seconds, max_posts=max_posts)
                else:
                    await self.post_to_targets(dry_run=True, interval_seconds=interval_seconds, max_posts=max_posts)
        else:
            self.logger.error("❌ System failed to initialize")

    async def run_scheduler(self, do_post: bool):
        """Планировщик: 6 слотов в день с разными нишами и ротацией АВТОРИЗОВАННЫХ аккаунтов"""
        # Расписание по локальному времени - 6 слотов в день каждые 3 часа
        slots = [
            ('morning', dtime(hour=6, minute=0)),
            ('late_morning', dtime(hour=9, minute=0)),
            ('noon', dtime(hour=12, minute=0)),
            ('afternoon', dtime(hour=15, minute=0)),
            ('evening', dtime(hour=18, minute=0)),
            ('night', dtime(hour=21, minute=0)),
        ]
        self.logger.info("Scheduler started: 6 slots per day (06:00, 09:00, 12:00, 15:00, 18:00, 21:00) with AUTHORIZED account rotation")
        self.posted_slots_today = {name: None for name, _ in slots}

        while True:
            now = datetime.now()
            today = now.date()

            # Сброс отметок в полночь
            for name in list(self.posted_slots_today.keys()):
                if self.posted_slots_today[name] != today:
                    self.posted_slots_today[name] = None

            # Найти следующий слот
            next_slot_name = None
            next_slot_dt = None
            for name, t in slots:
                slot_dt = datetime.combine(today, t)
                if slot_dt <= now:
                    # Если время слота прошло, переносим на завтра
                    slot_dt = slot_dt + timedelta(days=1)
                if next_slot_dt is None or slot_dt < next_slot_dt:
                    next_slot_dt = slot_dt
                    next_slot_name = name

            # Подождать до следующего слота
            wait_seconds = max(1, int((next_slot_dt - now).total_seconds()))
            self.logger.info(f"Next slot: {next_slot_name} at {next_slot_dt.strftime('%Y-%m-%d %H:%M:%S')} (in {wait_seconds}s)")
            await asyncio.sleep(wait_seconds)

            # Время слота наступило
            slot_name = next_slot_name
            run_day = datetime.now().date()

            if self.posted_slots_today.get(slot_name) == run_day:
                # Уже постили в этом слоте сегодня (на случай перезапуска)
                self.logger.info(f"Slot {slot_name}: already posted today, skipping")
                continue

            # Выполнить постинг из соответствующей ниши с ротацией АВТОРИЗОВАННЫХ аккаунтов
            niche = slot_name  # 'morning'|'noon'|'evening' как ключ ниши
            # Если нишевые тексты не найдены, fallback на общий messages.txt
            dry_run = not do_post
            
            # Логируем статистику использования аккаунтов
            self.logger.info(f"Authorized account usage stats: {dict(self.account_usage)}")
            
            await self.post_to_targets(dry_run=dry_run, interval_seconds=60, max_posts=1, niche=niche)
            self.posted_slots_today[slot_name] = run_day

# Функция для запуска
async def main():
    parser = argparse.ArgumentParser(description='Telegram PR promotion system (Authorized accounts only)')
    parser.add_argument('--post', action='store_true', help='Отправлять сообщения (иначе dry-run)')
    parser.add_argument('--interval', type=int, default=60, help='Интервал между постами в секундах')
    parser.add_argument('--max-posts', type=int, default=1, help='Максимум отправок за запуск')
    parser.add_argument('--schedule', action='store_true', help='Режим планировщика: утро/день/вечер')
    args = parser.parse_args()

    promotion_system = AuthorizedOnlyPromotionSystem()
    await promotion_system.run(do_post=args.post, interval_seconds=args.interval, max_posts=args.max_posts, schedule=args.schedule)

if __name__ == "__main__":
    asyncio.run(main())
