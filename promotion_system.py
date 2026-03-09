import asyncio
import random
import json
import logging
import argparse
from pathlib import Path
from datetime import datetime, timedelta, time as dtime
from typing import Dict, Optional

from telethon import TelegramClient
from telethon.errors import RPCError, FloodWaitError
from telethon.tl.functions.account import UpdateProfileRequest

from chatgpt_response_generator import ChatGPTResponseGenerator

# from alert_system import AlertSystem  # Временно отключено из-за конфликтов


class PromotionSystem:
    def __init__(self, admin_id: int = 210147380):
        self.accounts = []
        self.clients = {}
        self.account_usage = {}
        self.posted_messages = {}
        # История постинга по группам с учётом аккаунтов:
        # {group: {account_name: "ISO-датавремя последнего успешного поста"}}
        self.group_post_history: Dict[str, Dict[str, str]] = {}
        self.targets = []
        self.messages = []
        self.niche_messages = {}
        self.posted_slots_today = {}
        self.dialog_entities_cache = {}
        self.group_niches = {}
        self.daily_posts = {}  # Счетчик постов в день для каждого аккаунта
        self.max_daily_posts = 20  # Максимум постов в день с аккаунта (увеличено для большего охвата)
        # self.alert_system = AlertSystem(admin_id=admin_id)  # Временно отключено
        self.last_successful_post = None
        self.reconnect_attempts = {}  # Счетчик попыток переподключения
        self.group_accounts = {}  # Привязка групп к конкретным аккаунтам (старый формат, для обратной совместимости)
        self.group_assignments = {}  # Строгие привязки групп к аккаунтам с warm-up периодом
        # GPT для генерации вариаций сообщений
        self.chatgpt = ChatGPTResponseGenerator()
        # Сообщения Kammora с фото
        self.kammora_messages = {}
        # Сообщения Lexus с фото (для украинских групп по продаже машин)
        self.lexus_messages = {}
        # Исключенные аккаунты для ниши ukraine_cars (старый метод)
        self.ukraine_cars_excluded_accounts = set()
        # Разрешенные аккаунты для Lexus (whitelist)
        self.lexus_allowed_accounts = set()
        self.setup_logging()
        
    def setup_logging(self):
        """Настройка логирования"""
        logs_dir = Path("logs")
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_file = logs_dir / "promotion.log"

        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
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
            self.create_default_config(config_file)
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in {config_file}: {e}")
            self.create_default_config(config_file)
    
    def create_default_config(self, config_file):
        """Создание конфигурации по умолчанию"""
        default_config = [
            {
                "phone": "+79001234567",
                "api_id": 7444016141,
                "api_hash": "9be03fb41eea0e14119fe4f908d6e741",
                "session_name": "account1",
                "nickname": "Алексей_Москва",
                "bio": "Ищу специалистов в разных областях"
            }
        ]
        
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=2, ensure_ascii=False)
            
        self.logger.info(f"Created default config file {config_file}")
        self.accounts = default_config

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

    def load_group_post_history(self, history_file: str = 'logs/group_post_history.json') -> None:
        """Загрузка истории постинга по группам.

        Формат:
            {
              "group_username_or_link": {
                  "account_name": "2025-12-23T10:15:00"
              }
            }
        """
        path = Path(history_file)
        if not path.exists():
            self.group_post_history = {}
            self.logger.info("No group post history file found, starting fresh")
            return
        try:
            with path.open('r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                self.group_post_history = data
            else:
                self.group_post_history = {}
            self.logger.info(f"Loaded group post history from {history_file}")
        except Exception as e:
            self.logger.error(f"Failed to load group post history from {history_file}: {e}")
            self.group_post_history = {}

    def save_group_post_history(self, history_file: str = 'logs/group_post_history.json') -> None:
        """Сохранение истории постинга по группам в JSON."""
        try:
            path = Path(history_file)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('w', encoding='utf-8') as f:
                json.dump(self.group_post_history, f, ensure_ascii=False, indent=2)
            self.logger.info(f"Saved group post history to {history_file}")
        except Exception as e:
            self.logger.error(f"Failed to save group post history to {history_file}: {e}")

    def can_post_to_group(
        self,
        group: str,
        account_name: str,
        cooldown_hours: int = 24,
        now: Optional[datetime] = None,
        niche: str = None,
    ) -> bool:
        """Проверка, можно ли постить в группу с данного аккаунта с учётом кулдауна.

        Возвращает:
            True, если последняя отправка была больше cooldown_hours часов назад
            или не было вообще.
        """
        if now is None:
            now = datetime.utcnow()
        
        # Для ukraine_cars проверяем лимит 2 поста в день
        if niche == 'ukraine_cars':
            posts_today = self.get_group_posts_today(group, account_name, now=now)
            if posts_today >= 2:
                self.logger.info(
                    f"⏳ Daily limit reached for {group} via {account_name}: "
                    f"{posts_today} posts today (max 2)"
                )
                return False
        
        group_info = self.group_post_history.get(group, {})
        ts_str = group_info.get(account_name)
        if not ts_str:
            return True
        
        # Если это массив (для ukraine_cars), проверяем последний пост
        if isinstance(ts_str, list):
            if not ts_str:
                return True
            try:
                last_dt = datetime.fromisoformat(ts_str[-1])
            except Exception:
                return True
        else:
            try:
                last_dt = datetime.fromisoformat(ts_str)
            except Exception:
                # Если формат битый, позволяем постить и перезапишем
                return True
        
        delta = now - last_dt
        if delta >= timedelta(hours=cooldown_hours):
            return True
        self.logger.info(
            f"⏳ Cooldown active for {group} via {account_name}: "
            f"last post {last_dt.isoformat()}, delta {delta}"
        )
        return False
    
    def get_group_posts_today(
        self,
        group: str,
        account_name: str,
        now: Optional[datetime] = None,
    ) -> int:
        """Получить количество постов в группу с данного аккаунта за сегодня."""
        if now is None:
            now = datetime.utcnow()
        today = now.date()
        
        group_info = self.group_post_history.get(group, {})
        ts_data = group_info.get(account_name)
        
        if not ts_data:
            return 0
        
        # Если это массив (для ukraine_cars)
        if isinstance(ts_data, list):
            count = 0
            for ts_str in ts_data:
                try:
                    post_dt = datetime.fromisoformat(ts_str)
                    if post_dt.date() == today:
                        count += 1
                except Exception:
                    continue
            return count
        else:
            # Старый формат - один пост
            try:
                last_dt = datetime.fromisoformat(ts_data)
                if last_dt.date() == today:
                    return 1
            except Exception:
                pass
            return 0
    
    def get_group_account_for_ukraine_cars(self, group: str) -> Optional[str]:
        """Получить аккаунт, который уже постил в эту группу сегодня (для ukraine_cars).
        Если никто не постил, возвращает None."""
        group_info = self.group_post_history.get(group, {})
        now = datetime.utcnow()
        today = now.date()
        
        for account_name, ts_data in group_info.items():
            if not ts_data:
                continue
            
            # Проверяем, был ли пост сегодня с этого аккаунта
            if isinstance(ts_data, list):
                for ts_str in ts_data:
                    try:
                        post_dt = datetime.fromisoformat(ts_str)
                        if post_dt.date() == today:
                            return account_name
                    except Exception:
                        continue
            else:
                try:
                    last_dt = datetime.fromisoformat(ts_data)
                    if last_dt.date() == today:
                        return account_name
                except Exception:
                    pass
        
        return None

    def mark_group_posted(
        self,
        group: str,
        account_name: str,
        when: Optional[datetime] = None,
        history_file: str = 'logs/group_post_history.json',
        niche: str = None,
    ) -> None:
        """Отмечает успешный постинг в группе данным аккаунтом и сохраняет историю.
        
        Для ukraine_cars хранит массив постов за день (максимум 2).
        Обновляет также group_account_assignments для строгой эксклюзивности.
        """
        if when is None:
            when = datetime.utcnow()
        if group not in self.group_post_history:
            self.group_post_history[group] = {}
        
        # Для ukraine_cars храним массив постов за день
        if niche == 'ukraine_cars':
            if account_name not in self.group_post_history[group]:
                self.group_post_history[group][account_name] = []
            
            # Проверяем, что не превышаем лимит 2 поста в день
            posts_today = self.get_group_posts_today(group, account_name, now=when)
            if posts_today >= 2:
                self.logger.warning(
                    f"⚠️ Attempted to mark 3rd post for {group} via {account_name}, "
                    f"but limit is 2 posts per day"
                )
                return
            
            # Добавляем новый пост в массив
            posts_list = self.group_post_history[group][account_name]
            if not isinstance(posts_list, list):
                # Конвертируем старый формат в новый
                posts_list = [posts_list] if posts_list else []
                self.group_post_history[group][account_name] = posts_list
            
            # Очищаем старые посты (не сегодняшние)
            today = when.date()
            posts_list = [
                ts for ts in posts_list
                if isinstance(ts, str) and datetime.fromisoformat(ts).date() == today
            ]
            
            # Добавляем новый пост
            posts_list.append(when.isoformat())
            self.group_post_history[group][account_name] = posts_list
            
            # Обновляем assignment для строгой эксклюзивности
            if group in self.group_assignments:
                assignment = self.group_assignments[group]
                # Проверяем, что это тот же аккаунт
                if assignment.get('account') == account_name:
                    # Обновляем счетчик постов
                    today_str = today.isoformat()
                    last_post_date = None
                    if assignment.get('last_post_at'):
                        try:
                            last_post_date = datetime.fromisoformat(assignment['last_post_at']).date()
                        except:
                            pass
                    
                    # Если последний пост был не сегодня, сбрасываем счетчик
                    if last_post_date != today:
                        assignment['posts_count'] = 0
                    
                    assignment['posts_count'] += 1
                    assignment['last_post_at'] = when.isoformat()
                    if not assignment.get('first_post_at'):
                        assignment['first_post_at'] = when.isoformat()
                    self.save_group_assignments()
                else:
                    self.logger.error(
                        f"⚠️ CRITICAL: Attempted to post to {group} via {account_name}, "
                        f"but group is assigned to {assignment.get('account')}! "
                        f"This should not happen with strict exclusivity!"
                    )
            else:
                # Если группы нет в assignments, но мы постим - это ошибка
                self.logger.warning(
                    f"⚠️ Group {group} is not in assignments but posting succeeded. "
                    f"Creating assignment retroactively."
                )
                # Назначаем группу аккаунту (считаем что warm-up уже был)
                self.assign_account_to_group(group, account_name, joined_at=when - timedelta(hours=24))
                if group in self.group_assignments:
                    assignment = self.group_assignments[group]
                    assignment['posts_count'] = 1
                    assignment['last_post_at'] = when.isoformat()
                    assignment['first_post_at'] = when.isoformat()
                    self.save_group_assignments()
        else:
            # Старый формат для других ниш
            self.group_post_history[group][account_name] = when.isoformat()
        
        self.save_group_post_history(history_file=history_file)

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
                'morning': 'messages_morning.txt',
                'noon': 'messages_noon.txt',
                'evening': 'messages_evening.txt',
                'photo': 'messages_photo.txt',
                'video': 'messages_video.txt',
                'general': 'messages_general.txt',
                'housing': 'messages_housing.txt',
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
                'family_retreat': 'messages_family_retreat.txt',
                'seamstress': 'messages_seamstress.txt',
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
    
    def load_group_accounts(self):
        """Загрузка привязки групп к конкретным аккаунтам (старый формат)"""
        try:
            with open('group_accounts.json', 'r', encoding='utf-8') as f:
                self.group_accounts = json.load(f)
            self.logger.info(f"Loaded {len(self.group_accounts)} group-account mappings")
        except FileNotFoundError:
            self.logger.info("group_accounts.json not found, using account rotation for all groups")
            self.group_accounts = {}
    
    def load_group_assignments(self, assignments_file: str = 'group_account_assignments.json'):
        """Загрузка строгих привязок групп к аккаунтам с информацией о warm-up периоде"""
        path = Path(assignments_file)
        if not path.exists():
            self.group_assignments = {}
            self.logger.info("group_account_assignments.json not found, starting with empty assignments")
            return
        try:
            with path.open('r', encoding='utf-8') as f:
                self.group_assignments = json.load(f)
            self.logger.info(f"✅ Loaded {len(self.group_assignments)} group-account assignments with warm-up tracking")
        except Exception as e:
            self.logger.error(f"❌ Failed to load group_account_assignments.json: {e}")
            self.group_assignments = {}
    
    def save_group_assignments(self, assignments_file: str = 'group_account_assignments.json'):
        """Сохранение строгих привязок групп к аккаунтам"""
        try:
            path = Path(assignments_file)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('w', encoding='utf-8') as f:
                json.dump(self.group_assignments, f, ensure_ascii=False, indent=2)
            self.logger.debug(f"Saved {len(self.group_assignments)} group-account assignments")
        except Exception as e:
            self.logger.error(f"❌ Failed to save group_account_assignments.json: {e}")
    
    def assign_account_to_group(self, group: str, account: str, joined_at: Optional[datetime] = None):
        """Назначение аккаунта группе с установкой warm-up периода
        
        Args:
            group: Имя группы (username или ID)
            account: Имя аккаунта
            joined_at: Время вступления (по умолчанию текущее время)
        """
        if joined_at is None:
            joined_at = datetime.utcnow()
        warm_up_until = joined_at + timedelta(hours=24)  # 24 часа warm-up
        
        self.group_assignments[group] = {
            "account": account,
            "joined_at": joined_at.isoformat(),
            "first_post_at": None,
            "warm_up_until": warm_up_until.isoformat(),
            "posts_count": 0,
            "last_post_at": None
        }
        self.save_group_assignments()
        self.logger.info(f"🔗 Назначен аккаунт {account} для группы {group} (warm-up до {warm_up_until.isoformat()})")
    
    def get_assigned_account(self, group: str) -> Optional[str]:
        """Получить назначенный аккаунт для группы
        
        Returns:
            Имя аккаунта или None, если группа не закреплена
        """
        if group in self.group_assignments:
            return self.group_assignments[group].get('account')
        return None
    
    def is_group_assigned(self, group: str) -> bool:
        """Проверка, закреплена ли группа за аккаунтом"""
        return group in self.group_assignments
    
    def can_post_after_warmup(self, group: str, now: Optional[datetime] = None) -> bool:
        """Проверка, закончился ли warm-up период для группы
        
        Args:
            group: Имя группы
            now: Текущее время (по умолчанию UTC)
            
        Returns:
            True, если warm-up закончился или группа не закреплена
        """
        if now is None:
            now = datetime.utcnow()
        if group not in self.group_assignments:
            return True  # Если нет записи, считаем что можно постить (backward compatibility)
        
        warm_up_until_str = self.group_assignments[group].get('warm_up_until')
        if not warm_up_until_str:
            return True
        
        try:
            warm_up_until = datetime.fromisoformat(warm_up_until_str)
            return now >= warm_up_until
        except Exception as e:
            self.logger.warning(f"Failed to parse warm_up_until for {group}: {e}")
            return True  # В случае ошибки разрешаем постить
    
    def get_group_daily_posts_count(self, group: str, now: Optional[datetime] = None) -> int:
        """Получить количество постов в группе за сегодня из assignment"""
        if now is None:
            now = datetime.utcnow()
        today = now.date()
        
        if group not in self.group_assignments:
            return 0
        
        assignment = self.group_assignments[group]
        posts_count = assignment.get('posts_count', 0)
        last_post_at_str = assignment.get('last_post_at')
        
        # Если последний пост был не сегодня, обнуляем счетчик
        if last_post_at_str:
            try:
                last_post_at = datetime.fromisoformat(last_post_at_str)
                if last_post_at.date() != today:
                    # Сбрасываем счетчик для нового дня
                    assignment['posts_count'] = 0
                    assignment['last_post_at'] = None
                    self.save_group_assignments()
                    return 0
            except Exception:
                pass
        
        return posts_count
    
    def load_kammora_messages(self, kammora_file: str = 'kammora_assets/messages.json'):
        """Загрузка сообщений Kammora с фото из JSON файла"""
        try:
            path = Path(kammora_file)
            if not path.exists():
                self.logger.warning(f"Kammora messages file {kammora_file} not found")
                self.kammora_messages = {}
                return
            
            with path.open('r', encoding='utf-8') as f:
                self.kammora_messages = json.load(f)
            
            en_count = len(self.kammora_messages.get('en', []))
            ru_count = len(self.kammora_messages.get('ru', []))
            en_alt_count = len(self.kammora_messages.get('en_alt', []))
            ru_alt_count = len(self.kammora_messages.get('ru_alt', []))
            
            self.logger.info(f"✅ Loaded Kammora messages: EN={en_count}, RU={ru_count}, EN_ALT={en_alt_count}, RU_ALT={ru_alt_count}")
            
        except Exception as e:
            self.logger.error(f"❌ Failed to load Kammora messages: {e}")
            self.kammora_messages = {}

    def load_lexus_messages(self, lexus_file: str = None):
        """Загрузка сообщений Lexus с фото из JSON файла
        
        Пробует загрузить из нескольких мест в порядке приоритета:
        1. config/messages/cars/messages.json
        2. lexus_assets/messages.json
        3. Переданный lexus_file (если указан явно)
        """
        # Определяем приоритетные пути для поиска файла
        possible_paths = []
        if lexus_file:
            possible_paths.append(Path(lexus_file))
        possible_paths.extend([
            Path('config/messages/cars/messages.json'),
            Path('/app/config/messages/cars/messages.json'),  # Docker путь
            Path('lexus_assets/messages.json'),
            Path('/app/lexus_assets/messages.json'),  # Docker путь
        ])
        
        lexus_file_path = None
        for path in possible_paths:
            if path.exists():
                lexus_file_path = path
                self.logger.info(f"📁 Found Lexus messages file at: {path}")
                break
        
        if not lexus_file_path:
            self.logger.warning(f"⚠️ Lexus messages file not found in any of: {[str(p) for p in possible_paths]}")
            self.lexus_messages = {}
            return
        
        try:
            with lexus_file_path.open('r', encoding='utf-8') as f:
                self.lexus_messages = json.load(f)
            
            uk_count = len(self.lexus_messages.get('uk', []))
            
            self.logger.info(f"✅ Loaded Lexus messages from {lexus_file_path}: UK={uk_count}")
            
        except Exception as e:
            self.logger.error(f"❌ Failed to load Lexus messages from {lexus_file_path}: {e}")
            self.lexus_messages = {}

    def load_ukraine_cars_accounts_config(self):
        """Загрузка конфигурации аккаунтов для ниши ukraine_cars (старый метод с исключениями)"""
        config_file = Path('ukraine_cars_accounts_config.json')
        if config_file.exists():
            try:
                with config_file.open('r', encoding='utf-8') as f:
                    config = json.load(f)
                self.ukraine_cars_excluded_accounts = set(config.get('excluded_accounts', []))
                if self.ukraine_cars_excluded_accounts:
                    self.logger.info(f"✅ Loaded Ukraine cars accounts config: excluded {len(self.ukraine_cars_excluded_accounts)} accounts: {sorted(self.ukraine_cars_excluded_accounts)}")
                else:
                    self.logger.info(f"✅ Loaded Ukraine cars accounts config: no excluded accounts")
            except Exception as e:
                self.logger.warning(f"⚠️ Failed to load ukraine_cars_accounts_config.json: {e}")
                self.ukraine_cars_excluded_accounts = set()
        else:
            self.ukraine_cars_excluded_accounts = set()
    
    def load_lexus_accounts_config(self):
        """Загрузка конфигурации аккаунтов для Lexus (whitelist)"""
        # Проверяем несколько возможных путей
        possible_paths = [
            Path('lexus_accounts_config.json'),
            Path('/app/lexus_accounts_config.json'),
        ]
        
        config_file = None
        for path in possible_paths:
            if path.exists():
                config_file = path
                self.logger.info(f"📁 Found lexus_accounts_config.json at: {path}")
                break
        
        if config_file and config_file.exists():
            try:
                with config_file.open('r', encoding='utf-8') as f:
                    config = json.load(f)
                self.lexus_allowed_accounts = set(config.get('allowed_accounts', []))
                if self.lexus_allowed_accounts:
                    self.logger.info(f"✅ Loaded Lexus accounts config: {len(self.lexus_allowed_accounts)} allowed accounts: {sorted(self.lexus_allowed_accounts)}")
                else:
                    self.logger.warning(f"⚠️ Lexus accounts config has no allowed_accounts")
                    self.lexus_allowed_accounts = set()
            except Exception as e:
                self.logger.warning(f"⚠️ Failed to load lexus_accounts_config.json from {config_file}: {e}")
                self.lexus_allowed_accounts = set()
        else:
            self.logger.warning(f"⚠️ lexus_accounts_config.json not found in any of: {possible_paths}, using all accounts for Lexus")
            self.lexus_allowed_accounts = set()

    async def resolve_target(self, client: TelegramClient, target: str):
        """Разрешение цели: username/link/ID -> entity"""
        try:
            # Проверяем подключение клиента перед запросами
            if not client.is_connected():
                self.logger.warning(f"⚠️ Client is disconnected, cannot resolve target {target}")
                return None
            
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
        except FloodWaitError as e:
            # FloodWait - это не критическая ошибка, логируем как предупреждение
            wait_seconds = e.seconds
            wait_minutes = wait_seconds // 60
            wait_hours = wait_minutes // 60
            if wait_hours > 0:
                self.logger.warning(f"⚠️ FloodWait для {target}: {wait_hours}ч {wait_minutes % 60}м (будет пропущено)")
            else:
                self.logger.warning(f"⚠️ FloodWait для {target}: {wait_minutes}м (будет пропущено)")
            return None
        except RPCError as e:
            error_msg = str(e)
            error_lower = error_msg.lower()
            
            # Проверяем на FloodWait в RPCError (может быть обернут в RPCError)
            if 'wait' in error_lower and ('required' in error_lower or 'seconds' in error_lower):
                # Извлекаем количество секунд из сообщения
                import re
                wait_match = re.search(r'wait of (\d+) seconds', error_msg, re.IGNORECASE)
                if wait_match:
                    wait_seconds = int(wait_match.group(1))
                    wait_minutes = wait_seconds // 60
                    wait_hours = wait_minutes // 60
                    if wait_hours > 0:
                        self.logger.warning(f"⚠️ FloodWait для {target}: {wait_hours}ч {wait_minutes % 60}м (будет пропущено)")
                    else:
                        self.logger.warning(f"⚠️ FloodWait для {target}: {wait_minutes}м (будет пропущено)")
                else:
                    self.logger.warning(f"⚠️ FloodWait для {target}: {error_msg} (будет пропущено)")
                return None
            
            # Ошибки отключенного клиента - логируем как предупреждение
            if "disconnected" in error_lower or "not connected" in error_lower or "Cannot send requests" in error_msg:
                self.logger.warning(f"⚠️ Client disconnected, cannot resolve target {target}: {error_msg}")
            else:
                # Другие RPC ошибки - как предупреждение (не критично)
                self.logger.warning(f"⚠️ Failed to resolve target {target}: {error_msg}")
            return None
        except Exception as e:
            error_msg = str(e)
            error_lower = error_msg.lower()
            
            # Проверяем на FloodWait в сообщении об ошибке (может быть в RPCError, а не в FloodWaitError)
            if 'wait' in error_lower and ('required' in error_lower or 'seconds' in error_lower):
                # Извлекаем количество секунд из сообщения
                import re
                wait_match = re.search(r'wait of (\d+) seconds', error_msg, re.IGNORECASE)
                if wait_match:
                    wait_seconds = int(wait_match.group(1))
                    wait_minutes = wait_seconds // 60
                    wait_hours = wait_minutes // 60
                    if wait_hours > 0:
                        self.logger.warning(f"⚠️ FloodWait для {target}: {wait_hours}ч {wait_minutes % 60}м (будет пропущено)")
                    else:
                        self.logger.warning(f"⚠️ FloodWait для {target}: {wait_minutes}м (будет пропущено)")
                else:
                    self.logger.warning(f"⚠️ FloodWait для {target}: {error_msg} (будет пропущено)")
                return None
            
            # Ошибки отключенного клиента - логируем как предупреждение
            if "disconnected" in error_lower or "not connected" in error_lower or "Cannot send requests" in error_msg:
                self.logger.warning(f"⚠️ Client disconnected, cannot resolve target {target}: {error_msg}")
                return None
            
            # Другие ошибки разрешения - логируем как предупреждение (не критично)
            self.logger.warning(f"⚠️ Failed to resolve target {target}: {error_msg}")
            return None

    def get_new_accounts_for_kammora(self):
        """Получение списка новых аккаунтов, которые еще не использовались для постинга"""
        if not self.clients:
            return set()
        
        # Получаем список аккаунтов, которые уже использовались
        used_accounts = set()
        if self.group_post_history:
            for group, accounts in self.group_post_history.items():
                used_accounts.update(accounts.keys())
        
        # Возвращаем аккаунты, которые НЕ использовались
        all_accounts = set(self.clients.keys())
        new_accounts = all_accounts - used_accounts
        
        if new_accounts:
            self.logger.info(f"📋 Новые аккаунты для Kammora: {sorted(new_accounts)}")
        else:
            self.logger.warning(f"⚠️ Все аккаунты уже использовались. Будут использоваться все доступные.")
            new_accounts = all_accounts  # Fallback на все аккаунты
        
        return new_accounts
    
    def get_next_client(self, target_group: str = None, kammora_only_new: bool = False, niche: str = None):
        """Получение следующего клиента для ротации с учетом дневных лимитов и привязки групп
        
        Args:
            target_group: Группа для постинга (для проверки привязки)
            kammora_only_new: Если True, использовать только новые аккаунты (для Kammora)
            niche: Ниша для постинга (для применения специальных правил, например, ukraine_cars)
        """
        if not self.clients:
            return None, None
        
        # Загружаем конфигурацию для ukraine_cars/Lexus если еще не загружена
        if niche == 'ukraine_cars':
            if not hasattr(self, 'lexus_allowed_accounts'):
                self.load_lexus_accounts_config()
            # Также загружаем старый конфиг для обратной совместимости
            if not hasattr(self, 'ukraine_cars_excluded_accounts'):
                self.load_ukraine_cars_accounts_config()
        
        # Проверяем, есть ли привязка группы к конкретному аккаунту
        if target_group and target_group in self.group_accounts:
            assigned_account = self.group_accounts[target_group]
            if assigned_account in self.clients:
                # Для ukraine_cars проверяем whitelist (приоритет) или blacklist (fallback)
                if niche == 'ukraine_cars':
                    # Если есть whitelist, проверяем его
                    if hasattr(self, 'lexus_allowed_accounts') and self.lexus_allowed_accounts:
                        if assigned_account not in self.lexus_allowed_accounts:
                            self.logger.info(f"Assigned account {assigned_account} is not in Lexus whitelist")
                            return None, None
                    # Иначе проверяем blacklist (старый метод)
                    elif hasattr(self, 'ukraine_cars_excluded_accounts') and assigned_account in self.ukraine_cars_excluded_accounts:
                        self.logger.info(f"Assigned account {assigned_account} is excluded for ukraine_cars niche")
                        return None, None
                
                # Проверяем дневной лимит для назначенного аккаунта
                if self.daily_posts.get(assigned_account, 0) < self.max_daily_posts:
                    self.logger.info(f"Using assigned account {assigned_account} for group {target_group}")
                    return assigned_account, self.clients[assigned_account]
                else:
                    self.logger.warning(f"Assigned account {assigned_account} for {target_group} has reached daily limit")
                    return None, None
        
        # Для Kammora используем только новые аккаунты
        if kammora_only_new:
            new_accounts = self.get_new_accounts_for_kammora()
            if not new_accounts:
                self.logger.warning("No new accounts available for Kammora")
                return None, None
        
        # Фильтруем клиентов, которые не превысили дневной лимит
        available_clients = {}
        for account_name, client in self.clients.items():
            # Для Kammora пропускаем использованные аккаунты
            if kammora_only_new and account_name not in new_accounts:
                continue
            
            # Для ukraine_cars используем whitelist (приоритет) или blacklist (fallback)
            if niche == 'ukraine_cars':
                # Если есть whitelist, используем его
                if hasattr(self, 'lexus_allowed_accounts') and self.lexus_allowed_accounts:
                    if account_name not in self.lexus_allowed_accounts:
                        continue  # Пропускаем аккаунты не из whitelist
                # Иначе используем blacklist (старый метод)
                elif hasattr(self, 'ukraine_cars_excluded_accounts') and account_name in self.ukraine_cars_excluded_accounts:
                    continue  # Пропускаем исключенные аккаунты
            
            if self.daily_posts.get(account_name, 0) < self.max_daily_posts:
                available_clients[account_name] = client
        
        if not available_clients:
            self.logger.warning("All accounts have reached daily post limit" + (" or are not new (for Kammora)" if kammora_only_new else ""))
            return None, None
        
        # Находим клиента с наименьшим использованием среди доступных
        min_usage = min(self.account_usage.get(name, 0) for name in available_clients.keys())
        for account_name in available_clients.keys():
            if self.account_usage.get(account_name, 0) == min_usage:
                return account_name, available_clients[account_name]
        
        # Fallback: первый доступный клиент
        first_account = list(available_clients.keys())[0]
        return first_account, available_clients[first_account]

    async def try_send_with_account_rotation(self, target: str, message: str, entity, dry_run: bool = False):
        """
        Попытка отправки сообщения с автоматическим переключением на другие аккаунты при ошибке.
        
        Returns:
            (success: bool, account_name: str) - успешность отправки и имя аккаунта, через который отправили
        """
        if dry_run:
            # В dry-run режиме просто возвращаем первый доступный аккаунт
            client_name, client = self.get_next_client(target_group=target)
            if client:
                return True, client_name
            return False, None
        
        # Получаем список всех доступных аккаунтов (которые не превысили лимит)
        available_accounts = []
        for account_name, client in self.clients.items():
            if self.daily_posts.get(account_name, 0) < self.max_daily_posts:
                available_accounts.append((account_name, client))
        
        if not available_accounts:
            self.logger.warning(f"No available accounts for {target} (all reached daily limit)")
            return False, None
        
        # Пробуем отправить через каждый доступный аккаунт
        tried_accounts = []
        for account_name, client in available_accounts:
            tried_accounts.append(account_name)
            try:
                await client.send_message(entity, message)
                self.logger.info(f"✅ Sent to {target} via {account_name}")
                self.logger.info(f"📝 Message text: {message[:200]}{'...' if len(message) > 200 else ''}")
                
                # Увеличиваем счётчики использования аккаунта
                self.account_usage[account_name] += 1
                self.daily_posts[account_name] += 1
                self.logger.info(f"Account {account_name} daily posts: {self.daily_posts[account_name]}/{self.max_daily_posts}")
                
                # Сохраняем время последнего успешного поста
                self.last_successful_post = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                return True, account_name
                
            except RPCError as e:
                error_msg = str(e)
                self.logger.warning(f"⚠️ Account {account_name} failed for {target}: {error_msg}")
                
                # Если это критическая ошибка (бан или флуд), не пробуем другие аккаунты
                if "banned" in error_msg.lower() and "you're banned" in error_msg.lower():
                    self.logger.error(f"❌ Account {account_name} is banned from {target}, trying next account...")
                    # Продолжаем пробовать другие аккаунты
                    continue
                elif "flood" in error_msg.lower():
                    self.logger.error(f"⏳ Flood wait for {account_name} in {target}, trying next account...")
                    # Продолжаем пробовать другие аккаунты
                    continue
                else:
                    # Для других ошибок (нет прав, приватный канал и т.д.) пробуем другие аккаунты
                    self.logger.info(f"🔄 Trying next account for {target}...")
                    continue
                    
            except Exception as e:
                self.logger.warning(f"⚠️ Unexpected error with {account_name} for {target}: {e}")
                # Продолжаем пробовать другие аккаунты
                continue
        
        # Если все аккаунты не смогли отправить
        self.logger.error(f"❌ Failed to send to {target} via all accounts: {', '.join(tried_accounts)}")
        return False, None
    
    async def try_send_photo_with_text(
        self, 
        target: str, 
        photo_path: str, 
        caption: str, 
        entity=None,  # Если None - разрешается для каждого аккаунта отдельно
        dry_run: bool = False
    ):
        """
        Попытка отправки фото с текстом с автоматическим переключением на другие аккаунты при ошибке.
        
        Args:
            target: Идентификатор группы
            photo_path: Путь к файлу фото
            caption: Текст подписи к фото
            entity: Entity группы
            dry_run: Режим тестирования
        
        Returns:
            (success: bool, account_name: str) - успешность отправки и имя аккаунта
        """
        if dry_run:
            client_name, client = self.get_next_client(target_group=target)
            if client:
                photo_file = Path(photo_path)
                if photo_file.exists():
                    self.logger.info(f"[DRY-RUN] Would send photo {photo_path} to {target} via {client_name}")
                    self.logger.info(f"[DRY-RUN] Caption: {caption[:200]}...")
                else:
                    self.logger.warning(f"[DRY-RUN] Photo file not found: {photo_path}")
                return True, client_name
            return False, None
        
        # Для Kammora используем только новые аккаунты (если они есть)
        # Проверяем, является ли группа Kammora
        is_kammora_group = self.group_niches.get(target) == 'kammora'
        
        # Получаем список доступных аккаунтов
        available_accounts = []
        accounts_to_use = self.clients.items()
        
        # Если это группа Kammora, фильтруем только новые аккаунты
        if is_kammora_group:
            new_accounts_set = self.get_new_accounts_for_kammora()
            if new_accounts_set:
                accounts_to_use = [(name, client) for name, client in self.clients.items() if name in new_accounts_set]
                self.logger.info(f"📋 Using only new accounts for Kammora group {target}: {sorted(new_accounts_set)}")
            else:
                # Если новых аккаунтов нет, используем все доступные
                self.logger.info(f"⚠️  No new accounts available for Kammora, using all available accounts for {target}")
        
        for account_name, client in accounts_to_use:
            if self.daily_posts.get(account_name, 0) < self.max_daily_posts:
                available_accounts.append((account_name, client))
        
        if not available_accounts:
            self.logger.warning(f"No available accounts for {target} (all reached daily limit)")
            return False, None
        
        # Проверяем существование файла
        # Поддерживаем разные форматы путей:
        # - Относительный: lexus_assets/lexus_variant_1.jpg (от текущей директории)
        # - Docker: /app/lexus_assets/lexus_variant_1.jpg
        # - Абсолютный: /полный/путь/к/файлу.jpg
        photo_file = None
        
        # Пробуем как относительный путь от текущей директории (для локального запуска)
        candidate = Path(photo_path)
        if candidate.exists():
            photo_file = candidate
        else:
            # Пробуем с префиксом /app/ (для Docker)
            candidate = Path(f"/app/{photo_path}")
            if candidate.exists():
                photo_file = candidate
            else:
                # Убираем префикс lexus_assets/ или kammora_assets/ если есть и пробуем снова
                clean_path = photo_path.replace('lexus_assets/', '').replace('kammora_assets/', '')
                # Сначала пробуем относительный путь от текущей директории
                candidate = Path(f"lexus_assets/{clean_path}")
                if candidate.exists():
                    photo_file = candidate
                else:
                    candidate = Path(f"kammora_assets/{clean_path}")
                    if candidate.exists():
                        photo_file = candidate
                    else:
                        # Пробуем Docker-пути
                        candidate = Path(f"/app/lexus_assets/{clean_path}")
                        if candidate.exists():
                            photo_file = candidate
                        else:
                            candidate = Path(f"/app/kammora_assets/{clean_path}")
                            if candidate.exists():
                                photo_file = candidate
        
        if not photo_file or not photo_file.exists():
            clean_path = photo_path.replace('lexus_assets/', '').replace('kammora_assets/', '')
            self.logger.error(
                f"❌ Photo file not found: {photo_path} "
                f"(tried: {photo_path}, /app/{photo_path}, lexus_assets/{clean_path}, "
                f"kammora_assets/{clean_path}, /app/lexus_assets/{clean_path}, /app/kammora_assets/{clean_path})"
            )
            return False, None
        
        # Пробуем отправить через каждый доступный аккаунт
        tried_accounts = []
        for account_name, client in available_accounts:
            tried_accounts.append(account_name)
            try:
                # КРИТИЧНО: Разрешаем entity для каждого аккаунта отдельно
                # Entity может быть разным для разных аккаунтов (разные аккаунты могут иметь разные типы entity)
                if entity is None:
                    account_entity = await self.resolve_target(client, target)
                else:
                    # Если entity передан, все равно проверяем его для этого аккаунта
                    # Но лучше разрешить заново для безопасности
                    account_entity = await self.resolve_target(client, target)
                
                if account_entity is None:
                    self.logger.warning(f"⚠️ Account {account_name} cannot resolve target {target}, trying next account...")
                    continue
                
                # Проверяем подключение клиента перед проверкой прав
                if not client.is_connected():
                    self.logger.warning(f"⚠️ Client {account_name} is disconnected, skipping {target}")
                    continue
                
                # Проверяем права на постинг ДО отправки
                try:
                    me = await client.get_me()
                    permissions = await client.get_permissions(account_entity, me)
                    can_send = False
                    if permissions:
                        if hasattr(permissions, 'send_messages'):
                            can_send = permissions.send_messages
                        elif hasattr(permissions, 'banned_rights') and permissions.banned_rights:
                            if hasattr(permissions.banned_rights, 'send_messages'):
                                can_send = not permissions.banned_rights.send_messages
                    
                    if not can_send:
                        self.logger.warning(f"⚠️ Account {account_name} cannot post to {target} (no permission), trying next account...")
                        continue
                except FloodWaitError as e:
                    wait_seconds = e.seconds
                    wait_minutes = wait_seconds // 60
                    self.logger.warning(f"⚠️ Account {account_name} FloodWait {wait_minutes}м при проверке прав для {target}, trying next account...")
                    continue
                except RPCError as perm_error:
                    error_msg = str(perm_error)
                    if "disconnected" in error_msg.lower() or "not connected" in error_msg.lower() or "Cannot send requests" in error_msg:
                        self.logger.warning(f"⚠️ Client {account_name} disconnected при проверке прав для {target}, trying next account...")
                    else:
                        self.logger.debug(f"⚠️ Could not check permissions for {account_name} in {target}: {perm_error}, will try to send anyway")
                except Exception as perm_error:
                    # Если не можем проверить права, все равно пробуем отправить
                    error_msg = str(perm_error)
                    if "disconnected" in error_msg.lower() or "not connected" in error_msg.lower() or "Cannot send requests" in error_msg:
                        self.logger.warning(f"⚠️ Client {account_name} disconnected при проверке прав для {target}, trying next account...")
                        continue
                    self.logger.debug(f"⚠️ Could not check permissions for {account_name} in {target}: {perm_error}, will try to send anyway")
                
                # Проверяем подключение клиента перед отправкой
                if not client.is_connected():
                    self.logger.warning(f"⚠️ Client {account_name} is disconnected before sending to {target}, trying next account...")
                    continue
                
                # Отправляем фото с подписью
                await client.send_file(
                    account_entity,
                    str(photo_file),
                    caption=caption
                )
                self.logger.info(f"✅ Sent photo to {target} via {account_name}")
                self.logger.info(f"📷 Photo: {photo_path}")
                self.logger.info(f"📝 Caption: {caption[:200]}{'...' if len(caption) > 200 else ''}")
                
                # Увеличиваем счётчики использования аккаунта
                self.account_usage[account_name] += 1
                self.daily_posts[account_name] += 1
                self.logger.info(f"Account {account_name} daily posts: {self.daily_posts[account_name]}/{self.max_daily_posts}")
                
                # Сохраняем время последнего успешного поста
                self.last_successful_post = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                return True, account_name
                
            except FloodWaitError as e:
                wait_seconds = e.seconds
                wait_minutes = wait_seconds // 60
                wait_hours = wait_minutes // 60
                if wait_hours > 0:
                    self.logger.warning(f"⚠️ Account {account_name} FloodWait {wait_hours}ч {wait_minutes % 60}м для {target}, trying next account...")
                else:
                    self.logger.warning(f"⚠️ Account {account_name} FloodWait {wait_minutes}м для {target}, trying next account...")
                continue
                
            except RPCError as e:
                error_msg = str(e)
                
                # Проверяем на ошибки отключенного клиента
                if "disconnected" in error_msg.lower() or "not connected" in error_msg.lower() or "Cannot send requests" in error_msg:
                    self.logger.warning(f"⚠️ Client {account_name} disconnected for {target}: {error_msg}, trying next account...")
                    continue
                
                self.logger.warning(f"⚠️ Account {account_name} failed for {target}: {error_msg}")
                
                # Если это критическая ошибка, пробуем другие аккаунты
                if "banned" in error_msg.lower() or "flood" in error_msg.lower() or "forbidden" in error_msg.lower() or "invalid" in error_msg.lower():
                    self.logger.info(f"🔄 Trying next account for {target}...")
                    continue
                else:
                    continue
                    
            except Exception as e:
                error_msg = str(e)
                
                # Проверяем на ошибки отключенного клиента
                if "disconnected" in error_msg.lower() or "not connected" in error_msg.lower() or "Cannot send requests" in error_msg:
                    self.logger.warning(f"⚠️ Client {account_name} disconnected for {target}: {error_msg}, trying next account...")
                    continue
                
                self.logger.warning(f"⚠️ Unexpected error with {account_name} for {target}: {error_msg}")
                continue
        
        # Если все аккаунты не смогли отправить
        # Логируем как WARNING, так как подробные ошибки уже залогированы выше для каждого аккаунта
        self.logger.warning(f"⚠️ Failed to send photo to {target} via all accounts: {', '.join(tried_accounts)} (подробности в логах выше)")
        return False, None

    async def post_to_targets(self, dry_run: bool = True, interval_seconds: int = 60, max_posts: int = 1, niche: str = None):
        """Постинг по целям с указанным интервалом и ротацией аккаунтов"""
        if not self.targets:
            self.logger.warning("No targets to post to. Skipping posting.")
            return
        # Загружаем сопоставление групп с нишами
        self.load_group_niches()
        # Загружаем историю постинга групп (для кулдауна)
        self.load_group_post_history()

        # Проверяем и переподключаем клиентов перед постингом
        if not self.clients:
            self.logger.error("No initialized clients available")
            return
        
        self.logger.info("🔍 Checking client connections before posting...")
        await self.check_and_reconnect_clients()
        
        if not self.clients:
            self.logger.error("❌ No available clients for posting after reconnection attempt")
            return

        sent_count = 0
        # Рандомизируем порядок групп
        random_targets = random.sample(self.targets, len(self.targets))
        now_utc = datetime.utcnow()
        
        for idx, target in enumerate(random_targets, start=1):
            # Определяем нишу для конкретной группы
            group_niche = self.group_niches.get(target, 'general')
            
            # Проверяем, является ли ниша "kammora" - используем фото+текст
            if group_niche == 'kammora' or (niche and niche == 'kammora'):
                # Логика для Kammora с фото
                if not self.kammora_messages:
                    self.logger.warning(f"Kammora messages not loaded, skipping {target}")
                    continue
                
                # Получаем entity для группы (для Kammora используем только новые аккаунты, если они есть)
                # Проверяем, есть ли еще новые аккаунты
                new_accounts = self.get_new_accounts_for_kammora()
                use_only_new = len(new_accounts) > 0  # Используем только новые, если они есть
                
                client_name, client = self.get_next_client(target_group=target, kammora_only_new=use_only_new)
                if client is None:
                    self.logger.warning(f"No available clients for posting to {target} (new accounts: {len(new_accounts)})")
                    continue
                
                # Проверяем кулдаун
                if not self.can_post_to_group(target, client_name, cooldown_hours=24, now=now_utc) and not dry_run:
                    self.logger.info(f"Skipping {target} for {client_name} due to 24h cooldown")
                    continue
                
                self.logger.info(f"🔍 Resolving target {target}...")
                entity = await self.resolve_target(client, target)
                if entity is None:
                    self.logger.warning(f"Could not resolve target {target}, skipping")
                    continue
                
                # Определяем язык группы по её названию
                target_lower = target.lower().replace('@', '')
                
                # Русские индикаторы
                russian_indicators = ['аренд', 'недвижим', 'квартир', 'дом', 'объяв', 'сосед', 'компаньон', 
                                     'obyavlen', 'russians', 'русск', 'bali_o', 'balioby']
                
                # Английские/международные индикаторы
                english_indicators = ['house', 'rent', 'estate', 'property', 'real', 'sale', 'apart', 
                                     'accommod', 'housing', 'roommate', 'share', 'bali_arenda', 'balifornia']
                
                use_ru = False
                russian_score = sum(1 for ind in russian_indicators if ind in target_lower)
                english_score = sum(1 for ind in english_indicators if ind in target_lower)
                
                # Если явно русские индикаторы сильнее - используем русский
                if russian_score > english_score:
                    use_ru = True
                # Если английские индикаторы есть - используем английский
                elif english_score > 0:
                    use_ru = False
                else:
                    # Если не понятно - чередуем (50/50)
                    use_ru = random.choice([True, False])
                
                # Выбираем сообщение
                if use_ru and self.kammora_messages.get('ru'):
                    kammora_list = self.kammora_messages['ru']
                    lang_name = "Russian"
                elif self.kammora_messages.get('en'):
                    kammora_list = self.kammora_messages['en']
                    lang_name = "English"
                else:
                    self.logger.warning(f"No Kammora messages available for {target}")
                    continue
                
                self.logger.info(f"Using {lang_name} Kammora message for {target} (RU indicators: {russian_score}, EN indicators: {english_score})")
                
                kammora_item = random.choice(kammora_list)
                photo_path = kammora_item.get('photo', '')
                caption = kammora_item.get('text', '')
                
                if not photo_path or not caption:
                    self.logger.warning(f"Invalid Kammora item for {target}, skipping")
                    continue
                
                # Генерируем вариацию текста через GPT (опционально)
                # Для Kammora просто переформулируем текст объявления, БЕЗ упоминания бота
                final_caption = caption
                if not dry_run and self.chatgpt is not None:
                    try:
                        # Используем метод переформулировки текста (без упоминания бота)
                        gpt_caption = await self.chatgpt.rephrase_text(caption, max_tokens=300)
                        if gpt_caption:
                            final_caption = gpt_caption.strip()
                            self.logger.info(f"✍️ GPT переформулировал текст для Kammora в {target}")
                    except Exception as e:
                        self.logger.warning(f"⚠️ Ошибка GPT для Kammora {target}: {e}, используем оригинальный текст")
                
                if dry_run:
                    self.logger.info(f"[DRY-RUN] Would send Kammora photo to {target} via {client_name}")
                    self.logger.info(f"[DRY-RUN] Photo: {photo_path}")
                    self.logger.info(f"[DRY-RUN] Caption: {final_caption[:200]}...")
                    sent_count += 1
                else:
                    success, used_account = await self.try_send_photo_with_text(
                        target=target,
                        photo_path=photo_path,
                        caption=final_caption,
                        entity=entity,
                        dry_run=False
                    )
                    
                    if success:
                        sent_count += 1
                        self.mark_group_posted(target, used_account)
                        self.logger.info(f"✅ Successfully posted Kammora photo to {target} via {used_account}")
                    else:
                        self.logger.error(f"❌ Failed to post Kammora photo to {target}")
                
                if sent_count >= max_posts and not dry_run:
                    self.logger.info(f"Max posts reached ({max_posts}). Stopping posting.")
                    break
                
                if idx < len(self.targets):
                    await asyncio.sleep(interval_seconds)
                continue
            
            # Проверяем, является ли ниша "ukraine_cars" - используем фото+текст Lexus
            if group_niche == 'ukraine_cars' or (niche and niche == 'ukraine_cars'):
                # Логика для Lexus с фото (украинские группы по продаже машин)
                if not self.lexus_messages:
                    self.logger.warning(f"Lexus messages not loaded, skipping {target}")
                    continue
                
                # СТРОГАЯ ПРОВЕРКА ЭКСКЛЮЗИВНОСТИ: получаем закрепленный аккаунт
                assigned_account = self.get_assigned_account(target)
                
                if assigned_account:
                    # Группа закреплена за аккаунтом - проверяем строго
                    if assigned_account not in self.clients:
                        self.logger.warning(
                            f"⚠️ Assigned account {assigned_account} not available for {target}, skipping"
                        )
                        continue
                    
                    # Проверка warm-up периода
                    if not self.can_post_after_warmup(target, now=now_utc):
                        warm_up_until_str = self.group_assignments[target].get('warm_up_until', 'N/A')
                        self.logger.info(
                            f"⏳ Skipping {target} - warm-up period not finished yet (until {warm_up_until_str})"
                        )
                        continue
                    
                    # Проверка лимита постов из assignment
                    posts_today_from_assignment = self.get_group_daily_posts_count(target, now=now_utc)
                    if posts_today_from_assignment >= 2:
                        self.logger.info(
                            f"⏳ Skipping {target} for {assigned_account} - daily limit reached "
                            f"({posts_today_from_assignment}/2 posts)"
                        )
                        continue
                    
                    # Проверка дневного лимита аккаунта
                    if self.daily_posts.get(assigned_account, 0) >= self.max_daily_posts:
                        self.logger.warning(
                            f"⚠️ Assigned account {assigned_account} has reached daily limit "
                            f"({self.daily_posts[assigned_account]}/{self.max_daily_posts}), skipping {target}"
                        )
                        continue
                    
                    # Используем ТОЛЬКО закрепленный аккаунт
                    client_name = assigned_account
                    client = self.clients[assigned_account]
                    self.logger.info(
                        f"🔗 Using assigned account {client_name} for {target} "
                        f"(posts today: {posts_today_from_assignment}/2)"
                    )
                else:
                    # Группа не закреплена - назначаем аккаунт при первом посте
                    client_name, client = self.get_next_client(target_group=target, niche='ukraine_cars')
                    if client is None:
                        self.logger.warning(f"⚠️ No available clients for posting to {target} (ukraine_cars)")
                        continue
                    
                    # Назначаем группу аккаунту
                    # Если группа уже в targets.txt, считаем что warm-up уже был (минус 24 часа)
                    # Иначе считаем что только что вступили
                    joined_at = now_utc - timedelta(hours=24)
                    self.assign_account_to_group(target, client_name, joined_at=joined_at)
                    # Сразу разрешаем постить (warm-up уже прошел)
                    self.group_assignments[target]['warm_up_until'] = (now_utc - timedelta(minutes=1)).isoformat()
                    self.save_group_assignments()
                    self.logger.info(
                        f"🔗 Assigned account {client_name} to new group {target} "
                        f"(warm-up skipped, group already in targets.txt)"
                    )
                
                # Для украинских групп используем украинские сообщения
                lexus_list = self.lexus_messages.get('uk', [])
                if not lexus_list:
                    self.logger.warning(f"No Lexus messages available for {target}")
                    continue
                
                self.logger.info(f"Using Ukrainian Lexus message for {target}")
                
                lexus_item = random.choice(lexus_list)
                photo_path = lexus_item.get('photo', '')
                caption = lexus_item.get('text', '')
                
                if not photo_path or not caption:
                    self.logger.warning(f"Invalid Lexus item for {target}, skipping")
                    continue
                
                # Генерируем вариацию текста через GPT (опционально)
                final_caption = caption
                if not dry_run and self.chatgpt is not None:
                    try:
                        # Переформулируем текст объявления (без упоминания бота)
                        gpt_caption = await self.chatgpt.rephrase_text(caption, max_tokens=300)
                        if gpt_caption:
                            final_caption = gpt_caption.strip()
                            self.logger.info(f"✍️ GPT переформулировал текст для Lexus в {target}")
                    except Exception as e:
                        self.logger.warning(f"⚠️ Ошибка GPT для Lexus {target}: {e}, используем оригинальный текст")
                
                if dry_run:
                    self.logger.info(f"[DRY-RUN] Would send Lexus photo to {target} via {client_name}")
                    self.logger.info(f"[DRY-RUN] Photo: {photo_path}")
                    self.logger.info(f"[DRY-RUN] Caption: {final_caption[:200]}...")
                    sent_count += 1
                else:
                    # КРИТИЧНО: Передаем None как entity - функция сама разрешит entity для каждого аккаунта отдельно
                    # Это важно, так как разные аккаунты могут видеть группу как канал или группу по-разному
                    success, used_account = await self.try_send_photo_with_text(
                        target=target,
                        photo_path=photo_path,
                        caption=final_caption,
                        entity=None,  # None = разрешить для каждого аккаунта отдельно
                        dry_run=False
                    )
                    
                    if success:
                        sent_count += 1
                        self.mark_group_posted(target, used_account, niche='ukraine_cars')
                        posts_today = self.get_group_posts_today(target, used_account)
                        self.logger.info(f"✅ Successfully posted Lexus photo to {target} via {used_account} (post {posts_today}/2 today)")
                    else:
                        # Логируем как WARNING, так как подробные ошибки уже залогированы в try_send_photo_with_text
                        self.logger.warning(f"⚠️ Failed to post Lexus photo to {target} (подробности в логах выше)")
                
                if sent_count >= max_posts and not dry_run:
                    self.logger.info(f"Max posts reached ({max_posts}). Stopping posting.")
                    break
                
                if idx < len(self.targets):
                    await asyncio.sleep(interval_seconds)
                continue
            
            # Обычная логика для текстовых сообщений (не kammora и не ukraine_cars)
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
            
            # Получаем entity для группы
            # Пробуем через первый доступный аккаунт для получения entity
            client_name, client = self.get_next_client(target_group=target)
            if client is None:
                self.logger.error(f"No available clients for posting to {target}")
                continue

            # Проверяем кулдаун для выбранного аккаунта и группы
            if not self.can_post_to_group(target, client_name, cooldown_hours=24, now=now_utc) and not dry_run:
                self.logger.info(f"Skipping {target} for {client_name} due to 24h cooldown")
                continue
                
            self.logger.info(f"🔍 Resolving target {target}...")
            entity = await self.resolve_target(client, target)
            if entity is None:
                self.logger.warning(f"Could not resolve target {target}, skipping")
                continue
            
            base_message = random.choice(source_messages)

            # Генерируем вариацию текста через ChatGPT на основе шаблона
            # ВАЖНО: Для постов в группы используем rephrase_text (БЕЗ упоминания бота)
            # Реклама бота идет только через личные сообщения
            message = base_message
            if not dry_run and self.chatgpt is not None:
                try:
                    # Используем rephrase_text для постов в группы (партизанский маркетинг)
                    # Это переформулирует текст БЕЗ упоминания бота
                    gpt_message = await self.chatgpt.rephrase_text(
                        text=base_message,
                        max_tokens=300
                    )
                    if gpt_message:
                        message = gpt_message.strip()
                        self.logger.info(
                            f"✍️ GPT переформулировал сообщение для {target} "
                            f"(niche={group_niche}) - партизанский маркетинг"
                        )
                    else:
                        self.logger.warning(
                            f"⚠️ GPT вернул пустой результат, используем базовый шаблон для {target}"
                        )
                except Exception as e:
                    self.logger.error(
                        f"❌ Ошибка при генерации текста через GPT для {target}: {e}. "
                        "Используем базовый шаблон."
                    )
                    message = base_message
            
            if dry_run:
                self.logger.info(f"[DRY-RUN] Would send to {target} via {client_name}: {message}")
                sent_count += 1
            else:
                # Используем новый метод с автоматическим переключением аккаунтов
                success, used_account = await self.try_send_with_account_rotation(
                    target=target,
                    message=message,
                    entity=entity,
                    dry_run=False
                )
                
                if success:
                    sent_count += 1
                    self.mark_group_posted(target, used_account)
                    self.logger.info(f"✅ Successfully posted to {target} via {used_account}")
                else:
                    self.logger.error(f"❌ Failed to post to {target} after trying all available accounts")

            if sent_count >= max_posts and not dry_run:
                self.logger.info(f"Max posts reached ({max_posts}). Stopping posting.")
                break

            if idx < len(self.targets):
                await asyncio.sleep(interval_seconds)
    
    def parse_proxy(self, proxy_config):
        """
        Парсинг конфигурации прокси для Telethon
        Telethon использует формат словаря:
        {
            'proxy_type': 'http' или 'socks5',
            'addr': 'IP адрес',
            'port': порт,
            'username': 'логин' (опционально),
            'password': 'пароль' (опционально)
        }
        
        Поддерживает форматы:
        - Строковый: "http://user:pass@host:port" или "socks5://user:pass@host:port"
        - Словарь: {"type": "http", "host": "...", "port": ..., ...}
        """
        if not proxy_config:
            return None
        
        # Если это строка в формате URL
        if isinstance(proxy_config, str):
            try:
                from urllib.parse import urlparse
                parsed = urlparse(proxy_config)
                proxy_type = parsed.scheme.lower()
                host = parsed.hostname
                port = parsed.port or (8080 if proxy_type in ['http', 'https'] else 1080)
                username = parsed.username or None
                password = parsed.password or None
                
                if not host or not port:
                    self.logger.warning(f"Неверный формат прокси: {proxy_config}")
                    return None
                
                if proxy_type in ['http', 'https']:
                    proxy_dict = {
                        'proxy_type': 'http',
                        'addr': host,
                        'port': port
                    }
                    if username:
                        proxy_dict['username'] = username
                    if password:
                        proxy_dict['password'] = password
                    return proxy_dict
                elif proxy_type == 'socks5':
                    proxy_dict = {
                        'proxy_type': 'socks5',
                        'addr': host,
                        'port': port
                    }
                    if username:
                        proxy_dict['username'] = username
                    if password:
                        proxy_dict['password'] = password
                    return proxy_dict
                else:
                    self.logger.warning(f"Неизвестный тип прокси: {proxy_type}, поддерживаются http, https и socks5")
                    return None
            except Exception as e:
                self.logger.warning(f"Ошибка парсинга прокси {proxy_config}: {e}")
                return None
        
        # Если это словарь
        if isinstance(proxy_config, dict):
            # Проверяем, не является ли это уже форматом Telethon
            if 'proxy_type' in proxy_config and 'addr' in proxy_config:
                return proxy_config
            
            # Парсим наш формат в формат Telethon
            proxy_type = proxy_config.get('type', proxy_config.get('proxy_type', 'http')).lower()
            host = proxy_config.get('host') or proxy_config.get('addr')
            port = proxy_config.get('port')
            username = proxy_config.get('username')
            password = proxy_config.get('password')
            
            if not host or not port:
                self.logger.warning("Прокси должен содержать host/addr и port")
                return None
            
            if proxy_type in ['http', 'https']:
                proxy_dict = {
                    'proxy_type': 'http',
                    'addr': host,
                    'port': port
                }
                if username:
                    proxy_dict['username'] = username
                if password:
                    proxy_dict['password'] = password
                return proxy_dict
            elif proxy_type == 'socks5':
                proxy_dict = {
                    'proxy_type': 'socks5',
                    'addr': host,
                    'port': port
                }
                if username:
                    proxy_dict['username'] = username
                if password:
                    proxy_dict['password'] = password
                return proxy_dict
            else:
                self.logger.warning(f"Неизвестный тип прокси: {proxy_type}, поддерживаются http, https и socks5")
                return None
        
        return None
    
    async def initialize_clients(self):
        """Инициализация всех клиентов с проверкой подключения"""
        for account in self.accounts:
            account_name = account['session_name']
            try:
                self.logger.info(f"🔄 Initializing {account_name}...")
                
                api_id = int(account['api_id'])
                # Приоритет: используем string_session из конфига, если есть
                string_session = account.get('string_session')
                self.logger.debug(f"  string_session type: {type(string_session)}, value: {str(string_session)[:50] if string_session else 'None'}...")
                proxy_config = account.get('proxy')  # Получаем конфигурацию прокси
                
                # Парсим прокси если указан
                proxy = None
                if proxy_config:
                    proxy = self.parse_proxy(proxy_config)
                    if proxy:
                        self.logger.info(f"  Using proxy for {account_name}: {proxy['addr']}:{proxy['port']} ({proxy['proxy_type']})")
                    else:
                        self.logger.warning(f"  Failed to parse proxy config for {account_name}, continuing without proxy")
                
                # Создаем клиент с прокси если указан
                client = None
                if string_session and string_session not in ['', 'TO_BE_CREATED', 'null', None]:
                    # Убеждаемся, что string_session это строка
                    if isinstance(string_session, str):
                        session_cleaned = string_session.strip()
                        if session_cleaned:
                            from telethon.sessions import StringSession
                            try:
                                self.logger.info(f"  Using StringSession for {account_name} (length: {len(session_cleaned)})")
                                session_obj = StringSession(session_cleaned)
                                client = TelegramClient(
                                    session_obj, 
                                    api_id, 
                                    account['api_hash'],
                                    proxy=proxy
                                )
                            except Exception as session_error:
                                self.logger.error(f"  Failed to create StringSession for {account_name}: {type(session_error).__name__}: {session_error}")
                                raise
                        else:
                            self.logger.warning(f"  string_session is empty string for {account_name}, using file session")
                    else:
                        self.logger.warning(f"  string_session is not a string for {account_name} (type: {type(string_session)}), using file session")
                
                if not client:
                    # Fallback: используем файловую сессию
                    self.logger.info(f"  Using file session for {account_name}")
                    client = TelegramClient(
                        f"sessions/{account_name}", 
                        api_id, 
                        account['api_hash'],
                        proxy=proxy
                    )
                
                await client.connect()
                self.logger.info(f"  Connected {account_name}")
                
                # Для StringSession не проверяем авторизацию (зависает)
                # Просто добавляем и доверяем что сессия валидна
                self.clients[account_name] = client
                self.logger.info(f"✅ Client {account_name} ready")
                
            except Exception as e:
                self.logger.error(f"❌ Failed {account_name}: {e}")
    
    async def reconnect_client(self, account_name: str):
        """Переподключение конкретного клиента"""
        try:
            # Находим аккаунт в конфигурации
            account = next((acc for acc in self.accounts if acc['session_name'] == account_name), None)
            if not account:
                self.logger.error(f"Account {account_name} not found in config")
                return False
            
            # Отключаем старый клиент если есть
            if account_name in self.clients:
                try:
                    await self.clients[account_name].disconnect()
                except:
                    pass
                del self.clients[account_name]
            
            # Создаем новый клиент
            api_id = int(account['api_id'])
            
            # Парсим прокси если указан
            proxy_config = account.get('proxy')
            proxy = None
            if proxy_config:
                proxy = self.parse_proxy(proxy_config)
                if proxy:
                    self.logger.info(f"  Reconnecting with proxy: {proxy['addr']}:{proxy['port']} ({proxy['proxy_type']})")
            
            # Используем StringSession если доступен
            string_session = account.get('string_session')
            if string_session:
                from telethon.sessions import StringSession
                client = TelegramClient(
                    StringSession(string_session),
                    api_id,
                    account['api_hash'],
                    proxy=proxy
                )
            else:
                client = TelegramClient(
                    f"sessions/{account['session_name']}", 
                    api_id, 
                    account['api_hash'],
                    proxy=proxy
                )
            # Для StringSession просто подключаемся (уже авторизованы)
            if string_session:
                await client.connect()
            else:
                await client.start(phone=lambda: None)
            
            if await client.is_user_authorized():
                self.clients[account_name] = client
                self.logger.info(f"✅ Reconnected client {account_name}")
                self.reconnect_attempts[account_name] = 0  # Сброс счетчика
                return True
            else:
                self.logger.error(f"❌ Failed to authorize client {account_name}")
                await client.disconnect()
                
                # Увеличиваем счетчик неудачных попыток
                self.reconnect_attempts[account_name] = self.reconnect_attempts.get(account_name, 0) + 1
                if self.reconnect_attempts[account_name] >= 3:
                    try:
                        if self.alert_system:
                            await self.alert_system.alert_reconnect_failed(account_name, self.reconnect_attempts[account_name])
                    except:
                        pass  # Alert system не инициализирована
                
                return False
        except Exception as e:
            self.logger.error(f"❌ Failed to reconnect {account_name}: {e}")
            
            # Увеличиваем счетчик неудачных попыток
            self.reconnect_attempts[account_name] = self.reconnect_attempts.get(account_name, 0) + 1
            if self.reconnect_attempts[account_name] >= 3:
                try:
                    if self.alert_system:
                        await self.alert_system.alert_reconnect_failed(account_name, self.reconnect_attempts[account_name])
                except:
                    pass  # Alert system не инициализирована
            
            return False
    
    async def check_and_reconnect_clients(self):
        """Проверка состояния всех клиентов и переподключение при необходимости"""
        disconnected = []
        
        for account_name, client in list(self.clients.items()):
            try:
                if not client.is_connected():
                    self.logger.warning(f"⚠️ Client {account_name} is disconnected")
                    disconnected.append((account_name, "Disconnected"))
                elif not await client.is_user_authorized():
                    self.logger.warning(f"⚠️ Client {account_name} is not authorized")
                    disconnected.append((account_name, "Not authorized"))
            except Exception as e:
                self.logger.warning(f"⚠️ Cannot check client {account_name}: {e}")
                disconnected.append((account_name, str(e)))
        
        # Переподключаем отключенные клиенты
        for account_name, reason in disconnected:
            self.logger.info(f"🔄 Attempting to reconnect {account_name}...")
            try:
                if self.alert_system:
                    await self.alert_system.alert_client_disconnected(account_name, reason)
            except:
                pass  # Alert system не инициализирована
            await self.reconnect_client(account_name)
        
        # Проверяем, остались ли клиенты после переподключения
        if disconnected and not self.clients:
            try:
                if self.alert_system:
                    await self.alert_system.alert_no_clients()
            except:
                pass  # Alert system не инициализирована
        
        return len(disconnected) == 0
    
    async def test_connection(self):
        """Тест подключения аккаунта"""
        try:
            for account_name, client in self.clients.items():
                if client.is_connected():
                    me = await client.get_me()
                    self.logger.info(f"✅ Account {account_name} connected as @{me.username}")
                    return True
        except Exception as e:
            self.logger.error(f"❌ Connection test failed: {e}")
            return False
    
    async def run(self, do_post: bool = False, interval_seconds: int = 60, max_posts: int = 1, schedule: bool = False):
        """Запуск системы продвижения"""
        self.logger.info(" Starting Promotion System...")
        
        # Загружаем конфигурацию
        self.load_accounts()
        self.load_targets()
        self.load_messages()
        self.load_niche_messages()
        self.load_group_niches()
        self.load_group_accounts()
        self.load_group_assignments()  # Загружаем строгие привязки с warm-up периодами
        self.load_kammora_messages()  # Загружаем сообщения Kammora с фото
        self.load_lexus_messages()  # Загружаем сообщения Lexus с фото
        
        # Инициализируем клиенты
        await self.initialize_clients()
        
        # Инициализируем систему алертов (используем первый аккаунт)
        # Делаем инициализацию в фоне, чтобы не блокировать запуск
        if self.accounts and len(self.accounts) > 0:
            try:
                first_account = self.accounts[0]
                # Даём 5 секунд на инициализацию
                await asyncio.wait_for(
                    self.alert_system.initialize(
                        api_id=int(first_account['api_id']),
                        api_hash=first_account['api_hash'],
                        string_session=first_account.get('string_session'),
                        session_name=f"alert_{first_account['session_name']}"
                    ),
                    timeout=5.0
                )
                self.logger.info("✅ Alert system initialized")
            except asyncio.TimeoutError:
                self.logger.warning("⚠️ Alert system initialization timeout - continuing without alerts")
            except Exception as e:
                self.logger.warning(f"⚠️ Failed to initialize alert system: {e} - continuing without alerts")
        
        # Тестируем подключение
        if await self.test_connection():
            self.logger.info("🎉 System ready! Use test_connection() to verify")
            
            # Отправляем уведомление о запуске
            try:
                if self.alert_system:
                    await self.alert_system.alert_system_started(len(self.clients))
            except:
                pass  # Alert system не инициализирована
            
            if schedule:
                await self.run_scheduler(do_post=do_post)
            else:
                if do_post:
                    await self.post_to_targets(dry_run=False, interval_seconds=interval_seconds, max_posts=max_posts)
                else:
                    await self.post_to_targets(dry_run=True, interval_seconds=interval_seconds, max_posts=max_posts)
        else:
            self.logger.error("❌ System failed to initialize")
            try:
                if self.alert_system:
                    await self.alert_system.alert_no_clients()
            except:
                pass  # Alert system не инициализирована

    async def run_scheduler(self, do_post: bool):
        """Планировщик: 6 слотов в день с разными нишами и ротацией аккаунтов"""
        import pytz
        jakarta_tz = pytz.timezone('Asia/Jakarta')
        
        # Расписание по Jakarta времени
        slots = [
            ('morning', dtime(hour=6, minute=0)),
            ('late_morning', dtime(hour=9, minute=0)),
            ('noon', dtime(hour=12, minute=0)),
            ('afternoon', dtime(hour=15, minute=0)),
            ('evening', dtime(hour=18, minute=0)),
            ('night', dtime(hour=21, minute=0)),
        ]
        self.logger.info("Scheduler started: 6 slots per day (06:00, 09:00, 12:00, 15:00, 18:00, 21:00) Jakarta time with account rotation")
        self.posted_slots_today = {name: None for name, _ in slots}

        while True:
            now = datetime.now(jakarta_tz)
            today = now.date()

            # Сброс отметок в полночь - исправленная логика
            for name in list(self.posted_slots_today.keys()):
                posted_date = self.posted_slots_today[name]
                # Если дата поста не сегодня (или None), сбрасываем
                if posted_date is None or posted_date < today:
                    self.posted_slots_today[name] = None
                    if posted_date and posted_date < today:
                        self.logger.info(f"Reset slot {name}: old date {posted_date} -> None (today is {today})")
            
            # Сброс счетчиков дневных постов в полночь
            # Проверяем, не начался ли новый день
            if not hasattr(self, '_last_reset_date') or self._last_reset_date < today:
                for account_name in self.daily_posts.keys():
                    self.daily_posts[account_name] = 0
                self._last_reset_date = today
                self.logger.info(f"✅ Reset daily post counters for all accounts (new day: {today})")

            # Найти следующий слот
            next_slot_name = None
            next_slot_dt = None
            for name, t in slots:
                slot_dt = jakarta_tz.localize(datetime.combine(today, t))
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
            run_day = datetime.now(jakarta_tz).date()
            self.logger.info(f"⏰ Woke up for slot: {slot_name}, date: {run_day}")

            if self.posted_slots_today.get(slot_name) == run_day:
                # Уже постили в этом слоте сегодня (на случай перезапуска)
                self.logger.info(f"Slot {slot_name}: already posted today, skipping")
                continue

            # Выполнить постинг из соответствующей ниши с ротацией аккаунтов
            niche = slot_name  # 'morning'|'noon'|'evening' как ключ ниши
            # Если нишевые тексты не найдены, fallback на общий messages.txt
            dry_run = not do_post
            
            # Логируем статистику использования аккаунтов
            self.logger.info(f"🚀 Starting posting for slot {slot_name}, dry_run={dry_run}")
            self.logger.info(f"Account usage stats: {dict(self.account_usage)}")
            
            # Увеличили max_posts до количества групп, чтобы система пыталась постить во все группы
            # даже если часть из них недоступна
            max_posts_per_slot = len(self.targets) if self.targets else 30  # Обрабатываем все группы
            await self.post_to_targets(dry_run=dry_run, interval_seconds=60, max_posts=max_posts_per_slot, niche=niche)
            self.posted_slots_today[slot_name] = run_day

# Функция для запуска
async def main():
    parser = argparse.ArgumentParser(description='Telegram PR promotion system')
    parser.add_argument('--post', action='store_true', help='Отправлять сообщения (иначе dry-run)')
    parser.add_argument('--interval', type=int, default=60, help='Интервал между постами в секундах')
    parser.add_argument('--max-posts', type=int, default=1, help='Максимум отправок за запуск')
    parser.add_argument('--schedule', action='store_true', help='Режим планировщика: утро/день/вечер')
    args = parser.parse_args()

    promotion_system = PromotionSystem()
    await promotion_system.run(do_post=args.post, interval_seconds=args.interval, max_posts=args.max_posts, schedule=args.schedule)

if __name__ == "__main__":
    asyncio.run(main())
