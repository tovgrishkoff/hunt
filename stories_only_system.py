#!/usr/bin/env python3
"""
Система ТОЛЬКО для просмотра Stories
Работает параллельно с основной системой постинга без конфликтов
"""

import asyncio
import random
import json
import logging
import os
import sqlite3
from datetime import datetime, time as dtime
from pathlib import Path
import pytz
from telethon import TelegramClient
from telethon.tl.functions.stories import GetPeerStoriesRequest, SendReactionRequest as SendStoryReactionRequest
from telethon.tl.types import ReactionEmoji

LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(parents=True, exist_ok=True)
STORIES_ONLY_LOG_FILE = LOGS_DIR / "stories_only_system.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(STORIES_ONLY_LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class StoriesOnlySystem:
    """Система только для просмотра Stories (не мешает постингу)"""
    
    def __init__(self):
        self.accounts = []
        self.clients = {}
        
        # Настройки для Stories
        self.stories_enabled = True
        self.story_reaction_probability = 0.3
        self.story_reactions = ['❤️', '🔥', '👍', '😍', '💯']
        self.viewed_stories_today = set()
        self.posting_guard_minutes = 30
        
        # Слоты постинга (НЕ трогаем Stories в это время!)
        self.posting_slots = [
            dtime(6, 0),   # 06:00 утро
            dtime(12, 0),  # 12:00 день
            dtime(15, 0),  # 15:00 послеобед
            dtime(18, 0),  # 18:00 вечер
            dtime(21, 0),  # 21:00 ночь
        ]
        
        logger.info("✨ Инициализация системы просмотра Stories")
    
    def load_accounts(self, config_file='accounts_config.json'):
        """Загрузка конфигурации аккаунтов"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                self.accounts = json.load(f)
            logger.info(f"✅ Загружено {len(self.accounts)} аккаунтов")
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки конфигурации: {e}")
    
    def enable_wal_mode(self, session_name):
        """Включение WAL mode для SQLite сессии"""
        session_file = f"sessions_stories/{session_name}.session"
        if Path(session_file).exists():
            try:
                conn = sqlite3.connect(session_file)
                conn.execute('PRAGMA journal_mode=WAL')
                conn.execute('PRAGMA busy_timeout=30000')
                conn.close()
                logger.info(f"✅ WAL mode включен для {session_name}")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось включить WAL mode для {session_name}: {e}")
    
    def parse_proxy(self, proxy_config):
        """Парсинг прокси в формат для Telethon"""
        if not proxy_config:
            return None
        
        if isinstance(proxy_config, str):
            try:
                from urllib.parse import urlparse
                parsed = urlparse(proxy_config)
                proxy_type = parsed.scheme.lower()
                host = parsed.hostname
                port = parsed.port or (8080 if proxy_type in ['http', 'https'] else 1080)
                username = parsed.username
                password = parsed.password
                
                if not host or not port:
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
            except Exception as e:
                logger.warning(f"⚠️ Ошибка парсинга прокси: {e}")
                return None
        
        return None
    
    async def initialize_clients(self):
        """Инициализация клиентов через StringSession или файловую сессию"""
        from telethon.sessions import StringSession
        
        for account in self.accounts:
            try:
                api_id = int(account['api_id'])
                session_name = account['session_name']
                string_session = account.get('string_session')
                proxy_config = account.get('proxy')
                
                # Парсим прокси если указан
                proxy = None
                if proxy_config:
                    proxy = self.parse_proxy(proxy_config)
                    if proxy:
                        proxy_host = proxy.get('addr', 'unknown') if isinstance(proxy, dict) else 'unknown'
                        proxy_port = proxy.get('port', 'unknown') if isinstance(proxy, dict) else 'unknown'
                        logger.info(f"🔗 Используем прокси для {session_name}: {proxy_host}:{proxy_port}")
                    else:
                        logger.warning(f"⚠️ Не удалось распарсить прокси для {session_name}, продолжаем без прокси")
                
                client = None
                
                # Пробуем использовать StringSession, если есть (проверяем на None и пустую строку)
                if string_session and string_session != 'null' and string_session.strip():
                    # Используем StringSession напрямую
                    client = TelegramClient(
                        StringSession(string_session.strip()), 
                        api_id, 
                        account['api_hash'],
                        proxy=proxy
                    )
                else:
                    # Если нет string_session, пробуем использовать файловую сессию
                    session_file = f"sessions_stories/stories_{session_name}.session"
                    if os.path.exists(session_file):
                        logger.info(f"📁 Используем файловую сессию для {session_name}")
                        client = TelegramClient(session_file, api_id, account['api_hash'], proxy=proxy)
                    else:
                        logger.warning(f"⚠️ Нет string_session и файловой сессии для {session_name}")
                        continue
                
                if client is None:
                    logger.warning(f"⚠️ Не удалось создать клиент для {session_name}")
                    continue
                
                await client.connect()
                
                # Проверяем авторизацию
                if not await client.is_user_authorized():
                    logger.warning(f"⚠️ {session_name} не авторизован")
                    await client.disconnect()
                    continue
                
                self.clients[account['session_name']] = client
                
                try:
                    me = await client.get_me()
                    username = getattr(me, 'username', 'No username')
                    logger.info(f"✅ Клиент {account['session_name']} (@{username}) готов")
                except Exception:
                    logger.info(f"✅ Клиент {account['session_name']} подключен")
                    
            except Exception as e:
                logger.error(f"❌ Ошибка инициализации {account['session_name']}: {e}")
    
    def is_posting_time(self):
        """Проверка, не время ли постинга (избегаем конфликтов)"""
        jakarta_tz = pytz.timezone('Asia/Jakarta')
        now = datetime.now(jakarta_tz)
        current_time = now.time()
        
        # Проверяем, не в пределах ±45 минут от слота постинга
        for slot in self.posting_slots:
            slot_minutes = slot.hour * 60 + slot.minute
            current_minutes = current_time.hour * 60 + current_time.minute
            
            if abs(slot_minutes - current_minutes) <= self.posting_guard_minutes:
                return True
        
        return False
    
    async def get_users_from_groups(self, client, account_name):
        """Получить участников из групп (только те, где нет бана)"""
        users = []
        
        # Целевые группы (те же, где постим)
        target_groups = [
            '@bali_ubud_changu',
            '@canggu_people',
            '@events_travels_group',
            '@balichat',
            '@bali_villa_arenda',
            '@mybalitrips',
            '@baliforum',
        ]
        
        for group in target_groups:
            try:
                # Проверяем подключение перед запросом
                if not client.is_connected():
                    if not await self.check_and_reconnect(client, account_name):
                        continue
                
                chat = await client.get_entity(group)
                # Получаем участников (небольшая выборка)
                participants = await client.get_participants(chat, limit=30)
                
                for user in participants:
                    if not getattr(user, 'bot', False) and hasattr(user, 'id'):
                        users.append(user)
                
                logger.info(f"✅ {account_name}: добавлено {len(participants)} из {group}")
                
                # Небольшая задержка между группами
                await asyncio.sleep(random.randint(2, 5))
                
            except Exception as e:
                # Если забанен или ошибка - пропускаем эту группу
                logger.debug(f"⚠️ {account_name}: пропуск {group} ({str(e)[:50]})")
                continue
        
        return users
    
    async def check_and_reconnect(self, client, account_name):
        """Проверка подключения и переподключение при необходимости"""
        try:
            if not client.is_connected():
                logger.warning(f"⚠️ {account_name}: клиент отключен, переподключаю...")
                await client.connect()
                if await client.is_user_authorized():
                    logger.info(f"✅ {account_name}: переподключен успешно")
                    return True
                else:
                    logger.error(f"❌ {account_name}: не авторизован после переподключения")
                    return False
            return True
        except Exception as e:
            logger.error(f"❌ {account_name}: ошибка проверки подключения: {e}")
            # Пробуем переподключиться
            try:
                await client.disconnect()
                await asyncio.sleep(2)
                await client.connect()
                if await client.is_user_authorized():
                    logger.info(f"✅ {account_name}: переподключен после ошибки")
                    return True
            except Exception as reconnect_error:
                logger.error(f"❌ {account_name}: не удалось переподключиться: {reconnect_error}")
            return False
    
    async def get_contacts_and_dialogs(self, client, account_name):
        """Получить список контактов из диалогов И участников групп"""
        users_to_check = []
        
        # Проверяем подключение перед началом работы
        if not await self.check_and_reconnect(client, account_name):
            return []
        
        try:
            # 1. Собираем контакты из диалогов
            logger.info(f"📱 {account_name}: собираю контакты из диалогов...")
            dialogs = await client.get_dialogs(limit=300)  # Увеличили с 100 до 300
            
            for dialog in dialogs:
                entity = dialog.entity
                if hasattr(entity, 'id') and hasattr(entity, 'first_name'):
                    if not getattr(entity, 'bot', False):
                        users_to_check.append(entity)
            
            logger.info(f"✅ {account_name}: нашел {len(users_to_check)} из диалогов")
            
            # 2. Добавляем участников из групп
            logger.info(f"🔍 {account_name}: собираю участников из групп...")
            group_users = await self.get_users_from_groups(client, account_name)
            
            # Объединяем, убирая дубликаты по ID
            existing_ids = {user.id for user in users_to_check}
            for user in group_users:
                if user.id not in existing_ids:
                    users_to_check.append(user)
                    existing_ids.add(user.id)
            
            logger.info(f"✅ {account_name}: ИТОГО {len(users_to_check)} человек (диалоги + группы)")
            return users_to_check
            
        except Exception as e:
            error_msg = str(e)
            # Если ошибка отключения - пробуем переподключиться
            if "disconnected" in error_msg.lower() or "not connected" in error_msg.lower():
                logger.warning(f"⚠️ {account_name}: клиент отключен, пробую переподключиться...")
                if await self.check_and_reconnect(client, account_name):
                    # Пробуем еще раз после переподключения
                    try:
                        dialogs = await client.get_dialogs(limit=300)
                        for dialog in dialogs:
                            entity = dialog.entity
                            if hasattr(entity, 'id') and hasattr(entity, 'first_name'):
                                if not getattr(entity, 'bot', False):
                                    users_to_check.append(entity)
                        logger.info(f"✅ {account_name}: получено {len(users_to_check)} контактов после переподключения")
                        return users_to_check
                    except Exception as retry_error:
                        logger.error(f"❌ {account_name}: ошибка после переподключения: {retry_error}")
            
            logger.error(f"❌ Ошибка получения контактов для {account_name}: {e}")
            return []
    
    async def view_and_react_to_stories(self, client, account_name):
        """Просмотр Stories контактов"""
        # Проверяем подключение перед началом работы
        if not await self.check_and_reconnect(client, account_name):
            logger.warning(f"⚠️ {account_name}: пропускаем цикл из-за проблем с подключением")
            return 0, 0
        
        try:
            users = await self.get_contacts_and_dialogs(client, account_name)
            
            if not users:
                logger.info(f"⚠️ {account_name}: нет контактов для просмотра Stories")
                return 0, 0
            
            stories_viewed = 0
            reactions_added = 0
            
            random.shuffle(users)
            # Увеличили с 20 до 50 человек за цикл
            selected_users = users[:min(50, len(users))]
            
            logger.info(f"👁️ {account_name}: проверяю Stories у {len(selected_users)} человек...")
            
            for user in selected_users:
                try:
                    # Проверяем подключение перед каждым запросом
                    if not client.is_connected():
                        if not await self.check_and_reconnect(client, account_name):
                            break  # Выходим из цикла, если не удалось переподключиться
                    
                    result = await client(GetPeerStoriesRequest(peer=user))
                    
                    if not result or not hasattr(result, 'stories'):
                        continue
                    
                    peer_stories = result.stories
                    if not hasattr(peer_stories, 'stories') or not peer_stories.stories:
                        continue
                    
                    for story in peer_stories.stories:
                        story_key = f"{user.id}_{story.id}"
                        
                        if story_key in self.viewed_stories_today:
                            continue
                        
                        self.viewed_stories_today.add(story_key)
                        stories_viewed += 1
                        
                        username = getattr(user, 'username', None) or f"{getattr(user, 'first_name', 'User')}"
                        logger.info(f"👁️ {account_name} просмотрел Story @{username}")
                        
                        if random.random() <= self.story_reaction_probability:
                            reaction = random.choice(self.story_reactions)
                            
                            try:
                                # Проверяем подключение перед отправкой реакции
                                if not client.is_connected():
                                    if not await self.check_and_reconnect(client, account_name):
                                        continue
                                
                                await client(SendStoryReactionRequest(
                                    peer=user,
                                    story_id=story.id,
                                    reaction=ReactionEmoji(emoticon=reaction)
                                ))
                                
                                reactions_added += 1
                                logger.info(f"❤️ {account_name} → {reaction} на Story @{username}")
                                await asyncio.sleep(random.randint(10, 25))
                                
                            except Exception as e:
                                logger.debug(f"Не удалось поставить реакцию: {str(e)[:50]}")
                        
                        await asyncio.sleep(random.randint(5, 15))
                    
                except Exception:
                    pass
                
                await asyncio.sleep(random.randint(3, 8))
            
            if stories_viewed > 0:
                logger.info(f"📊 {account_name}: {stories_viewed} Stories, {reactions_added} реакций")
            
            return stories_viewed, reactions_added
            
        except Exception as e:
            logger.error(f"❌ Ошибка Stories для {account_name}: {e}")
            return 0, 0
    
    async def run_stories_cycle(self):
        """Цикл просмотра Stories"""
        if self.is_posting_time():
            logger.info("⏸️ Время постинга - пропускаем (не мешаем основной системе)")
            return
        
        logger.info("👁️ Запуск цикла просмотра Stories контактов...")
        
        total_stories = 0
        total_reactions = 0
        
        for account_name, client in list(self.clients.items()):  # Используем list() для безопасной итерации
            # Проверяем подключение перед началом работы с аккаунтом
            if not await self.check_and_reconnect(client, account_name):
                logger.warning(f"⚠️ {account_name}: пропускаем из-за проблем с подключением")
                continue
            
            logger.info(f"📱 {account_name} просматривает Stories...")
            
            stories, reactions = await self.view_and_react_to_stories(client, account_name)
            
            total_stories += stories
            total_reactions += reactions
            
            # Задержка между аккаунтами
            await asyncio.sleep(random.randint(120, 240))
        
        logger.info(f"✅ Цикл завершен: {total_stories} просмотров, {total_reactions} реакций")
        
        return total_stories, total_reactions
    
    async def run_schedule(self):
        """Расписание: Stories только между постингами"""
        logger.info("🚀 Запуск системы просмотра Stories")
        logger.info(f"⏸️ Не работает во время постинга: {[f'{s.hour:02d}:{s.minute:02d}' for s in self.posting_slots]}")
        
        while True:
            jakarta_tz = pytz.timezone('Asia/Jakarta')
            now = datetime.now(jakarta_tz)
            
            logger.info(f"\n⏰ Текущее время: {now.strftime('%H:%M:%S')}")
            
            if self.is_posting_time():
                logger.info("⏸️ Время постинга - ждем 15 минут...")
                await asyncio.sleep(900)  # Ждем 15 минут перед повторной проверкой
            else:
                logger.info("👁️ Запуск просмотра Stories...")
                
                try:
                    await self.run_stories_cycle()
                except Exception as e:
                    logger.error(f"❌ Ошибка: {e}")
                
                logger.info("😴 Следующий цикл через 2 часа")
                await asyncio.sleep(7200)  # 2 часа
            
            # Сброс статистики в полночь
            if now.hour == 0 and now.minute < 5:
                self.viewed_stories_today.clear()
                logger.info("🔄 Сброс дневной статистики")


async def main():
    """Запуск системы Stories"""
    print("\n" + "="*70)
    print("👁️ СИСТЕМА ПРОСМОТРА STORIES")
    print("="*70)
    print("\n📋 Режим работы:")
    print("   • Только Stories контактов")
    print("   • Не работает во время постинга (06:00, 12:00, 15:00, 18:00, 21:00)")
    print("   • Отдельные сессии (нет конфликтов с постингом)")
    print("   • Цикл каждые 2 часа между постингами\n")
    
    system = StoriesOnlySystem()
    
    try:
        system.load_accounts()
        await system.initialize_clients()
        
        logger.info(f"✅ Инициализировано {len(system.clients)} аккаунтов")
        
        await system.run_schedule()
        
    except KeyboardInterrupt:
        logger.info("\n⏹️ Остановка системы...")
    except Exception as e:
        logger.error(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        logger.info("👋 Завершение работы")


if __name__ == '__main__':
    asyncio.run(main())

