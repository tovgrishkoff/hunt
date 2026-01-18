#!/usr/bin/env python3
"""
Тест улучшенной AI классификации
"""

import asyncio
import json
import os
from ai_classifier import AIClassifier
from config import BOT_TOKEN

# Тестовые сообщения для проверки классификации
TEST_MESSAGES = [
    # Поиск услуг
    "Ищу фотографа на свадьбу 15 июля, бюджет 500$",
    "Нужен мастер по маникюру на дом, срочно",
    "Ищем визажиста на выпускной, бюджет 200$",
    "Требуется водитель с машиной на 3 дня",
    
    # Предложения услуг
    "Снимаю профессиональные фото, свадьбы, портреты",
    "Делаю маникюр и педикюр, выезд на дом",
    "Предлагаю услуги визажиста, свадебный макияж",
    "Работаю водителем, трансферы, экскурсии",
    
    # Обычное общение
    "Привет всем! Как дела?",
    "Кто сегодня пойдет на пляж?",
    "Погода отличная сегодня",
    "Всем доброго дня!",
    
    # Спам
    "Заработай 1000$ в день без вложений!",
    "Бинарные опционы - быстрый заработок",
    "Подпишитесь на канал, поставьте лайк",
    "Сетевой маркетинг - ваш путь к успеху"
]

async def test_enhanced_classification():
    """Тестирует улучшенную классификацию"""
    print("🤖 Тестирование улучшенной AI классификации\n")
    
    # Инициализируем классификатор
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("❌ OPENAI_API_KEY не найден в переменных окружения")
        return
    
    classifier = AIClassifier(api_key)
    
    print("📊 Результаты классификации:\n")
    print("-" * 80)
    
    for i, message in enumerate(TEST_MESSAGES, 1):
        print(f"📝 Тест {i}: {message}")
        
        try:
            result = await classifier.classify_message(message)
            
            print(f"✅ Результат:")
            print(f"   • Тип: {result.get('message_type', 'N/A')}")
            print(f"   • Спам: {result.get('is_spam', False)}")
            print(f"   • Ниши: {result.get('niches', [])}")
            print(f"   • Контекст: {result.get('context', 'N/A')}")
            print(f"   • Срочность: {result.get('urgency', 'N/A')}")
            print(f"   • Бюджет: {result.get('budget', 'N/A')}")
            print(f"   • Уверенность: {result.get('confidence', 0)}%")
            print(f"   • Причина: {result.get('reason', 'N/A')}")
            
        except Exception as e:
            print(f"❌ Ошибка: {e}")
        
        print("-" * 80)
    
    # Показываем статистику
    print("\n📈 Статистика:")
    cache_stats = classifier.get_cache_stats()
    learning_stats = classifier.get_learning_stats()
    
    print(f"• Размер кэша: {cache_stats['cache_size']}")
    print(f"• Всего примеров: {learning_stats.get('total_examples', 0)}")
    print(f"• Исправлений: {learning_stats.get('corrections_count', 0)}")
    print(f"• Точность: {learning_stats.get('accuracy_rate', 0):.1f}%")

async def test_correction_system():
    """Тестирует систему исправлений"""
    print("\n🔧 Тестирование системы исправлений\n")
    
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("❌ OPENAI_API_KEY не найден")
        return
    
    classifier = AIClassifier(api_key)
    
    # Тестируем исправление
    test_message = "Ищу фотографа на свадьбу"
    corrected_result = {
        "message_type": "ПОИСК",
        "is_spam": False,
        "niches": ["Фотограф"],
        "context": "Поиск фотографа на свадьбу",
        "urgency": "срочно",
        "budget": "500$",
        "confidence": 95,
        "reason": "Исправлено администратором"
    }
    
    print(f"📝 Тестовое сообщение: {test_message}")
    print(f"🔧 Исправление: {corrected_result}")
    
    # Сохраняем исправление
    classifier.correct_classification(test_message, corrected_result)
    
    print("✅ Исправление сохранено")
    
    # Показываем обновленную статистику
    learning_stats = classifier.get_learning_stats()
    print(f"📊 Обновленная статистика:")
    print(f"• Всего примеров: {learning_stats.get('total_examples', 0)}")
    print(f"• Исправлений: {learning_stats.get('corrections_count', 0)}")

async def test_export_system():
    """Тестирует систему экспорта"""
    print("\n📤 Тестирование системы экспорта\n")
    
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("❌ OPENAI_API_KEY не найден")
        return
    
    classifier = AIClassifier(api_key)
    
    # Экспортируем данные
    filename = "test_export.json"
    classifier.export_learning_data(filename)
    
    if os.path.exists(filename):
        print(f"✅ Данные экспортированы в {filename}")
        
        # Читаем и показываем структуру
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        print(f"📊 Экспортировано записей: {len(data)}")
        if data:
            print(f"📝 Пример записи:")
            print(json.dumps(data[0], ensure_ascii=False, indent=2))
        
        # Удаляем тестовый файл
        os.remove(filename)
        print(f"🗑️ Тестовый файл удален")
    else:
        print("❌ Ошибка экспорта")

async def main():
    """Основная функция тестирования"""
    print("🚀 Запуск тестов улучшенной AI классификации\n")
    
    # Тест 1: Классификация
    await test_enhanced_classification()
    
    # Тест 2: Система исправлений
    await test_correction_system()
    
    # Тест 3: Система экспорта
    await test_export_system()
    
    print("\n✅ Все тесты завершены!")

if __name__ == "__main__":
    asyncio.run(main()) 