# 📚 Руководство по миграции Lexus Promotion на PostgreSQL

## 📋 Обзор

Данное руководство описывает миграцию системы Lexus Promotion с файлового хранения (JSON/TXT) на PostgreSQL с использованием Async SQLAlchemy.

## 🎯 Ключевые изменения

### 1. Строгая привязка групп к аккаунтам
- Одна группа = Один аккаунт (через `assigned_account_id`)
- Если аккаунт 'A' вступил в группу, аккаунт 'B' НИКОГДА не должен туда писать

### 2. Warm-up период
- После вступления аккаунт "молчит" в группе 24 часа
- Поле `warmup_ends_at` = `joined_at` + 24 часа
- Постинг разрешен только после `warmup_ends_at`

### 3. Лимиты
- **Группа:** Максимум 2 поста в сутки (`daily_posts_in_group < 2`)
- **Аккаунт:** Максимум 20 постов в сутки (`daily_posts_count < 20`)
- Автоматический сброс счетчиков в полночь UTC

### 4. FloodWait обработка
- Поле `next_allowed_action_time` в таблице `accounts`
- Поле `status = 'flood_wait'` для заблокированных аккаунтов

## 🗄️ Структура БД

### Таблица `accounts`

```sql
CREATE TABLE accounts (
    id SERIAL PRIMARY KEY,
    phone VARCHAR(20),
    session_string TEXT,
    session_name VARCHAR(255) UNIQUE NOT NULL,
    status VARCHAR(50) DEFAULT 'active',  -- 'active', 'banned', 'flood_wait'
    next_allowed_action_time TIMESTAMP,  -- Для FloodWait
    daily_posts_count INTEGER DEFAULT 0,
    last_stats_reset TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

**Поля:**
- `session_name` - уникальное имя сессии (из accounts_config.json)
- `status` - статус аккаунта
- `next_allowed_action_time` - время, до которого аккаунт во FloodWait
- `daily_posts_count` - счетчик постов за день (макс 20)
- `last_stats_reset` - дата последнего сброса счетчика

### Таблица `targets`

```sql
CREATE TABLE targets (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT,
    link VARCHAR(500) UNIQUE NOT NULL,  -- @username или t.me/...
    title VARCHAR(500),
    niche VARCHAR(100) NOT NULL,  -- 'ukraine_cars', etc.
    status VARCHAR(50) DEFAULT 'new',  -- 'new', 'joined', 'error', 'banned'
    assigned_account_id INTEGER REFERENCES accounts(id) ON DELETE SET NULL,
    joined_at TIMESTAMP,
    warmup_ends_at TIMESTAMP,  -- joined_at + 24h
    last_post_at TIMESTAMP,
    daily_posts_in_group INTEGER DEFAULT 0,  -- Лимит 2 поста
    last_group_stats_reset TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

**Поля:**
- `link` - уникальная ссылка на группу (нормализованная: @username)
- `niche` - ниша группы
- `assigned_account_id` - **строгая привязка** к аккаунту
- `joined_at` - время вступления аккаунта
- `warmup_ends_at` - время окончания warm-up (joined_at + 24h)
- `daily_posts_in_group` - счетчик постов в группу за день (макс 2)

### Таблица `post_history`

```sql
CREATE TABLE post_history (
    id SERIAL PRIMARY KEY,
    account_id INTEGER REFERENCES accounts(id) ON DELETE CASCADE,
    target_id INTEGER REFERENCES targets(id) ON DELETE CASCADE,
    message_content TEXT,
    photo_path VARCHAR(500),
    status VARCHAR(50) DEFAULT 'success',  -- 'success', 'error', 'flood_wait', 'skipped'
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

## 📦 Установка и настройка

### 1. Зависимости

Добавьте в `requirements.txt`:

```
sqlalchemy[asyncio]>=2.0.0
asyncpg>=0.29.0
```

### 2. Переменные окружения

В `docker-compose.lexus.yml` добавьте:

```yaml
environment:
  - DATABASE_URL=postgresql+asyncpg://telegram_user_bali:telegram_password_bali@postgres:5432/telegram_promotion_bali
  # Или по отдельным переменным:
  - POSTGRES_HOST=postgres
  - POSTGRES_PORT=5432
  - POSTGRES_USER=telegram_user_bali
  - POSTGRES_PASSWORD=telegram_password_bali
  - POSTGRES_DB=telegram_promotion_bali
```

### 3. Подключение к существующей БД

Если у вас уже есть PostgreSQL для Bali системы, можно использовать её:

```yaml
environment:
  - DATABASE_URL=postgresql+asyncpg://telegram_user_bali:telegram_password_bali@telegram-bali-postgres:5432/telegram_promotion_bali
```

Или создать отдельную БД для Lexus (рекомендуется).

## 🔄 Миграция данных

### Шаг 1: Запуск скрипта миграции

```bash
cd /home/tovgrishkoff/PIAR/telegram_promotion_system_bali
python3 lexus_db/migrate_from_files.py
```

Скрипт:
1. Читает `targets.txt` и `group_niches.json`
2. Читает `accounts_config.json` и `lexus_accounts_config.json`
3. Читает `group_account_assignments.json` (если есть)
4. Создает записи в таблицах `accounts` и `targets`
5. Привязывает группы к аккаунтам (если есть assignments)

### Шаг 2: Проверка результатов

```bash
# Подключитесь к БД
docker exec -it telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali

# Проверьте количество записей
SELECT COUNT(*) FROM accounts;
SELECT COUNT(*) FROM targets WHERE niche = 'ukraine_cars';
SELECT COUNT(*) FROM targets WHERE assigned_account_id IS NOT NULL;
```

## 💻 Использование в коде

### Пример 1: Получение групп, готовых для постинга

```python
from lexus_db.session import AsyncSessionLocal
from lexus_db.db_manager import DbManager

async with AsyncSessionLocal() as session:
    db_manager = DbManager(session)
    
    # Получить группы, готовые для постинга
    ready_groups = await db_manager.get_groups_ready_for_posting(
        niche='ukraine_cars',
        limit=50
    )
    
    for group in ready_groups:
        account = group.assigned_account
        print(f"Group: {group.link}, Account: {account.session_name}")
        print(f"  Warm-up finished: {group.is_warmup_finished()}")
        print(f"  Daily posts in group: {group.daily_posts_in_group}/2")
        print(f"  Account daily posts: {account.daily_posts_count}/20")
```

### Пример 2: Привязка группы к аккаунту (после вступления)

```python
async with AsyncSessionLocal() as session:
    db_manager = DbManager(session)
    
    # После успешного вступления
    success = await db_manager.assign_group(
        group_link='@autobazar_com_ua',
        account_id=1,  # ID аккаунта из БД
        joined_at=datetime.utcnow()
    )
    
    if success:
        print("✅ Group assigned successfully")
```

### Пример 3: Запись поста в историю

```python
async with AsyncSessionLocal() as session:
    db_manager = DbManager(session)
    
    # После успешного поста
    await db_manager.record_post(
        account_id=1,
        target_id=5,
        message_content="Продается Lexus IS 250...",
        photo_path="/app/lexus_assets/lexus_variant_1.jpg",
        status='success'
    )
    
    # Или при ошибке
    await db_manager.record_post(
        account_id=1,
        target_id=5,
        status='error',
        error_message="FloodWait: 3600 seconds"
    )
```

### Пример 4: Обработка FloodWait

```python
async with AsyncSessionLocal() as session:
    db_manager = DbManager(session)
    
    # Установка FloodWait
    wait_until = datetime.utcnow() + timedelta(seconds=3600)
    await db_manager.set_account_flood_wait(
        account_id=1,
        wait_until=wait_until
    )
    
    # Очистка FloodWait (когда время прошло)
    await db_manager.clear_account_flood_wait(account_id=1)
```

## 🔍 Методы DbManager

### `assign_group(group_link, account_id, joined_at=None) -> bool`
Привязка группы к аккаунту после вступления.

### `get_groups_ready_for_posting(niche='ukraine_cars', limit=None) -> List[Target]`
Получить группы, готовые для постинга (с учетом всех ограничений).

### `record_post(account_id, target_id, message_content, photo_path, status, error_message) -> bool`
Запись поста в историю и обновление счетчиков.

### `set_account_flood_wait(account_id, wait_until)`
Установка FloodWait для аккаунта.

### `clear_account_flood_wait(account_id)`
Очистка FloodWait для аккаунта.

### `reset_daily_counters_if_needed()`
Автоматический сброс дневных счетчиков (вызывается автоматически в других методах).

## 📝 Важные замечания

1. **Сброс счетчиков:** Метод `get_groups_ready_for_posting()` автоматически сбрасывает счетчики, если наступил новый день.

2. **Нормализация ссылок:** Все ссылки на группы нормализуются (t.me/group → @group).

3. **Warm-up период:** Группа становится доступной для постинга только после `warmup_ends_at`.

4. **Строгая привязка:** Если группа уже привязана к аккаунту, её нельзя перепривязать к другому.

5. **Лимиты:** Проверяются перед каждым постом:
   - `daily_posts_in_group < 2` (лимит группы)
   - `daily_posts_count < 20` (лимит аккаунта)

## 🐳 Docker совместимость

Все настройки БД передаются через переменные окружения:
- `DATABASE_URL` - полный URL подключения (приоритет)
- Или отдельные переменные: `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`

Система автоматически определяет, работает ли в Docker, и использует правильный хост.
