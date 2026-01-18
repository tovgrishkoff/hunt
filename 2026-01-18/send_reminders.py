#!/usr/bin/env python3
"""
Скрипт для отправки напоминаний пользователям о необходимости выбрать ниши
(выбор страны теперь опциональный)
"""

import asyncio
import asyncpg
import json
from datetime import datetime, timezone
from aiogram import Bot
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import BOT_TOKEN, DB_DSN
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def send_reminders():
    """Отправляет напоминания пользователям"""
    try:
        # Подключаемся к базе данных
        conn = await asyncpg.connect(DB_DSN)
        
        # Получаем всех пользователей
        rows = await conn.fetch('SELECT user_id, categories, countries, subscription_active, trial_until FROM subscribers')
        
        # Инициализируем бота
        bot = Bot(token=BOT_TOKEN)
        
        now = datetime.now(timezone.utc)
        
        stats = {
            'total': 0,
            'sent': 0,
            'errors': 0,
            'no_niches': 0,
            'trial_no_setup': 0
        }
        
        for row in rows:
            stats['total'] += 1
            user_id = row['user_id']
            categories = json.loads(row['categories']) if row['categories'] else []
            countries = json.loads(row['countries']) if row['countries'] else []
            subscription_active = row['subscription_active']
            trial_until = row['trial_until']
            
            # Определяем статус
            is_trial = not subscription_active and trial_until and trial_until > now
            has_niches = len(categories) > 0
            has_countries = len(countries) > 0
            
            # Определяем, кому нужно отправить напоминание
            needs_reminder = False
            reminder_type = None
            
            # Убрали проверку на отсутствие стран - выбор страны теперь опциональный
            if not has_niches and has_countries:
                # Есть страны, но нет ниш
                needs_reminder = True
                reminder_type = 'no_niches'
                stats['no_niches'] += 1
            elif is_trial and not has_niches and not has_countries:
                # Триал, но ничего не настроено
                needs_reminder = True
                reminder_type = 'trial_no_setup'
                stats['trial_no_setup'] += 1
            
            if needs_reminder:
                try:
                    if reminder_type == 'no_niches':
                        message_text = (
                            "⚠️ **Важное напоминание!**\n\n"
                            "Вы выбрали страну, но не выбрали ниши.\n\n"
                            "📋 **Инструкция:**\n"
                            "1️⃣ Нажмите на кнопку **🗂 Выбрать нишу**\n"
                            "2️⃣ Выберите интересующие вас ниши\n"
                            "3️⃣ Нажмите **✅ Готово**\n\n"
                            "💡 **Важно:** Без выбора ниш вы не будете получать уведомления!\n\n"
                            f"🎁 На триальном периоде можно выбрать только 1 нишу."
                        )
                    elif reminder_type == 'trial_no_setup':
                        message_text = (
                            "👋 **Добро пожаловать в Lead_Hunterbot!**\n\n"
                            "Вы зарегистрированы, но еще не настроили бота.\n\n"
                            "📋 **Инструкция по настройке:**\n\n"
                            "1️⃣ **Выберите ниши** 🗂\n"
                            "   Нажмите кнопку **🗂 Выбрать нишу**\n"
                            "   Выберите интересующие вас ниши\n"
                            "   Нажмите **✅ Готово**\n\n"
                            "2️⃣ **Фильтрация по странам (опционально)** 🌍\n"
                            "   Нажмите кнопку **🌍 Выбрать страну**\n"
                            "   Если не выберете страны - будете получать уведомления из всех стран\n"
                            "   Если выберете страны - будете получать только из выбранных стран\n\n"
                            "💡 **Важно:** Без выбора ниш вы не будете получать уведомления!\n\n"
                            "⏳ У вас активен триал на 7 дней\n"
                            "🎁 На триальном периоде можно выбрать только 1 нишу.\n"
                            "Оформите подписку для выбора нескольких ниш."
                        )
                    
                    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                    
                    keyboard_buttons = []
                    if reminder_type == 'trial_no_setup':
                        keyboard_buttons.append([InlineKeyboardButton(text="🌍 Выбрать страну", callback_data="show_countries_menu")])
                    if reminder_type in ['no_niches', 'trial_no_setup']:
                        keyboard_buttons.append([InlineKeyboardButton(text="🗂 Выбрать нишу", callback_data="show_niches_menu")])
                    
                    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
                    
                    await bot.send_message(
                        user_id,
                        message_text,
                        parse_mode="Markdown",
                        reply_markup=keyboard
                    )
                    
                    stats['sent'] += 1
                    logger.info(f"✅ Напоминание отправлено пользователю {user_id} (тип: {reminder_type})")
                    
                    # Небольшая задержка, чтобы не перегрузить API
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    stats['errors'] += 1
                    logger.error(f"❌ Ошибка отправки напоминания пользователю {user_id}: {e}")
        
        await bot.session.close()
        await conn.close()
        
        # Выводим статистику
        print("\n" + "="*50)
        print("📊 СТАТИСТИКА ОТПРАВКИ НАПОМИНАНИЙ")
        print("="*50)
        print(f"👥 Всего пользователей: {stats['total']}")
        print(f"✅ Отправлено напоминаний: {stats['sent']}")
        print(f"❌ Ошибок: {stats['errors']}")
        print(f"\n📋 Детализация:")
        print(f"   • Нет ниш (есть страны): {stats['no_niches']}")
        print(f"   • Триал без настройки: {stats['trial_no_setup']}")
        print("="*50)
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(send_reminders())

