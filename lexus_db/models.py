"""
Модели базы данных для системы Lexus Promotion (Async SQLAlchemy)
"""
from sqlalchemy import Column, Integer, String, Boolean, Text, BigInteger, TIMESTAMP, ForeignKey, DateTime
from sqlalchemy.orm import DeclarativeBase, relationship
from datetime import datetime, timedelta
from typing import Optional


class Base(DeclarativeBase):
    """Базовый класс для всех моделей"""
    pass


class Account(Base):
    """Модель аккаунта Telegram"""
    __tablename__ = 'accounts'
    
    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String(20), nullable=True)
    string_session = Column(Text, nullable=True)  # String session для Telethon (используется string_session, как в БД)
    session_name = Column(String(255), unique=True, nullable=False, index=True)  # Имя сессии
    
    # Статус аккаунта
    status = Column(String(50), default='active', index=True)  # 'active', 'banned', 'flood_wait'
    
    # Дополнительные поля (могут отсутствовать в БД)
    api_id = Column(Integer, nullable=True)
    api_hash = Column(String(255), nullable=True)
    proxy = Column(Text, nullable=True)
    nickname = Column(String(255), nullable=True)
    bio = Column(Text, nullable=True)
    
    # FloodWait обработка (опционально, может отсутствовать в БД)
    next_allowed_action_time = Column(TIMESTAMP, nullable=True, index=True)  # Когда можно выполнить следующее действие
    
    # Лимиты постинга (опционально, может отсутствовать в БД)
    daily_posts_count = Column(Integer, default=0, nullable=True)  # Счетчик постов за день
    last_stats_reset = Column(TIMESTAMP, nullable=True, index=True)  # Дата последнего сброса счетчика (для сброса в полночь)
    
    # Метаданные
    created_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=True)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)
    
    # Relationships (упрощенные для БД Bali)
    assigned_targets = relationship("Target", foreign_keys="Target.assigned_account_id", back_populates="assigned_account")
    # post_history relationship removed for Bali DB compatibility
    
    def reset_daily_count_if_needed(self):
        """Сброс счетчика постов, если наступил новый день"""
        if self.last_stats_reset:
            now = datetime.utcnow()
            last_reset_date = self.last_stats_reset.date()
            if now.date() > last_reset_date:
                self.daily_posts_count = 0
                self.last_stats_reset = now
                return True
        else:
            # Первый раз - инициализируем
            self.last_stats_reset = datetime.utcnow()
            self.daily_posts_count = 0
            return True
        return False


class Target(Base):
    """Модель группы/канала (цель для постинга)"""
    __tablename__ = 'groups'  # В БД Bali используется таблица 'groups', а не 'targets'
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), unique=True, nullable=False, index=True)  # @username (в БД Bali используется username)
    title = Column(String(500), nullable=True)  # Название группы
    
    # Ниша
    niche = Column(String(100), nullable=True, index=True)  # 'ukraine_cars', 'bali', etc.
    
    # Статус группы
    status = Column(String(50), default='new', index=True)  # 'new', 'active', 'error', 'banned'
    
    # Строгая привязка к аккаунту
    assigned_account_id = Column(Integer, ForeignKey('accounts.id', ondelete='SET NULL'), nullable=True, index=True)
    
    # Временные метки
    joined_at = Column(TIMESTAMP, nullable=True, index=True)  # Когда аккаунт вступил в группу
    warm_up_until = Column(TIMESTAMP, nullable=True, index=True)  # Когда заканчивается warm-up (в БД Bali используется warm_up_until)
    last_post_at = Column(TIMESTAMP, nullable=True, index=True)  # Время последнего поста
    
    # Лимиты постинга в группу (в БД Bali используется daily_posts_count вместо daily_posts_in_group)
    daily_posts_count = Column(Integer, default=0, nullable=True)  # Количество постов в группу за сегодня (макс 2)
    
    # Дополнительные поля для БД Bali
    can_post = Column(Boolean, default=True, nullable=True)
    members_count = Column(Integer, nullable=True)
    
    # Метаданные
    created_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=True)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)
    
    # Properties для обратной совместимости с кодом, использующим 'link' и 'warmup_ends_at'
    @property
    def link(self):
        """Возвращает username как link для обратной совместимости"""
        return self.username
    
    @property
    def warmup_ends_at(self):
        """Возвращает warm_up_until как warmup_ends_at для обратной совместимости"""
        return self.warm_up_until
    
    @property
    def daily_posts_in_group(self):
        """Возвращает daily_posts_count как daily_posts_in_group для обратной совместимости"""
        return self.daily_posts_count or 0
    
    # Relationships (упрощенные для БД Bali)
    assigned_account = relationship("Account", foreign_keys=[assigned_account_id], back_populates="assigned_targets")
    
    def reset_daily_count_if_needed(self):
        """Сброс счетчика постов группы, если наступил новый день"""
        if self.last_group_stats_reset:
            now = datetime.utcnow()
            last_reset_date = self.last_group_stats_reset.date()
            if now.date() > last_reset_date:
                self.daily_posts_in_group = 0
                self.last_group_stats_reset = now
                return True
        else:
            # Первый раз - инициализируем
            self.last_group_stats_reset = datetime.utcnow()
            self.daily_posts_in_group = 0
            return True
        return False
    
    def set_warmup_ends_at(self, joined_at: Optional[datetime] = None):
        """Установка времени окончания warm-up периода (24 часа после вступления)"""
        if joined_at is None:
            joined_at = datetime.utcnow()
        self.joined_at = joined_at
        self.warm_up_until = joined_at + timedelta(hours=24)  # Используем warm_up_until для БД Bali
    
    def is_warmup_finished(self) -> bool:
        """Проверка, закончился ли warm-up период"""
        warmup_end = self.warm_up_until or self.warmup_ends_at
        if not warmup_end:
            return False
        return datetime.utcnow() >= warmup_end


class PostHistory(Base):
    """История постинга (логи)"""
    __tablename__ = 'posts'  # В БД Bali используется таблица 'posts', а не 'post_history'
    
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False, index=True)
    group_id = Column(Integer, ForeignKey('groups.id', ondelete='CASCADE'), nullable=False, index=True)  # В БД Bali используется group_id вместо target_id
    message_text = Column(Text, nullable=True)  # Текст сообщения (в БД Bali используется message_text вместо message_content)
    photo_path = Column(String(500), nullable=True)  # Путь к фото, если было
    
    # Статус поста (в БД Bali используется success boolean и error_message)
    success = Column(Boolean, default=True, nullable=True)  # Успешен ли пост
    error_message = Column(Text, nullable=True)  # Сообщение об ошибке, если была
    
    # Дополнительные поля для БД Bali
    sent_at = Column(TIMESTAMP, nullable=True, index=True)  # Когда был отправлен пост
    niche = Column(String(100), nullable=True, index=True)  # Ниша поста
    
    # Properties для обратной совместимости
    @property
    def target_id(self):
        """Возвращает group_id как target_id для обратной совместимости"""
        return self.group_id
    
    @property
    def message_content(self):
        """Возвращает message_text как message_content для обратной совместимости"""
        return self.message_text
    
    @property
    def status(self):
        """Возвращает статус на основе success"""
        if self.success:
            return 'success'
        elif self.error_message:
            return 'error'
        return 'unknown'
    
    @property
    def created_at(self):
        """Возвращает sent_at как created_at для обратной совместимости"""
        return self.sent_at
    
    # Relationships (упрощенные для БД Bali)
    account = relationship("Account", foreign_keys=[account_id])
    target = relationship("Target", foreign_keys=[group_id])
