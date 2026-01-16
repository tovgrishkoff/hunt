import asyncio
import random
import json
import logging
import time
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from telethon import TelegramClient
from telethon.errors import RPCError
from telethon.tl.functions.account import UpdateProfileRequest

class AntiDetectionSystem:
    def __init__(self):
        self.accounts = []
        self.clients = {}
        self.targets = []
        self.niche_messages = {}
        self.group_niches = {}
        
        # Система анти-детекции
        self.behavior_patterns = {}  # Паттерны поведения для каждого аккаунта
        self.posting_history = {}    # История постинга
        self.account_fingerprints = {}  # Отпечатки аккаунтов
        self.group_interactions = {}    # Взаимодействия с группами
        
        # Настройки анти-детекции
        self.min_typing_delay = 1.0      # Минимальная задержка печати
        self.max_typing_delay = 3.0      # Максимальная задержка печати
        self.min_post_interval = 300     # 5 минут между постами
        self.max_post_interval = 1800    # 30 минут между постами
        self.human_typing_speed = 0.1    # Скорость печати человека
        self.random_actions_probability = 0.3  # Вероятность случайных действий
        
        # Паттерны человеческого поведения
        self.human_behavior_patterns = {
            'morning_person': {'active_hours': (6, 12), 'posting_probability': 0.8},
            'day_person': {'active_hours': (12, 18), 'posting_probability': 0.9},
            'evening_person': {'active_hours': (18, 22), 'posting_probability': 0.7},
            'night_person': {'active_hours': (22, 6), 'posting_probability': 0.4}
        }
        
        self.setup_logging()
        
    def setup_logging(self):
        """Настройка логирования"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('anti_detection.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def load_accounts(self, config_file='accounts_config.json'):
        """Загрузка конфигурации аккаунтов"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                self.accounts = json.load(f)
            
            # Инициализация паттернов поведения для каждого аккаунта
            for account in self.accounts:
                session_name = account['session_name']
                self.behavior_patterns[session_name] = {
                    'personality_type': random.choice(list(self.human_behavior_patterns.keys())),
                    'typing_speed': random.uniform(0.05, 0.15),
                    'posting_frequency': random.uniform(0.3, 0.8),
                    'group_preferences': [],
                    'avoid_groups': [],
                    'last_activity': None,
                    'session_duration': random.uniform(1800, 7200),  # 30-120 минут
                    'break_duration': random.uniform(3600, 14400),   # 1-4 часа
                    'random_actions_count': 0
                }
                
                self.posting_history[session_name] = {
                    'posts_today': 0,
                    'posts_this_week': 0,
                    'last_post_time': None,
                    'posting_times': [],
                    'message_lengths': [],
                    'groups_used': set(),
                    'cooldown_until': None
                }
                
            self.logger.info(f"Loaded {len(self.accounts)} accounts with anti-detection patterns")
            
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
        
        # Инициализация взаимодействий с группами
        for target in self.targets:
            self.group_interactions[target] = {
                'last_post_time': None,
                'posts_today': 0,
                'posts_this_week': 0,
                'accounts_used': set(),
                'cooldown_until': None,
                'activity_level': random.uniform(0.3, 0.9),
                'response_rate': random.uniform(0.1, 0.5)
            }
            
        self.logger.info(f"Loaded {len(self.targets)} targets with interaction tracking")

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
            niche = niches[i % len(niches)]
            self.group_niches[target] = niche
            
        with open('group_niches.json', 'w', encoding='utf-8') as f:
            json.dump(self.group_niches, f, indent=2, ensure_ascii=False)
            
        self.logger.info(f"Created default group-niche mapping for {len(self.targets)} groups")

    def generate_account_fingerprint(self, account_name):
        """Генерация отпечатка аккаунта для анти-детекции"""
        behavior = self.behavior_patterns[account_name]
        
        fingerprint = {
            'typing_speed': behavior['typing_speed'],
            'posting_frequency': behavior['posting_frequency'],
            'personality_type': behavior['personality_type'],
            'session_duration': behavior['session_duration'],
            'break_duration': behavior['break_duration'],
            'preferred_hours': self.human_behavior_patterns[behavior['personality_type']]['active_hours'],
            'random_actions_probability': self.random_actions_probability
        }
        
        self.account_fingerprints[account_name] = fingerprint
        return fingerprint

    def is_account_active_now(self, account_name):
        """Проверка активности аккаунта в текущее время"""
        behavior = self.behavior_patterns[account_name]
        personality_type = behavior['personality_type']
        active_hours = self.human_behavior_patterns[personality_type]['active_hours']
        
        now = datetime.now()
        current_hour = now.hour
        
        if active_hours[0] < active_hours[1]:  # Обычный случай (например, 6-12)
            return active_hours[0] <= current_hour < active_hours[1]
        else:  # Переход через полночь (например, 22-6)
            return current_hour >= active_hours[0] or current_hour < active_hours[1]

    def calculate_posting_probability(self, account_name):
        """Расчет вероятности постинга для аккаунта"""
        behavior = self.behavior_patterns[account_name]
        personality_type = behavior['personality_type']
        base_probability = self.human_behavior_patterns[personality_type]['posting_probability']
        
        # Модификаторы
        if not self.is_account_active_now(account_name):
            base_probability *= 0.3  # Снижаем вероятность вне активных часов
        
        # Модификатор по частоте постинга
        posting_frequency = behavior['posting_frequency']
        base_probability *= posting_frequency
        
        # Модификатор по времени с последнего поста
        history = self.posting_history[account_name]
        if history['last_post_time']:
            time_since_last = (datetime.now() - history['last_post_time']).total_seconds()
            if time_since_last < 3600:  # Меньше часа
                base_probability *= 0.2
            elif time_since_last > 14400:  # Больше 4 часов
                base_probability *= 1.2
        
        return min(base_probability, 1.0)

    def select_optimal_account(self, exclude_accounts=None):
        """Выбор оптимального аккаунта с учетом анти-детекции"""
        if exclude_accounts is None:
            exclude_accounts = set()
        
        available_accounts = []
        
        for account_name in self.accounts:
            if account_name['session_name'] in exclude_accounts:
                continue
                
            session_name = account_name['session_name']
            history = self.posting_history[session_name]
            
            # Проверяем лимиты
            if history['posts_today'] >= 3:  # Максимум 3 поста в день
                continue
                
            # Проверяем кулдаун
            if history['cooldown_until'] and datetime.now() < history['cooldown_until']:
                continue
                
            # Рассчитываем вероятность постинга
            posting_probability = self.calculate_posting_probability(session_name)
            
            # Проверяем активность
            if not self.is_account_active_now(session_name):
                posting_probability *= 0.5
                
            if posting_probability > 0.3:  # Минимальный порог
                available_accounts.append((session_name, posting_probability))
        
        if not available_accounts:
            return None
        
        # Выбираем аккаунт с наивысшей вероятностью
        available_accounts.sort(key=lambda x: x[1], reverse=True)
        return available_accounts[0][0]

    def select_optimal_group(self, account_name, exclude_groups=None):
        """Выбор оптимальной группы с учетом анти-детекции"""
        if exclude_groups is None:
            exclude_groups = set()
        
        available_groups = []
        history = self.posting_history[account_name]
        
        for group in self.targets:
            if group in exclude_groups:
                continue
            if group in history['groups_used']:
                continue
                
            group_interaction = self.group_interactions[group]
            
            # Проверяем кулдаун группы
            if group_interaction['cooldown_until'] and datetime.now() < group_interaction['cooldown_until']:
                continue
                
            # Рассчитываем приоритет группы
            priority = group_interaction['activity_level']
            
            # Модификатор по времени с последнего поста
            if group_interaction['last_post_time']:
                time_since_last = (datetime.now() - group_interaction['last_post_time']).total_seconds()
                if time_since_last > 86400:  # Больше суток
                    priority *= 1.5
                elif time_since_last < 3600:  # Меньше часа
                    priority *= 0.3
            
            # Модификатор по количеству постов
            if group_interaction['posts_today'] == 0:
                priority *= 1.2
            elif group_interaction['posts_today'] >= 2:
                priority *= 0.5
            
            available_groups.append((group, priority))
        
        if not available_groups:
            return None
        
        # Выбираем группу с наивысшим приоритетом
        available_groups.sort(key=lambda x: x[1], reverse=True)
        return available_groups[0][0]

    def generate_human_typing_delay(self, message_length):
        """Генерация задержки печати как у человека"""
        behavior = self.behavior_patterns.get('current_account', {})
        typing_speed = behavior.get('typing_speed', self.human_typing_speed)
        
        # Базовое время печати
        base_time = message_length * typing_speed
        
        # Добавляем случайность
        random_factor = random.uniform(0.8, 1.2)
        
        # Добавляем паузы для "размышления"
        thinking_pauses = random.randint(0, 3)
        thinking_time = thinking_pauses * random.uniform(0.5, 2.0)
        
        total_time = base_time * random_factor + thinking_time
        
        return min(max(total_time, self.min_typing_delay), self.max_typing_delay)

    async def simulate_human_typing(self, client, entity, message):
        """Симуляция человеческой печати"""
        # Начинаем печатать
        await client.send_message(entity, message, parse_mode=None)
        
        # Случайная задержка после отправки
        delay = random.uniform(0.5, 2.0)
        await asyncio.sleep(delay)

    async def perform_random_actions(self, client, account_name):
        """Выполнение случайных действий для имитации человеческого поведения"""
        behavior = self.behavior_patterns[account_name]
        
        if random.random() < self.random_actions_probability:
            actions = [
                'check_dialogs',
                'scroll_chat',
                'check_notifications',
                'update_profile'
            ]
            
            action = random.choice(actions)
            
            try:
                if action == 'check_dialogs':
                    # Проверяем диалоги
                    dialogs = [d async for d in client.iter_dialogs(limit=5)]
                    self.logger.info(f"Random action: checked {len(dialogs)} dialogs")
                    
                elif action == 'scroll_chat':
                    # Прокручиваем чат
                    if self.targets:
                        target = random.choice(self.targets)
                        entity = await self.resolve_target(client, target)
                        if entity:
                            messages = [m async for m in client.iter_messages(entity, limit=3)]
                            self.logger.info(f"Random action: scrolled chat {target}")
                            
                elif action == 'check_notifications':
                    # Проверяем уведомления
                    self.logger.info("Random action: checked notifications")
                    
                elif action == 'update_profile':
                    # Обновляем профиль
                    if random.random() < 0.1:  # 10% шанс
                        await self.update_account_profile(client, account_name)
                        
            except Exception as e:
                self.logger.warning(f"Random action failed: {e}")
            
            behavior['random_actions_count'] += 1

    async def update_account_profile(self, client, account_name):
        """Обновление профиля аккаунта для анти-детекции"""
        try:
            # Получаем текущую информацию
            me = await client.get_me()
            
            # Генерируем случайные изменения
            if random.random() < 0.3:  # 30% шанс изменить статус
                statuses = [
                    "Ищу специалистов на Бали",
                    "В поиске качественных услуг",
                    "Активно ищу профессионалов",
                    "Ищу лучших специалистов",
                    "В поиске надежных мастеров"
                ]
                
                new_status = random.choice(statuses)
                await client(UpdateProfileRequest(about=new_status))
                self.logger.info(f"Updated profile status for {account_name}")
                
        except Exception as e:
            self.logger.warning(f"Failed to update profile for {account_name}: {e}")

    def update_posting_history(self, account_name, group, message):
        """Обновление истории постинга"""
        now = datetime.now()
        
        # Обновляем историю аккаунта
        history = self.posting_history[account_name]
        history['posts_today'] += 1
        history['posts_this_week'] += 1
        history['last_post_time'] = now
        history['posting_times'].append(now)
        history['message_lengths'].append(len(message))
        history['groups_used'].add(group)
        history['cooldown_until'] = now + timedelta(hours=6)
        
        # Обновляем взаимодействия с группой
        group_interaction = self.group_interactions[group]
        group_interaction['last_post_time'] = now
        group_interaction['posts_today'] += 1
        group_interaction['posts_this_week'] += 1
        group_interaction['accounts_used'].add(account_name)
        group_interaction['cooldown_until'] = now + timedelta(hours=24)
        
        # Обновляем поведенческие паттерны
        behavior = self.behavior_patterns[account_name]
        behavior['last_activity'] = now
        
        self.logger.info(f"Updated posting history: {account_name} -> {group}")

    def reset_daily_stats(self):
        """Сброс дневной статистики"""
        for account_name in self.posting_history:
            self.posting_history[account_name]['posts_today'] = 0
            
        for group in self.group_interactions:
            self.group_interactions[group]['posts_today'] = 0
            
        self.logger.info("Daily stats reset")

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

    async def execute_anti_detection_post(self, account_name, group, niche, message, dry_run=True):
        """Выполнение поста с анти-детекцией"""
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
                # Устанавливаем текущий аккаунт для генерации задержек
                self.behavior_patterns['current_account'] = self.behavior_patterns[account_name]
                
                # Симулируем человеческую печать
                await self.simulate_human_typing(client, entity, message)
                
                # Выполняем случайные действия
                await self.perform_random_actions(client, account_name)
                
                self.logger.info(f"✅ SENT to {group} via {account_name}: {message}")
                self.update_posting_history(account_name, group, message)
                return True
                
            except RPCError as e:
                self.logger.error(f"RPCError sending to {group} via {account_name}: {e}")
                return False
            except Exception as e:
                self.logger.error(f"Failed to send to {group} via {account_name}: {e}")
                return False

    async def run_anti_detection_system(self, dry_run=True, max_posts=None):
        """Запуск системы анти-детекции"""
        self.logger.info("🛡️ Starting Anti-Detection System...")
        
        executed_posts = 0
        
        while True:
            now = datetime.now()
            
            # Сброс дневной статистики в полночь
            if now.hour == 0 and now.minute == 0:
                self.reset_daily_stats()
            
            # Выбираем оптимальный аккаунт
            account_name = self.select_optimal_account()
            if not account_name:
                self.logger.warning("No available accounts for posting")
                await asyncio.sleep(3600)  # Ждем час
                continue
            
            # Выбираем оптимальную группу
            group = self.select_optimal_group(account_name)
            if not group:
                self.logger.warning(f"No available groups for account {account_name}")
                await asyncio.sleep(1800)  # Ждем 30 минут
                continue
            
            # Получаем сообщение
            niche = self.group_niches.get(group, 'morning')
            if niche in self.niche_messages:
                message = random.choice(self.niche_messages[niche])
            else:
                message = "Ищу специалиста на Бали"
            
            # Выполняем пост
            success = await self.execute_anti_detection_post(account_name, group, niche, message, dry_run)
            if success:
                executed_posts += 1
                
                if max_posts and executed_posts >= max_posts:
                    self.logger.info(f"Max posts reached ({max_posts})")
                    break
            
            # Случайный интервал между постами
            interval = random.randint(self.min_post_interval, self.max_post_interval)
            self.logger.info(f"Waiting {interval} seconds before next post...")
            await asyncio.sleep(interval)

    async def run(self, dry_run=True, max_posts=None, schedule=False):
        """Запуск системы"""
        self.logger.info("🚀 Starting Anti-Detection System...")
        
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
            await self.run_anti_detection_system(dry_run=dry_run, max_posts=max_posts)
        else:
            # Одноразовый запуск
            account_name = self.select_optimal_account()
            group = self.select_optimal_group(account_name)
            
            if account_name and group:
                niche = self.group_niches.get(group, 'morning')
                if niche in self.niche_messages:
                    message = random.choice(self.niche_messages[niche])
                else:
                    message = "Ищу специалиста на Бали"
                
                await self.execute_anti_detection_post(account_name, group, niche, message, dry_run)

# Функция для запуска
async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Anti-Detection Telegram PR promotion system')
    parser.add_argument('--post', action='store_true', help='Отправлять сообщения (иначе dry-run)')
    parser.add_argument('--max-posts', type=int, help='Максимум отправок за запуск')
    parser.add_argument('--schedule', action='store_true', help='Режим планировщика')
    args = parser.parse_args()

    system = AntiDetectionSystem()
    await system.run(dry_run=not args.post, max_posts=args.max_posts, schedule=args.schedule)

if __name__ == "__main__":
    asyncio.run(main())
