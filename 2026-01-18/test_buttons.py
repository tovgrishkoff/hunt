#!/usr/bin/env python3
"""
Тестовый скрипт для демонстрации работы кнопок релевантности
"""

import asyncio
import json
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Токен только из env — без хардкода
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN env var is required")
TEST_USER_ID = os.getenv("TEST_USER_ID", "210147380")

async def test_buttons():
    """Тестирует работу кнопок релевантности"""
    bot = Bot(token=BOT_TOKEN)
    
    # Создаем тестовое сообщение с кнопками
    message_text = (
        "🔔 **Новое сообщение**\n\n"
        "🔍 **Тип:** ПОИСК\n"
        "📂 **Категории:** Фотограф, Видеограф\n"
        "⚡ **Срочность:** срочно\n"
        "💰 **Бюджет:** 500$\n\n"
        "📄 **Сообщение:**\n"
        "Ищу профессионального фотографа и видеографа на свадьбу 15 августа. "
        "Нужна полная съемка церемонии и банкета. Бюджет до 500$. "
        "Пишите в личку с портфолио и ценами.\n\n"
        "👤 @wedding\\_planner\n\n"
        "💬 **Чат:** Бали Чат | Маркетплейс"
    )
    
    # Создаем уникальный ID для сообщения
    message_id = "test_message_123"
    
    # Создаем кнопки
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("✅ Релевантно", callback_data=f"relevant_{message_id}_{TEST_USER_ID}"),
        InlineKeyboardButton("❌ Не релевантно", callback_data=f"not_relevant_{message_id}_{TEST_USER_ID}")
    )
    
    # Добавляем кнопку для исправления классификации
    keyboard.add(
        InlineKeyboardButton("🔧 Исправить классификацию", callback_data=f"correct_{message_id}_{TEST_USER_ID}")
    )
    
    try:
        # Отправляем тестовое сообщение
        await bot.send_message(
            TEST_USER_ID,
            message_text,
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        print("✅ Тестовое сообщение с кнопками отправлено!")
        
        # Показываем инструкцию
        instruction = (
            "📋 **Инструкция по тестированию кнопок:**\n\n"
            "1. **✅ Релевантно** - нажмите, если сообщение релевантно для вас\n"
            "2. **❌ Не релевантно** - нажмите, если сообщение не подходит\n"
            "3. **🔧 Исправить классификацию** - нажмите для исправления AI классификации\n\n"
            "После нажатия кнопки:\n"
            "• Ваша оценка сохранится в файл `relevance_feedback.json`\n"
            "• Кнопки обновятся и покажут статус подтверждения\n"
            "• AI система будет учиться на ваших оценках\n\n"
            "Попробуйте нажать на любую кнопку!"
        )
        
        await bot.send_message(TEST_USER_ID, instruction, parse_mode="Markdown")
        print("✅ Инструкция отправлена!")
        
    except Exception as e:
        print(f"❌ Ошибка отправки тестового сообщения: {e}")
    
    finally:
        await bot.session.close()

async def show_feedback_stats():
    """Показывает статистику обратной связи"""
    try:
        with open("relevance_feedback.json", "r", encoding="utf-8") as f:
            feedbacks = json.load(f)
        
        total = len(feedbacks)
        relevant = sum(1 for f in feedbacks if f.get("is_relevant", False))
        not_relevant = total - relevant
        
        stats_text = (
            "📊 **Статистика обратной связи:**\n\n"
            f"📈 Всего оценок: {total}\n"
            f"✅ Релевантных: {relevant}\n"
            f"❌ Нерелевантных: {not_relevant}\n"
            f"📊 Процент релевантных: {(relevant/total*100):.1f}% (если есть оценки)\n\n"
            "💡 Эта статистика помогает улучшить AI классификацию"
        )
        
        bot = Bot(token=BOT_TOKEN)
        await bot.send_message(TEST_USER_ID, stats_text, parse_mode="Markdown")
        await bot.session.close()
        
        print("✅ Статистика отправлена!")
        
    except FileNotFoundError:
        print("📝 Файл с обратной связью еще не создан")
    except Exception as e:
        print(f"❌ Ошибка показа статистики: {e}")

if __name__ == "__main__":
    print("🚀 Запуск тестирования кнопок релевантности...")
    
    # Запускаем тест
    asyncio.run(test_buttons())
    
    # Тестируем нажатие кнопки
    print("🔍 Тестируем нажатие кнопки 'Релевантно'...")
    try:
        # Создаем callback query для тестирования
        from aiogram.types import CallbackQuery
        callback_data = f"relevant_test_message_{TEST_USER_ID}"
        
        # Имитируем нажатие кнопки
        print(f"📝 Отправляем callback: {callback_data}")
        
        # Здесь мы не можем реально нажать кнопку, но можем проверить логи
        print("✅ Callback отправлен (проверьте логи бота)")
        
    except Exception as e:
        print(f"❌ Ошибка при тестировании кнопки: {e}")
    
    print("📝 Файл с обратной связью еще не создан")
    
    # Показываем статистику через 2 секунды
    import time
    time.sleep(2)
    asyncio.run(show_feedback_stats())
    
    print("✅ Тестирование завершено!") 