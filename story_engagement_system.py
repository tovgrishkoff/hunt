#!/usr/bin/env python3
"""
Система взаимодействия со Stories и постами в чатах
Безопасный способ привлечения внимания без риска бана
"""

import asyncio
import random
import logging
from datetime import datetime, timedelta
from telethon import TelegramClient
from telethon.tl.functions.stories import GetAllStoriesRequest, GetPeerStoriesRequest
from telethon.tl.functions.messages import SendReactionRequest
from telethon.tl.types import ReactionEmoji, InputPeerUser, InputPeerChannel
import json
from pathlib import Path

logs_dir = Path("logs")
logs_dir.mkdir(parents=True, exist_ok=True)
story_log_file = logs_dir / "story_engagement_system.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(story_log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class StoryEngagementSystem:
    """Система для просмотра Stories и постановки реакций"""
    
    def __init__(self, accounts_config_path='accounts_config.json'):
        self.accounts_config_path = accounts_config_path
        self.accounts = []
        self.clients = {}
        self.viewed_stories = set()  # Чтобы не смотреть одну историю дважды
        
        # Настройки поведения
        self.STORY_VIEW_PROBABILITY = 0.7  # 70% историй просматриваем
        self.STORY_REACTION_PROBABILITY = 0.3  # 30% просмотренных историй лайкаем
        self.POST_REACTION_PROBABILITY = 0.15  # 15% постов в чатах лайкаем
        
        # Доступные реакции для Stories и постов
        self.STORY_REACTIONS = ['❤️', '🔥', '👍', '😍', '💯']
        self.POST_REACTIONS = ['👍', '❤️', '🔥', '👏']
        
        # Задержки (секунды)
        self.MIN_DELAY_BETWEEN_VIEWS = 10
        self.MAX_DELAY_BETWEEN_VIEWS = 45
        self.MIN_DELAY_BETWEEN_REACTIONS = 15
        self.MAX_DELAY_BETWEEN_REACTIONS = 60
        
    async def initialize(self):
        """Инициализация клиентов"""
        logger.info("🚀 Инициализация Story Engagement System...")
        
        # Загружаем конфигурацию аккаунтов
        with open(self.accounts_config_path, 'r', encoding='utf-8') as f:
            self.accounts = json.load(f)
        
        logger.info(f"📱 Загружено {len(self.accounts)} аккаунтов")
        
        # Подключаем аккаунты
        for account in self.accounts:
            await self.connect_account(account)
    
    async def connect_account(self, account):
        """Подключение аккаунта к Telegram"""
        session_name = account['session_name']
        api_id = account['api_id']
        api_hash = account['api_hash']
        
        try:
            if 'string_session' in account and account['string_session']:
                from telethon.sessions import StringSession
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
                logger.warning(f"⚠️ Аккаунт {session_name} не авторизован!")
                return
            
            self.clients[session_name] = client
            me = await client.get_me()
            logger.info(f"✅ Подключен: {session_name} (@{me.username or me.phone})")
            
        except Exception as e:
            logger.error(f"❌ Ошибка подключения {session_name}: {e}")
    
    async def get_chat_participants(self, client, chat_username, limit=100):
        """Получить участников чата для просмотра их Stories"""
        try:
            chat = await client.get_entity(chat_username)
            participants = await client.get_participants(chat, limit=limit)
            logger.info(f"👥 Получено {len(participants)} участников из {chat_username}")
            return participants
        except Exception as e:
            logger.error(f"❌ Ошибка получения участников {chat_username}: {e}")
            return []
    
    async def view_user_stories(self, client, user, account_name):
        """Просмотр Stories конкретного пользователя"""
        try:
            # Пропускаем с вероятностью
            if random.random() > self.STORY_VIEW_PROBABILITY:
                return 0
            
            # Получаем Stories пользователя
            try:
                stories_result = await client(GetPeerStoriesRequest(peer=user))
                
                if not stories_result or not hasattr(stories_result, 'stories'):
                    return 0
                
                stories = stories_result.stories.stories if hasattr(stories_result.stories, 'stories') else []
                
                if not stories:
                    return 0
                
                viewed_count = 0
                
                for story in stories:
                    story_id = f"{user.id}_{story.id}"
                    
                    # Пропускаем уже просмотренные
                    if story_id in self.viewed_stories:
                        continue
                    
                    # Просматриваем Story (автоматически при получении)
                    self.viewed_stories.add(story_id)
                    viewed_count += 1
                    
                    logger.info(f"👁️ {account_name} просмотрел Story пользователя @{user.username or user.id}")
                    
                    # Ставим реакцию с вероятностью
                    if random.random() <= self.STORY_REACTION_PROBABILITY:
                        await self.react_to_story(client, user, story, account_name)
                    
                    # Задержка между просмотрами
                    await asyncio.sleep(random.randint(self.MIN_DELAY_BETWEEN_VIEWS, self.MAX_DELAY_BETWEEN_VIEWS))
                
                return viewed_count
                
            except Exception as e:
                # Stories могут быть недоступны - это нормально
                return 0
                
        except Exception as e:
            logger.debug(f"Пропуск Stories для {user.id}: {str(e)[:50]}")
            return 0
    
    async def react_to_story(self, client, user, story, account_name):
        """Поставить реакцию на Story"""
        try:
            reaction = random.choice(self.STORY_REACTIONS)
            
            await client(SendReactionRequest(
                peer=user,
                msg_id=story.id,
                reaction=[ReactionEmoji(emoticon=reaction)]
            ))
            
            logger.info(f"❤️ {account_name} поставил {reaction} на Story пользователя @{user.username or user.id}")
            
            # Задержка после реакции
            await asyncio.sleep(random.randint(self.MIN_DELAY_BETWEEN_REACTIONS, self.MAX_DELAY_BETWEEN_REACTIONS))
            
        except Exception as e:
            logger.debug(f"Не удалось поставить реакцию на Story: {str(e)[:50]}")
    
    async def react_to_chat_messages(self, client, chat_username, account_name, messages_limit=20):
        """Ставить реакции на сообщения в чате"""
        try:
            chat = await client.get_entity(chat_username)
            messages = await client.get_messages(chat, limit=messages_limit)
            
            reacted_count = 0
            
            for message in messages:
                # Пропускаем с вероятностью
                if random.random() > self.POST_REACTION_PROBABILITY:
                    continue
                
                # Пропускаем сервисные сообщения
                if not message.text:
                    continue
                
                try:
                    reaction = random.choice(self.POST_REACTIONS)
                    
                    await client(SendReactionRequest(
                        peer=chat,
                        msg_id=message.id,
                        reaction=[ReactionEmoji(emoticon=reaction)]
                    ))
                    
                    reacted_count += 1
                    logger.info(f"👍 {account_name} поставил {reaction} на пост в {chat_username}")
                    
                    # Задержка между реакциями
                    await asyncio.sleep(random.randint(self.MIN_DELAY_BETWEEN_REACTIONS, self.MAX_DELAY_BETWEEN_REACTIONS))
                    
                except Exception as e:
                    logger.debug(f"Не удалось поставить реакцию: {str(e)[:50]}")
            
            if reacted_count > 0:
                logger.info(f"✅ {account_name}: поставлено {reacted_count} реакций в {chat_username}")
            
            return reacted_count
            
        except Exception as e:
            logger.error(f"❌ Ошибка реакций в {chat_username}: {e}")
            return 0
    
    async def process_chat(self, client, account_name, chat_username):
        """Обработка одного чата: Stories участников + реакции на посты"""
        logger.info(f"🎯 {account_name} обрабатывает {chat_username}")
        
        # 1. Ставим реакции на посты в чате
        reactions_count = await self.react_to_chat_messages(client, chat_username, account_name)
        
        # 2. Получаем участников чата
        participants = await self.get_chat_participants(client, chat_username, limit=50)
        
        # 3. Просматриваем их Stories
        stories_viewed = 0
        for participant in participants[:20]:  # Обрабатываем первых 20 участников
            if participant.bot:  # Пропускаем ботов
                continue
            
            viewed = await self.view_user_stories(client, participant, account_name)
            stories_viewed += viewed
            
            # Небольшая задержка между пользователями
            if viewed > 0:
                await asyncio.sleep(random.randint(5, 15))
        
        logger.info(f"📊 {account_name} в {chat_username}: {reactions_count} реакций, {stories_viewed} Stories")
        
        return {
            'reactions': reactions_count,
            'stories_viewed': stories_viewed
        }
    
    async def run_engagement_cycle(self, target_chats):
        """Один цикл взаимодействия со всеми чатами"""
        logger.info("🔄 Запуск цикла взаимодействия...")
        
        total_reactions = 0
        total_stories = 0
        
        for account_name, client in self.clients.items():
            for chat in target_chats:
                try:
                    result = await self.process_chat(client, account_name, chat)
                    total_reactions += result['reactions']
                    total_stories += result['stories_viewed']
                    
                    # Задержка между чатами
                    await asyncio.sleep(random.randint(60, 120))
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка обработки {chat} аккаунтом {account_name}: {e}")
            
            # Большая задержка между аккаунтами
            await asyncio.sleep(random.randint(300, 600))
        
        logger.info(f"✅ Цикл завершен: {total_reactions} реакций, {total_stories} Stories просмотрено")
        
        return {
            'total_reactions': total_reactions,
            'total_stories': total_stories
        }
    
    async def run_continuous(self, target_chats, interval_hours=6):
        """Непрерывная работа с заданным интервалом"""
        logger.info(f"🚀 Запуск непрерывного режима (интервал: {interval_hours} часов)")
        
        while True:
            try:
                result = await self.run_engagement_cycle(target_chats)
                logger.info(f"📊 Статистика цикла: {result}")
                
                # Ждем до следующего цикла
                wait_seconds = interval_hours * 3600
                logger.info(f"😴 Следующий цикл через {interval_hours} часов")
                await asyncio.sleep(wait_seconds)
                
            except Exception as e:
                logger.error(f"❌ Ошибка в цикле: {e}")
                await asyncio.sleep(600)  # Ждем 10 минут при ошибке
    
    async def close(self):
        """Закрытие всех клиентов"""
        for client in self.clients.values():
            await client.disconnect()
        logger.info("👋 Все клиенты отключены")


async def main():
    """Основная функция запуска"""
    
    # Целевые чаты для мониторинга
    TARGET_CHATS = [
        '@bali_ubud_changu',
        '@canggu_people',
        '@events_travels_group',
        '@balichat',
        '@bali_villa_arenda',
        # Можно добавить больше чатов
    ]
    
    system = StoryEngagementSystem()
    
    try:
        await system.initialize()
        
        # Запуск в непрерывном режиме (каждые 6 часов)
        await system.run_continuous(TARGET_CHATS, interval_hours=6)
        
    except KeyboardInterrupt:
        logger.info("⏹️ Остановка системы...")
    finally:
        await system.close()


if __name__ == '__main__':
    asyncio.run(main())

