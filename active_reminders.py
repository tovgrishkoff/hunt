#!/usr/bin/env python3
"""
Активная система напоминаний для пользователей с истекшими триалами
Отправляет напоминания каждые 2-3 дня пользователям, которые не подписались после истечения триала
"""

import asyncio
import asyncpg
from datetime import datetime, timezone, timedelta
import os
import requests
import time
import logging
from dotenv import load_dotenv

# Загружаем переменные окружения из .env.docker или .env
load_dotenv('.env.docker')
load_dotenv('.env')  # Резервный вариант
load_dotenv()  # Загружаем из текущей директории

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('active_reminders.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Настройки подключения к БД
# Если запускаемся вне Docker, используем localhost
# Если внутри Docker, используем имя сервиса postgres
DB_HOST = os.getenv('DB_HOST', 'localhost')
# Если DB_HOST=postgres (для Docker), но мы запущены локально - используем localhost
if DB_HOST == 'postgres' and not os.path.exists('/.dockerenv'):
    DB_HOST = 'localhost'
    logger.info("⚠️ Обнаружен DB_HOST=postgres, но запуск вне Docker. Используем localhost")

DB_PORT = os.getenv('DB_PORT', '5434')
# Если порт из .env.docker (5432), но запуск локально - используем 5434
if DB_PORT == '5432' and DB_HOST == 'localhost':
    DB_PORT = '5434'

DB_NAME = os.getenv('DB_NAME', 'bali_bot')
DB_USER = os.getenv('DB_USER', 'grishkoff')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'testpass')
BOT_TOKEN = os.getenv('BOT_TOKEN')

# Интервал между отправками напоминаний (в днях)
REMINDER_INTERVAL_DAYS = 2  # Отправляем каждые 2 дня

# Тексты напоминаний (разные варианты для разнообразия)
REMINDER_MESSAGES = [
    """
👋 Привет! 

Я заметил, что твой триальный период закончился, но ты еще не оформил подписку.

🎯 **Почему стоит вернуться:**

✅ Получай уведомления о новых возможностях в твоих нишах
✅ Не пропусти важные предложения от клиентов
✅ Экономь время на поиске заказов

💎 **Специальное предложение для возвращающихся пользователей!**

Нажми кнопку ниже, чтобы оформить подписку и продолжить получать уведомления:
""",
    """
🔔 Напоминание!

Твой триальный период закончился, но мы скучаем по тебе!

📊 **Что ты упускаешь:**
• Новые заказы в твоих категориях
• Возможности для сотрудничества
• Актуальные предложения на рынке Бали

🚀 **Вернись и продолжай получать уведомления!**

Оформи подписку прямо сейчас:
""",
    """
💼 Привет!

Твой триал истек, но возможности для бизнеса продолжают появляться каждый день!

🎯 **Вернись к нам и получи:**
• Мгновенные уведомления о новых заказах
• Фильтрацию по твоим категориям
• Прямые контакты с клиентами

💎 **Не упусти свой шанс!**

Оформи подписку и продолжай развивать свой бизнес:
""",
    """
👋 С возвращением!

Мы заметили, что ты давно не заходил в бот после окончания триала.

🎁 **Специальное предложение:**
Вернись сейчас и получи доступ ко всем функциям бота!

✅ Уведомления о новых заказах
✅ Фильтрация по категориям
✅ Прямые контакты с клиентами

Нажми кнопку ниже, чтобы оформить подписку:
"""
]

async def create_reminder_tracking_table(conn):
    """Создает таблицу для отслеживания отправленных напоминаний"""
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS reminder_tracking (
            user_id BIGINT PRIMARY KEY,
            last_reminder_sent TIMESTAMP WITH TIME ZONE,
            reminder_count INTEGER DEFAULT 0,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    ''')
    logger.info("✅ Таблица reminder_tracking проверена/создана")

async def get_expired_users(conn, days_since_expiry=7):
    """Получает пользователей с истекшими триалами (более указанного количества дней назад)"""
    now = datetime.now(timezone.utc)
    expiry_threshold = now - timedelta(days=days_since_expiry)
    
    users = await conn.fetch('''
        SELECT 
            s.user_id,
            s.trial_until,
            s.subscription_active,
            s.created_at,
            COALESCE(rt.last_reminder_sent, s.trial_until) as last_reminder,
            COALESCE(rt.reminder_count, 0) as reminder_count
        FROM subscribers s
        LEFT JOIN reminder_tracking rt ON s.user_id = rt.user_id
        WHERE s.subscription_active = FALSE
        AND s.trial_until IS NOT NULL
        AND s.trial_until < $1
        AND COALESCE(s.bot_blocked, FALSE) = FALSE
        AND s.user_id != 210147380
        ORDER BY s.trial_until DESC
    ''', expiry_threshold)
    
    return users

async def should_send_reminder(user, now):
    """Проверяет, нужно ли отправить напоминание пользователю"""
    last_reminder = user['last_reminder']
    reminder_count = user['reminder_count']
    
    # Если напоминание еще не отправлялось, отправляем сразу
    if not last_reminder:
        return True
    
    # Проверяем, прошло ли достаточно времени с последнего напоминания
    days_since_last = (now - last_reminder).days
    
    # Отправляем каждые 2 дня
    # УБРАНО ОГРАНИЧЕНИЕ: отправляем напоминания регулярно, пока бот не заблокирован
    if days_since_last >= REMINDER_INTERVAL_DAYS:
        return True
    
    return False

async def update_reminder_tracking(conn, user_id, now):
    """Обновляет информацию о последнем отправленном напоминании"""
    await conn.execute('''
        INSERT INTO reminder_tracking (user_id, last_reminder_sent, reminder_count)
        VALUES ($1, $2, 1)
        ON CONFLICT (user_id) 
        DO UPDATE SET 
            last_reminder_sent = $2,
            reminder_count = reminder_tracking.reminder_count + 1
    ''', user_id, now)

async def send_reminder_to_user(
    user_id, message_text, reminder_number, bot_token=None, parse_mode="Markdown"
):
    """Отправляет напоминание пользователю через Telegram API"""
    if bot_token is None:
        bot_token = BOT_TOKEN or os.getenv('BOT_TOKEN')
    
    if not bot_token:
        logger.error(f"❌ BOT_TOKEN не установлен для отправки пользователю {user_id}")
        return False
    
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        
        # Создаем клавиатуру с кнопками
        keyboard = {
            "inline_keyboard": [
                [{"text": "⭐ Оформить подписку", "callback_data": "pay_subscribe"}],
                [{"text": "📋 Меню", "callback_data": "menu"}]
            ]
        }
        
        data = {
            "chat_id": user_id,
            "text": message_text,
            "parse_mode": parse_mode,
            "reply_markup": keyboard
        }
        
        response = requests.post(url, json=data, timeout=10)
        
        if response.status_code == 200:
            logger.info(f"✅ Напоминание #{reminder_number} отправлено пользователю {user_id}")
            return True
        if response.status_code == 403 or "blocked" in response.text.lower():
            logger.warning(f"🚫 Пользователь {user_id} заблокировал бота")
            return "blocked"
        logger.error(f"❌ Ошибка отправки пользователю {user_id}: {response.text}")
        return False
            
    except Exception as e:
        logger.error(f"❌ Ошибка отправки пользователю {user_id}: {e}")
        return False

ZERO_LEADS_MESSAGE = """
📊 <b>7 дней в триале — 0 лидов</b>

Вы уже настроили ниши, но за неделю не пришло ни одного уведомления. Частые причины:

• В нише мало спроса в выбранных чатах (попробуйте соседнюю нишу или снимите фильтр стран)
• Слишком узкий фильтр по странам
• Триал совпал с тихим периодом в чатах

Напишите @huansya0 — поможем подобрать ниши. Или оформите подписку и расширьте охват:
"""


async def send_zero_leads_trial_reminders(conn, bot_token):
    """Один раз: ≥7 дней триала и 0 лидов."""
    await conn.execute(
        """
        ALTER TABLE subscribers
        ADD COLUMN IF NOT EXISTS trial_zero_leads_reminder_sent BOOLEAN DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS trial_started_at TIMESTAMP WITH TIME ZONE,
        ADD COLUMN IF NOT EXISTS trial_leads_count INTEGER DEFAULT 0,
        ADD COLUMN IF NOT EXISTS bot_blocked BOOLEAN DEFAULT FALSE
        """
    )
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(days=7)
    users = await conn.fetch(
        """
        SELECT user_id, trial_leads_count, categories
        FROM subscribers
        WHERE subscription_active IS NOT TRUE
          AND trial_until IS NOT NULL
          AND trial_until > $1
          AND COALESCE(trial_started_at, created_at) <= $2
          AND COALESCE(trial_leads_count, 0) = 0
          AND COALESCE(trial_zero_leads_reminder_sent, FALSE) = FALSE
          AND COALESCE(bot_blocked, FALSE) = FALSE
          AND categories IS NOT NULL
          AND categories::text NOT IN ('[]', 'null', '')
        """,
        now,
        threshold,
    )
    sent = 0
    for u in users:
        uid = u["user_id"]
        result = await send_reminder_to_user(
            uid, ZERO_LEADS_MESSAGE, 0, bot_token, parse_mode="HTML"
        )
        if result is True:
            await conn.execute(
                "UPDATE subscribers SET trial_zero_leads_reminder_sent = TRUE WHERE user_id = $1",
                uid,
            )
            sent += 1
        elif result == "blocked":
            await conn.execute(
                "UPDATE subscribers SET bot_blocked = TRUE WHERE user_id = $1", uid
            )
        await asyncio.sleep(0.5)
    logger.info(f"📭 Zero-leads trial reminders sent: {sent}")


async def send_active_reminders():
    """Основная функция отправки активных напоминаний"""
    # Проверяем BOT_TOKEN (может быть загружен из разных источников)
    bot_token = BOT_TOKEN or os.getenv('BOT_TOKEN')
    if not bot_token:
        logger.error("❌ BOT_TOKEN не установлен! Проверьте переменные окружения.")
        logger.error("   Убедитесь, что файл .env.docker содержит BOT_TOKEN")
        logger.error("   Или установите переменную окружения: export BOT_TOKEN=...")
        return
    
    logger.info(f"✅ BOT_TOKEN загружен (длина: {len(bot_token)} символов)")
    
    # Подключаемся к БД
    db_dsn = f'postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
    logger.info(f"🔌 Подключение к БД: {DB_HOST}:{DB_PORT}/{DB_NAME}")
    try:
        conn = await asyncpg.connect(db_dsn, timeout=10)
        logger.info("✅ Подключение к БД успешно")
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к БД: {e}")
        logger.error(f"   Проверьте настройки: host={DB_HOST}, port={DB_PORT}, db={DB_NAME}")
        return
    
    try:
        # Создаем таблицу для отслеживания
        await create_reminder_tracking_table(conn)

        try:
            from trial_pre_expiry_reminders import send_trial_pre_expiry_reminders

            await send_trial_pre_expiry_reminders()
        except Exception as e:
            logger.error(f"Pre-expiry reminders error: {e}")

        await send_zero_leads_trial_reminders(conn, bot_token)
        
        # Получаем пользователей с истекшими триалами (более 7 дней назад)
        logger.info("🔍 Поиск пользователей с истекшими триалами...")
        users = await get_expired_users(conn, days_since_expiry=7)
        
        logger.info(f"📊 Найдено {len(users)} пользователей с истекшими триалами")
        
        if len(users) == 0:
            logger.info("✅ Нет пользователей для отправки напоминаний")
            return
        
        # Текущее время
        now = datetime.now(timezone.utc)
        
        # Отправляем напоминания
        sent = 0
        skipped = 0
        failed = 0
        
        for user in users:
            user_id = user['user_id']
            reminder_count = user['reminder_count']
            
            # Проверяем, нужно ли отправить напоминание
            if not await should_send_reminder(user, now):
                skipped += 1
                days_since = (now - user['last_reminder']).days if user['last_reminder'] else 0
                logger.info(f"⏭️ Пропуск пользователя {user_id} (последнее напоминание {days_since} дней назад, всего: {reminder_count})")
                continue
            
            # Выбираем текст напоминания (циклически)
            message_text = REMINDER_MESSAGES[reminder_count % len(REMINDER_MESSAGES)]
            
            # Отправляем напоминание (используем bot_token из области видимости функции)
            result = await send_reminder_to_user(
                user_id, message_text, reminder_count + 1, bot_token
            )
            if result is True:
                await update_reminder_tracking(conn, user_id, now)
                sent += 1
            elif result == "blocked":
                await conn.execute(
                    "UPDATE subscribers SET bot_blocked = TRUE WHERE user_id = $1", user_id
                )
                failed += 1
            else:
                failed += 1
            
            # Небольшая задержка между отправками
            await asyncio.sleep(0.5)
        
        logger.info("=" * 60)
        logger.info(f"📊 Итого:")
        logger.info(f"  ✅ Отправлено: {sent}")
        logger.info(f"  ⏭️ Пропущено: {skipped}")
        logger.info(f"  ❌ Ошибок: {failed}")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        await conn.close()

if __name__ == "__main__":
    logger.info("🚀 Запуск системы активных напоминаний")
    logger.info("=" * 60)
    asyncio.run(send_active_reminders())

