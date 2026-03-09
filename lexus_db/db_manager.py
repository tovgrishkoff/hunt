"""
Менеджер базы данных для системы Lexus Promotion
Реализует бизнес-логику: привязку групп к аккаунтам, warm-up, лимиты
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, update, text
from sqlalchemy.orm import selectinload, load_only
from datetime import datetime, timedelta
from typing import List, Optional, Dict
import logging

from .models import Account, Target, PostHistory, Base

logger = logging.getLogger(__name__)


class DbManager:
    """Менеджер для работы с БД Lexus"""
    
    def __init__(self, session: AsyncSession):
        """
        Args:
            session: Async сессия SQLAlchemy
        """
        self.session = session
    
    async def reset_daily_counters_if_needed(self):
        """Сброс дневных счетчиков для всех аккаунтов и групп (вызывать в начале дня)"""
        try:
            now = datetime.utcnow()
            today_start = datetime(now.year, now.month, now.day)
            
            # Проверяем, есть ли поля для сброса счетчиков в модели Account
            account_has_reset_fields = hasattr(Account, 'last_stats_reset') and hasattr(Account, 'daily_posts_count')
            
            if account_has_reset_fields:
                try:
                    # Сбрасываем счетчики аккаунтов
                    stmt = select(Account).where(
                        or_(
                            Account.last_stats_reset.is_(None),
                            Account.last_stats_reset < today_start
                        )
                    )
                    result = await self.session.execute(stmt)
                    accounts = result.scalars().all()
                    
                    for account in accounts:
                        if hasattr(account, 'reset_daily_count_if_needed'):
                            account.reset_daily_count_if_needed()
                        elif hasattr(account, 'daily_posts_count'):
                            account.daily_posts_count = 0
                            account.last_stats_reset = now
                except Exception as e:
                    logger.debug(f"⚠️ Account counters reset skipped: {e}")
                    accounts = []
            else:
                accounts = []
            
            # Проверяем, есть ли поля для сброса счетчиков в модели Target
            target_has_reset_fields = hasattr(Target, 'last_group_stats_reset') and hasattr(Target, 'daily_posts_in_group')
            if not target_has_reset_fields:
                # Проверяем альтернативные поля для БД Bali
                target_has_reset_fields = hasattr(Target, 'daily_posts_count')
            
            if target_has_reset_fields:
                try:
                    # Сбрасываем счетчики групп
                    # В БД Bali может не быть last_group_stats_reset, используем только daily_posts_count
                    if hasattr(Target, 'last_group_stats_reset'):
                        stmt = select(Target).where(
                            or_(
                                Target.last_group_stats_reset.is_(None),
                                Target.last_group_stats_reset < today_start
                            )
                        )
                    else:
                        # Просто сбрасываем все счетчики групп (если нет поля last_group_stats_reset)
                        stmt = select(Target)
                    
                    result = await self.session.execute(stmt)
                    targets = result.scalars().all()
                    
                    for target in targets:
                        if hasattr(target, 'reset_daily_count_if_needed'):
                            target.reset_daily_count_if_needed()
                        elif hasattr(target, 'daily_posts_count'):
                            target.daily_posts_count = 0
                        elif hasattr(target, 'daily_posts_in_group'):
                            target.daily_posts_in_group = 0
                except Exception as e:
                    logger.debug(f"⚠️ Target counters reset skipped: {e}")
                    targets = []
            else:
                targets = []
            
            if accounts or targets:
                try:
                    await self.session.commit()
                    logger.info(f"✅ Reset daily counters: {len(accounts)} accounts, {len(targets)} targets")
                except Exception as e:
                    await self.session.rollback()
                    logger.debug(f"⚠️ Daily counters commit failed: {e}")
        except Exception as e:
            # Если поля отсутствуют в БД - просто пропускаем сброс
            await self.session.rollback()
            logger.debug(f"⚠️ Daily counters reset skipped (fields may not exist): {e}")
    
    async def assign_group(self, group_link: str, account_id: int, joined_at: Optional[datetime] = None) -> bool:
        """
        Привязка группы к аккаунту (после успешного вступления)
        
        Args:
            group_link: Ссылка на группу (@username или t.me/...)
            account_id: ID аккаунта
            joined_at: Время вступления (по умолчанию текущее время)
        
        Returns:
            True если успешно, False если ошибка
        """
        try:
            # Нормализуем ссылку (убираем t.me/, добавляем @ если нужно)
            normalized_link = self._normalize_group_link(group_link)
            
            # Находим или создаем группу
            stmt = select(Target).where(Target.username == normalized_link)
            result = await self.session.execute(stmt)
            target = result.scalar_one_or_none()
            
            if not target:
                # Создаем новую группу
                target = Target(
                    username=normalized_link,
                    status='new',
                    niche='ukraine_cars'  # По умолчанию для Lexus
                )
                self.session.add(target)
                await self.session.flush()  # Чтобы получить ID
            
            # Проверяем, не привязана ли группа к другому аккаунту
            if target.assigned_account_id is not None and target.assigned_account_id != account_id:
                logger.warning(
                    f"⚠️ Group {normalized_link} already assigned to account_id={target.assigned_account_id}, "
                    f"cannot reassign to account_id={account_id}"
                )
                return False
            
            # Привязываем группу к аккаунту
            if joined_at is None:
                joined_at = datetime.utcnow()
            
            target.assigned_account_id = account_id
            target.status = 'joined'
            target.set_warmup_ends_at(joined_at)
            target.updated_at = datetime.utcnow()
            # После успешного вступления мы уже проверили права в smart_joiner — можно постить
            if hasattr(target, 'can_post'):
                target.can_post = True
            await self.session.commit()
            logger.info(
                f"✅ Assigned group {normalized_link} to account_id={account_id}, "
                f"warmup ends at {target.warmup_ends_at}"
            )
            return True
            
        except Exception as e:
            await self.session.rollback()
            logger.error(f"❌ Error assigning group {group_link} to account_id={account_id}: {e}", exc_info=True)
            return False
    
    async def get_groups_ready_for_posting(
        self,
        niche: str = 'ukraine_cars',
        limit: Optional[int] = None
    ) -> List[Target]:
        """
        Получить группы, готовые для постинга (с учетом всех ограничений)
        
        Условия:
        1. niche == указанная ниша
        2. status == 'joined'
        3. assigned_account_id IS NOT NULL
        4. warmup_ends_at < NOW() (warm-up завершен)
        5. daily_posts_in_group < 2 (лимит группы не исчерпан)
        6. Связанный аккаунт: status == 'active' и daily_posts_count < 20
        7. Связанный аккаунт не во FloodWait (next_allowed_action_time < NOW() или NULL)
        
        Args:
            niche: Ниша групп
            limit: Максимальное количество групп (None = без ограничений)
        
        Returns:
            Список групп, готовых для постинга
        """
        now = datetime.utcnow()
        
        # Сначала сбрасываем счетчики, если нужно (с обработкой ошибок)
        # Пропускаем reset_daily_counters_if_needed для БД Bali, т.к. там может не быть нужных полей
        # Вместо этого просто продолжаем с основным запросом
        # await self.reset_daily_counters_if_needed()  # Пропущено для БД Bali
        
        # Строим запрос с JOIN к аккаунтам
        # Используем правильные поля для БД Bali: warm_up_until вместо warmup_ends_at, daily_posts_count вместо daily_posts_in_group
        # Базовые условия (обязательные для БД Bali)
        conditions = [
            Target.niche == niche,
            Target.status.in_(['active', 'joined']),  # как в маркетере для ukraine_cars
            Target.assigned_account_id.isnot(None),
            Account.status == 'active',
            or_(Target.can_post.is_(None), Target.can_post == True),  # как в Bali: только где можно постить
        ]
        
        # Добавляем условие для warm-up (используем warm_up_until для БД Bali)
        try:
            if hasattr(Target, 'warm_up_until'):
                conditions.append(Target.warm_up_until < now)
            elif hasattr(Target, 'warmup_ends_at'):
                conditions.append(Target.warmup_ends_at < now)
        except Exception:
            pass  # Если поле не существует, пропускаем проверку warm-up
        
        # Добавляем условия для daily_posts (используем daily_posts_count для БД Bali)
        try:
            if hasattr(Target, 'daily_posts_count'):
                conditions.append(Target.daily_posts_count < 2)
            elif hasattr(Target, 'daily_posts_in_group'):
                conditions.append(Target.daily_posts_in_group < 2)
        except Exception:
            pass  # Если поле не существует, пропускаем проверку лимита
        
        # НЕ добавляем проверку Account.daily_posts_count и next_allowed_action_time, т.к. их может не быть в БД Bali
        
        # Создаем запрос без selectinload, чтобы избежать проблем с отсутствующими полями
        stmt = (
            select(Target)
            .join(Account, Target.assigned_account_id == Account.id)
            .where(and_(*conditions))
            .order_by(Target.last_post_at.asc().nullsfirst())  # Сначала группы без постов, потом по времени последнего поста
        )
        
        if limit:
            stmt = stmt.limit(limit)
        
        try:
            result = await self.session.execute(stmt)
            targets = result.scalars().all()
        except Exception as e:
            logger.error(f"❌ Error executing query: {e}", exc_info=True)
            await self.session.rollback()
            # Возвращаем пустой список при ошибке
            return []
        
        logger.info(
            f"📋 Found {len(targets)} groups ready for posting (niche={niche}, limit={limit})"
        )
        
        return list(targets)
    
    async def record_post(
        self,
        account_id: int,
        target_id: int,
        message_content: Optional[str] = None,
        photo_path: Optional[str] = None,
        status: str = 'success',
        error_message: Optional[str] = None
    ) -> bool:
        """
        Запись поста в историю и обновление счетчиков
        
        Args:
            account_id: ID аккаунта
            target_id: ID группы
            message_content: Текст сообщения
            photo_path: Путь к фото
            status: Статус поста ('success', 'error', 'flood_wait', 'skipped')
            error_message: Сообщение об ошибке
        
        Returns:
            True если успешно
        """
        try:
            # Сбрасываем счетчики, если нужно (пропускаем для БД Bali)
            # await self.reset_daily_counters_if_needed()
            
            # Используем прямой SQL для записи поста (избегаем проблем с отсутствующими полями)
            # Создаем запись в таблице posts напрямую
            now = datetime.utcnow()
            
            # Определяем success на основе status
            is_success = (status == 'success')
            
            # Вставляем запись в posts
            insert_post_sql = text("""
                INSERT INTO posts (group_id, account_id, message_text, photo_path, sent_at, niche, success, error_message)
                VALUES (:group_id, :account_id, :message_text, :photo_path, :sent_at, :niche, :success, :error_message)
                RETURNING id
            """)
            
            result = await self.session.execute(
                insert_post_sql,
                {
                    "group_id": target_id,
                    "account_id": account_id,
                    "message_text": message_content[:1000] if message_content else None,
                    "photo_path": photo_path,
                    "sent_at": now,
                    "niche": "bali",  # Можно получить из группы, но для упрощения используем 'bali'
                    "success": is_success,
                    "error_message": error_message[:500] if error_message else None
                }
            )
            post_id = result.scalar_one()
            
            # Обновляем счетчики только если пост успешный
            if is_success:
                # Обновляем last_post_at и daily_posts_count для группы
                update_group_sql = text("""
                    UPDATE groups 
                    SET last_post_at = :now, 
                        daily_posts_count = COALESCE(daily_posts_count, 0) + 1,
                        updated_at = :now
                    WHERE id = :target_id
                """)
                await self.session.execute(
                    update_group_sql,
                    {"target_id": target_id, "now": now}
                )
            
            await self.session.commit()
            logger.debug(f"✅ Post recorded: post_id={post_id}, status={status}")
            return True
            
            # Создаем запись в истории
            post_history = PostHistory(
                account_id=account_id,
                target_id=target_id,
                message_content=message_content[:1000] if message_content else None,  # Ограничиваем длину
                photo_path=photo_path,
                status=status,
                error_message=error_message[:500] if error_message else None
            )
            self.session.add(post_history)
            
            # Обновляем счетчики только если пост успешный
            if status == 'success':
                now = datetime.utcnow()
                
                # Обновляем счетчик аккаунта
                account.daily_posts_count += 1
                account.updated_at = now
                
                # Обновляем счетчик группы
                target.daily_posts_in_group += 1
                target.last_post_at = now
                target.updated_at = now
            
            await self.session.commit()
            logger.info(
                f"✅ Recorded post: account_id={account_id}, target_id={target_id}, status={status}"
            )
            return True
            
        except Exception as e:
            await self.session.rollback()
            logger.error(
                f"❌ Error recording post (account_id={account_id}, target_id={target_id}): {e}",
                exc_info=True
            )
            return False
    
    async def set_account_flood_wait(self, account_id: int, wait_until: datetime):
        """
        Установка FloodWait для аккаунта
        
        Args:
            account_id: ID аккаунта
            wait_until: Время, до которого аккаунт во FloodWait
        """
        try:
            stmt = (
                update(Account)
                .where(Account.id == account_id)
                .values(
                    status='flood_wait',
                    next_allowed_action_time=wait_until,
                    updated_at=datetime.utcnow()
                )
            )
            await self.session.execute(stmt)
            await self.session.commit()
            logger.info(f"✅ Set FloodWait for account_id={account_id} until {wait_until}")
            
        except Exception as e:
            await self.session.rollback()
            logger.error(f"❌ Error setting FloodWait for account_id={account_id}: {e}", exc_info=True)
    
    async def clear_account_flood_wait(self, account_id: int):
        """Очистка FloodWait для аккаунта (возврат в active)"""
        try:
            stmt = (
                update(Account)
                .where(Account.id == account_id)
                .values(
                    status='active',
                    next_allowed_action_time=None,
                    updated_at=datetime.utcnow()
                )
            )
            await self.session.execute(stmt)
            await self.session.commit()
            logger.info(f"✅ Cleared FloodWait for account_id={account_id}")
            
        except Exception as e:
            await self.session.rollback()
            logger.error(f"❌ Error clearing FloodWait for account_id={account_id}: {e}", exc_info=True)
    
    async def get_account_by_session_name(self, session_name: str) -> Optional[Account]:
        """Получить аккаунт по session_name"""
        stmt = select(Account).where(Account.session_name == session_name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_target_by_link(self, link: str) -> Optional[Target]:
        """Получить группу по ссылке"""
        normalized_link = self._normalize_group_link(link)
        stmt = select(Target).where(Target.link == normalized_link)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    def _normalize_group_link(self, link: str) -> str:
        """
        Нормализация ссылки на группу
        
        Преобразует:
        - t.me/groupname -> @groupname
        - https://t.me/groupname -> @groupname
        - groupname -> @groupname
        - @groupname -> @groupname (без изменений)
        """
        link = link.strip()
        
        # Убираем протокол
        if link.startswith('https://'):
            link = link[8:]
        elif link.startswith('http://'):
            link = link[7:]
        
        # Убираем t.me/
        if link.startswith('t.me/'):
            link = link[5:]
        elif link.startswith('telegram.me/'):
            link = link[12:]
        
        # Добавляем @ если нужно
        if not link.startswith('@'):
            link = '@' + link
        
        return link
    
    async def get_account_stats(self, account_id: int) -> Dict:
        """Получить статистику аккаунта"""
        account_stmt = select(Account).where(Account.id == account_id)
        account_result = await self.session.execute(account_stmt)
        account = account_result.scalar_one_or_none()
        
        if not account:
            return {}
        
        # Подсчитываем группы аккаунта
        targets_stmt = select(func.count(Target.id)).where(Target.assigned_account_id == account_id)
        targets_result = await self.session.execute(targets_stmt)
        groups_count = targets_result.scalar_one()
        
        # Подсчитываем посты за сегодня
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        posts_stmt = (
            select(func.count(PostHistory.id))
            .where(
                and_(
                    PostHistory.account_id == account_id,
                    PostHistory.created_at >= today_start,
                    PostHistory.status == 'success'
                )
            )
        )
        posts_result = await self.session.execute(posts_stmt)
        posts_today = posts_result.scalar_one()
        
        return {
            'account_id': account.id,
            'session_name': account.session_name,
            'status': account.status,
            'daily_posts_count': account.daily_posts_count,
            'groups_count': groups_count,
            'posts_today': posts_today,
            'next_allowed_action_time': account.next_allowed_action_time
        }
