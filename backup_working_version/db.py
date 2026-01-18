import aiosqlite
from datetime import datetime, timedelta
from config import TRIAL_DAYS
import json
from typing import Optional, Dict, List
import logging

logger = logging.getLogger(__name__)

DB_PATH = "users.db"

async def init_db():
    """Инициализация базы данных"""
    async with aiosqlite.connect(DB_PATH) as db:
        # Создаем таблицу пользователей
        await db.execute('''CREATE TABLE IF NOT EXISTS users
                     (user_id INTEGER PRIMARY KEY,
                      username TEXT,
                      topic TEXT,
                      registered_at TIMESTAMP,
                      trial_ends_at TIMESTAMP,
                      subscription BOOLEAN DEFAULT 0)''')
        
        # Проверяем существование колонок
        async with db.execute("PRAGMA table_info(users)") as cursor:
            columns = [column[1] for column in await cursor.fetchall()]
            
        # Добавляем отсутствующие колонки
        if 'trial_ends_at' not in columns:
            await db.execute('ALTER TABLE users ADD COLUMN trial_ends_at TIMESTAMP')
        if 'subscription' not in columns:
            await db.execute('ALTER TABLE users ADD COLUMN subscription BOOLEAN DEFAULT 0')
        
        # Создаем таблицу настроек пользователя
        await db.execute('''CREATE TABLE IF NOT EXISTS user_settings
                     (user_id INTEGER PRIMARY KEY,
                      notification_frequency TEXT DEFAULT 'instant',
                      is_paused BOOLEAN DEFAULT 0,
                      custom_keywords TEXT,
                      FOREIGN KEY (user_id) REFERENCES users(user_id))''')
        
        # Создаем таблицу выбранных ключевых слов
        await db.execute('''CREATE TABLE IF NOT EXISTS user_keywords
                     (user_id INTEGER,
                      keyword_category TEXT,
                      keyword TEXT,
                      FOREIGN KEY (user_id) REFERENCES users(user_id),
                      PRIMARY KEY (user_id, keyword_category, keyword))''')
        
        # Создаем таблицу подписок по нишам
        await db.execute('''CREATE TABLE IF NOT EXISTS user_niches
                     (user_id INTEGER,
                      niche TEXT,
                      PRIMARY KEY (user_id, niche),
                      FOREIGN KEY (user_id) REFERENCES users(user_id))''')
        
        await db.commit()

async def add_user(user_id: int, username: str, topic: str = None):
    """Добавление нового пользователя"""
    async with aiosqlite.connect(DB_PATH) as db:
        # Добавляем пользователя
        await db.execute('''INSERT OR IGNORE INTO users 
                     (user_id, username, registered_at, trial_ends_at, subscription, topic)
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  (user_id, username, datetime.now(), 
                   datetime.now() + timedelta(hours=1), False, topic))
        
        # Добавляем настройки по умолчанию
        await db.execute('''INSERT OR IGNORE INTO user_settings 
                     (user_id, notification_frequency, is_paused, custom_keywords)
                     VALUES (?, 'instant', 0, '[]')''',
                  (user_id,))
        
        await db.commit()

async def get_user_keywords(user_id: int) -> dict:
    """Получить выбранные пользователем ключевые слова"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('''SELECT keyword_category, keyword 
                     FROM user_keywords 
                     WHERE user_id = ?''', (user_id,)) as cursor:
            rows = await cursor.fetchall()
            
            keywords = {}
            for category, keyword in rows:
                if category not in keywords:
                    keywords[category] = []
                keywords[category].append(keyword)
            
            return keywords

async def add_user_keyword(user_id: int, category: str, keyword: str):
    """Добавить ключевое слово для пользователя"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''INSERT OR IGNORE INTO user_keywords 
                     (user_id, keyword_category, keyword)
                     VALUES (?, ?, ?)''', (user_id, category, keyword))
        await db.commit()

async def remove_user_keyword(user_id: int, category: str, keyword: str):
    """Удалить ключевое слово у пользователя"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''DELETE FROM user_keywords 
                     WHERE user_id = ? AND keyword_category = ? AND keyword = ?''',
                  (user_id, category, keyword))
        await db.commit()

async def get_all_users() -> List[Dict]:
    """Получает список всех пользователей"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM users') as cursor:
                users = await cursor.fetchall()
                return [dict(user) for user in users]
    except Exception as e:
        logger.error(f"Ошибка при получении списка пользователей: {e}")
        return []

async def get_user(user_id: int) -> Optional[Dict]:
    """Получает информацию о пользователе"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)) as cursor:
                user = await cursor.fetchone()
                return dict(user) if user else None
    except Exception as e:
        logger.error(f"Ошибка при получении пользователя: {e}")
        return None

async def get_user_settings(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT * FROM user_settings WHERE user_id = ?', (user_id,)) as cursor:
            return await cursor.fetchone()

async def update_user_settings(user_id: int, settings: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''UPDATE user_settings 
                     SET notification_frequency = ?,
                         is_paused = ?,
                         custom_keywords = ?
                     WHERE user_id = ?''',
                  (settings.get('notification_frequency', 'instant'),
                   settings.get('is_paused', False),
                   json.dumps(settings.get('custom_keywords', [])),
                   user_id))
        await db.commit()
        print(f"DEBUG: user {user_id} pause status set to {settings.get('is_paused')}")

async def activate_subscription(user_id: int, days: int):
    async with aiosqlite.connect(DB_PATH) as db:
        # Получаем текущую дату окончания подписки
        async with db.execute('SELECT trial_ends_at FROM users WHERE user_id = ?', (user_id,)) as cursor:
            current_end = await cursor.fetchone()
            if current_end:
                current_end = datetime.strptime(current_end[0], '%Y-%m-%d %H:%M:%S.%f')
                new_end = current_end + timedelta(days=days)
            else:
                new_end = datetime.now() + timedelta(days=days)
        
        # Обновляем дату окончания подписки
        await db.execute('''UPDATE users 
                     SET trial_ends_at = ?,
                         is_active = 1
                     WHERE user_id = ?''',
                  (new_end, user_id))
        await db.commit()

async def check_subscription(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('''SELECT trial_ends_at, is_active 
                     FROM users 
                     WHERE user_id = ?''', (user_id,)) as cursor:
            result = await cursor.fetchone()
            if not result:
                return False
            
            trial_ends_at, is_active = result
            if not is_active:
                return False
            
            if not trial_ends_at:
                return False
            
            trial_ends_at = datetime.strptime(trial_ends_at, '%Y-%m-%d %H:%M:%S.%f')
            return datetime.now() < trial_ends_at

async def deactivate_subscription(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET is_active = 0 WHERE user_id = ?', (user_id,))
        await db.commit()

async def add_user_niche(user_id: int, niche: str):
    """Добавить подписку пользователя на нишу"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''INSERT OR IGNORE INTO user_niches (user_id, niche) VALUES (?, ?)''', (user_id, niche))
        await db.commit()

async def get_user_niches(user_id: int) -> list:
    """Get all niches that user is subscribed to"""
    async with aiosqlite.connect("users.db") as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT niche FROM user_niches WHERE user_id = ?",
            (user_id,)
        )
        rows = await cursor.fetchall()
        return [row["niche"] for row in rows]

async def get_subscribers_for_niche(niche: str):
    """Получить список user_id, подписанных на нишу"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('''SELECT user_id FROM user_niches WHERE niche = ?''', (niche,)) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

async def remove_user_niche(user_id: int, niche: str):
    """Удалить подписку пользователя на нишу"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''DELETE FROM user_niches WHERE user_id = ? AND niche = ?''', (user_id, niche))
        await db.commit()

# Инициализация базы данных при импорте
# init_db()  # Удаляем эту строку, так как теперь init_db асинхронная 

# Удаляем неиспользуемую функцию toggle_pause_callback 