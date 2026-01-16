#!/usr/bin/env python3
"""
Тестовый скрипт для проверки работы ChatGPT генератора ответов
"""

import asyncio
import os
import sys
from pathlib import Path

# Добавляем текущую директорию в путь
sys.path.insert(0, str(Path(__file__).parent))

from chatgpt_response_generator import ChatGPTResponseGenerator
from smart_response_analyzer import SmartResponseAnalyzer

async def test_chatgpt_generator():
    """Тестирование ChatGPT генератора напрямую"""
    print("=" * 80)
    print("🧪 Тестирование ChatGPT Response Generator")
    print("=" * 80)
    print()
    
    # Проверяем наличие API ключа
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("❌ OPENAI_API_KEY не установлен!")
        print("💡 Установите переменную окружения или добавьте в docker-compose.yml")
        return False
    
    print(f"✅ API ключ найден: {api_key[:20]}...")
    print()
    
    # Создаем генератор
    generator = ChatGPTResponseGenerator()
    
    if not generator.enabled:
        print("❌ ChatGPT генератор не инициализирован")
        return False
    
    print("✅ ChatGPT генератор инициализирован")
    print()
    
    # Тестовые сообщения с разными типами услуг
    test_messages = [
        {
            "message": "Привет! Я фотограф, могу сделать фотосессию на Бали. Цены от 100$",
            "service_type": "photo_video"
        },
        {
            "message": "Здравствуйте! Предлагаю аренду виллы на Бали. 3 спальни, бассейн, вид на океан",
            "service_type": "real_estate"
        },
        {
            "message": "Привет! Делаю маникюр и педикюр. Выезд на дом. Цены от 50$",
            "service_type": "beauty"
        },
        {
            "message": "Здравствуйте! Предлагаю аренду скутера на Бали. 10$ в день, есть доставка",
            "service_type": "transport"
        },
        {
            "message": "Привет! Организую экскурсии по Бали. Гид с опытом 5 лет, индивидуальные туры",
            "service_type": "tourism"
        },
        {
            "message": "Здравствуйте! Предлагаю услуги дизайнера интерьеров",
            "service_type": "default"
        }
    ]
    
    print("📝 Тестирование на разных типах сообщений:")
    print("-" * 80)
    
    success_count = 0
    total_count = len(test_messages)
    
    for i, test_case in enumerate(test_messages, 1):
        message = test_case["message"]
        service_type = test_case["service_type"]
        
        print(f"\n{i}. Тип услуги: {service_type}")
        print(f"   Входящее сообщение: {message}")
        print(f"   Генерация ответа...")
        
        try:
            response = await generator.generate_selling_response(
                incoming_message=message,
                service_type=service_type
            )
            
            if response:
                success_count += 1
                print(f"   ✅ Ответ ({len(response)} символов):")
                print(f"   {response}")
                
                # Проверяем наличие упоминания бота
                if "@Lead_Hunbot" in response or "Lead_Hunbot" in response:
                    print(f"   ✅ Содержит упоминание бота")
                else:
                    print(f"   ⚠️ НЕ содержит упоминание бота!")
                
                # Проверяем наличие призыва к действию
                action_words = ["переходи", "заходи", "проверь", "попробуй", "загляни", "открой", "посмотри"]
                has_action = any(word in response.lower() for word in action_words)
                if has_action:
                    print(f"   ✅ Содержит призыв к действию")
                else:
                    print(f"   ℹ️ Без прямого призыва к действию (это нормально для 30% ответов)")
            else:
                print(f"   ❌ Не удалось сгенерировать ответ")
        
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
        
        print("-" * 80)
        
        # Небольшая задержка между запросами
        if i < total_count:
            await asyncio.sleep(1)
    
    print()
    print("=" * 80)
    print(f"📊 Результаты: {success_count}/{total_count} успешных генераций")
    print("=" * 80)
    
    return success_count > 0


async def test_smart_analyzer():
    """Тестирование через SmartResponseAnalyzer (как в реальной работе)"""
    print("\n" + "=" * 80)
    print("🧠 Тестирование через SmartResponseAnalyzer")
    print("=" * 80)
    print()
    
    analyzer = SmartResponseAnalyzer(use_chatgpt=True)
    
    test_messages = [
        "Привет! Я фотограф, могу сделать фотосессию на Бали. Цены от 100$",
        "Здравствуйте! Предлагаю аренду виллы на Бали. 3 спальни, бассейн",
        "Привет! Делаю маникюр и педикюр. Выезд на дом. Цены от 50$"
    ]
    
    for i, message in enumerate(test_messages, 1):
        print(f"\n{i}. Входящее сообщение: {message}")
        print(f"   Генерация ответа через SmartResponseAnalyzer...")
        
        try:
            response = await analyzer.analyze_message_async(message)
            
            if response:
                print(f"   ✅ Ответ ({len(response)} символов):")
                print(f"   {response}")
            else:
                print(f"   ❌ Не удалось сгенерировать ответ")
        
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
            import traceback
            traceback.print_exc()
        
        print("-" * 80)
        
        if i < len(test_messages):
            await asyncio.sleep(1)


async def main():
    """Главная функция"""
    print("\n" + "=" * 80)
    print("🚀 ТЕСТИРОВАНИЕ ChatGPT АВТООТВЕТЧИКА")
    print("=" * 80)
    print()
    
    # Тест 1: Прямое тестирование генератора
    print("ТЕСТ 1: Прямое тестирование ChatGPT генератора")
    success1 = await test_chatgpt_generator()
    
    # Тест 2: Тестирование через анализатор
    print("\n\nТЕСТ 2: Тестирование через SmartResponseAnalyzer")
    await test_smart_analyzer()
    
    print("\n" + "=" * 80)
    if success1:
        print("✅ Тестирование завершено успешно!")
        print("💡 ChatGPT генератор работает корректно")
    else:
        print("⚠️ Тестирование завершено с ошибками")
        print("💡 Проверьте настройку OPENAI_API_KEY")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())

