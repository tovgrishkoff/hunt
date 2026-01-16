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
from telethon.errors import (
    FloodWaitError,
    ChatWriteForbiddenError,
    UserBannedInChannelError,
    RPCError
)

from lexus_db.session import AsyncSessionLocal
from lexus_db.models import Account, Target
from lexus_db.db_manager import DbManager
from sqlalchemy import select, and_, or_

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/logs/poster.log'),
        logging.StreamHandler()
    ]
)
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
        Для ниши 'bali' загружает из config/messages/bali/messages.json
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
        """Загружает сообщения из config/messages/bali/messages.json и группирует по категориям"""
        messages_by_category = {}
        
        # Пути к файлу с сообщениями
        messages_paths = [
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
            logger.warning("⚠️ config/messages/bali/messages.json not found")
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
        
        # Получаем под-нишу для группы
        sub_niche = self.group_niches.get(normalized_link)
        
        # Маппинг новых категорий на существующие
        category_mapping = {
            'bali_rent': 'rental_property',  # Недвижимость Бали → rental_property
            'bali_it_bots': 'general',       # IT/Бизнес Бали → general
        }
        
        # Применяем маппинг, если категория не найдена напрямую
        if sub_niche and sub_niche in category_mapping:
            mapped_category = category_mapping[sub_niche]
            if mapped_category in self.messages_by_category:
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
        
        async with AsyncSessionLocal() as session:
            db_manager = DbManager(session)
            
            try:
                # ШАГ 1: Получаем группы, готовые для постинга
                ready_groups = await db_manager.get_groups_ready_for_posting(
                    niche=self.niche,
                    limit=batch_size
                )
            except Exception as e:
                logger.error(f"❌ Error getting groups ready for posting: {e}", exc_info=True)
                await session.rollback()
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
                
                # Проверяем привязку аккаунта
                if not target.assigned_account_id:
                    logger.warning(f"  ⚠️ Группа {target.link} не привязана к аккаунту, пропускаем")
                    error_count += 1
                    continue
                
                # Загружаем аккаунт (используем прямой SQL-запрос для БД Bali, чтобы избежать проблем с отсутствующими полями)
                try:
                    # Используем прямой SQL, чтобы загрузить только существующие поля
                    from sqlalchemy import text
                    account_sql = text("""
                        SELECT id, phone, string_session, session_name, status, 
                               api_id, api_hash, proxy, nickname, bio,
                               created_at, updated_at
                        FROM accounts 
                        WHERE id = :account_id
                    """)
                    account_result = await session.execute(account_sql, {"account_id": target.assigned_account_id})
                    account_row = account_result.fetchone()
                    
                    if account_row:
                        # Создаем объект Account из результата
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
                            updated_at=account_row[11]
                        )
                    else:
                        account = None
                except Exception as e:
                    logger.error(f"  ❌ Error loading account {target.assigned_account_id}: {e}")
                    account = None
                
                if not account:
                    logger.error(f"  ❌ Аккаунт {target.assigned_account_id} не найден в БД")
                    error_count += 1
                    continue
                
                # Проверяем, что аккаунт из whitelist для Бали (только для ниши 'bali')
                if self.niche == 'bali' and self.bali_allowed_accounts and account.session_name not in self.bali_allowed_accounts:
                    logger.warning(f"  ⚠️ Аккаунт {account.session_name} не в whitelist для Бали, пропускаем")
                    error_count += 1
                    continue
                
                # Для Ukraine используем только Ukraine аккаунты
                if self.niche == 'ukraine_cars':
                    ukraine_accounts = ['promotion_dao_bro', 'promotion_alex_ever', 'promotion_rod_shaihutdinov']
                    if account.session_name not in ukraine_accounts:
                        logger.warning(f"  ⚠️ Аккаунт {account.session_name} не является Ukraine аккаунтом, пропускаем")
                        error_count += 1
                        continue
                
                logger.info(f"  👤 Используем аккаунт: {account.session_name} (id={account.id})")
                
                # Создаем клиент
                client = await self.create_client(account)
                if not client:
                    logger.error(f"  ❌ Не удалось создать клиент для {account.session_name}")
                    error_count += 1
                    continue
                
                try:
                    # ШАГ 3: Выбираем релевантный пост для группы
                    # Используем username напрямую, чтобы избежать lazy loading
                    group_link = group_username
                    relevant_messages = self._get_relevant_messages(group_link)
                    
                    if not relevant_messages:
                        logger.error(f"  ❌ Нет релевантных сообщений для группы {target.link}")
                        error_count += 1
                        continue
                    
                    post_content = random.choice(relevant_messages)
                    text = post_content.get('text', '')
                    image_path = post_content.get('image') or post_content.get('photo')
                    
                    if not text:
                        logger.warning(f"  ⚠️ Пустой текст поста, пропускаем")
                        error_count += 1
                        continue
                    
                    logger.info(f"  📝 Текст поста: {text[:50]}...")
                    if image_path:
                        logger.info(f"  🖼️  Фото: {image_path}")
                    
                    # ШАГ 4: Отправка поста
                    group_link = target.link
                    username = group_link.lstrip('@')
                    
                    try:
                        # Обрабатываем путь к фото (может быть относительным, например lexus_assets/lexus_variant_1.jpg)
                        full_image_path = None
                        if image_path:
                            # Если путь абсолютный и существует
                            if Path(image_path).exists():
                                full_image_path = image_path
                            else:
                                # Ищем в различных местах
                                possible_paths = [
                                    Path(image_path),  # Оригинальный путь
                                    Path('/app') / image_path,  # В контейнере
                                    Path('/app/lexus_assets') / image_path.replace('lexus_assets/', ''),  # В lexus_assets
                                    Path('/app/assets') / image_path.replace('lexus_assets/', ''),  # В assets
                                    Path('/app/data/ukraine/assets') / image_path.replace('lexus_assets/', ''),  # В ukraine assets
                                ]
                                
                                for path in possible_paths:
                                    if path.exists():
                                        full_image_path = str(path)
                                        logger.info(f"  🔍 Found photo at: {full_image_path}")
                                        break
                                
                                if not full_image_path:
                                    logger.warning(f"  ⚠️ Photo not found: {image_path}, sending text only")
                        
                        if full_image_path:
                            # Отправляем с фото
                            await client.send_file(username, full_image_path, caption=text)
                            logger.info(f"  ✅ Пост с фото отправлен в {group_link}")
                        else:
                            # Отправляем только текст
                            await client.send_message(username, text)
                            logger.info(f"  ✅ Пост отправлен в {group_link}")
                        
                        # ШАГ 5: Записываем в историю и обновляем счетчики
                        # record_post() автоматически обновляет:
                        # - account.daily_posts_count += 1
                        # - target.daily_posts_in_group += 1
                        # - target.last_post_at = NOW()
                        await db_manager.record_post(
                            account_id=account.id,
                            target_id=target.id,
                            message_content=text[:1000],  # Ограничиваем длину
                            photo_path=image_path,
                            status='success'
                        )
                        
                        await session.commit()
                        posted_count += 1
                        
                        # Пауза между постами (30-60 секунд)
                        pause_seconds = random.randint(30, 60)
                        logger.info(f"  ⏸️  Пауза {pause_seconds} сек перед следующим постом...")
                        await asyncio.sleep(pause_seconds)
                        
                    except FloodWaitError as e:
                        wait_seconds = e.seconds
                        logger.warning(f"  ⏳ FloodWait {wait_seconds} сек для аккаунта {account.session_name}")
                        
                        # Устанавливаем FloodWait для аккаунта
                        wait_until = datetime.utcnow() + timedelta(seconds=wait_seconds)
                        await db_manager.set_account_flood_wait(account.id, wait_until)
                        
                        # Записываем в историю
                        await db_manager.record_post(
                            account_id=account.id,
                            target_id=target.id,
                            message_content=text[:1000] if text else None,
                            status='flood_wait',
                            error_message=f"FloodWait: {wait_seconds} seconds"
                        )
                        
                        error_count += 1
                        
                        # Пауза перед следующим постом
                        await asyncio.sleep(60)
                    
                    except (ChatWriteForbiddenError, UserBannedInChannelError) as e:
                        error_msg = f"Запрещено писать в группе: {str(e)}"
                        logger.error(f"  🚫 {error_msg}")
                        
                        # САМООЧИЩЕНИЕ БД: Помечаем группу как read_only и can_post=False
                        target.status = 'read_only'
                        target.can_post = False
                        target.updated_at = datetime.utcnow()
                        logger.info(f"  🔄 Группа {group_username} помечена как read_only, can_post=False (самоочищение БД)")
                        
                        # Записываем в историю
                        await db_manager.record_post(
                            account_id=account.id,
                            target_id=target.id,
                            status='error',
                            error_message=error_msg
                        )
                        
                        await session.commit()
                        error_count += 1
                        await asyncio.sleep(30)
                    
                    except RPCError as e:
                        error_msg = f"RPC Error: {str(e)}"
                        error_str = str(e).lower()
                        
                        # Проверяем, является ли это ошибкой "You can't write in this chat"
                        if "can't write" in error_str or "write forbidden" in error_str or "chatwriteforbidden" in error_str:
                            logger.error(f"  🚫 {error_msg}")
                            
                            # САМООЧИЩЕНИЕ БД: Помечаем группу как read_only и can_post=False
                            target.status = 'read_only'
                            target.can_post = False
                            target.updated_at = datetime.utcnow()
                            logger.info(f"  🔄 Группа {group_username} помечена как read_only, can_post=False (самоочищение БД из RPCError)")
                        else:
                            logger.error(f"  ❌ {error_msg}")
                        
                        await db_manager.record_post(
                            account_id=account.id,
                            target_id=target.id,
                            status='error',
                            error_message=error_msg
                        )
                        
                        await session.commit()
                        error_count += 1
                        await asyncio.sleep(30)
                
                except Exception as e:
                    logger.error(f"  ❌ Неожиданная ошибка при постинге: {e}", exc_info=True)
                    error_count += 1
                    await asyncio.sleep(30)
                
                finally:
                    # Закрываем клиент
                    try:
                        if client and client.is_connected():
                            await client.disconnect()
                    except:
                        pass
            
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
