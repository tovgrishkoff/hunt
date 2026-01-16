"""
Модели базы данных для всех микросервисов
"""
from sqlalchemy import Column, Integer, String, Boolean, Text, BigInteger, TIMESTAMP, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()


class Account(Base):
    """Модель аккаунта Telegram"""
    __tablename__ = 'accounts'
    
    id = Column(Integer, primary_key=True)
    session_name = Column(String(255), unique=True, nullable=False, index=True)
    phone = Column(String(20))
    api_id = Column(Integer)
    api_hash = Column(String(255))
    string_session = Column(Text)
    proxy = Column(Text)
    nickname = Column(String(255))
    bio = Column(Text)
    status = Column(String(50), default='active')  # active, banned, warmup, inactive
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    groups = relationship("Group", back_populates="assigned_account")
    posts = relationship("Post", back_populates="account")
    story_views = relationship("StoryView", back_populates="account")
    dm_responses = relationship("DMResponse", back_populates="account")


class Group(Base):
    """Модель группы Telegram"""
    __tablename__ = 'groups'
    
    id = Column(Integer, primary_key=True)
    username = Column(String(255), unique=True, nullable=False, index=True)
    title = Column(String(500))
    niche = Column(String(100), index=True)  # cars, real_estate, general, etc.
    assigned_account_id = Column(Integer, ForeignKey('accounts.id'), nullable=True, index=True)
    joined_at = Column(TIMESTAMP)
    warm_up_until = Column(TIMESTAMP, index=True)
    status = Column(String(50), default='active')  # new, active, banned, left, inaccessible
    can_post = Column(Boolean, default=True)
    members_count = Column(Integer)
    last_post_at = Column(TIMESTAMP, index=True)  # Время последнего поста
    daily_posts_count = Column(Integer, default=0)  # Счетчик постов за день
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    assigned_account = relationship("Account", back_populates="groups")
    posts = relationship("Post", back_populates="group")


class Post(Base):
    """Модель поста в группу"""
    __tablename__ = 'posts'
    
    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey('groups.id'), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=False, index=True)
    message_text = Column(Text)
    photo_path = Column(String(500))
    sent_at = Column(TIMESTAMP, default=datetime.utcnow, index=True)
    niche = Column(String(100), index=True)
    success = Column(Boolean, default=True)
    error_message = Column(Text)
    
    # Relationships
    group = relationship("Group", back_populates="posts")
    account = relationship("Account", back_populates="posts")


class StoryView(Base):
    """Модель просмотра Story"""
    __tablename__ = 'story_views'
    
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=False, index=True)
    user_id = Column(BigInteger, index=True)
    username = Column(String(255))
    story_id = Column(String(255), index=True)
    reacted = Column(Boolean, default=False)
    reaction_type = Column(String(50))
    viewed_at = Column(TIMESTAMP, default=datetime.utcnow, index=True)
    
    # Relationships
    account = relationship("Account", back_populates="story_views")


class DMResponse(Base):
    """Модель ответа на DM"""
    __tablename__ = 'dm_responses'
    
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=False, index=True)
    user_id = Column(BigInteger, index=True)
    username = Column(String(255))
    incoming_message = Column(Text)
    response_text = Column(Text)
    service_type = Column(String(100))
    sent_at = Column(TIMESTAMP, default=datetime.utcnow, index=True)
    
    # Relationships
    account = relationship("Account", back_populates="dm_responses")

