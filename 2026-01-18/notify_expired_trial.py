#!/usr/bin/env python3
"""
Скрипт для отправки уведомлений пользователям с истекшим триалом
о необходимости оформления подписки
"""

import asyncio
import logging
import sys
from datetime import datetime, timezone
from aiogram import Bot
from aiogram.utils.exceptions import TelegramAPIError, ChatNotFound, BotBlocked
import asyncpg
from config import BOT_TOKEN, DB_DSN

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

MANAGER_USERNAME = "@huansya0"

MESSAGE_TEXT = f"""⏰ *Ваш триальный период истек*

Вы больше не получаете уведомления о новых сообщениях из Telegram-чатов.

Чтобы продолжить пользоваться сервисом, необходимо оформить подписку.

📞 *Свяжитесь с менеджером для оформления подписки:*
👤 Менеджер: {MANAGER_USERNAME}

💬 Напишите менеджеру в Telegram для получения информации о подписке и её оформления.

После оплаты менеджер активирует подписку, и вы снова будете получать уведомления!

Спасибо за использование нашего сервиса! 🙏"""


async def get_expired_trial_users(conn):
    """Получает пользователей с истекшим триалом, но с выбранными нишами"""
    now = datetime.now(timezone.utc)
    
    query = '''
        SELECT 
            user_id,
            categories,
            trial_until,
            subscription_active
        FROM subscribers
        WHERE (subscription_active = FALSE OR subscription_active IS NULL)
        AND trial_until IS NOT NULL
        AND trial_until <= $1
        AND categories IS NOT NULL
        AND categories != '[]'::jsonb
        AND user_id != '210147380'
        ORDER BY trial_until DESC
    '''
    
    rows = await conn.fetch(query, now)
    return rows


async def send_notification(bot: Bot, user_id: int):
    """Отправляет уведомление пользователю"""
    try:
        await bot.send_message(
            user_id,
            MESSAGE_TEXT,
            parse_mode="Markdown"
        )
        logger.info(f"✅ Уведомление отправлено пользователю {user_id}")
        return True
    except (ChatNotFound, BotBlocked) as e:
        logger.warning(f"⚠️ Пользователь {user_id} не найден или заблокировал бота: {e}")
        return False
    except TelegramAPIError as e:
        logger.error(f"❌ Ошибка API Telegram при отправке пользователю {user_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка при отправке пользователю {user_id}: {e}")
        return False


async def main():
    """Основная функция"""
    logger.info("🚀 Запуск скрипта отправки уведомлений пользователям с истекшим триалом")
    
    # Подключаемся к базе данных
    conn = None
    bot = None
    
    try:
        # Подключаемся к БД
        conn = await asyncpg.connect(DB_DSN)
        logger.info("✅ Подключено к базе данных")
        
        # Получаем список пользователей с истекшим триалом
        users = await get_expired_trial_users(conn)
        logger.info(f"📊 Найдено {len(users)} пользователей с истекшим триалом и выбранными нишами")
        
        if not users:
            logger.info("ℹ️ Нет пользователей для отправки уведомлений")
            return
        
        # Инициализируем бота
        bot = Bot(token=BOT_TOKEN)
        logger.info("✅ Бот инициализирован")
        
        # Отправляем уведомления
        stats = {
            'total': len(users),
            'sent': 0,
            'errors': 0,
            'blocked': 0
        }
        
        for user in users:
            user_id = user['user_id']
            categories = user['categories']
            trial_until = user['trial_until']
            
            logger.info(f"📤 Отправка уведомления пользователю {user_id} (триал истек: {trial_until}, ниши: {categories})")
            
            success = await send_notification(bot, user_id)
            
            if success:
                stats['sent'] += 1
            else:
                stats['errors'] += 1
                stats['blocked'] += 1  # Если отправка не удалась, вероятно пользователь заблокировал бота
            
            # Небольшая задержка между отправками, чтобы не превысить лимиты API
            await asyncio.sleep(0.5)
        
        # Выводим статистику
        logger.info("=" * 60)
        logger.info("📊 СТАТИСТИКА ОТПРАВКИ:")
        logger.info(f"   Всего пользователей: {stats['total']}")
        logger.info(f"   ✅ Успешно отправлено: {stats['sent']}")
        logger.info(f"   ❌ Ошибок: {stats['errors']}")
        logger.info(f"   🚫 Заблокировали бота: {stats['blocked']}")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)
    
    finally:
        # Закрываем соединения
        if bot:
            await bot.session.close()
        if conn:
            await conn.close()
        logger.info("✅ Соединения закрыты")


if __name__ == "__main__":
    asyncio.run(main())
