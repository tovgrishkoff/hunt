"""
Менеджер базы данных для работы с синхронными сессиями SQLAlchemy
Используется в scheduler.py и других синхронных компонентах
"""
import logging
from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy import func, or_, and_
from .session import SessionLocal
from .models import Account, Group, Post  # Используем модели из shared/database/models.py

logger = logging.getLogger(__name__)


class DbManager:
    """Менеджер БД для синхронной работы"""
    
    def __init__(self, db_url: str = None):
        # db_url игнорируем, так как SessionLocal уже настроен в session.py
        self.db = SessionLocal()

    def close(self):
        """Закрыть сессию БД"""
        if self.db:
            self.db.close()

    def __del__(self):
        """Автоматическое закрытие при удалении объекта"""
        self.close()

    # ==========================
    # Методы для Smart Joiner
    # ==========================

    def get_targets(self, status: str, niche: str, limit: int = 5):
        """
        Получить список целей для обработки
        Использует модель Group из shared/database/models.py
        """
        try:
            return self.db.query(Group).filter(
                Group.status == status,
                Group.niche == niche
            ).limit(limit).all()
        except Exception as e:
            logger.error(f"DB Error getting targets: {e}")
            return []

    def get_active_accounts(self):
        """Получить активные аккаунты, готовые к работе"""
        try:
            now = datetime.now()
            return self.db.query(Account).filter(
                Account.status == 'active',
                or_(
                    Account.next_allowed_action_time == None,
                    Account.next_allowed_action_time <= now
                )
            ).all()
        except Exception as e:
            logger.error(f"DB Error getting active accounts: {e}")
            return []
    
    def get_account_by_id(self, account_id: int):
        """Получить аккаунт по ID"""
        try:
            return self.db.query(Account).filter(Account.id == account_id).first()
        except Exception as e:
            logger.error(f"DB Error getting account: {e}")
            return None

    def get_account_by_session_name(self, session_name: str):
        """Получить аккаунт по имени сессии"""
        try:
            return self.db.query(Account).filter(Account.session_name == session_name).first()
        except Exception as e:
            logger.error(f"DB Error getting account by session_name: {e}")
            return None

    def assign_group(self, group_id: int, account_id: int, status: str, warmup_ends_at: datetime):
        """Привязать группу к аккаунту"""
        try:
            group = self.db.query(Group).filter(Group.id == group_id).first()
            if group:
                group.assigned_account_id = account_id
                group.status = status
                group.joined_at = datetime.now()
                group.warm_up_until = warmup_ends_at
                self.db.commit()
                return True
            return False
        except Exception as e:
            self.db.rollback()
            logger.error(f"DB Error assigning group: {e}")
            return False

    def update_account_status(self, account_id: int, status: str, next_action_time: datetime = None):
        """Обновить статус аккаунта (например, flood_wait)"""
        try:
            account = self.db.query(Account).filter(Account.id == account_id).first()
            if account:
                account.status = status
                if next_action_time:
                    # Если поле next_allowed_action_time существует в модели
                    if hasattr(account, 'next_allowed_action_time'):
                        account.next_allowed_action_time = next_action_time
                self.db.commit()
                return True
            return False
        except Exception as e:
            self.db.rollback()
            logger.error(f"DB Error updating account: {e}")
            return False

    def update_group_status(self, group_id: int, status: str, error_message: str = None):
        """Обновить статус группы"""
        try:
            group = self.db.query(Group).filter(Group.id == group_id).first()
            if group:
                group.status = status
                # Если поле error_message существует в модели
                if error_message and hasattr(group, 'error_message'):
                    group.error_message = error_message
                self.db.commit()
                return True
            return False
        except Exception as e:
            self.db.rollback()
            logger.error(f"DB Error updating group: {e}")
            return False

    # ==========================
    # Методы для Marketer (Poster)
    # ==========================

    def count_posts_today(self, account_id: int = None, group_id: int = None) -> int:
        """Считает посты за последние 24 часа"""
        try:
            now = datetime.now()
            yesterday = now - timedelta(days=1)
            
            query = self.db.query(Post).filter(Post.sent_at >= yesterday)
            
            if account_id:
                query = query.filter(Post.account_id == account_id)
            if group_id:
                query = query.filter(Post.group_id == group_id)
                
            return query.count()
        except Exception as e:
            logger.error(f"DB Error counting posts: {e}")
            return 0

    def get_targets_for_posting(self, niche: str, limit: int = 10):
        """
        Выбирает группы, где:
        1. Статус active (joined)
        2. Warm-up закончился (warm_up_until <= now)
        3. Лимиты не превышены (daily_posts_count < 2)
        4. Аккаунт жив и у него лимиты ок
        """
        try:
            now = datetime.now()
            
            # Сначала получаем все потенциально готовые группы для логирования
            all_potential = self.db.query(Group).join(
                Account, Group.assigned_account_id == Account.id
            ).filter(
                Group.niche == niche,
                Group.status == 'active',
                Group.can_post == True,
                Account.status == 'active'
            ).all()
            
            # Логируем группы, которые пропускаются из-за warm-up
            for group in all_potential:
                if group.warm_up_until and group.warm_up_until > now:
                    time_until_ready = group.warm_up_until - now
                    hours_left = time_until_ready.total_seconds() / 3600
                    logger.debug(f"⏳ Skipping group {group.id} ({group.username}): in warm-up period. Ready at {group.warm_up_until} (in {hours_left:.1f}h)")
            
            # Используем модель Group из shared/database/models.py
            targets = self.db.query(Group).join(
                Account, Group.assigned_account_id == Account.id
            ).filter(
                Group.niche == niche,
                Group.status == 'active',
                Group.can_post == True,  # Только группы, где можно постить
                Group.warm_up_until <= now,  # Warm-up завершен
                Group.daily_posts_count < 2,  # Лимит группы (макс 2 поста в день)
                Account.status == 'active'
            ).limit(limit).all()
            
            return targets
        except Exception as e:
            logger.error(f"DB Error getting targets for posting: {e}")
            return []

    def update_target_last_post(self, group_id: int):
        """Обновляет время последнего поста"""
        try:
            group = self.db.query(Group).filter(Group.id == group_id).first()
            if group:
                group.last_post_at = datetime.now()
                self.db.commit()
                return True
            return False
        except Exception as e:
            self.db.rollback()
            logger.error(f"DB Error updating last post: {e}")
            return False

    def record_post(self, account_id: int, group_id: int, status: str, message_text: str = ""):
        """Записывает пост, обновляет счетчики"""
        try:
            now = datetime.now()
            
            # 1. Обновляем аккаунт (если есть поле daily_posts_count)
            account = self.db.query(Account).filter(Account.id == account_id).first()
            if account and hasattr(account, 'daily_posts_count'):
                account.daily_posts_count = (account.daily_posts_count or 0) + 1
                if hasattr(account, 'last_activity_at'):
                    account.last_activity_at = now

            # 2. Обновляем группу
            group = self.db.query(Group).filter(Group.id == group_id).first()
            if group:
                group.daily_posts_count = (group.daily_posts_count or 0) + 1
                group.last_post_at = now

            # 3. Создаем запись поста
            post = Post(
                group_id=group_id,
                account_id=account_id,
                message_text=message_text[:500] if message_text else None,  # Ограничение длины
                sent_at=now,
                niche=group.niche if group else None,
                success=(status == 'success')
            )
            if status != 'success':
                post.error_message = status
            
            self.db.add(post)
            self.db.commit()
            return True
        except Exception as e:
            self.db.rollback()
            logger.error(f"DB Error recording post: {e}")
            return False

    # ==========================
    # Вспомогательные методы
    # ==========================

    def reset_daily_counters_if_needed(self):
        """Сброс дневных счетчиков для всех аккаунтов и групп (вызывать в начале дня)"""
        try:
            now = datetime.now()
            today_start = datetime(now.year, now.month, now.day)
            
            # Сбрасываем счетчики аккаунтов
            accounts = self.db.query(Account).filter(
                or_(
                    ~Account.updated_at.is_(None),  # Если поле существует
                    Account.updated_at < today_start
                )
            ).all()
            
            for account in accounts:
                if hasattr(account, 'daily_posts_count'):
                    account.daily_posts_count = 0
                if hasattr(account, 'last_stats_reset'):
                    account.last_stats_reset = now
            
            # Сбрасываем счетчики групп
            groups = self.db.query(Group).filter(
                or_(
                    ~Group.updated_at.is_(None),
                    Group.updated_at < today_start
                )
            ).all()
            
            for group in groups:
                if hasattr(group, 'daily_posts_count'):
                    group.daily_posts_count = 0
            
            self.db.commit()
            return True
        except Exception as e:
            self.db.rollback()
            logger.error(f"DB Error resetting daily counters: {e}")
            return False
