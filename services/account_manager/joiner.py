"""
Логика поиска и вступления в группы
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import pytz
from telethon.tl.functions.channels import JoinChannelRequest, GetFullChannelRequest
from telethon.tl.functions.messages import GetFullChatRequest
from telethon.errors import FloodWaitError, UserAlreadyParticipantError, UsernameNotOccupiedError

from shared.database.session import get_db
from shared.database.models import Account, Group

logger = logging.getLogger(__name__)


class GroupJoiner:
    """Класс для поиска и вступления в группы"""
    
    def __init__(self, client_manager, config_loader, niche_config):
        self.client_manager = client_manager
        self.config_loader = config_loader
        self.niche_config = niche_config
        self.timezone = pytz.timezone(niche_config['joining_schedule']['timezone'])
    
    async def check_can_post_in_group(self, client, entity):
        """Проверка возможности постить в группу"""
        try:
            me = await client.get_me()
            permissions = await client.get_permissions(entity, me)
            if permissions:
                if hasattr(permissions, 'send_messages'):
                    return permissions.send_messages
                elif hasattr(permissions, 'banned_rights') and permissions.banned_rights:
                    if hasattr(permissions.banned_rights, 'send_messages'):
                        return not permissions.banned_rights.send_messages
            return True
        except Exception as e:
            logger.warning(f"Failed to check permissions: {e}")
            return False
    
    async def search_groups(self, client, keyword: str, limit: int = 20):
        """Поиск групп по ключевому слову"""
        try:
            from telethon.tl.functions.contacts import SearchRequest
            
            results = await client(SearchRequest(
                q=keyword,
                limit=limit
            ))
            
            groups = []
            for chat in results.chats:
                if hasattr(chat, 'username') and chat.username:
                    groups.append({
                        'username': f"@{chat.username}",
                        'title': getattr(chat, 'title', 'Unknown'),
                        'id': chat.id,
                        'members_count': getattr(chat, 'participants_count', 0)
                    })
            
            return groups
        except Exception as e:
            logger.error(f"Error searching for '{keyword}': {e}")
            return []
    
    async def join_group(self, client, account_name: str, group_info: Dict) -> bool:
        """Вступление в группу с проверкой прав"""
        username = group_info['username']
        db_gen = get_db()
        db = next(db_gen)
        
        try:
            # Проверяем, есть ли уже группа в БД
            existing_group = db.query(Group).filter(Group.username == username).first()
            if existing_group and existing_group.status == 'active':
                logger.info(f"  ℹ️ Group {username} already in database")
                return True
            
            # Получаем entity группы
            entity = await client.get_entity(username)
            
            # Проверяем права на постинг
            can_post = await self.check_can_post_in_group(client, entity)
            if not can_post:
                logger.warning(f"  ⚠️ Cannot post in {username}, skipping")
                return False
            
            # Проверяем, не участник ли уже
            try:
                await client.get_participants(entity, limit=1)
                logger.info(f"  ℹ️ Already a member of {username}")
                is_new = False
            except:
                # Вступаем в группу
                await client(JoinChannelRequest(username))
                logger.info(f"  ✅ Joined group {username}")
                is_new = True
            
            # Получаем аккаунт из БД
            account = db.query(Account).filter(Account.session_name == account_name).first()
            if not account:
                logger.error(f"  ❌ Account {account_name} not found in DB")
                return False
            
            # Сохраняем группу в БД
            if existing_group:
                existing_group.assigned_account_id = account.id
                existing_group.joined_at = datetime.utcnow()
                existing_group.warm_up_until = datetime.utcnow() + timedelta(
                    hours=self.niche_config['limits']['warm_up_hours']
                )
                existing_group.status = 'active'
                existing_group.can_post = True
                existing_group.niche = self.niche_config['name']
                db.commit()
                logger.info(f"  🔗 Updated group {username} in DB")
            else:
                new_group = Group(
                    username=username,
                    title=group_info['title'],
                    niche=self.niche_config['name'],
                    assigned_account_id=account.id,
                    joined_at=datetime.utcnow(),
                    warm_up_until=datetime.utcnow() + timedelta(
                        hours=self.niche_config['limits']['warm_up_hours']
                    ),
                    status='active',
                    can_post=True,
                    members_count=group_info.get('members_count', 0)
                )
                db.add(new_group)
                db.commit()
                logger.info(f"  🔗 Added group {username} to DB with warm-up until {new_group.warm_up_until}")
            
            return True
            
        except UserAlreadyParticipantError:
            logger.info(f"  ℹ️ Already a member of {username}")
            return True
        except UsernameNotOccupiedError:
            logger.warning(f"  ⚠️ Group {username} not found")
            return False
        except FloodWaitError as e:
            logger.warning(f"  ⚠️ FloodWait: {e.seconds} seconds")
            await asyncio.sleep(e.seconds)
            return False
        except Exception as e:
            logger.error(f"  ❌ Error joining {username}: {e}")
            return False
        finally:
            db.close()
    
    async def run(self):
        """Основной цикл работы"""
        keywords = self.niche_config['search_keywords']
        schedule = self.niche_config['joining_schedule']
        
        logger.info(f"⏰ Schedule timezone: {schedule['timezone']}")
        logger.info(f"🔍 Search keywords: {len(keywords)}")
        
        while True:
            now = datetime.now(self.timezone)
            current_time = now.time()
            
            # Проверяем, наступило ли время для поиска
            should_run = False
            for slot in schedule['slots']:
                slot_time = datetime.strptime(slot['time'], '%H:%M').time()
                # Запускаем поиск в указанное время (допуск ±5 минут)
                if (current_time.hour == slot_time.hour and 
                    abs(current_time.minute - slot_time.minute) <= 5):
                    should_run = True
                    logger.info(f"⏰ Running search at {slot['name']} slot")
                    break
            
            if should_run:
                # Запускаем поиск и вступление
                for keyword in keywords[:10]:  # Ограничиваем количество ключевых слов за раз
                    logger.info(f"🔍 Searching for: {keyword}")
                    
                    # Используем первый доступный аккаунт для поиска
                    if not self.client_manager.clients:
                        logger.error("❌ No clients available")
                        break
                    
                    account_name = list(self.client_manager.clients.keys())[0]
                    client = self.client_manager.clients[account_name]
                    
                    # Поиск групп
                    groups = await self.search_groups(client, keyword, limit=20)
                    logger.info(f"  Found {len(groups)} groups")
                    
                    # Вступление в найденные группы
                    for group_info in groups:
                        await self.join_group(client, account_name, group_info)
                        await asyncio.sleep(30)  # Задержка между вступлениями
                    
                    await asyncio.sleep(60)  # Задержка между поисками
            
            # Проверяем каждые 5 минут
            await asyncio.sleep(300)

