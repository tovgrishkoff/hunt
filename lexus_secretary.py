#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Secretary для Lexus: Умный помощник по продаже автомобиля с GPT
Отвечает на вопросы и переводит на @grishkoff
"""
import asyncio
import json
import logging
import sys
import os
import random
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.events import NewMessage
from telethon.tl.types import User
from telethon.errors import FloodWaitError, UsernameNotOccupiedError, RPCError

# Добавляем корень проекта в PYTHONPATH
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Импорты для GPT Handler и ConfigLoader
try:
    from shared.config.loader import ConfigLoader
    from services.secretary.gpt_handler import GPTHandler
    GPT_AVAILABLE = True
except ImportError as e:
    GPT_AVAILABLE = False
    logging.warning(f"GPT modules not available: {e}")

# Настройка логирования
log_dir = Path('logs')
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / 'lexus_secretary.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class LexusSecretary:
    """Секретарь для Lexus - отвечает через GPT и переводит на @grishkoff"""
    
    def __init__(self, forward_to_username: str = 'grishkoff'):
        """
        Args:
            forward_to_username: Username пользователя для пересылки (без @)
        """
        self.forward_to_username = forward_to_username
        self.forward_to_entity = None
        self.clients = {}
        self.accounts = []
        self.recent_responses = {}  # {(account_name, user_id): timestamp} для избежания дублей
        self.recent_window = 60  # секунд
        
        # GPT Handler и конфигурация
        self.config_loader = None
        self.gpt_handler = None
        self.niche_config = None
        self.secretary_config = {}
    
    def load_accounts(self, accounts_config: str = 'accounts_config.json', lexus_config: str = 'lexus_accounts_config.json'):
        """Загрузка аккаунтов для Lexus из отдельного конфига"""
        try:
            # Сначала проверяем, есть ли отдельный конфиг для Lexus
            lexus_config_path = Path(lexus_config)
            if lexus_config_path.exists():
                try:
                    with open(lexus_config_path, 'r', encoding='utf-8') as f:
                        lexus_config_data = json.load(f)
                        allowed_account_names = set(lexus_config_data.get('allowed_accounts', []))
                    
                    if allowed_account_names:
                        # Загружаем все аккаунты
                        accounts_config_path = Path(accounts_config)
                        if not accounts_config_path.exists():
                            logger.error(f"❌ Config file {accounts_config} not found")
                            return False
                        
                        with open(accounts_config_path, 'r', encoding='utf-8') as f:
                            all_accounts = json.load(f)
                        
                        # Фильтруем только разрешенные аккаунты
                        self.accounts = [
                            acc for acc in all_accounts
                            if acc.get('session_name') in allowed_account_names
                        ]
                        
                        logger.info(f"✅ Loaded {len(self.accounts)} Lexus accounts from {lexus_config}")
                        logger.info(f"   Allowed accounts: {sorted(allowed_account_names)}")
                        return True
                    else:
                        logger.warning(f"⚠️ No allowed_accounts in {lexus_config}, falling back to excluded accounts method")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to load {lexus_config}: {e}, falling back to excluded accounts method")
            
            # Fallback: используем старый метод с исключениями (для обратной совместимости)
            logger.info(f"⚠️ Using fallback method: loading all accounts except excluded ones")
            config_path = Path(accounts_config)
            if not config_path.exists():
                logger.error(f"❌ Config file {accounts_config} not found")
                return False
            
            with open(config_path, 'r', encoding='utf-8') as f:
                all_accounts = json.load(f)
            
            # Загружаем список исключенных аккаунтов для ukraine_cars
            excluded_accounts = set()
            ukraine_config_path = Path('ukraine_cars_accounts_config.json')
            if ukraine_config_path.exists():
                try:
                    with open(ukraine_config_path, 'r', encoding='utf-8') as f:
                        ukraine_config = json.load(f)
                        excluded_accounts = set(ukraine_config.get('excluded_accounts', []))
                        if excluded_accounts:
                            logger.info(f"⚠️ Excluding {len(excluded_accounts)} accounts: {excluded_accounts}")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to load ukraine_cars config: {e}")
            
            # Фильтруем аккаунты (используем только те, которые НЕ исключены)
            self.accounts = [
                acc for acc in all_accounts
                if acc.get('session_name') not in excluded_accounts
            ]
            
            logger.info(f"✅ Loaded {len(self.accounts)} accounts using fallback method (excluded accounts)")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error loading accounts: {e}")
            return False
    
    def parse_proxy(self, proxy_string: Optional[str]):
        """Парсинг строки прокси"""
        if not proxy_string:
            return None
        
        try:
            if proxy_string.startswith('http://'):
                parts = proxy_string.replace('http://', '').split('@')
                if len(parts) == 2:
                    auth, addr = parts
                    user, pwd = auth.split(':')
                    host, port = addr.split(':')
                    return {
                        'proxy_type': 'http',
                        'addr': host,
                        'port': int(port),
                        'username': user,
                        'password': pwd
                    }
        except Exception as e:
            logger.warning(f"Failed to parse proxy {proxy_string}: {e}")
        
        return None
    
    async def create_client(self, account_config: dict) -> Optional[TelegramClient]:
        """Создать клиент для аккаунта"""
        session_name = account_config.get('session_name')
        api_id = account_config.get('api_id')
        api_hash = account_config.get('api_hash')
        string_session = account_config.get('string_session')
        proxy = account_config.get('proxy')
        
        if not all([session_name, api_id, api_hash]):
            logger.error(f"❌ Missing required fields for {session_name}")
            return None
        
        proxy_config = self.parse_proxy(proxy)
        
        # Создаем клиент
        try:
            if string_session and string_session.strip() and string_session not in ['', 'null']:
                session_obj = StringSession(string_session.strip())
                client = TelegramClient(
                    session_obj,
                    api_id,
                    api_hash,
                    proxy=proxy_config
                )
                logger.info(f"Created client {session_name} with StringSession")
            else:
                # Файловая сессия
                session_path = Path('sessions') / f"{session_name}.session"
                client = TelegramClient(
                    str(session_path),
                    api_id,
                    api_hash,
                    proxy=proxy_config
                )
                logger.info(f"Created client {session_name} with file session")
            
            # Подключаемся
            await client.connect()
            
            if not await client.is_user_authorized():
                logger.warning(f"⚠️ Client {session_name} is not authorized")
                await client.disconnect()
                return None
            
            self.clients[session_name] = client
            logger.info(f"✅ Client {session_name} connected and authorized")
            return client
            
        except Exception as e:
            logger.error(f"❌ Failed to create client {session_name}: {e}")
            return None
    
    async def initialize_forward_target(self):
        """Инициализация получателя пересылки"""
        if not self.clients:
            logger.error("❌ No clients available to resolve forward target")
            return False
        
        # Используем первый доступный клиент для поиска получателя
        first_client = list(self.clients.values())[0]
        
        # Проверяем подключение клиента
        if not first_client.is_connected():
            logger.error("❌ First client is disconnected, cannot resolve forward target")
            return False
        
        # Пробуем разрешить с @ и без @
        usernames_to_try = [
            self.forward_to_username if self.forward_to_username.startswith('@') else f"@{self.forward_to_username}",
            self.forward_to_username if not self.forward_to_username.startswith('@') else self.forward_to_username[1:]
        ]
        
        for username in usernames_to_try:
            try:
                self.forward_to_entity = await first_client.get_entity(username)
                logger.info(f"✅ Forward target resolved: {username}")
                return True
            except UsernameNotOccupiedError:
                logger.warning(f"⚠️ Username {username} not found, trying next variant...")
                continue
            except FloodWaitError as e:
                wait_seconds = e.seconds
                wait_minutes = wait_seconds // 60
                wait_hours = wait_minutes // 60
                if wait_hours > 0:
                    logger.warning(f"⚠️ FloodWait при разрешении {username}: {wait_hours}ч {wait_minutes % 60}м, попробуем позже")
                else:
                    logger.warning(f"⚠️ FloodWait при разрешении {username}: {wait_minutes}м, попробуем позже")
                # FloodWait - не критическая ошибка, попробуем позже
                return False
            except RPCError as e:
                error_msg = str(e)
                if "disconnected" in error_msg.lower() or "not connected" in error_msg.lower() or "Cannot send requests" in error_msg:
                    logger.warning(f"⚠️ Client disconnected при разрешении {username}: {error_msg}")
                    return False
                # Другие RPC ошибки - пробуем следующий вариант
                logger.warning(f"⚠️ RPC Error при разрешении {username}: {error_msg}, trying next variant...")
                continue
            except Exception as e:
                error_msg = str(e)
                if "disconnected" in error_msg.lower() or "not connected" in error_msg.lower() or "Cannot send requests" in error_msg:
                    logger.warning(f"⚠️ Client disconnected при разрешении {username}: {error_msg}")
                    return False
                # Другие ошибки - пробуем следующий вариант
                logger.warning(f"⚠️ Error resolving {username}: {error_msg}, trying next variant...")
                continue
        
        logger.error(f"❌ Failed to resolve forward target @{self.forward_to_username} (tried all variants)")
        return False
    
    def recently_responded(self, account_name: str, user_id: int) -> bool:
        """Проверка, не отвечали ли мы недавно (избежание дублей)"""
        key = (account_name, user_id)
        now = datetime.utcnow()
        
        if key in self.recent_responses:
            last_response_time = self.recent_responses[key]
            if (now - last_response_time).total_seconds() < self.recent_window:
                return True
        
        # Очищаем старые записи
        self.recent_responses = {
            k: v for k, v in self.recent_responses.items()
            if (now - v).total_seconds() < self.recent_window
        }
        
        return False
    
    def mark_responded(self, account_name: str, user_id: int):
        """Пометить, что мы ответили пользователю"""
        self.recent_responses[(account_name, user_id)] = datetime.utcnow()
    
    async def get_conversation_history(self, client: TelegramClient, user: User, limit: int = 10) -> List[Dict]:
        """
        Получить историю переписки с пользователем
        
        Args:
            client: Telegram клиент
            user: Пользователь
            limit: Максимум сообщений
        
        Returns:
            Список сообщений в формате [{"role": "user", "content": "..."}, ...]
        """
        try:
            messages = []
            async for message in client.iter_messages(user, limit=limit, reverse=True):
                if not message.text:
                    continue
                
                # Определяем роль (user или assistant)
                if message.out:
                    role = "assistant"
                else:
                    role = "user"
                
                messages.append({
                    "role": role,
                    "content": message.text
                })
            
            return messages
            
        except Exception as e:
            logger.warning(f"  ⚠️ Error getting conversation history: {e}")
            return []
    
    async def check_if_active_conversation(self, client: TelegramClient, user: User) -> bool:
        """
        Проверка, идет ли активная переписка (есть ли ответы пользователя после нашего последнего сообщения)
        
        Args:
            client: Telegram клиент
            user: Пользователь
        
        Returns:
            True если идет переписка (пользователь уже ответил после нашего последнего сообщения)
        """
        try:
            # Получаем последние 10 сообщений
            messages = []
            async for message in client.iter_messages(user, limit=10):
                messages.append(message)
            
            if not messages:
                return False
            
            # Ищем наше последнее сообщение (out=True)
            our_last_message_index = None
            for i, msg in enumerate(messages):
                if msg.out:  # Наше сообщение
                    our_last_message_index = i
                    break
            
            # Если нет наших сообщений - это первое сообщение, не переписка
            if our_last_message_index is None:
                return False
            
            # Проверяем, есть ли сообщения от пользователя ПОСЛЕ нашего последнего
            # (сообщения с меньшим индексом = более новые)
            for i in range(our_last_message_index):
                if not messages[i].out:  # Сообщение от пользователя
                    # Есть ответ пользователя после нашего последнего сообщения
                    logger.debug(f"  💬 Found user reply after our last message (message {i} of {len(messages)})")
                    return True
            
            # Нет ответов пользователя после нашего последнего сообщения
            return False
            
        except Exception as e:
            logger.warning(f"  ⚠️ Error checking conversation status: {e}")
            # В случае ошибки считаем, что переписки нет (отвечаем как обычно)
            return False
    
    async def simulate_typing(self, client: TelegramClient, user: User):
        """
        Имитация печатания (typing simulation)
        
        Args:
            client: Telegram клиент
            user: Пользователь
        """
        try:
            # Задержка перед началом печатания
            await asyncio.sleep(random.uniform(1, 3))
            
            # Показываем статус "печатает"
            await client.send_read_acknowledge(user)
            
            # Имитируем печатание
            delay = random.uniform(self.typing_delay_min, self.typing_delay_max)
            await asyncio.sleep(delay)
            
        except Exception as e:
            logger.debug(f"  ⚠️ Error simulating typing: {e}")
            # Если не получилось, просто ждем
            await asyncio.sleep(random.uniform(self.typing_delay_min, self.typing_delay_max))
    
    def should_forward_to_owner(self, message_text: str) -> bool:
        """
        Проверка, нужно ли перевести на владельца (@grishkoff)
        
        Args:
            message_text: Текст сообщения
        
        Returns:
            True если нужно перевести
        """
        forward_keywords = self.secretary_config.get('target_action', {}).get('forward_keywords', [])
        message_lower = message_text.lower()
        
        for keyword in forward_keywords:
            if keyword in message_lower:
                return True
        
        return False
    
    async def forward_message_to_owner(
        self,
        client: TelegramClient,
        event: NewMessage.Event,
        account_name: str,
        username: str,
        user_id: int,
        message_text: str,
        has_media: bool
    ):
        """
        Пересылка сообщения на @grishkoff
        
        Args:
            client: Telegram клиент
            event: Событие сообщения
            account_name: Имя аккаунта
            username: Username отправителя
            user_id: ID отправителя
            message_text: Текст сообщения
            has_media: Есть ли медиа
        """
        try:
            # Инициализируем получателя
            if not await self.initialize_forward_target():
                logger.error("  ❌ Cannot forward - forward target not initialized")
                return
            
            # Формируем префикс с информацией об отправителе
            forward_prefix = (
                f"📬 Сообщение для @{self.forward_to_username}\n\n"
                f"От: @{username} (ID: {user_id})\n"
                f"Аккаунт: {account_name}\n"
                f"{'Медиа: ✅' if has_media else ''}\n"
                f"{'─' * 40}\n\n"
            )
            
            # Отправляем префикс с информацией
            try:
                await client.send_message(
                    self.forward_to_entity,
                    forward_prefix,
                    silent=False
                )
                
                # Пересылаем оригинальное сообщение
                await client.forward_messages(
                    self.forward_to_entity,
                    event.message,
                    silent=True  # Без звука, так как уже отправили префикс
                )
                
                logger.info(f"  ✅ Forwarded message from @{username} to @{self.forward_to_username}")
                
            except FloodWaitError as e:
                logger.warning(f"  ⏳ FloodWait {e.seconds} seconds for forwarding")
                await asyncio.sleep(min(e.seconds, 300))
            except Exception as e:
                logger.error(f"  ❌ Error forwarding message: {e}", exc_info=True)
                
        except Exception as e:
            logger.error(f"  ❌ Error in forward_message_to_owner: {e}", exc_info=True)
    
    async def handle_message(self, event: NewMessage.Event, account_name: str, client: TelegramClient):
        """
        Обработка входящего сообщения: ответ через GPT или пересылка на @grishkoff
        
        Args:
            event: Событие нового сообщения
            account_name: Имя аккаунта
            client: Telegram клиент
        """
        try:
            # Получаем информацию о пользователе
            sender = await event.get_sender()
            
            if not sender:
                return
            
            # Проверяем, что это личное сообщение (не группа)
            if not isinstance(sender, User):
                return
            
            # Проверяем, что это не бот
            if getattr(sender, 'bot', False):
                logger.debug(f"  ⏭️ Skipping message from bot: {sender.id}")
                return
            
            user_id = sender.id
            username = getattr(sender, 'username', None) or f"ID{user_id}"
            message_text = event.message.text or ""
            has_media = bool(event.message.media)
            
            # Проверяем, не отвечали ли мы недавно (избежание дублей)
            if self.recently_responded(account_name, user_id):
                logger.debug(f"  ⏭️ Skipping - recently responded to @{username}")
                return
            
            logger.info(f"  📨 New DM from @{username} via {account_name}: {message_text[:100]}...")
            
            # Проверяем, идет ли уже активная переписка
            is_active_conversation = await self.check_if_active_conversation(client, sender)
            
            if is_active_conversation:
                # Идет переписка - только пересылаем, не отвечаем автоматически
                logger.info(f"  💬 Active conversation detected with @{username} - forwarding only, no auto-reply")
                await self.forward_message_to_owner(
                    client=client,
                    event=event,
                    account_name=account_name,
                    username=username,
                    user_id=user_id,
                    message_text=message_text,
                    has_media=has_media
                )
                return
            
            # Проверяем, нужно ли сразу переводить на владельца (просмотр, торг, телефон)
            if self.should_forward_to_owner(message_text):
                logger.info(f"  🔄 Forward trigger detected in message from @{username} - forwarding to @{self.forward_to_username}")
                await self.forward_message_to_owner(
                    client=client,
                    event=event,
                    account_name=account_name,
                    username=username,
                    user_id=user_id,
                    message_text=message_text,
                    has_media=has_media
                )
                return
            
            # Нет активной переписки и нет триггеров - отвечаем через GPT
            if not self.gpt_handler:
                logger.warning(f"  ⚠️ GPT Handler not available, forwarding message")
                await self.forward_message_to_owner(
                    client=client,
                    event=event,
                    account_name=account_name,
                    username=username,
                    user_id=user_id,
                    message_text=message_text,
                    has_media=has_media
                )
                return
            
            # Получаем историю переписки
            conversation_history = await self.get_conversation_history(client, sender, limit=self.secretary_config.get('conversation_history_limit', 10))
            
            # Генерируем ответ через GPT
            response_text = await self.gpt_handler.generate_response(
                incoming_message=message_text,
                conversation_history=conversation_history,
                user_info={"id": user_id, "username": username}
            )
            
            # Имитируем печатание
            await self.simulate_typing(client, sender)
            
            # Отправляем ответ
            try:
                await event.reply(response_text)
                logger.info(f"  ✅ Replied to @{username}: {response_text[:100]}...")
                
                # Помечаем, что мы ответили
                self.mark_responded(account_name, user_id)
                
            except FloodWaitError as e:
                logger.warning(f"  ⏳ FloodWait {e.seconds} seconds for @{username}")
                await asyncio.sleep(min(e.seconds, 300))
            except Exception as e:
                logger.error(f"  ❌ Error sending reply: {e}", exc_info=True)
            
        except Exception as e:
            logger.error(f"  ❌ Error handling message: {e}", exc_info=True)
    
    def setup_handlers(self):
        """Настройка обработчиков событий для всех клиентов"""
        for account_name, client in self.clients.items():
            # Создаем замыкание для правильного захвата переменных
            acc_name = account_name
            cli = client
            
            @client.on(NewMessage(incoming=True, func=lambda e: e.is_private))
            async def handler(event, account=acc_name, client_handler=cli):
                await self.handle_message(event, account, client_handler)
            
            logger.info(f"  ✅ Registered handler for {account_name}")
        
        logger.info(f"✅ Registered handlers for {len(self.clients)} accounts")
    
    async def initialize(self):
        """Инициализация всех компонентов"""
        # Загружаем конфигурацию ниши (cars)
        if GPT_AVAILABLE:
            try:
                self.config_loader = ConfigLoader()
                self.niche_config = self.config_loader.load_niche_config(niche_name='cars')
                logger.info(f"📋 Loaded niche config: {self.niche_config.get('display_name', 'cars')}")
                
                # Загружаем конфигурацию секретаря
                self.secretary_config = self.niche_config.get('secretary', {})
                
                # Загружаем настройки задержек
                self.typing_delay_min = self.secretary_config.get('typing_delay_min', 5)
                self.typing_delay_max = self.secretary_config.get('typing_delay_max', 15)
                
                # Инициализация GPT обработчика
                api_key = os.getenv('OPENAI_API_KEY')
                if api_key:
                    self.gpt_handler = GPTHandler(api_key=api_key, niche_config=self.niche_config)
                    logger.info("✅ GPT Handler initialized")
                else:
                    logger.warning("⚠️ OPENAI_API_KEY not found, GPT responses will be disabled")
                    self.gpt_handler = None
            except Exception as e:
                logger.error(f"❌ Failed to load config or GPT handler: {e}")
                self.gpt_handler = None
        else:
            logger.warning("⚠️ GPT modules not available, GPT responses will be disabled")
            self.gpt_handler = None
        
        # Загружаем аккаунты
        if not self.load_accounts():
            raise ValueError("Failed to load accounts")
        
        # Создаем клиенты
        logger.info("🔄 Creating clients...")
        for account in self.accounts:
            await self.create_client(account)
        
        if not self.clients:
            raise ValueError("No clients created")
        
        logger.info(f"✅ Initialized {len(self.clients)} clients")
        
        # Инициализируем получателя пересылки
        # Пробуем разрешить получателя, но не падаем с ошибкой, если не получается (может быть FloodWait)
        if not await self.initialize_forward_target():
            logger.warning(f"⚠️ Could not resolve forward target @{self.forward_to_username} during initialization")
            logger.warning(f"⚠️ Will retry when first message arrives (may be FloodWait)")
            # Не выбрасываем ошибку - попробуем разрешить позже при получении первого сообщения
        
        # Настраиваем обработчики
        self.setup_handlers()
    
    async def run(self):
        """Основной цикл работы"""
        await self.initialize()
        
        logger.info("=" * 80)
        logger.info("🚀 LEXUS SECRETARY - Умный помощник по продаже автомобиля")
        logger.info("=" * 80)
        logger.info(f"📋 Monitoring DMs for {len(self.clients)} accounts")
        logger.info(f"🤖 GPT Handler: {'✅ Enabled' if self.gpt_handler else '❌ Disabled'}")
        logger.info(f"📤 Forwarding to: @{self.forward_to_username}")
        logger.info("=" * 80)
        logger.info("🔄 Waiting for incoming messages...")
        logger.info("   Service is running. Press Ctrl+C to stop.")
        logger.info("=" * 80)
        
        # Запускаем все клиенты и ждем события
        try:
            tasks = []
            for account_name, client in self.clients.items():
                async def keep_alive(cli=client, name=account_name):
                    try:
                        await cli.run_until_disconnected()
                    except Exception as e:
                        logger.error(f"❌ Client {name} disconnected: {e}")
                
                task = asyncio.create_task(keep_alive())
                tasks.append(task)
            
            await asyncio.gather(*tasks, return_exceptions=True)
            
        except KeyboardInterrupt:
            logger.info("🛑 Shutting down...")
        except Exception as e:
            logger.error(f"❌ Error in main loop: {e}", exc_info=True)
        finally:
            # Отключаем все клиенты
            for name, client in self.clients.items():
                try:
                    if client.is_connected():
                        await client.disconnect()
                except:
                    pass


async def main():
    """Основная функция запуска"""
    secretary = LexusSecretary(forward_to_username='grishkoff')
    
    try:
        await secretary.run()
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down...")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
