#!/usr/bin/env python3
"""
Тестовый скрипт для проверки фильтра инфраструктуры
"""
import asyncio
import sys
import os

# Добавляем путь к модулям
sys.path.insert(0, '/home/tovgrishkoff/mvp2105/backup_working_version')

async def test_filter():
    """Тестирование фильтра через прямое обращение к функции"""
    
    # Импортируем только нужные части
    from monitor import MessageMonitor
    from aiogram import Bot
    from database import Database
    from config import DB_DSN, TELEGRAM_BOT_TOKEN
    
    print("=" * 70)
    print("ТЕСТИРОВАНИЕ ФИЛЬТРА ИНФРАСТРУКТУРЫ")
    print("=" * 70)
    
    # Создаем минимальный монитор (без реальных подключений)
    bot = Bot(token=TELEGRAM_BOT_TOKEN) if TELEGRAM_BOT_TOKEN else None
    db = Database(DB_DSN) if DB_DSN else None
    
    monitor = MessageMonitor(bot, db, openai_api_key=None)
    
    # Тестовые сообщения
    test_messages = [
        ("Просто тц нужен большой рядом с Чангу . Кто знает где ?", True),  # Должно блокироваться
        ("Сдам виллу рядом с торговым центром в Чангу", False),  # НЕ должно блокироваться (есть "сдам")
        ("Где найти аптеку рядом с Убудом?", True),  # Должно блокироваться
        ("Нужен магазин с продуктами", True),  # Должно блокироваться
        ("Сниму квартиру рядом с моллом", False),  # НЕ должно блокироваться (есть "сниму")
    ]
    
    for msg, should_block in test_messages:
        print(f"\n{'='*70}")
        print(f"📝 Тестовое сообщение: {msg}")
        print(f"{'='*70}")
        
        try:
            result = await monitor._hybrid_classify_message(msg, sender_username=None)
            
            print(f"✅ Результат:")
            print(f"   - Тип: {result.get('message_type', 'N/A')}")
            print(f"   - Ниши: {result.get('niches', [])}")
            print(f"   - Контекст: {result.get('context', 'N/A')}")
            print(f"   - Причина: {result.get('reason', 'N/A')}")
            
            # Проверяем результат
            is_blocked = result.get('reason') == 'Infrastructure filter (early check)'
            
            if is_blocked and should_block:
                print(f"   ✅ ТЕСТ ПРОЙДЕН: Фильтр сработал правильно!")
            elif not is_blocked and not should_block:
                print(f"   ✅ ТЕСТ ПРОЙДЕН: Сообщение пропущено правильно!")
            elif is_blocked and not should_block:
                print(f"   ❌ ТЕСТ НЕ ПРОЙДЕН: Сообщение заблокировано, но не должно было!")
            else:
                print(f"   ❌ ТЕСТ НЕ ПРОЙДЕН: Сообщение не заблокировано, но должно было!")
                
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n{'='*70}")
    print("ТЕСТИРОВАНИЕ ЗАВЕРШЕНО")
    print(f"{'='*70}")

if __name__ == "__main__":
    asyncio.run(test_filter())











