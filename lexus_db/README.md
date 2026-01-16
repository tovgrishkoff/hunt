# Lexus DB - База данных для системы Lexus Promotion

Пакет для работы с PostgreSQL (Async SQLAlchemy) для системы Lexus Promotion.

## Структура

- `models.py` - Модели SQLAlchemy (Account, Target, PostHistory)
- `session.py` - Настройка async сессий и подключения к БД
- `db_manager.py` - Менеджер с бизнес-логикой (привязки, лимиты, warm-up)
- `migrate_from_files.py` - Скрипт миграции данных из файлов в БД

## Быстрый старт

### 1. Установка зависимостей

Добавьте в `requirements.txt`:
```
sqlalchemy[asyncio]>=2.0.0
asyncpg>=0.29.0
```

### 2. Настройка переменных окружения

```bash
export DATABASE_URL="postgresql+asyncpg://user:password@host:port/dbname"
# Или отдельные переменные:
export POSTGRES_HOST=postgres
export POSTGRES_PORT=5432
export POSTGRES_USER=telegram_user_bali
export POSTGRES_PASSWORD=telegram_password_bali
export POSTGRES_DB=telegram_promotion_bali
```

### 3. Инициализация БД

```python
from lexus_db.session import init_db

await init_db()  # Создает таблицы
```

### 4. Миграция данных

```bash
python3 lexus_db/migrate_from_files.py
```

## Примеры использования

См. `LEXUS_DB_MIGRATION_GUIDE.md` для подробных примеров.
