"""
Управление сессией базы данных для Lexus (Async SQLAlchemy)
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
import os
from typing import AsyncGenerator


def get_database_url() -> str:
    """
    Получить URL базы данных с учетом окружения
    
    Формат DATABASE_URL: postgresql+asyncpg://user:password@host:port/dbname
    """
    database_url = os.getenv('DATABASE_URL')
    
    if database_url:
        # Если URL уже указан, проверяем, что он async-совместим
        if database_url.startswith('postgresql://'):
            # Конвертируем postgresql:// в postgresql+asyncpg://
            database_url = database_url.replace('postgresql://', 'postgresql+asyncpg://', 1)
        return database_url
    
    # Определяем хост и порт
    is_docker = os.path.exists('/.dockerenv') or os.getenv('RUNNING_IN_DOCKER') == 'true'
    
    if is_docker:
        host = os.getenv('POSTGRES_HOST', 'postgres')
        port = os.getenv('POSTGRES_PORT', '5432')
    else:
        host = os.getenv('POSTGRES_HOST', 'localhost')
        port = os.getenv('POSTGRES_PORT', '5438')  # По умолчанию для локальной разработки
    
    user = os.getenv('POSTGRES_USER', 'telegram_user_bali')
    password = os.getenv('POSTGRES_PASSWORD', 'telegram_password_bali')
    db_name = os.getenv('POSTGRES_DB', 'telegram_promotion_bali')
    
    return f'postgresql+asyncpg://{user}:{password}@{host}:{port}/{db_name}'


# Создаем async engine
DATABASE_URL = get_database_url()
engine = create_async_engine(
    DATABASE_URL,
    poolclass=NullPool,  # Для Docker лучше использовать NullPool
    echo=False,  # Установите True для отладки SQL-запросов
    future=True
)

# Создаем фабрику async сессий
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency для получения async сессии БД
    
    Usage:
        async for db in get_db():
            result = await db.execute(...)
            await db.commit()
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Инициализация БД (создание таблиц)"""
    from .models import Base
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """Закрытие соединений с БД"""
    await engine.dispose()
