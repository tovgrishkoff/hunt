#!/usr/bin/env python3
"""
Скрипт для отправки сообщения пользователю о продлении подписки
"""

import asyncio
import sys
import os

# Добавляем путь к проекту
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backup_working_version'))

from aiogram import Bot
from config import TELEGRAM_BOT_TOKEN

async def send_subscription_message():
    """Отправляет сообщение пользователю о продлении подписки"""
    
    user_id = 418544967
    
    message_text = """👋 Привет!

Ваша подписка истекла, но мы добавили вам бонусом 4 дня, чтобы вы могли продолжить пользоваться сервисом! 🎁

Будете ли вы продлевать подписку? Если да, напишите, пожалуйста, нам — мы подготовим всё необходимое.

Спасибо, что используете наш сервис! 🙏"""
    
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        
        print(f"📤 Отправка сообщения пользователю {user_id}...")
        await bot.send_message(user_id, message_text)
        print(f"✅ Сообщение успешно отправлено пользователю {user_id}")
        
        await bot.session.close()
        
    except Exception as e:
        print(f"❌ Ошибка при отправке сообщения: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(send_subscription_message())
    sys.exit(exit_code)

