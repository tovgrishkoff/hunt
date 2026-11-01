#!/usr/bin/env python3
"""
Скрипт для рассылки напоминания подписчикам о выборе ниш
"""
import asyncio
import logging
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import Database
from config import BOT_TOKEN, DB_DSN

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def broadcast_niches_reminder():
    """Рассылает напоминание подписчикам о выборе ниш"""
    bot = Bot(token=BOT_TOKEN)
    db = Database(dsn=DB_DSN)
    await db.connect()
    
    try:
        # Получаем всех подписчиков
        users = await db.get_all_users()
        logger.info(f"📊 Найдено {len(users)} подписчиков")
        
        sent_count = 0
        failed_count = 0
        skipped_count = 0
        
        message_text = """🔔 **Важное напоминание!**

Чтобы получать уведомления о новых сообщениях в чатах, вам нужно выбрать интересующие вас ниши (категории).

📋 **Доступные ниши:**
• Фотограф
• Видеограф
• Недвижимость (Спрос)
• Недвижимость (Предложение)
• Продажа недвижимости
• Аренда авто
• Аренда байков
• Обмен валют
• Туризм
• Маникюр
• Волосы
• Реснички
• Брови
• Макияж
• Косметология
• Кальяны
• Аренда Playstation
• Медиа-студия
• Транспорт

🌍 **Также не забудьте выбрать страны:**
• Бали
• Таиланд
• Турция

👉 Используйте команду /niche для выбора ниш
👉 Используйте команду /menu → "🌍 Выбрать страну" для выбора стран

После выбора вы начнете получать уведомления о релевантных сообщениях! 🎉"""
        
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("📋 Выбрать ниши", callback_data="show_niches_menu"),
            InlineKeyboardButton("🌍 Выбрать страны", callback_data="show_countries_menu")
        )
        
        for user in users:
            user_id = user['user_id']
            categories = user.get('categories', '[]')
            countries = user.get('countries', '[]')
            
            # Пропускаем пользователей, у которых уже есть ниши
            if categories and categories != '[]':
                try:
                    import json
                    cats = json.loads(categories) if isinstance(categories, str) else categories
                    if cats and len(cats) > 0:
                        skipped_count += 1
                        logger.info(f"⏭️ Пропуск пользователя {user_id} (уже есть ниши: {cats})")
                        continue
                except:
                    pass
            
            try:
                await bot.send_message(
                    user_id,
                    message_text,
                    parse_mode="Markdown",
                    reply_markup=keyboard
                )
                sent_count += 1
                logger.info(f"✅ Сообщение отправлено пользователю {user_id}")
                
                # Небольшая задержка, чтобы не перегружать Telegram API
                await asyncio.sleep(0.1)
                
            except Exception as e:
                failed_count += 1
                logger.error(f"❌ Ошибка отправки пользователю {user_id}: {e}")
        
        logger.info(f"""
📊 Статистика рассылки:
✅ Отправлено: {sent_count}
⏭️ Пропущено (уже есть ниши): {skipped_count}
❌ Ошибок: {failed_count}
📊 Всего подписчиков: {len(users)}
        """)
        
    finally:
        await db.close()
        await bot.close()

if __name__ == "__main__":
    asyncio.run(broadcast_niches_reminder())

