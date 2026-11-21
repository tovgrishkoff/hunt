"""
Модуль просмотра Stories участников групп
"""
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
import random
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from sqlalchemy import func, and_

from telethon.tl.functions.stories import (
    GetAllStoriesRequest,
    GetPeerStoriesRequest,
    IncrementStoryViewsRequest,
    ReadStoriesRequest,
    SendReactionRequest,
)
from telethon.tl.functions.contacts import AddContactRequest
from telethon.tl.types import ReactionEmoji
from telethon.errors import (
    FloodWaitError,
    UserNotParticipantError,
    ChannelPrivateError,
    ChatAdminRequiredError,
    RPCError
)

from shared.database.session import SessionLocal
from shared.database.models import Account, Group, StoryView

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AccountSnapshot:
    """Минимальный слепок аккаунта для работы без DB-сессии."""
    id: int
    session_name: str


class StoryViewer:
    """Класс для просмотра Stories участников групп"""

    def __init__(self, client_manager, niche_config=None):
        self.client_manager = client_manager
        self.niche_config = niche_config or {}
        
        # Получаем настройки из конфига ниши
        activity_config = self.niche_config.get('activity', {})
        
        # Настройки поведения
        self.STORY_VIEW_PROBABILITY = activity_config.get('story_view_probability', 0.7)
        self.STORY_REACTION_PROBABILITY = activity_config.get('story_reaction_probability', 0.3)
        self.MAX_VIEWS_PER_DAY = activity_config.get('max_views_per_day', 200)
        self.MIN_VIEWS_PER_DAY = activity_config.get('min_views_per_day', 100)
        
        # Доступные реакции для Stories
        self.STORY_REACTIONS = activity_config.get('story_reactions', ['❤️', '🔥', '👍', '😍', '💯'])
        
        # Задержки (секунды)
        self.MIN_DELAY_BETWEEN_VIEWS = activity_config.get('min_delay_between_views', 10)
        self.MAX_DELAY_BETWEEN_VIEWS = activity_config.get('max_delay_between_views', 45)
        self.MIN_DELAY_BETWEEN_REACTIONS = activity_config.get('min_delay_between_reactions', 15)
        self.MAX_DELAY_BETWEEN_REACTIONS = activity_config.get('max_delay_between_reactions', 60)
        self.MIN_DELAY_BETWEEN_USERS = 5
        self.MAX_DELAY_BETWEEN_USERS = 15
        
        # Аккаунты для просмотра Stories контактов (диалоги).
        # Для Bali нам важно, чтобы сторис смотрели те же промо-аккаунты, что постят.
        self.contacts_view_accounts = set(activity_config.get('contacts_view_accounts', []))
        # Снимок явного списка из JSON до merge — не даём story_view_excluded_accounts выкинуть эти сессии
        self.explicit_contacts_view_session_names = set(self.contacts_view_accounts)
        if self.niche_config.get('name') == 'bali':
            # 1) Подтягиваем allowed_accounts из bali_accounts_config.json (как было)
            for p in [
                Path('/app/config/bali_accounts_config.json'),
                Path('/app/bali_accounts_config.json'),
                Path('config/bali_accounts_config.json'),
                Path('bali_accounts_config.json'),
            ]:
                if p.exists():
                    try:
                        with open(p, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        allowed = data.get('allowed_accounts') or []
                        join_extra = data.get('join_accounts') or []
                        contacts_extra = data.get('contacts_view_accounts') or []
                        merged = {
                            s for s in list(allowed) + list(join_extra) + list(contacts_extra)
                            if s
                        }
                        if merged:
                            self.contacts_view_accounts |= merged
                            logger.info(
                                "Bali: аккаунты из bali_accounts_config добавлены в просмотр сторис: %s",
                                sorted(self.contacts_view_accounts),
                            )
                            break
                    except Exception as e:
                        logger.warning("Не удалось загрузить %s: %s", p, e)

            # 2) Дополнительно расширяем список всеми active+niche='bali' аккаунтами из БД,
            # чтобы охватить promotion_new_account (@grishkoff) и остальных постящих.
            try:
                db = SessionLocal()
                try:
                    bali_accounts = (
                        db.query(Account.session_name)
                        .filter(
                            Account.status.in_(("active", "cooldown", "listener")),
                            Account.niche == "bali",
                        )
                        .all()
                    )
                    from_db = {row[0] for row in bali_accounts if row[0]}
                    if from_db:
                        self.contacts_view_accounts |= from_db
                        logger.info(
                            "Bali: добавлены active и cooldown niche='bali' для просмотра сторис: %s",
                            sorted(from_db),
                        )
                finally:
                    db.close()
            except Exception as e:
                logger.warning("Не удалось загрузить Bali-аккаунты из БД для сторис: %s", e)

            # Усиливаем активность по умолчанию для Bali (если в конфиге не задано жёстко)
            if self.STORY_VIEW_PROBABILITY < 0.8:
                self.STORY_VIEW_PROBABILITY = 0.8
            if self.STORY_REACTION_PROBABILITY < 0.3:
                self.STORY_REACTION_PROBABILITY = 0.3

        self.contacts_dialogs_limit = activity_config.get('contacts_dialogs_limit', 300)
        # Юзернеймы, которых не смотрим и не лайкаем (бан-лист)
        self.story_view_exclude_usernames = set(
            u.strip().lower() for u in activity_config.get('story_view_exclude_usernames', [])
            if u and isinstance(u, str)
        )
        # Приоритетные юзернеймы: смотрим всегда, ставим реакции с макс. вероятностью; обрабатываются первыми
        self.story_view_priority_usernames = set(
            u.strip().lower() for u in activity_config.get('story_view_priority_usernames', [])
            if u and isinstance(u, str)
        )
        self.story_view_priority_reaction_probability = min(
            1.0,
            max(0.0, float(activity_config.get('story_view_priority_reaction_probability', 1.0)))
        )
        # PeerFlood / join-only: смотрят сторис, но не ставят реакции и не инициируют ЛС.
        self.story_no_reaction_accounts = set(
            s for s in activity_config.get('story_no_reaction_accounts', []) if s
        )
        if self.story_no_reaction_accounts:
            logger.info(
                "Story reactions disabled for accounts: %s",
                sorted(self.story_no_reaction_accounts),
            )
    
    def get_viewed_stories_today(self, db, account_id: int) -> set:
        """
        Получить множество просмотренных stories за сегодня для аккаунта
        
        Args:
            db: Сессия БД
            account_id: ID аккаунта
        
        Returns:
            Множество story_id (формат: "{user_id}_{story_id}")
        """
        today = datetime.utcnow().date()
        today_start = datetime.combine(today, datetime.min.time())
        today_end = datetime.combine(today + timedelta(days=1), datetime.min.time())
        
        viewed = db.query(StoryView.story_id).filter(
            and_(
                StoryView.account_id == account_id,
                StoryView.viewed_at >= today_start,
                StoryView.viewed_at < today_end
            )
        ).all()
        
        return {row[0] for row in viewed if row[0]}
    
    def get_views_count_today(self, db, account_id: int) -> int:
        """
        Получить количество просмотров за сегодня для аккаунта
        
        Args:
            db: Сессия БД
            account_id: ID аккаунта
        
        Returns:
            Количество просмотров
        """
        today = datetime.utcnow().date()
        today_start = datetime.combine(today, datetime.min.time())
        today_end = datetime.combine(today + timedelta(days=1), datetime.min.time())
        
        count = db.query(func.count(StoryView.id)).filter(
            and_(
                StoryView.account_id == account_id,
                StoryView.viewed_at >= today_start,
                StoryView.viewed_at < today_end
            )
        ).scalar() or 0
        
        return count
    
    def was_story_viewed_recently(self, db, account_id: int, user_id: int, story_id: int, hours: int = 24) -> bool:
        """
        Проверить, был ли просмотрен story за последние N часов
        
        Args:
            db: Сессия БД
            account_id: ID аккаунта
            user_id: ID пользователя
            story_id: ID story
            hours: Количество часов для проверки
        
        Returns:
            True если был просмотрен, False если нет
        """
        story_key = f"{user_id}_{story_id}"
        threshold = datetime.utcnow() - timedelta(hours=hours)
        
        existing = db.query(StoryView).filter(
            and_(
                StoryView.account_id == account_id,
                StoryView.story_id == story_key,
                StoryView.viewed_at >= threshold
            )
        ).first()
        
        return existing is not None
    
    async def get_contacts_from_dialogs(self, client, limit: int = 300) -> List:
        """
        Получить список контактов из диалогов
        
        Args:
            client: Telegram клиент
            limit: Максимум диалогов для проверки
        
        Returns:
            Список пользователей из диалогов
        """
        try:
            users = []
            dialogs = await client.get_dialogs(limit=limit)
            
            for dialog in dialogs:
                entity = dialog.entity
                # Фильтруем только пользователей (не боты, не группы)
                if hasattr(entity, 'id') and hasattr(entity, 'first_name'):
                    if not getattr(entity, 'bot', False):
                        users.append(entity)
            
            logger.debug(f"  📱 Получено {len(users)} контактов из диалогов")
            return users
            
        except Exception as e:
            logger.warning(f"  ⚠️ Ошибка получения контактов из диалогов: {e}")
            return []
    
    async def get_group_participants(self, client, group: Group, limit: int = 50) -> List:
        """
        Получить участников группы
        
        Args:
            client: Telegram клиент
            group: Группа из БД
            limit: Максимум участников
        
        Returns:
            Список участников
        """
        try:
            entity = await client.get_entity(group.username)
            participants = await client.get_participants(entity, limit=limit)
            
            # Фильтруем ботов и пользователей без ID
            filtered = [
                p for p in participants
                if not getattr(p, 'bot', False) and hasattr(p, 'id')
            ]
            
            logger.info(f"  👥 {group.username}: участников {len(filtered)}")
            return filtered
            
        except (ChannelPrivateError, ChatAdminRequiredError, UserNotParticipantError) as e:
            logger.info(f"  👥 {group.username}: список участников закрыт ({e.__class__.__name__})")
            return []
        except Exception as e:
            logger.warning(f"  ⚠️ Ошибка получения участников из {group.username}: {e}")
            return []

    async def view_story_feed(self, client, account: Account, remaining_views: int) -> Tuple[int, int]:
        """Смотрит сторис из ленты аккаунта, а не только из случайных участников чата."""
        viewed = 0
        reactions = 0
        try:
            result = await client(GetAllStoriesRequest())
        except FloodWaitError as e:
            logger.warning(f"  ⏳ FloodWait {e.seconds}с на ленту сторис {account.session_name}")
            return 0, 0
        except RPCError as e:
            logger.info(f"  📖 {account.session_name}: лента сторис недоступна ({e.__class__.__name__})")
            return 0, 0

        peer_stories = getattr(result, "peer_stories", None) or []
        users = {
            user.id: user
            for user in (getattr(result, "users", None) or [])
            if getattr(user, "id", None)
        }
        logger.info(f"  📖 {account.session_name}: в ленте {len(peer_stories)} человек со сторис")
        for item in peer_stories:
            if viewed >= remaining_views:
                break
            user_id = getattr(getattr(item, "peer", None), "user_id", None)
            user = users.get(user_id)
            if user is None or getattr(user, "bot", False):
                continue
            v, r = await self.view_user_stories(client, account, user, group=None)
            viewed += v
            reactions += r
        return viewed, reactions
    
    async def view_user_stories(
        self,
        client,
        account: Account,
        user,
        group: Optional[Group] = None
    ) -> Tuple[int, int]:
        """
        Просмотр Stories конкретного пользователя
        
        Args:
            client: Telegram клиент
            account: Аккаунт из БД
            user: Пользователь Telegram
            group: Группа из БД
        
        Returns:
            (viewed_count: int, reactions_count: int)
        """
        viewed_count = 0
        reactions_count = 0
        
        try:
            username = getattr(user, 'username', None)
            username_lower = username.lower() if username else None
            is_priority = bool(username_lower and username_lower in self.story_view_priority_usernames)
            
            # Не смотрим и не лайкаем забаненных пользователей
            if self.story_view_exclude_usernames and username_lower and username_lower in self.story_view_exclude_usernames:
                logger.debug(f"    ⏭️ Пропуск @{username} (в списке исключений)")
                return 0, 0
            
            # Пропускаем с вероятностью (приоритетных всегда смотрим)
            if not is_priority and random.random() > self.STORY_VIEW_PROBABILITY:
                return 0, 0
            
            # Получаем Stories пользователя
            try:
                stories_result = await client(GetPeerStoriesRequest(peer=user))
                
                if not stories_result or not hasattr(stories_result, 'stories'):
                    return 0, 0
                
                stories = stories_result.stories.stories if hasattr(stories_result.stories, 'stories') else []
                
                if not stories:
                    return 0, 0
                
                # Проверяем в БД, какие stories уже просмотрены
                db = SessionLocal()
                try:
                    for story in stories:
                        story_key = f"{user.id}_{story.id}"
                        
                        # Проверяем, был ли просмотрен за последние 24 часа
                        if self.was_story_viewed_recently(db, account.id, user.id, story.id, hours=24):
                            continue
                        
                        # Пропускаем с вероятностью
                        if random.random() > self.STORY_VIEW_PROBABILITY:
                            continue

                        # Фикс: получение stories НЕ означает просмотр.
                        # Явно инкрементим просмотры и помечаем как прочитанные.
                        try:
                            await client(
                                IncrementStoryViewsRequest(
                                    peer=user,
                                    id=[story.id],
                                )
                            )
                            await client(ReadStoriesRequest(peer=user, max_id=story.id))
                        except FloodWaitError as e:
                            wait_seconds = min(e.seconds, 300)
                            logger.warning(
                                f"    ⏳ FloodWait {wait_seconds} секунд для просмотра Story"
                            )
                            await asyncio.sleep(wait_seconds)
                            continue
                        except RPCError as e:
                            logger.debug(
                                f"    ⚠️ Не удалось отметить просмотр Story: {str(e)[:80]}"
                            )
                            continue
                        except Exception as e:
                            logger.debug(
                                f"    ⚠️ Не удалось отметить просмотр Story: {str(e)[:80]}"
                            )
                            continue
                        
                        # Просматриваем Story (автоматически при получении через GetPeerStoriesRequest)
                        # Сохраняем в БД
                        story_view = StoryView(
                            account_id=account.id,
                            user_id=user.id,
                            username=getattr(user, 'username', None) or f"ID{user.id}",
                            story_id=story_key,
                            reacted=False,
                            viewed_at=datetime.utcnow()
                        )
                        
                        # Ставим реакцию с вероятностью (для приоритетных — своя, обычно 1.0).
                        # join-only / PeerFlood-аккаунты только смотрят, без лайков.
                        no_react = account.session_name in getattr(
                            self, "story_no_reaction_accounts", set()
                        )
                        reaction_prob = (
                            0.0
                            if no_react
                            else (
                                self.story_view_priority_reaction_probability
                                if is_priority
                                else self.STORY_REACTION_PROBABILITY
                            )
                        )
                        if random.random() <= reaction_prob:
                            try:
                                reaction = random.choice(self.STORY_REACTIONS)
                                
                                # Используем правильный метод для Stories
                                await client(SendReactionRequest(
                                    peer=user,
                                    story_id=story.id,
                                    reaction=ReactionEmoji(emoticon=reaction)
                                ))
                                
                                story_view.reacted = True
                                story_view.reaction_type = reaction
                                reactions_count += 1
                                logger.debug(f"    ❤️ {account.session_name} → {reaction} на Story @{user.username or user.id}")
                                
                                # Задержка после реакции
                                await asyncio.sleep(random.randint(self.MIN_DELAY_BETWEEN_REACTIONS, self.MAX_DELAY_BETWEEN_REACTIONS))
                                
                            except FloodWaitError as e:
                                logger.warning(f"    ⏳ FloodWait {e.seconds} секунд для реакции")
                                await asyncio.sleep(min(e.seconds, 300))
                            except Exception as e:
                                logger.debug(f"    ⚠️ Не удалось поставить реакцию: {str(e)[:50]}")
                        
                        db.add(story_view)
                        db.commit()
                        viewed_count += 1
                        
                        username = getattr(user, 'username', None) or f"ID{user.id}"
                        if group:
                            logger.info(f"    👁️ {account.session_name} просмотрел Story @{username} из {group.username}")
                        else:
                            logger.info(f"    👁️ {account.session_name} просмотрел Story @{username} (контакт)")
                        
                        # Задержка между просмотрами
                        await asyncio.sleep(random.randint(self.MIN_DELAY_BETWEEN_VIEWS, self.MAX_DELAY_BETWEEN_VIEWS))
                        
                except Exception as e:
                    db.rollback()
                    logger.error(f"    ❌ Ошибка при сохранении в БД: {e}")
                finally:
                    db.close()
                
                return viewed_count, reactions_count
                
            except FloodWaitError as e:
                wait_seconds = min(e.seconds, 3600)
                logger.warning(f"    ⏳ FloodWait {wait_seconds} секунд для получения Stories")
                await asyncio.sleep(wait_seconds)
                return 0, 0
            except Exception as e:
                # Stories могут быть недоступны - это нормально
                logger.debug(f"    ⚠️ Не удалось получить Stories: {str(e)[:50]}")
                return 0, 0
                
        except Exception as e:
            logger.debug(f"    ⚠️ Ошибка при просмотре Stories: {str(e)[:50]}")
            return 0, 0
    
    def get_active_groups_for_account(self, db, account_id: int, limit: int = 20) -> List[Group]:
        """
        Получить активные группы, закрепленные за аккаунтом
        
        Args:
            db: Сессия БД
            account_id: ID аккаунта
            limit: Максимум групп
        
        Returns:
            Список групп
        """
        groups = db.query(Group).filter(
            and_(
                Group.assigned_account_id == account_id,
                Group.status.in_(('active', 'joined')),
                Group.can_post == True
            )
        ).limit(limit).all()
        
        return groups
    
    async def ensure_and_view_priority_stories(
        self, client, account: Account, remaining_views: int
    ) -> Tuple[int, int]:
        """Добавить приоритетных юзеров в контакты и сразу посмотреть их сторис."""
        if not self.story_view_priority_usernames or remaining_views <= 0:
            return 0, 0

        me = await client.get_me()
        my_username = (getattr(me, "username", None) or "").lower()
        viewed_total = 0
        reactions_total = 0

        for uname in sorted(self.story_view_priority_usernames):
            if viewed_total >= remaining_views:
                break
            if not uname or uname == my_username:
                continue
            try:
                entity = await client.get_entity(uname)
            except Exception as e:
                logger.warning(
                    "  ⚠️ %s: не резолвится приоритет @%s: %s",
                    account.session_name,
                    uname,
                    e,
                )
                continue

            # В контакты — чтобы стабильно попадал в ленту Stories.
            try:
                await client(
                    AddContactRequest(
                        id=await client.get_input_entity(entity),
                        first_name=(getattr(entity, "first_name", None) or uname)[:64],
                        last_name=(getattr(entity, "last_name", None) or "")[:64],
                        phone="",
                        add_phone_privacy_exception=False,
                    )
                )
                logger.info(
                    "  ⭐ %s: @%s добавлен/обновлён в контактах",
                    account.session_name,
                    uname,
                )
            except Exception as e:
                logger.info(
                    "  ℹ️ %s: контакт @%s уже есть или не добавился (%s)",
                    account.session_name,
                    uname,
                    type(e).__name__,
                )

            viewed, reactions = await self.view_user_stories(
                client, account, entity, group=None
            )
            viewed_total += viewed
            reactions_total += reactions
            if viewed > 0:
                await asyncio.sleep(
                    random.randint(
                        int(self.MIN_DELAY_BETWEEN_USERS),
                        int(getattr(self, "MAX_DELAY_BETWEEN_USERS", 15)),
                    )
                )
            else:
                await asyncio.sleep(random.uniform(1.2, 2.8))

        return viewed_total, reactions_total

    async def process_account(self, account: Account) -> Tuple[int, int]:
        """
        Обработка одного аккаунта: просмотр Stories участников его групп
        
        Args:
            account: Аккаунт из БД
        
        Returns:
            (total_viewed: int, total_reactions: int)
        """
        if account.session_name not in self.client_manager.clients:
            logger.warning(f"⚠️ Клиент {account.session_name} не загружен, пропускаем")
            return 0, 0
        
        client = self.client_manager.clients[account.session_name]
        
        # Убеждаемся, что клиент подключен
        if not client or not client.is_connected():
            logger.warning(f"⚠️ Клиент {account.session_name} не подключен, пытаемся переподключить...")
            client = await self.client_manager.ensure_client_connected(account.session_name)
            if not client:
                logger.warning(f"⚠️ Не удалось подключить клиент {account.session_name}, пропускаем")
                return 0, 0
        
        db = SessionLocal()
        try:
            # Проверяем лимит просмотров за сегодня
            views_today = self.get_views_count_today(db, account.id)
            
            if views_today >= self.MAX_VIEWS_PER_DAY:
                logger.info(f"  ℹ️ Аккаунт {account.session_name}: лимит просмотров достигнут ({views_today}/{self.MAX_VIEWS_PER_DAY})")
                return 0, 0
            
            remaining_views = self.MAX_VIEWS_PER_DAY - views_today
            logger.info(f"  📊 Аккаунт {account.session_name}: {views_today}/{self.MAX_VIEWS_PER_DAY} просмотров, осталось {remaining_views}")
            
            total_viewed = 0
            total_reactions = 0

            feed_viewed, feed_reactions = await self.view_story_feed(
                client, account, remaining_views
            )
            total_viewed += feed_viewed
            total_reactions += feed_reactions

            # Админ/приоритет (@grishkoff и др.): в контакты + сторис/лайк у всех аккаунтов.
            left = max(0, remaining_views - total_viewed)
            p_viewed, p_react = await self.ensure_and_view_priority_stories(
                client, account, left
            )
            total_viewed += p_viewed
            total_reactions += p_react
            
            # Проверяем, является ли аккаунт аккаунтом для просмотра контактов
            contacts = []
            if account.session_name in self.contacts_view_accounts:
                # Режим просмотра Stories контактов (диалогов)
                logger.info(f"  📱 Аккаунт {account.session_name}: режим просмотра Stories контактов")
                
                # Получаем контакты из диалогов
                contacts = await self.get_contacts_from_dialogs(client, limit=self.contacts_dialogs_limit)
                
                if not contacts:
                    logger.info(
                        f"  ℹ️ Аккаунт {account.session_name}: нет контактов в диалогах, "
                        "смотрю сторис участников групп"
                    )
                
                logger.info(f"  📋 Аккаунт {account.session_name}: найдено {len(contacts)} контактов")
                
                # Приоритетные контакты — в начало списка, остальные перемешиваем
                def is_priority_contact(entity):
                    un = getattr(entity, 'username', None)
                    return un and un.lower() in self.story_view_priority_usernames
                priority = [c for c in contacts if is_priority_contact(c)]
                rest = [c for c in contacts if not is_priority_contact(c)]
                random.shuffle(rest)
                contacts = priority + rest
                if priority:
                    logger.info(f"  ⭐ Приоритетных контактов: {len(priority)}")
                
                # Обрабатываем контакты (максимум 90 за цикл для активного режима)
                processed_count = 0
                for contact in contacts[:90]:
                    # Проверяем лимит просмотров
                    if total_viewed >= remaining_views:
                        logger.info(f"  ✅ Достигнут лимит просмотров ({total_viewed})")
                        break
                    
                    # Просматриваем Stories (group=None для контактов)
                    viewed, reactions = await self.view_user_stories(client, account, contact, group=None)
                    total_viewed += viewed
                    total_reactions += reactions
                    processed_count += viewed
                    
                    # Задержка между пользователями
                    if viewed > 0:
                        await asyncio.sleep(random.randint(self.MIN_DELAY_BETWEEN_USERS, self.MAX_DELAY_BETWEEN_USERS))
                
                logger.info(f"  ✅ Аккаунт {account.session_name}: обработано {processed_count} контактов")
                
            if total_viewed == 0:
                # В личке нечего смотреть — сторис участников своих групп.
                # Получаем группы, закрепленные за аккаунтом
                groups = self.get_active_groups_for_account(db, account.id, limit=10)
                
                if not groups:
                    logger.info(f"  ℹ️ Аккаунт {account.session_name}: нет активных групп")
                    return 0, 0
                
                logger.info(f"  📋 Аккаунт {account.session_name}: обрабатывает {len(groups)} групп")
                
                for group in groups:
                    try:
                        logger.info(f"  🎯 Группа: {group.username}")
                        
                        # Получаем участников группы
                        participants = await self.get_group_participants(client, group, limit=30)
                        
                        if not participants:
                            continue
                        
                        # Перемешиваем для разнообразия
                        random.shuffle(participants)
                        
                        # Обрабатываем участников (максимум 20 за группу)
                        processed_count = 0
                        for participant in participants[:20]:
                            # Проверяем лимит просмотров
                            if total_viewed >= remaining_views:
                                logger.info(f"  ✅ Достигнут лимит просмотров ({total_viewed})")
                                break
                            
                            # Просматриваем Stories
                            viewed, reactions = await self.view_user_stories(client, account, participant, group)
                            total_viewed += viewed
                            total_reactions += reactions
                            processed_count += viewed
                            
                            # Задержка между пользователями
                            if viewed > 0:
                                await asyncio.sleep(random.randint(self.MIN_DELAY_BETWEEN_USERS, self.MAX_DELAY_BETWEEN_USERS))
                        
                        logger.info(f"  ✅ Группа {group.username}: {processed_count} просмотров")
                        
                        # Задержка между группами
                        await asyncio.sleep(random.randint(30, 60))
                        
                    except Exception as e:
                        logger.error(f"  ❌ Ошибка при обработке группы {group.username}: {e}", exc_info=True)
                        continue
            
            logger.info(f"  ✅ Аккаунт {account.session_name}: всего {total_viewed} просмотров, {total_reactions} реакций")
            
            return total_viewed, total_reactions
            
        except Exception as e:
            logger.error(f"  ❌ Ошибка при обработке аккаунта {account.session_name}: {e}", exc_info=True)
            return 0, 0
        finally:
            db.close()
    
    async def process_all_accounts(self) -> Tuple[int, int]:
        """
        Обработка всех активных аккаунтов
        
        Returns:
            (total_viewed: int, total_reactions: int)
        """
        db = SessionLocal()
        try:
            # Получаем активные аккаунты
            accounts = (
                db.query(Account)
                .filter(
                    Account.status.in_(("active", "cooldown")),
                    Account.niche == "bali",
                )
                .all()
            )
            
            if not accounts:
                logger.warning("⚠️ Нет активных аккаунтов")
                return 0, 0
            
            # Исключения из просмотра (опционально из конфига ниши; по умолчанию никого не исключаем)
            activity_cfg = (self.niche_config or {}).get('activity', {})
            excluded_sessions = set(activity_cfg.get('story_view_excluded_accounts', []))
            protected = getattr(self, "explicit_contacts_view_session_names", set())
            overlap = excluded_sessions & protected
            if overlap:
                logger.warning(
                    "Снято с story_view_excluded_accounts (явные contacts_view_accounts): %s",
                    sorted(overlap),
                )
                excluded_sessions -= protected
            if excluded_sessions:
                accounts = [a for a in accounts if a.session_name not in excluded_sessions]
                logger.info("Исключены из просмотра сторис: %s", sorted(excluded_sessions))

            # Делаем слепок, чтобы избежать DetachedInstanceError
            account_snapshots = [
                AccountSnapshot(id=account.id, session_name=account.session_name)
                for account in accounts
            ]

            # ВАЖНО: используем scoped_session, поэтому освобождаем сессию
            # до запуска обработки, чтобы вложенные SessionLocal() не закрывали
            # текущую сессию и не делали Account detached.
            db.close()
            db = None
            
            # Сначала прогоняем аккаунты для контактов/сторис, чтобы активность
            # была "видимой" быстрее, а затем остальные.
            contacts_accounts = [
                a for a in account_snapshots if a.session_name in self.contacts_view_accounts
            ]
            other_accounts = [
                a for a in account_snapshots if a.session_name not in self.contacts_view_accounts
            ]
            # @grishkoff (promotion_new_account) долго идёт по сотне диалогов.
            # Остальных пускаем первыми, иначе они ждут весь цикл.
            def _story_order(snapshot: AccountSnapshot) -> tuple:
                return (snapshot.session_name == "promotion_new_account", snapshot.session_name)

            ordered_accounts = sorted(
                [*contacts_accounts, *other_accounts],
                key=_story_order,
            )

            logger.info(f"📋 Обработка {len(account_snapshots)} активных аккаунтов...")
            
            total_viewed = 0
            total_reactions = 0
            
            for account in ordered_accounts:
                try:
                    # Если клиент не загрузился (часто из-за AuthKeyDuplicatedError),
                    # пропускаем без задержек.
                    if account.session_name not in self.client_manager.clients:
                        if account.session_name in getattr(
                            self, "explicit_contacts_view_session_names", set()
                        ):
                            logger.warning(
                                "⚠️ Клиент %s не загружен — сторис из контактов пропущены. "
                                "Проверьте прокси/сессию (Telethon не подключился при старте activity).",
                                account.session_name,
                            )
                        else:
                            logger.warning(
                                f"⚠️ Клиент {account.session_name} не загружен, пропускаем"
                            )
                        continue

                    viewed, reactions = await self.process_account(account)
                    total_viewed += viewed
                    total_reactions += reactions
                    
                    # Задержка между аккаунтами (умеренная, т.к. внутри уже есть задержки)
                    await asyncio.sleep(random.randint(30, 90))
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка при обработке аккаунта {account.session_name}: {e}", exc_info=True)
                    continue
            
            logger.info(f"✅ Все аккаунты обработаны: {total_viewed} просмотров, {total_reactions} реакций")
            
            return total_viewed, total_reactions
            
        except Exception as e:
            logger.error(f"❌ Ошибка при обработке аккаунтов: {e}", exc_info=True)
            return 0, 0
        finally:
            if db is not None:
                db.close()

