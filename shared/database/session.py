"""
Управление сессией базы данных
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
import os

# Получаем URL БД из переменных окружения
# Если запущено вне Docker, используем localhost:5437
# Если запущено внутри Docker, используем имя сервиса postgres:5432
def get_database_url():
    """Получить URL базы данных с учетом окружения"""
    if os.getenv('DATABASE_URL'):
        return os.getenv('DATABASE_URL')
    
    # Определяем хост и порт
    is_docker = os.path.exists('/.dockerenv') or os.getenv('RUNNING_IN_DOCKER') == 'true'
    
    if is_docker:
        host = 'postgres'
        port = '5432'
    else:
        host = 'localhost'
        # Для системы Бали по умолчанию используется отдельный порт 5438
        port = os.getenv('POSTGRES_PORT', '5438')
    
    # Дефолты настроены под отдельную БД для Бали
    user = os.getenv('POSTGRES_USER', 'telegram_user_bali')
    password = os.getenv('POSTGRES_PASSWORD', 'telegram_password_bali')
    db_name = os.getenv('POSTGRES_DB', 'telegram_promotion_bali')
    
    return f'postgresql://{user}:{password}@{host}:{port}/{db_name}'

DATABASE_URL = get_database_url()

# Создаем движок БД
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=10, max_overflow=20)

# Создаем фабрику сессий
SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))


def get_db():
    """Получить сессию БД (для dependency injection)"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Инициализировать БД (создать таблицы)"""
    from .models import Base
    Base.metadata.create_all(bind=engine)

