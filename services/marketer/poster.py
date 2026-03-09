#!/usr/bin/env python3
"""
Smart Poster - Умный постер для публикации рекламных постов в группы
Работает с PostgreSQL через Async SQLAlchemy
"""
import asyncio
import logging
import json
import os
import random
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from pathlib import Path

# Добавляем корень проекта в путь
sys.path.insert(0, '/app')

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.errors import (
    FloodWaitError,
    ChatWriteForbiddenError,
    ChatSendMediaForbiddenError,
    UserBannedInChannelError,
    ChannelPrivateError,
    UserAlreadyParticipantError,
    RPCError
)

from lexus_db.session import AsyncSessionLocal
from lexus_db.models import Account, Target
from lexus_db.db_manager import DbManager
from sqlalchemy import select, and_, or_, text, func, case

_handlers = [logging.StreamHandler()]
_log_path = Path('/app/logs/poster.log')
if _log_path.parent.exists():
    try:
        _handlers.append(logging.FileHandler(_log_path))
    except OSError:
        pass
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=_handlers)
logger = logging.getLogger(__name__)


class SmartPoster:
    """Класс для публикации рекламных постов в группы"""
    
    def __init__(self, niche: str, config_path: str = '/app/config/marketing_posts.json'):
        """
        Args:
            niche: Ниша для постинга (например, 'ukraine_cars', 'bali_rent')
            config_path: Путь к файлу с конфигурацией постов
        """
        self.niche = niche
        self.config_path = Path(config_path)
        self.posts_config = self._load_posts()
        self.accounts_config = self._load_accounts_config()
        self.project_name = os.getenv('PROJECT_NAME', 'default')
        # Загружаем Бали аккаунты ТОЛЬКО для ниши 'bali'
        self.bali_allowed_accounts = self._load_bali_allowed_accounts() if niche == 'bali' else set()
        # Загружаем маппинг групп к под-нишам для релевантного постинга
        self.group_niches = self._load_group_niches()
        # Загружаем сообщения с категориями для релевантного выбора
        self.messages_by_category = self._load_messages_by_category()
    
    def _load_posts(self) -> List[Dict]:
        """
        Загружает варианты постов (текст + путь к фото) из JSON конфига
        Для ниши 'bali' загружает из bali_assets/messages.json (приоритет) или config/messages/bali/messages.json
        Для ниши 'ukraine_cars' загружает из config/messages/cars/messages.json
        
        Returns:
            Список словарей с ключами 'text' и 'image' (или 'photo')
        """
        # Для ниши 'bali' используем messages.json вместо marketing_posts.json
        if self.niche == 'bali':
            messages_paths = [
                Path('/app/config/messages/bali/messages.json'),
                Path('config/messages/bali/messages.json'),
                Path('../config/messages/bali/messages.json'),
            ]
            
            for messages_file in messages_paths:
                if messages_file.exists():
                    try:
                        with open(messages_file, 'r', encoding='utf-8') as f:
                            all_messages = json.load(f)
                        logger.info(f"✅ Loaded {len(all_messages)} messages from {messages_file}")
                        return all_messages
                    except Exception as e:
                        logger.error(f"❌ Failed to load messages from {messages_file}: {e}")
        
        # Для ниши 'ukraine_cars' используем config/messages/cars/messages.json
        if self.niche == 'ukraine_cars':
            messages_paths = [
                Path('/app/config/messages/cars/messages.json'),
                Path('config/messages/cars/messages.json'),
                Path('../config/messages/cars/messages.json'),
            ]
            
            for messages_file in messages_paths:
                if messages_file.exists():
                    try:
                        with open(messages_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        # Формат: {"uk": [{"variant": 0, "photo": "...", "text": "..."}]}
                        # Извлекаем сообщения для украинского языка
                        uk_messages = data.get('uk', [])
                        if uk_messages:
                            # Преобразуем формат: photo -> image для совместимости
                            formatted_messages = []
                            for msg in uk_messages:
                                formatted_msg = {
                                    'text': msg.get('text', ''),
                                    'image': msg.get('photo') or msg.get('image'),  # Поддерживаем оба формата
                                    'variant': msg.get('variant', 0)
                                }
                                formatted_messages.append(formatted_msg)
                            logger.info(f"✅ Loaded {len(formatted_messages)} Lexus messages from {messages_file}")
                            return formatted_messages
                        else:
                            logger.warning(f"⚠️ No 'uk' messages found in {messages_file}")
                    except Exception as e:
                        logger.error(f"❌ Failed to load Lexus messages from {messages_file}: {e}")
        
        # Для других ниш используем старый формат
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                posts = data.get(self.niche, [])
                logger.info(f"✅ Loaded {len(posts)} post templates for niche '{self.niche}'")
                return posts
            else:
                logger.warning(f"⚠️ Config file {self.config_path} not found! Using dummy post.")
                return [{"text": f"Test post for {self.niche}", "image": None}]
        except Exception as e:
            logger.error(f"❌ Failed to load posts config: {e}")
            return [{"text": f"Test post for {self.niche}", "image": None}]
    
    def _load_accounts_config(self) -> dict:
        """Загрузка конфигурации аккаунтов из JSON"""
        import json
        # Пути к файлу с конфигурацией аккаунтов
        config_paths = [
            Path('/app/accounts_config.json'),  # В контейнере (корень проекта)
            Path('accounts_config.json'),  # Текущая директория
            Path('../accounts_config.json'),  # Родительская директория
        ]
        
        for config_file in config_paths:
            try:
                if config_file.exists():
                    with open(config_file, 'r', encoding='utf-8') as f:
                        accounts_list = json.load(f)
                    # Преобразуем список в словарь {session_name: account_config}
                    logger.info(f"✅ Loaded accounts config from {config_file}")
                    return {acc['session_name']: acc for acc in accounts_list}
            except Exception as e:
                logger.debug(f"⚠️ Failed to load accounts config from {config_file}: {e}")
                continue
        
        logger.warning(f"⚠️ Accounts config file not found in any location. Using DB data only.")
        return {}
    
    def _parse_proxy(self, proxy_string: str) -> Optional[dict]:
        """
        Парсинг строки прокси
        
        Форматы:
        - socks5://user:pass@host:port
        - http://user:pass@host:port
        
        Returns:
            Словарь с настройками прокси или None
        """
        try:
            from urllib.parse import urlparse
            
            parsed = urlparse(proxy_string)
            
            proxy_type = parsed.scheme
            if proxy_type == 'socks5':
                return {
                    'proxy_type': 'socks5',
                    'addr': parsed.hostname,
                    'port': parsed.port,
                    'username': parsed.username,
                    'password': parsed.password
                }
            elif proxy_type in ['http', 'https']:
                return {
                    'proxy_type': 'http',
                    'addr': parsed.hostname,
                    'port': parsed.port,
                    'username': parsed.username,
                    'password': parsed.password
                }
        except Exception as e:
            logger.warning(f"⚠️ Failed to parse proxy {proxy_string}: {e}")
        
        return None
    
    def _load_bali_allowed_accounts(self) -> set:
        """Загрузка списка разрешенных аккаунтов для Бали"""
        bali_config_paths = [
            Path('/app/bali_accounts_config.json'),  # В контейнере
            Path('/app/config/bali_accounts_config.json'),  # В config
            Path('bali_accounts_config.json'),  # Текущая директория
            Path('../bali_accounts_config.json'),  # Родительская директория
        ]
        
        for path in bali_config_paths:
            if path.exists():
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        bali_config = json.load(f)
                        allowed = set(bali_config.get('allowed_accounts', []))
                        if allowed:
                            logger.info(f"✅ Loaded Bali allowed accounts: {sorted(allowed)}")
                            return allowed
                except Exception as e:
                    logger.warning(f"⚠️ Failed to load bali_accounts_config.json from {path}: {e}")
        
        logger.warning("⚠️ bali_accounts_config.json not found, using all accounts")
        return set()  # Пустой set = разрешены все аккаунты
    
    def _load_group_niches(self) -> Dict[str, str]:
        """Загрузка маппинга групп к под-нишам из group_niches.json"""
        group_niches_paths = [
            Path('/app/group_niches.json'),  # В контейнере (корень проекта)
            Path('/app/config/group_niches.json'),  # В config
            Path('group_niches.json'),  # Текущая директория
            Path('../group_niches.json'),  # Родительская директория
            Path('config/group_niches.json'),  # В config (относительно текущей директории)
        ]
        
        for path in group_niches_paths:
            if path.exists():
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        mapping = json.load(f)
                        logger.info(f"✅ Loaded {len(mapping)} group niches from {path}")
                        return mapping
                except Exception as e:
                    logger.warning(f"⚠️ Failed to load group_niches.json from {path}: {e}")
        
        logger.warning("⚠️ group_niches.json not found in any location, using default mapping (all groups will get general messages)")
        return {}
    
    def _load_messages_by_category(self) -> Dict[str, List[Dict]]:
        """Загружает сообщения из bali_assets/messages.json (приоритет) или config/messages/bali и группирует по категориям"""
        messages_by_category = {}
        
        # Для ukraine_cars не загружаем сообщения по категориям (используются сообщения из posts_config)
        if self.niche == 'ukraine_cars':
            logger.debug("⏭️ Skipping messages_by_category for ukraine_cars (using posts_config instead)")
            return messages_by_category
        
        # Пути к файлу с сообщениями (bali_assets — приоритет)
        messages_paths = [
            Path('/app/bali_assets/messages.json'),
            Path('bali_assets/messages.json'),
            Path('../bali_assets/messages.json'),
            Path('/app/config/messages/bali/messages.json'),
            Path('config/messages/bali/messages.json'),
            Path('../config/messages/bali/messages.json'),
        ]
        
        messages_file = None
        for path in messages_paths:
            if path.exists():
                messages_file = path
                break
        
        if not messages_file:
            logger.warning("⚠️ bali_assets/messages.json и config/messages/bali/messages.json not found")
            return messages_by_category
        
        try:
            with open(messages_file, 'r', encoding='utf-8') as f:
                all_messages = json.load(f)
            
            # Группируем сообщения по source_file (категории)
            for message in all_messages:
                source_file = message.get('source_file', 'general')
                # Извлекаем категорию из имени файла (messages_bike_rental.txt -> bike_rental)
                category = source_file.replace('messages_', '').replace('.txt', '')
                
                if category not in messages_by_category:
                    messages_by_category[category] = []
                
                messages_by_category[category].append(message)
            
            # Собираем агрегированную категорию "services" для поиска услуг / мастеров
            service_source_categories = [
                'cosmetology',
                'eyebrows',
                'eyelashes',
                'designer',
            ]
            services_pool: List[Dict] = []
            for cat in service_source_categories:
                services_pool.extend(messages_by_category.get(cat, []))
            if services_pool:
                messages_by_category['services'] = services_pool
            
            # Логируем статистику
            for category, messages in messages_by_category.items():
                logger.info(f"  📝 {category}: {len(messages)} сообщений")
            
            logger.info(f"✅ Loaded messages by category: {len(messages_by_category)} categories, {sum(len(msgs) for msgs in messages_by_category.values())} total messages")
            
        except Exception as e:
            logger.error(f"❌ Failed to load messages by category: {e}")
        
        return messages_by_category
    
    def _get_relevant_messages(self, group_link: str) -> List[Dict]:
        """
        Получить релевантные сообщения для группы на основе её под-ниши
        
        Args:
            group_link: Ссылка на группу (@username или t.me/...)
        
        Returns:
            Список релевантных сообщений или все сообщения, если под-ниша не найдена
        """
        # Режим "только ретрит" (RETREAT_ONLY_MODE=true) — максимум буст ретриту 7–10 марта
        # Только bali_retreat (8 марта) — 100% постов про ретрит на Бали
        retreat_only = os.getenv('RETREAT_ONLY_MODE', '').lower() in ('1', 'true', 'yes')
        if retreat_only and self.niche == 'bali':
            bali_retreat = self.messages_by_category.get('bali_retreat', [])
            if bali_retreat:
                logger.info(
                    f"  🎯 RETREAT_ONLY_MODE: только Бали ретрит 7–10 марта ({len(bali_retreat)} сообщений) для {group_link}"
                )
                return bali_retreat

        # Для ниши ukraine_cars всегда используем сообщения из posts_config (Lexus)
        if self.niche == 'ukraine_cars':
            if self.posts_config:
                logger.info(f"  🚗 Using Lexus messages ({len(self.posts_config)} messages) for {group_link}")
                return self.posts_config
            else:
                logger.warning(f"  ⚠️ No Lexus messages loaded for ukraine_cars niche")
                return []
        
        # Нормализуем ссылку (убираем t.me/, добавляем @ если нужно)
        normalized_link = group_link.lstrip('t.me/').lstrip('@')
        if not normalized_link.startswith('@'):
            normalized_link = '@' + normalized_link
        
        group_lower = group_link.lower()
        
        # Получаем под-нишу для группы
        sub_niche = self.group_niches.get(normalized_link)
        
        # 1) Специализированные beauty / services‑группы → отдельный блок поиска услуг
        # Примеры: balibeauty, uslugi_na_bali, balichatservices, baliservice, Belkin_Bali_Service
        if 'services' in self.messages_by_category:
            beauty_services_keywords = [
                'beauty',
                'uslugi',
                'услуги',
                'service',
                'salon',
                'салон',
                'makeup',
                'макияж',
                'маник',
                'педик',
                'бров',
                'ресниц',
                'hair',
                'волос',
                'cosmetology',
                'косметолог',
                'spa',
            ]
            if any(k in group_lower for k in beauty_services_keywords):
                services_messages = self.messages_by_category['services']
                logger.info(
                    f"  🎯 Using services messages ({len(services_messages)} messages) "
                    f"for {group_link} (beauty/services group)"
                )
                return services_messages
        
        # 2) ПРИОРИТЕТ: travel‑/Bali‑чаты → туры Jay Shambo (Индия, Бали ретрит, Тибет Кайлас)
        # ВАЖНО: благотворительная йога (valentine_charity_yoga) только в балийских чатах.
        base_retreat_categories = ['india_holi', 'india_retreat']
        tours_pool_categories = ['india_holi', 'india_retreat', 'bali_retreat', 'tibet_kailash']
        has_retreat = any(cat in self.messages_by_category for cat in base_retreat_categories)
        if sub_niche not in base_retreat_categories and has_retreat:
            # Группы про путешествия, Бали, попутчиков, туры, йогу, ретриты, экспатов
            india_retreat_keywords = [
                'travel',
                'путешеств',
                'попутчик',
                'тур',
                'yoga',
                'йога',
                'retreat',
                'ретрит',
                'bali',
                'бали',
                'комьюнити',
                'community',
                'чат',
                'chat',
                'expat',
                'экспат',
                'nomad',
                'номад',
            ]
            if any(keyword in group_lower for keyword in india_retreat_keywords):
                # Пул туров: Индия (Холи + ретрит) + Бали ретрит + Тибет Кайлас
                retreat_messages: List[Dict] = []
                for cat in tours_pool_categories:
                    retreat_messages.extend(self.messages_by_category.get(cat, []))

                # Целевые категории для микса: ретрит + продажа/аренда/услуги/общие
                extra_categories_order = ['sale_property', 'services', 'rental_property', 'general']
                available_extras = [
                    cat for cat in extra_categories_order if cat in self.messages_by_category
                ]

                # Для НЕ-балийских чатов — только туры (Индия + Бали + Тибет), без локальных услуг
                is_bali_group = ('bali' in group_lower) or ('бали' in group_lower)
                if not is_bali_group:
                    logger.info(
                        f"  🎯 PRIORITY RETREAT: Non-Bali travel/expat group, using tours pool India+Bali+Tibet "
                        f"({len(retreat_messages)} messages) for {group_link}"
                    )
                    return retreat_messages

                # Для балийских travel‑чатов оставляем микс (ретрит 70% + другие темы).
                # Для балийских travel‑чатов ДОБАВЛЯЕМ благотворительную йогу (valentine_charity_yoga)
                # в ретрит-пул, чтобы йога-просылка шла только в Bali‑чаты.
                valentine_msgs = self.messages_by_category.get('valentine_charity_yoga') or []
                if valentine_msgs:
                    retreat_messages = retreat_messages + valentine_msgs

                if not available_extras:
                    logger.info(
                        f"  🎯 PRIORITY RETREAT: Using India-retreat+valentine pool "
                        f"({len(retreat_messages)} messages) for {group_link} (Bali travel group, no extra categories)"
                    )
                    return retreat_messages
                
                # Упор на ретрит в Индию: ~70% ретрит, остальное — микс других тем
                base_weight = 10
                weights_retreat = 7  # 7/10 = 70% ретрит (поиск людей на ретрит в Индию)
                weights = {'retreat': weights_retreat}
                remaining_weight = base_weight - weights_retreat
                per_extra = max(1, remaining_weight // len(available_extras))
                for cat in available_extras:
                    weights[cat] = per_extra
                
                mixed_messages: List[Dict] = []
                def _extend_weighted(category: str, msgs: List[Dict]) -> None:
                    w = weights.get(category, 0)
                    if msgs and w > 0:
                        mixed_messages.extend(msgs * w)
                
                _extend_weighted('retreat', retreat_messages)
                for cat in available_extras:
                    _extend_weighted(cat, self.messages_by_category.get(cat) or [])
                
                if not mixed_messages:
                    logger.warning(
                        f"  ⚠️ Failed to build mixed pool for {group_link}, "
                        f"falling back to retreat only ({len(retreat_messages)} messages)"
                    )
                    return retreat_messages
                
                logger.info(
                    f"  🎯 PRIORITY MIX: tours India+Bali+Tibet 70% + {', '.join(available_extras)} "
                    f"for {group_link} (weights={weights})"
                )
                return mixed_messages
        
        # Маппинг новых категорий на существующие
        category_mapping = {
            'bali_rent': 'rental_property',  # Аренда недвижимости Бали → rental_property
            'bali_it_bots': 'general',       # IT/Бизнес Бали → general
            'sale_property': 'sale_property',  # Продажа недвижимости → sale_property
            'india_holi': 'india_holi',  # Индия Холи → india_holi
            'india_retreat': 'india_retreat_pool',  # Ретрит в Индию → объединённый пул (см. ниже)
        }
        
        # Группы с под-нишей india_retreat: пул туров Jay Shambo — Индия (Холи + ретрит), Бали ретрит, Тибет Кайлас
        #   - для балийских travel‑чатов дополнительно добавляем благотворительную йогу
        if sub_niche == 'india_retreat':
            group_lower = (group_link or '').lower()
            is_bali_group = ('bali' in group_lower) or ('бали' in group_lower)
            retreat_pool: List[Dict] = []
            for cat in ['india_holi', 'india_retreat', 'bali_retreat', 'tibet_kailash']:
                retreat_pool.extend(self.messages_by_category.get(cat, []))

            # В балийские чаты добавляем сообщения благотворительной йоги
            if is_bali_group:
                valentine_msgs = self.messages_by_category.get('valentine_charity_yoga') or []
                retreat_pool = retreat_pool + valentine_msgs

            if retreat_pool:
                logger.info(
                    f"  🎯 Using tours pool India+Bali+Tibet ({len(retreat_pool)} messages) for {group_link} "
                    f"({'Bali travel group' if is_bali_group else 'expat/nomad'})"
                )
                return retreat_pool
        
        # Применяем маппинг, если категория не найдена напрямую
        if sub_niche and sub_niche in category_mapping:
            mapped_category = category_mapping[sub_niche]
            if mapped_category == 'india_retreat_pool':
                retreat_pool = []
                for cat in ['india_holi', 'india_retreat', 'bali_retreat', 'tibet_kailash', 'valentine_charity_yoga']:
                    retreat_pool.extend(self.messages_by_category.get(cat, []))
                if retreat_pool:
                    logger.info(f"  🎯 Using tours pool India+Bali+Tibet ({len(retreat_pool)} messages) for {group_link}")
                    return retreat_pool
            elif mapped_category in self.messages_by_category:
                messages = self.messages_by_category[mapped_category]
                logger.info(f"  🎯 Using {mapped_category} messages ({len(messages)} messages) for {group_link} (mapped from {sub_niche})")
                return messages
        
        if sub_niche and sub_niche not in ['disabled_kammora', 'ukraine_cars']:
            # Проверяем, есть ли сообщения для этой категории
            if sub_niche in self.messages_by_category:
                messages = self.messages_by_category[sub_niche]
                logger.info(f"  🎯 Using {sub_niche} messages ({len(messages)} messages) for {group_link}")
                return messages
            else:
                logger.debug(f"  ⚠️ Sub-niche '{sub_niche}' found for {group_link}, but no messages for this category")
        
        # Fallback: используем все сообщения или сообщения из posts_config
        if self.posts_config:
            logger.info(f"  📋 Using all messages ({len(self.posts_config)} messages) for {group_link} (no specific category)")
            return self.posts_config
        
        logger.warning(f"  ⚠️ No messages available for {group_link}")
        return []
    
    async def create_client(self, account: Account) -> Optional[TelegramClient]:
        """
        Создать TelegramClient для аккаунта
        
        Args:
            account: Account из БД
        
        Returns:
            TelegramClient или None
        """
        session_name = account.session_name
        
        # Получаем конфигурацию аккаунта (из JSON или из БД)
        account_config = self.accounts_config.get(session_name, {})
        
        # Используем данные из БД, если они есть, иначе из конфига
        api_id = account.api_id or account_config.get('api_id')
        api_hash = account.api_hash or account_config.get('api_hash')
        string_session = account.string_session or account_config.get('string_session')
        proxy = account.proxy or account_config.get('proxy')
        
        if not all([api_id, api_hash, string_session]):
            logger.error(f"❌ Missing required fields for {session_name}")
            return None
        
        # Парсим прокси
        proxy_config = None
        if proxy:
            proxy_config = self._parse_proxy(proxy)
        
        try:
            # Создаем клиент
            session_obj = StringSession(string_session.strip())
            client = TelegramClient(
                session_obj,
                int(api_id),
                api_hash,
                proxy=proxy_config
            )
            
            await client.connect()
            
            if not await client.is_user_authorized():
                logger.warning(f"⚠️ Client {session_name} is not authorized")
                await client.disconnect()
                return None
            
            logger.debug(f"✅ Client {session_name} connected")
            return client
            
        except Exception as e:
            logger.error(f"❌ Failed to create client for {session_name}: {e}")
            return None
    
    async def run_batch(self, batch_size: int = 10):
        """
        Запуск батча постинга
        
        Алгоритм:
        1. Найти группы со статусом 'joined'
        2. Проверить warm-up (warmup_ends_at < NOW())
        3. Взять привязанный аккаунт (assigned_account_id)
        4. Опубликовать пост (текст + фото)
        5. Обновить время последнего поста
        
        Args:
            batch_size: Максимальное количество постов за запуск
        """
        logger.info("=" * 80)
        logger.info(f"📢 SMART POSTER - БАТЧ ПОСТИНГА")
        logger.info("=" * 80)
        logger.info(f"📋 Проект: {self.project_name}")
        logger.info(f"📋 Ниша: {self.niche}")
        logger.info(f"📊 Размер батча: {batch_size}")
        logger.info("=" * 80)
        
        # Для отладки: убедиться, что подключаемся к нужной БД (Lexus должен видеть lexus-postgres)
        try:
            from lexus_db.session import get_database_url
            dsn = get_database_url() or ""
            masked = dsn.split("@")[-1] if "@" in dsn else "(not set)"
            logger.info(f"🔗 DB for poster: ...@{masked}")
        except Exception:
            pass

        async with AsyncSessionLocal() as session:
            db_manager = DbManager(session)

            # ШАГ 0: Автоочистка flood_wait — переводим в active, если next_allowed_action_time истёк
            try:
                cleared = await session.execute(
                    text(
                        "UPDATE accounts SET status = 'active', next_allowed_action_time = NULL, updated_at = NOW() "
                        "WHERE status IN ('flood_wait', 'cooldown') "
                        "AND (next_allowed_action_time IS NULL OR next_allowed_action_time <= NOW())"
                    )
                )
                if cleared.rowcount and cleared.rowcount > 0:
                    await session.commit()
                    logger.info(f"✅ Автоочистка: {cleared.rowcount} аккаунт(ов) переведены из flood_wait в active")
            except Exception as e:
                logger.debug(f"Автоочистка flood_wait (возможно, колонка отсутствует): {e}")
                await session.rollback()

            total_active = 0
            try:
                # ШАГ 1: Получаем группы, готовые для постинга (НЕ привязываемся к assigned_account_id:
                # будем выбирать аккаунт динамически с учетом блоклиста связок).
                now = datetime.utcnow()
                logger.info(f"🔍 Searching for groups: niche={self.niche}, status=active, warm_up_until <= {now}")
                
                # Определяем статус для поиска: для ukraine_cars используем 'joined', для bali - 'active'
                # Также учитываем 'active' для обратной совместимости
                target_statuses = ['joined', 'active'] if self.niche == 'ukraine_cars' else ['active', 'joined']
                
                # Сначала проверим, сколько всего групп с нужными условиями
                count_stmt = (
                    select(func.count(Target.id))
                    .where(
                        and_(
                            Target.niche == self.niche,
                            Target.status.in_(target_statuses),
                        )
                    )
                )
                count_result = await session.execute(count_stmt)
                total_active = count_result.scalar_one() or 0
                logger.info(f"📊 Total groups ready for posting in niche '{self.niche}': {total_active}")
                
                stmt = (
                    select(Target)
                    .where(
                        and_(
                            Target.niche == self.niche,
                            Target.status.in_(target_statuses),  # Для ukraine_cars: 'joined' или 'active', для bali: 'active' или 'joined'
                            or_(Target.warm_up_until.is_(None), Target.warm_up_until <= func.now()),
                            or_(Target.can_post.is_(None), Target.can_post.is_(True)),
                            or_(Target.daily_posts_count.is_(None), Target.daily_posts_count < 2),
                        )
                    )
                    # Ротация по чатам: не долбить одни и те же, стучаться в новые прогретые.
                    # 1) С назначенным аккаунтом.
                    # 2) Кто ещё без поста сегодня (daily_posts_count 0) — даём первый пост разным чатам.
                    # 3) Недавно прогретые (warm_up_until только что прошёл) — приоритет новым.
                    # 4) Кому давно не постили (last_post_at старый).
                    # 5) Крупные как tie-breaker.
                    # 6) Случайный порядок при равном приоритете — чтобы не постить каждый раз в одни и те же группы.
                    .order_by(
                        case((Target.assigned_account_id.isnot(None), 0), else_=1).asc(),
                        Target.daily_posts_count.asc().nullsfirst(),  # 0 постов сегодня — в приоритете
                        Target.warm_up_until.desc().nullslast(),      # недавно прогретые первыми
                        Target.last_post_at.asc().nullsfirst(),      # давно не постили
                        Target.members_count.desc().nullslast(),
                        func.random(),
                    )
                    .limit(batch_size)
                )
                result = await session.execute(stmt)
                ready_groups = result.scalars().all()
                logger.info(f"📋 Found {len(ready_groups)} groups ready for posting (from {total_active} active)")
            except Exception as e:
                logger.error(f"❌ Error getting groups ready for posting: {e}", exc_info=True)
                await session.rollback()
                ready_groups = []

            # Fallback: если по строгим фильтрам 0 групп, но активных много — ищем без can_post и daily_posts_count
            if not ready_groups and total_active > 0:
                logger.warning(
                    "⚠️ По строгим фильтрам групп 0. Повторный поиск без can_post и daily_posts_count "
                    "(сбросьте счётчики: scripts/fix_lexus_poster_ready.sh или проверьте права)."
                )
                try:
                    stmt_fallback = (
                        select(Target)
                        .where(
                            and_(
                                Target.niche == self.niche,
                                Target.status.in_(target_statuses),
                                or_(Target.warm_up_until.is_(None), Target.warm_up_until <= now),
                            )
                        )
                        .order_by(
                            case((Target.assigned_account_id.isnot(None), 0), else_=1).asc(),
                            Target.daily_posts_count.asc().nullsfirst(),
                            Target.warm_up_until.desc().nullslast(),
                            Target.last_post_at.asc().nullsfirst(),
                            Target.members_count.desc().nullslast(),
                            func.random(),
                        )
                        .limit(batch_size)
                    )
                    result_fb = await session.execute(stmt_fallback)
                    ready_groups = result_fb.scalars().all()
                    logger.info(f"📋 Fallback: найдено {len(ready_groups)} групп для постинга")
                except Exception as e:
                    logger.error(f"❌ Fallback search failed: {e}", exc_info=True)
                    ready_groups = []

            if not ready_groups:
                logger.info("📭 Нет групп, готовых для постинга")
                return
            
            logger.info(f"📋 Найдено {len(ready_groups)} групп для постинга")
            
            # ШАГ 2: Цикл постинга
            posted_count = 0
            error_count = 0
            
            for idx, target in enumerate(ready_groups, 1):
                # Получаем username напрямую, чтобы избежать lazy loading
                group_username = target.username if hasattr(target, 'username') else getattr(target, 'link', 'unknown')
                logger.info(f"\n{'='*60}")
                logger.info(f"📋 [{idx}/{len(ready_groups)}] Группа: {group_username}")
                logger.info(f"{'='*60}")

                # Выбираем контент для постинга один раз (для повторных попыток разными аккаунтами)
                group_link = group_username
                relevant_messages = self._get_relevant_messages(group_link)
                if not relevant_messages:
                    logger.error(f"  ❌ Нет релевантных сообщений для группы {target.link}")
                    error_count += 1
                    continue

                # Определяем категорию группы для проверки (нужно для rental_property)
                normalized_link = group_link.lstrip('t.me/').lstrip('@')
                if not normalized_link.startswith('@'):
                    normalized_link = '@' + normalized_link
                sub_niche = self.group_niches.get(normalized_link)
                category_mapping = {
                    'bali_rent': 'rental_property',  # Аренда недвижимости Бали → rental_property
                }
                group_category = category_mapping.get(sub_niche) if sub_niche else None

                # Приоритет: сообщения с priority >= 1 выбираются чаще (10x при RETREAT_ONLY, иначе 5x)
                priority_msgs = [m for m in relevant_messages if m.get('priority', 0) >= 1]
                retreat_only = os.getenv('RETREAT_ONLY_MODE', '').lower() in ('1', 'true', 'yes')
                priority_mult = 10 if (retreat_only and self.niche == 'bali') else 5
                if priority_msgs:
                    pool = priority_msgs * priority_mult + relevant_messages
                else:
                    pool = relevant_messages
                post_content = random.choice(pool)
                text_msg = post_content.get('text', '')
                image_path = post_content.get('image') or post_content.get('photo')

                # Для Бали: если сообщение о ПРОДАЖЕ недвижимости без фото — подставляем дефолтные изображения апартов
                # ВАЖНО: для аренды (rental_property) фото НЕ крепим!
                if self.niche == "bali":
                    source_file = post_content.get("source_file", "")
                    
                    # Определяем категорию сообщения по source_file
                    is_rental_property = (
                        source_file == "messages_rental_property.txt" or
                        "rental_property" in source_file.lower() or
                        group_category == "rental_property"  # Также проверяем категорию группы
                    )
                    
                    # Если это аренда - убираем фото, даже если оно было указано
                    if is_rental_property:
                        if image_path:
                            logger.info(f"  🚫 Removing photo for rental_property (source_file: {source_file}, group_category: {group_category})")
                        image_path = None
                    # Если это продажа без фото - подставляем дефолтные изображения
                    elif not image_path and source_file in {
                        "messages_sale_property.txt",  # Только для продажи!
                        "messages_housing.txt",
                    }:
                        default_apartment_photos = [
                            "/app/bali_assets/apart/apart_investment_collage_ru.jpg",
                            "/app/bali_assets/apart/apart_investment_variant_1_ru.jpg",
                            "/app/bali_assets/apart/apart_investment_variant_2_ru.jpg",
                            "/app/bali_assets/apart/apart_investment_variant_3_ru.jpg",
                            "/app/bali_assets/apart/apart_investment_variant_4_ru.jpg",
                        ]
                        image_path = random.choice(default_apartment_photos)

                if not text_msg:
                    logger.warning("  ⚠️ Пустой текст поста, пропускаем")
                    error_count += 1
                    continue

                logger.info(f"  📝 Текст поста: {text_msg[:50]}...")
                if image_path:
                    logger.info(f"  🖼️  Фото: {image_path}")

                # РОТАЦИЯ ДО ПОБЕДНОГО: пробуем группу разными аккаунтами, пока не получится
                attempt = 0
                max_attempts = max(1, len(self.bali_allowed_accounts)) if self.niche == "bali" else 5
                success_for_group = False

                while attempt < max_attempts and not success_for_group:
                    attempt += 1

                    # Выбираем аккаунт для этой группы, исключая тех, кто уже в блоклисте
                    preferred_id = getattr(target, "assigned_account_id", None)
                    if self.niche == "bali" and self.bali_allowed_accounts:
                        allowed_sessions = sorted(self.bali_allowed_accounts)
                    else:
                        allowed_sessions = None  # все active

                    account_sql = text(
                        """
                        SELECT a.id, a.phone, a.string_session, a.session_name, a.status,
                               a.api_id, a.api_hash, a.proxy, a.nickname, a.bio,
                               a.created_at, a.updated_at
                        FROM accounts a
                        WHERE (
                            a.status = 'active'
                            OR (
                                (a.status IN ('cooldown', 'flood_wait'))
                                AND (a.next_allowed_action_time IS NULL OR a.next_allowed_action_time <= NOW())
                            )
                        )
                          AND (
                            :allowed_sessions_is_null
                            OR a.session_name = ANY(CAST(:allowed_sessions AS TEXT[]))
                          )
                          AND NOT EXISTS (
                            SELECT 1
                            FROM account_group_blocklist b
                            WHERE b.group_id = :group_id AND b.account_id = a.id
                          )
                        ORDER BY
                          CASE
                            WHEN CAST(:preferred_id AS INTEGER) IS NOT NULL
                              AND a.id = CAST(:preferred_id AS INTEGER)
                            THEN 0
                            ELSE 1
                          END,
                          a.id
                        LIMIT 1
                        """
                    )

                    params = {
                        "group_id": target.id,
                        "preferred_id": preferred_id,
                        "allowed_sessions_is_null": allowed_sessions is None,
                        "allowed_sessions": allowed_sessions or [],
                    }
                    account_row = (await session.execute(account_sql, params)).fetchone()
                    if not account_row:
                        logger.warning(
                            f"  ⚠️ Нет доступных аккаунтов для группы {group_username} "
                            f"(все в блоклисте). Перевожу группу в 'no_accounts_left'."
                        )
                        target.status = "no_accounts_left"
                        target.updated_at = datetime.utcnow()
                        await session.commit()
                        error_count += 1
                        break

                    account = Account(
                        id=account_row[0],
                        phone=account_row[1],
                        string_session=account_row[2],
                        session_name=account_row[3],
                        status=account_row[4],
                        api_id=account_row[5],
                        api_hash=account_row[6],
                        proxy=account_row[7],
                        nickname=account_row[8],
                        bio=account_row[9],
                        created_at=account_row[10],
                        updated_at=account_row[11],
                    )

                    logger.info(
                        f"  👤 Попытка {attempt}/{max_attempts}: аккаунт {account.session_name} (id={account.id})"
                    )

                    # Для Ukraine используем только Ukraine аккаунты
                    if self.niche == "ukraine_cars":
                        ukraine_accounts = [
                            "promotion_dao_bro",
                            "promotion_alex_ever",
                            "promotion_rod_shaihutdinov",
                        ]
                        if account.session_name not in ukraine_accounts:
                            logger.warning(
                                f"  ⚠️ Аккаунт {account.session_name} не является Ukraine аккаунтом, "
                                "пробуем следующий"
                            )
                            # баним связку, чтобы не выбирать его снова для этой группы
                            await session.execute(
                                text(
                                    "INSERT INTO account_group_blocklist (group_id, account_id, reason) "
                                    "VALUES (:gid, :aid, :reason) "
                                    "ON CONFLICT (group_id, account_id) DO NOTHING"
                                ),
                                {"gid": target.id, "aid": account.id, "reason": "ukraine_account_not_allowed"},
                            )
                            await session.commit()
                            continue

                    client = await self.create_client(account)
                    if not client:
                        logger.error(f"  ❌ Не удалось создать клиент для {account.session_name}")
                        await session.execute(
                            text(
                                "INSERT INTO account_group_blocklist (group_id, account_id, reason) "
                                "VALUES (:gid, :aid, :reason) "
                                "ON CONFLICT (group_id, account_id) DO NOTHING"
                            ),
                            {"gid": target.id, "aid": account.id, "reason": "client_create_failed"},
                        )
                        await session.commit()
                        error_count += 1
                        continue

                    try:
                        username = group_username.lstrip("@")

                        # ВАЖНО: проверяем членство перед постингом
                        try:
                            entity = await client.get_entity(username)
                            # Пытаемся получить информацию о группе - если ошибка, значит не участник
                            me = await client.get_me()
                            permissions = await client.get_permissions(entity, me)
                            if not permissions:
                                raise Exception("Нет доступа к группе")
                        except FloodWaitError:
                            # FloodWait при get_entity — не «не участник», а лимит Telegram; пробуем другой аккаунт
                            raise
                        except (ChannelPrivateError, Exception) as e:
                            error_msg = f"Аккаунт не является участником группы: {str(e)[:100]}"
                            logger.warning(f"  ⚠️ {error_msg}")
                            
                            # Добавляем в блоклист
                            await session.execute(
                                text(
                                    "INSERT INTO account_group_blocklist (group_id, account_id, reason) "
                                    "VALUES (:gid, :aid, :reason) "
                                    "ON CONFLICT (group_id, account_id) DO NOTHING"
                                ),
                                {"gid": target.id, "aid": account.id, "reason": error_msg[:500]},
                            )
                            # «Не участник» → status='new', чтобы account-manager снова вступил в группу
                            # Приват/удалена → inaccessible
                            err_lower = str(e).lower()
                            if ("not a member" in err_lower or "participant" in err_lower) and "private" not in err_lower:
                                target.status = "new"
                                logger.info(f"  📌 Группа {group_username} → status=new (account-manager попытается вступить)")
                            else:
                                target.status = "inaccessible"
                            target.can_post = False
                            target.updated_at = datetime.utcnow()
                            await session.commit()
                            error_count += 1
                            continue
                        
                        # Если не участник, пытаемся вступить
                        joined_successfully = False
                        try:
                            await client(JoinChannelRequest(username))
                            logger.info(f"  ✅ Вступил в группу {username}")
                            joined_successfully = True
                        except UserAlreadyParticipantError:
                            logger.debug(f"  ℹ️ Уже участник {username}")
                            joined_successfully = True
                        except Exception as e:
                            logger.warning(f"  ⚠️ Не удалось вступить в {username}: {str(e)[:50]}")
                        
                        # Обновляем статус на 'joined' после успешного вступления
                        if joined_successfully and target.status != 'joined':
                            target.status = 'joined'
                            logger.debug(f"  📝 Обновлен статус группы {username} на 'joined'")

                        # Обрабатываем путь к фото
                        full_image_path = None
                        if image_path:
                            # Bali: никогда не используем lexus_assets (иногда попадали ошибочно в messages.json)
                            if self.niche == "bali" and str(image_path).startswith("lexus_assets/"):
                                logger.warning(
                                    f"  ⚠️ Ignoring lexus photo for Bali: {image_path}"
                                )
                                image_path = None

                            if Path(image_path).exists():
                                full_image_path = image_path
                            else:
                                # Важно: для Bali ищем только в bali_assets/assets; для Ukraine допускаем lexus_assets.
                                possible_paths = [Path(image_path), Path("/app") / image_path]

                                if self.niche == "bali":
                                    possible_paths.extend(
                                        [
                                            Path("/app/bali_assets") / str(image_path).replace("bali_assets/", ""),
                                            Path("/app/assets") / str(image_path).replace("bali_assets/", ""),
                                        ]
                                    )
                                else:
                                    possible_paths.extend(
                                        [
                                            Path("/app/lexus_assets")
                                            / str(image_path).replace("lexus_assets/", ""),
                                            Path("/app/assets")
                                            / str(image_path).replace("lexus_assets/", ""),
                                            Path("/app/data/ukraine/assets")
                                            / str(image_path).replace("lexus_assets/", ""),
                                        ]
                                    )
                                for pth in possible_paths:
                                    if pth.exists():
                                        full_image_path = str(pth)
                                        logger.info(f"  🔍 Found photo at: {full_image_path}")
                                        break
                                if not full_image_path:
                                    logger.warning(
                                        f"  ⚠️ Photo not found: {image_path}, sending text only"
                                    )

                        sent_with_photo = False
                        if full_image_path:
                            try:
                                await client.send_file(username, full_image_path, caption=text_msg)
                                sent_with_photo = True
                            except ChatSendMediaForbiddenError:
                                logger.warning(
                                    f"  📷 В группе {group_username} запрещены фото, отправляю только текст"
                                )
                                try:
                                    await client.send_message(username, text_msg)
                                except (ChatWriteForbiddenError, UserBannedInChannelError) as e2:
                                    error_msg = f"Запрещено писать в группе: {str(e2)}"
                                    logger.error(f"  🚫 {error_msg} — помечаю группу как read_only")
                                    target.status = "read_only"
                                    target.can_post = False
                                    target.updated_at = datetime.utcnow()
                                    await db_manager.record_post(
                                        account_id=account.id,
                                        target_id=target.id,
                                        status="error",
                                        error_message=error_msg,
                                    )
                                    await session.commit()
                                    error_count += 1
                                    success_for_group = False
                                    break
                            except RPCError as e_photo:
                                err_str = str(e_photo).lower()
                                is_403 = getattr(e_photo, "code", None) == 403
                                is_photo_forbidden = (
                                    "photo" in err_str and "forbidden" in err_str
                                ) or "send_media" in err_str or "chat_send_media" in err_str
                                if is_403 or is_photo_forbidden:
                                    logger.warning(
                                        f"  📷 RPC 403/фото запрещены в {group_username}, отправляю только текст"
                                    )
                                    try:
                                        await client.send_message(username, text_msg)
                                    except (ChatWriteForbiddenError, UserBannedInChannelError) as e2:
                                        error_msg = f"Запрещено писать в группе: {str(e2)}"
                                        logger.error(f"  🚫 {error_msg} — помечаю группу как read_only")
                                        target.status = "read_only"
                                        target.can_post = False
                                        target.updated_at = datetime.utcnow()
                                        await db_manager.record_post(
                                            account_id=account.id,
                                            target_id=target.id,
                                            status="error",
                                            error_message=error_msg,
                                        )
                                        await session.commit()
                                        error_count += 1
                                        success_for_group = False
                                        break
                                else:
                                    raise
                        else:
                            await client.send_message(username, text_msg)

                        logger.info(
                            f"  ✅ Пост отправлен в {group_username} (account={account.session_name})"
                        )

                        await db_manager.record_post(
                            account_id=account.id,
                            target_id=target.id,
                            message_content=text_msg[:1000],
                            photo_path=image_path if sent_with_photo else None,
                            status="success",
                        )

                        # Обновляем "последний успешный" аккаунт для группы
                        target.assigned_account_id = account.id
                        target.updated_at = datetime.utcnow()
                        
                        # Обновляем статус на 'joined' после успешного поста (если еще не обновлен)
                        if target.status != 'joined':
                            target.status = 'joined'
                            logger.debug(f"  📝 Обновлен статус группы {group_username} на 'joined' после успешного поста")
                        
                        # Если аккаунт был в cooldown/flood_wait, но ограничение истекло — переводим в active
                        if account.status in ('cooldown', 'flood_wait'):
                            await session.execute(
                                text("UPDATE accounts SET status = 'active' WHERE id = :aid AND (next_allowed_action_time IS NULL OR next_allowed_action_time <= NOW())"),
                                {"aid": account.id}
                            )

                        await session.commit()
                        posted_count += 1
                        success_for_group = True

                        pause_seconds = random.randint(30, 60)
                        logger.info(
                            f"  ⏸️  Пауза {pause_seconds} сек перед следующим постом..."
                        )
                        await asyncio.sleep(pause_seconds)

                    except FloodWaitError as e:
                        wait_seconds = e.seconds
                        logger.warning(
                            f"  ⏳ FloodWait {wait_seconds} сек для аккаунта {account.session_name} — "
                            f"перевожу в cooldown до истечения, пробуем другой аккаунт"
                        )
                        await db_manager.record_post(
                            account_id=account.id,
                            target_id=target.id,
                            message_content=text_msg[:1000] if text_msg else None,
                            status="flood_wait",
                            error_message=f"FloodWait: {wait_seconds} seconds",
                        )
                        wait_until = datetime.utcnow() + timedelta(seconds=wait_seconds)
                        await db_manager.set_account_flood_wait(account.id, wait_until)
                        await session.commit()
                        error_count += 1
                        continue

                    except (ChatWriteForbiddenError, UserBannedInChannelError) as e:
                        error_msg = f"Запрещено писать в группе: {str(e)}"
                        logger.error(f"  🚫 {error_msg}")

                        await session.execute(
                            text(
                                "INSERT INTO account_group_blocklist (group_id, account_id, reason) "
                                "VALUES (:gid, :aid, :reason) "
                                "ON CONFLICT (group_id, account_id) DO NOTHING"
                            ),
                            {"gid": target.id, "aid": account.id, "reason": error_msg[:500]},
                        )

                        await db_manager.record_post(
                            account_id=account.id,
                            target_id=target.id,
                            status="error",
                            error_message=error_msg,
                        )
                        # Если группа read-only («You can't write in this chat») — не пробуем другие аккаунты
                        err_lower = error_msg.lower()
                        if "can't write in this chat" in err_lower or "you can't write" in err_lower:
                            target.status = "read_only"
                            target.can_post = False
                            target.updated_at = datetime.utcnow()
                            logger.warning(f"  📖 Группа {target.username} помечена как read_only, постинг отключён")
                            success_for_group = False
                        await session.commit()
                        error_count += 1
                        if target.status == "read_only":
                            break
                        await asyncio.sleep(5)

                    except RPCError as e:
                        error_msg = f"RPC Error: {str(e)}"
                        logger.error(f"  ❌ {error_msg}")

                        error_str = str(e).lower()
                        
                        # Блокирующие ошибки - группа недоступна для постинга ВООБЩЕ
                        blocking_errors = [
                            "allow_payment_required",  # Требуется оплата
                            "chat_send_plain_forbidden",  # Текстовые сообщения запрещены
                            "topic_closed",  # Топики закрыты (для форумов)
                            "the channel specified is private",  # Канал приватный и нет доступа
                            "you lack permission to access it",  # Нет разрешения на доступ
                            "you were banned from it",  # Забанен в канале
                        ]
                        # Read-only группа: писать нельзя никому — помечаем и не пробуем другие аккаунты
                        is_read_only_group = (
                            "can't write in this chat" in error_str
                            or "you can't write in this chat" in error_str
                        )
                        is_blocking_error = any(
                            blocking_err in error_str for blocking_err in blocking_errors
                        )

                        # Ошибки для блоклиста аккаунта (можно попробовать другой аккаунт)
                        account_blocklist_errors = [
                            "can't write" in error_str,
                            "write forbidden" in error_str,
                            "chatwriteforbidden" in error_str,
                            "you're banned" in error_str,
                        ]

                        # Read-only группа → статус read_only, не пробуем другие аккаунты
                        if is_read_only_group:
                            logger.warning(
                                f"  📖 Группа {target.username}: read-only (can't write), "
                                f"помечаю и отключаю постинг"
                            )
                            target.status = "read_only"
                            target.can_post = False
                            target.updated_at = datetime.utcnow()
                            await db_manager.record_post(
                                account_id=account.id,
                                target_id=target.id,
                                status="error",
                                error_message=error_msg,
                            )
                            await session.commit()
                            error_count += 1
                            success_for_group = False
                            break

                        # Если это блокирующая ошибка - помечаем группу как недоступную
                        if is_blocking_error:
                            logger.warning(
                                f"  🚫 Блокирующая ошибка для группы {target.username}: "
                                f"перевожу в статус 'inaccessible'"
                            )
                            target.status = "inaccessible"
                            target.can_post = False
                            target.updated_at = datetime.utcnow()
                            await session.commit()

                            # Записываем ошибку
                            await db_manager.record_post(
                                account_id=account.id,
                                target_id=target.id,
                                status="error",
                                error_message=error_msg,
                            )
                            await session.commit()
                            error_count += 1
                            # Прерываем попытки для этой группы
                            success_for_group = False
                            break

                        # Если это ошибка для конкретного аккаунта - добавляем в блоклист
                        elif any(account_blocklist_errors):
                            await session.execute(
                                text(
                                    "INSERT INTO account_group_blocklist (group_id, account_id, reason) "
                                    "VALUES (:gid, :aid, :reason) "
                                    "ON CONFLICT (group_id, account_id) DO NOTHING"
                                ),
                                {"gid": target.id, "aid": account.id, "reason": error_msg[:500]},
                            )

                        await db_manager.record_post(
                            account_id=account.id,
                            target_id=target.id,
                            status="error",
                            error_message=error_msg,
                        )
                        await session.commit()
                        error_count += 1
                        await asyncio.sleep(5)

                    except Exception as e:
                        logger.error(
                            f"  ❌ Неожиданная ошибка при постинге: {e}", exc_info=True
                        )
                        error_count += 1
                        await asyncio.sleep(5)

                    finally:
                        try:
                            if client and client.is_connected():
                                await client.disconnect()
                        except Exception:
                            pass

                # Если не получилось ни с одним аккаунтом — проверяем статус группы
                if not success_for_group and target.status == "active":
                    # Проверяем, есть ли еще незабаненные аккаунты для группы
                    remain_sql = text(
                        """
                        SELECT COUNT(*)
                        FROM accounts a
                        WHERE a.status = 'active'
                          AND (
                            :allowed_sessions_is_null
                            OR a.session_name = ANY(CAST(:allowed_sessions AS TEXT[]))
                          )
                          AND NOT EXISTS (
                            SELECT 1 FROM account_group_blocklist b
                            WHERE b.group_id = :group_id AND b.account_id = a.id
                          )
                        """
                    )
                    allowed_sessions = sorted(self.bali_allowed_accounts) if (self.niche == "bali" and self.bali_allowed_accounts) else None
                    remain = (
                        await session.execute(
                            remain_sql,
                            {
                                "group_id": target.id,
                                "allowed_sessions_is_null": allowed_sessions is None,
                                "allowed_sessions": allowed_sessions or [],
                            },
                        )
                    ).scalar_one()
                    
                    if remain == 0:
                        # Проверяем последние ошибки - если все были блокирующими, помечаем как inaccessible
                        recent_errors_sql = text(
                            """
                            SELECT error_message
                            FROM posts
                            WHERE group_id = :group_id
                              AND sent_at >= NOW() - INTERVAL '1 hour'
                              AND success = false
                            ORDER BY sent_at DESC
                            LIMIT 5
                            """
                        )
                        recent_errors = await session.execute(
                            recent_errors_sql,
                            {"group_id": target.id}
                        )
                        error_messages = [row[0] for row in recent_errors.fetchall() if row[0]]
                        
                        # Если все ошибки указывают на блокирующие проблемы
                        blocking_keywords = [
                            "private",
                            "lack permission",
                            "banned from it",
                            "inaccessible"
                        ]
                        all_blocking = len(error_messages) >= 3 and all(
                            any(keyword in (msg or "").lower() for keyword in blocking_keywords)
                            for msg in error_messages[:3]
                        )
                        
                        if all_blocking:
                            logger.warning(
                                f"  🚫 Группа {group_username} недоступна (все ошибки блокирующие): "
                                f"перевожу в статус 'inaccessible'"
                            )
                            target.status = "inaccessible"
                            target.can_post = False
                        else:
                            logger.warning(
                                f"  ⚠️ Группа {group_username}: все аккаунты в блоклисте, "
                                f"перевожу в статус 'no_accounts_left'"
                            )
                            target.status = "no_accounts_left"
                        
                        target.updated_at = datetime.utcnow()
                        await session.commit()
            
            logger.info("\n" + "=" * 80)
            logger.info(f"✅ БАТЧ ПОСТИНГА ЗАВЕРШЕН")
            logger.info(f"📊 Статистика: {posted_count} успешно, {error_count} ошибок")
            logger.info("=" * 80)


async def main():
    """Точка входа для запуска скрипта"""
    import sys
    
    # Парсинг аргументов
    niche = os.getenv('NICHE', 'ukraine_cars')
    batch_size = 5
    
    if len(sys.argv) > 1:
        niche = sys.argv[1]
    if len(sys.argv) > 2:
        batch_size = int(sys.argv[2])
    
    # Запуск
    poster = SmartPoster(niche=niche)
    await poster.run_batch(batch_size=batch_size)


if __name__ == "__main__":
    asyncio.run(main())
