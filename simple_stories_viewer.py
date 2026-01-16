#!/usr/bin/env python3
"""
Простая система просмотра Stories и реакций
Работает даже с забаненными аккаунтами
"""

import asyncio
import random
import logging
import json
from datetime import datetime
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.stories import GetPeerStoriesRequest, SendReactionRequest as SendStoryReactionRequest
from telethon.tl.types import ReactionEmoji

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('stories_viewer.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class SimpleStoriesViewer:
    """Простой просмотрщик Stories"""
    
    def __init__(self):
        self.clients = {}
        self.viewed_stories = set()
        
        # Настройки
        self.REACTION_PROBABILITY = 0.3  # 30% Stories лайкаем
        self.REACTIONS = ['❤️', '🔥', '👍', '😍', '💯']
        
    async def connect_account(self, phone, api_id, api_hash, session_name, string_session=None):
        """Подключение одного аккаунта"""
        try:
            # Используем ФАЙЛ сессии вместо StringSession (надежнее)
            client = TelegramClient(f"sessions/{session_name}", api_id, api_hash)
            
            await client.connect()
            
            if not await client.is_user_authorized():
                logger.warning(f"⚠️ {session_name} не авторизован")
                await client.disconnect()
                return None
            
            me = await client.get_me()
            logger.info(f"✅ Подключен: {session_name} (@{me.username or phone})")
            
            return client
            
        except Exception as e:
            logger.error(f"❌ Ошибка подключения {session_name}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def get_chat_members(self, client, chat_username, limit=50):
        """Получить участников чата"""
        try:
            chat = await client.get_entity(chat_username)
            members = await client.get_participants(chat, limit=limit)
            logger.info(f"👥 Получено {len(members)} участников из {chat_username}")
            return members
        except Exception as e:
            logger.error(f"❌ Ошибка получения участников {chat_username}: {e}")
            return []
    
    async def view_stories_simple(self, client, account_name, user):
        """Упрощенный просмотр Stories пользователя"""
        try:
            # Пытаемся получить Stories
            result = await client(GetPeerStoriesRequest(peer=user))
            
            if not result or not hasattr(result, 'stories'):
                return 0
            
            # Получаем Stories
            peer_stories = result.stories
            if not hasattr(peer_stories, 'stories') or not peer_stories.stories:
                return 0
            
            stories_list = peer_stories.stories
            viewed_count = 0
            
            for story in stories_list:
                story_key = f"{user.id}_{story.id}"
                
                if story_key in self.viewed_stories:
                    continue
                
                self.viewed_stories.add(story_key)
                viewed_count += 1
                
                username = user.username or f"ID{user.id}"
                logger.info(f"👁️ {account_name} просмотрел Story @{username}")
                
                # Ставим реакцию с вероятностью
                if random.random() <= self.REACTION_PROBABILITY:
                    await self.react_to_story(client, account_name, user, story)
                
                # Задержка между Stories
                await asyncio.sleep(random.randint(10, 30))
            
            return viewed_count
            
        except Exception as e:
            # Это нормально - не у всех есть Stories
            return 0
    
    async def react_to_story(self, client, account_name, user, story):
        """Поставить реакцию на Story"""
        try:
            reaction = random.choice(self.REACTIONS)
            
            await client(SendStoryReactionRequest(
                peer=user,
                story_id=story.id,
                reaction=ReactionEmoji(emoticon=reaction)
            ))
            
            username = user.username or f"ID{user.id}"
            logger.info(f"❤️ {account_name} → {reaction} на Story @{username}")
            
            await asyncio.sleep(random.randint(15, 45))
            
        except Exception as e:
            logger.debug(f"Реакция на Story не удалась: {str(e)[:50]}")
    
    async def process_chat_stories(self, client, account_name, chat_username):
        """Обработка Stories участников одного чата"""
        logger.info(f"🎯 {account_name} обрабатывает {chat_username}")
        
        # Получаем участников
        members = await self.get_chat_members(client, chat_username, limit=50)
        
        if not members:
            return 0
        
        total_viewed = 0
        
        # Обрабатываем случайную выборку участников
        sample_size = min(20, len(members))
        selected_members = random.sample(members, sample_size)
        
        for user in selected_members:
            if user.bot:  # Пропускаем ботов
                continue
            
            viewed = await self.view_stories_simple(client, account_name, user)
            total_viewed += viewed
            
            # Задержка между пользователями
            if viewed > 0:
                await asyncio.sleep(random.randint(5, 15))
        
        logger.info(f"📊 {account_name} в {chat_username}: просмотрено {total_viewed} Stories")
        return total_viewed
    
    async def run_cycle(self, client, account_name, target_chats):
        """Один цикл обработки чатов для одного аккаунта"""
        total = 0
        
        for chat in target_chats:
            try:
                viewed = await self.process_chat_stories(client, account_name, chat)
                total += viewed
                
                # Задержка между чатами
                await asyncio.sleep(random.randint(60, 120))
                
            except Exception as e:
                logger.error(f"❌ Ошибка в {chat}: {e}")
        
        return total
    
    async def close_all(self):
        """Закрыть все клиенты"""
        for client in self.clients.values():
            await client.disconnect()


async def main():
    """Основная функция"""
    print("\n" + "="*70)
    print("👁️  СИСТЕМА ПРОСМОТРА STORIES И РЕАКЦИЙ")
    print("="*70 + "\n")
    
    # Загружаем конфигурацию для Stories (отдельные сессии)
    try:
        with open('accounts_config_stories.json', 'r', encoding='utf-8') as f:
            accounts = json.load(f)
        logger.info(f"✅ Загружена конфигурация Stories: {len(accounts)} аккаунтов")
    except FileNotFoundError:
        logger.error("❌ Файл accounts_config_stories.json не найден!")
        logger.error("   Сначала выполните: python create_stories_sessions.py")
        return
    
    # Целевые чаты
    TARGET_CHATS = [
        '@bali_ubud_changu',
        '@canggu_people',
        '@events_travels_group',
        '@balichat',
        '@bali_villa_arenda',
    ]
    
    viewer = SimpleStoriesViewer()
    
    try:
        # Подключаем ВСЕ аккаунты (включая забаненные)
        for account in accounts:
            logger.info(f"📱 Подключение {account['session_name']}...")
            
            client = await viewer.connect_account(
                phone=account['phone'],
                api_id=account['api_id'],
                api_hash=account['api_hash'],
                session_name=account['session_name'],
                string_session=account.get('string_session')
            )
            
            if client:
                viewer.clients[account['session_name']] = client
        
        if not viewer.clients:
            logger.error("❌ Нет подключенных аккаунтов!")
            return
        
        logger.info(f"\n✅ Подключено {len(viewer.clients)} аккаунтов\n")
        
        # Запускаем ОДИН тестовый цикл
        logger.info("🧪 Запуск тестового цикла...")
        
        total_stories = 0
        
        for account_name, client in viewer.clients.items():
            logger.info(f"\n📱 === {account_name} ===")
            
            stories = await viewer.run_cycle(client, account_name, TARGET_CHATS[:2])  # Только 2 чата для теста
            total_stories += stories
            
            logger.info(f"✅ {account_name}: {stories} Stories")
            
            # Задержка между аккаунтами
            await asyncio.sleep(random.randint(60, 120))
        
        print("\n" + "="*70)
        print(f"📊 ИТОГО ПРОСМОТРЕНО STORIES: {total_stories}")
        print("="*70 + "\n")
        
        # Для непрерывной работы раскомментируйте:
        # while True:
        #     await asyncio.sleep(4 * 3600)  # Каждые 4 часа
        #     logger.info("🔄 Новый цикл...")
        
    except KeyboardInterrupt:
        logger.info("\n⏹️ Остановка...")
    except Exception as e:
        logger.error(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await viewer.close_all()
        logger.info("👋 Завершено\n")


if __name__ == '__main__':
    asyncio.run(main())

