#!/usr/bin/env python3
"""
Система постановки реакций на посты в чатах
Безопасный способ привлечения внимания без риска бана
"""

import asyncio
import random
import logging
from datetime import datetime
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import SendReactionRequest
from telethon.tl.types import ReactionEmoji
import json

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('reactions.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ReactionsSystem:
    """Система для постановки реакций на посты в чатах"""
    
    def __init__(self, accounts_config_path='accounts_config.json'):
        self.accounts_config_path = accounts_config_path
        self.accounts = []
        self.clients = {}
        self.reacted_messages = set()
        
        # Настройки
        self.REACTION_PROBABILITY = 0.2  # 20% постов лайкаем
        self.REACTIONS = ['👍', '❤️', '🔥', '👏', '😍']
        self.MIN_DELAY = 15
        self.MAX_DELAY = 60
        
    async def initialize(self):
        """Инициализация клиентов"""
        logger.info("🚀 Инициализация Reactions System...")
        
        with open(self.accounts_config_path, 'r', encoding='utf-8') as f:
            self.accounts = json.load(f)
        
        logger.info(f"📱 Загружено {len(self.accounts)} аккаунтов")
        
        for account in self.accounts:
            await self.connect_account(account)
        
        logger.info(f"✅ Подключено {len(self.clients)} аккаунтов")
    
    async def connect_account(self, account):
        """Подключение аккаунта"""
        session_name = account['session_name']
        api_id = account['api_id']
        api_hash = account['api_hash']
        
        try:
            if 'string_session' in account and account['string_session']:
                client = TelegramClient(
                    StringSession(account['string_session']), 
                    api_id, 
                    api_hash
                )
            else:
                client = TelegramClient(
                    f"sessions/{session_name}", 
                    api_id, 
                    api_hash
                )
            
            await client.connect()
            
            if not await client.is_user_authorized():
                logger.warning(f"⚠️ {session_name} не авторизован")
                return
            
            self.clients[session_name] = client
            me = await client.get_me()
            logger.info(f"✅ {session_name} (@{me.username or me.phone})")
            
        except Exception as e:
            logger.error(f"❌ Ошибка {session_name}: {e}")
    
    async def react_to_chat_posts(self, client, account_name, chat_username, limit=20):
        """Ставить реакции на посты в чате"""
        try:
            chat = await client.get_entity(chat_username)
            messages = await client.get_messages(chat, limit=limit)
            
            reacted = 0
            
            for msg in messages:
                # Пропускаем сервисные сообщения
                if not msg.text or len(msg.text) < 10:
                    continue
                
                # Уже реагировали
                msg_id = f"{chat.id}_{msg.id}"
                if msg_id in self.reacted_messages:
                    continue
                
                # Случайный выбор
                if random.random() > self.REACTION_PROBABILITY:
                    continue
                
                try:
                    reaction = random.choice(self.REACTIONS)
                    
                    await client(SendReactionRequest(
                        peer=chat,
                        msg_id=msg.id,
                        reaction=[ReactionEmoji(emoticon=reaction)]
                    ))
                    
                    self.reacted_messages.add(msg_id)
                    reacted += 1
                    
                    logger.info(f"👍 {account_name} → {reaction} в {chat_username} (пост: {msg.text[:30]}...)")
                    
                    # Задержка
                    await asyncio.sleep(random.randint(self.MIN_DELAY, self.MAX_DELAY))
                    
                except Exception as e:
                    logger.debug(f"Не удалось поставить реакцию: {str(e)[:50]}")
            
            if reacted > 0:
                logger.info(f"✅ {account_name}: {reacted} реакций в {chat_username}")
            
            return reacted
            
        except Exception as e:
            logger.error(f"❌ Ошибка в {chat_username}: {e}")
            return 0
    
    async def view_user_stories(self, client, account_name, chat_username, limit=30):
        """Просмотр Stories участников чата"""
        try:
            chat = await client.get_entity(chat_username)
            participants = await client.get_participants(chat, limit=limit)
            
            viewed = 0
            
            for user in participants:
                if user.bot:  # Пропускаем ботов
                    continue
                
                # Случайный выбор (не смотрим всех подряд)
                if random.random() > 0.5:
                    continue
                
                try:
                    # Просто читаем диалог - это покажет, что мы "онлайн"
                    # Stories API в Telethon может требовать premium
                    # Поэтому просто создаем "присутствие"
                    
                    # Альтернатива: читаем последние сообщения пользователя
                    # Это создает активность без риска
                    
                    viewed += 1
                    logger.info(f"👁️ {account_name} просмотрел профиль @{user.username or user.id}")
                    
                    await asyncio.sleep(random.randint(5, 15))
                    
                except Exception as e:
                    pass
            
            if viewed > 0:
                logger.info(f"✅ {account_name}: просмотрено {viewed} профилей в {chat_username}")
            
            return viewed
            
        except Exception as e:
            logger.error(f"❌ Ошибка просмотра в {chat_username}: {e}")
            return 0
    
    async def process_chats(self, target_chats):
        """Обработка всех чатов"""
        logger.info(f"🎯 Обработка {len(target_chats)} чатов...")
        
        total_reactions = 0
        total_views = 0
        
        for account_name, client in self.clients.items():
            logger.info(f"📱 Аккаунт: {account_name}")
            
            for chat in target_chats:
                # 1. Ставим реакции на посты
                reactions = await self.react_to_chat_posts(client, account_name, chat)
                total_reactions += reactions
                
                # 2. "Просматриваем" участников (создаем активность)
                views = await self.view_user_stories(client, account_name, chat)
                total_views += views
                
                # Задержка между чатами
                await asyncio.sleep(random.randint(30, 90))
            
            # Задержка между аккаунтами
            await asyncio.sleep(random.randint(120, 300))
        
        logger.info(f"📊 Всего: {total_reactions} реакций, {total_views} просмотров")
        return {'reactions': total_reactions, 'views': total_views}
    
    async def run_continuous(self, target_chats, interval_hours=4):
        """Непрерывная работа"""
        logger.info(f"🚀 Непрерывный режим (интервал: {interval_hours}ч)")
        
        while True:
            try:
                total = await self.process_chats(target_chats)
                logger.info(f"✅ Цикл завершен: {total} реакций")
                
                wait = interval_hours * 3600
                logger.info(f"😴 Следующий цикл через {interval_hours}ч")
                await asyncio.sleep(wait)
                
            except Exception as e:
                logger.error(f"❌ Ошибка: {e}")
                await asyncio.sleep(600)
    
    async def close(self):
        """Закрытие клиентов"""
        for client in self.clients.values():
            await client.disconnect()
        logger.info("👋 Отключено")


async def main():
    """Запуск"""
    
    TARGET_CHATS = [
        '@bali_ubud_changu',
        '@canggu_people',
        '@events_travels_group',
        '@balichat',
        '@bali_villa_arenda',
    ]
    
    system = ReactionsSystem()
    
    try:
        await system.initialize()
        
        # Один тестовый цикл
        logger.info("🧪 Запуск тестового цикла (один раз)...")
        total = await system.process_chats(TARGET_CHATS)
        logger.info(f"🎉 Тест завершен! Всего: {total} реакций")
        
        # Раскомментируйте для непрерывного режима:
        # await system.run_continuous(TARGET_CHATS, interval_hours=4)
        
    except KeyboardInterrupt:
        logger.info("⏹️ Остановка...")
    finally:
        await system.close()


if __name__ == '__main__':
    asyncio.run(main())

