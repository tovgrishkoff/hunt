#!/usr/bin/env python3
"""
Простой тест ChatGPT генератора
"""

import asyncio
import os
import sys

# Проверяем API ключ
api_key = os.getenv('OPENAI_API_KEY')
if not api_key:
    print("❌ OPENAI_API_KEY не установлен!")
    sys.exit(1)

print(f"✅ API ключ найден: {api_key[:20]}...")
print()

# Импортируем модули
try:
    from chatgpt_response_generator import ChatGPTResponseGenerator
    print("✅ Модуль chatgpt_response_generator загружен")
except Exception as e:
    print(f"❌ Ошибка импорта: {e}")
    sys.exit(1)

async def test_single_message():
    """Тестирование одного сообщения"""
    generator = ChatGPTResponseGenerator()
    
    if not generator.enabled:
        print("❌ ChatGPT генератор не включен")
        return
    
    print("✅ ChatGPT генератор инициализирован")
    print()
    
    # Тестовое сообщение
    test_message = "Привет! Я фотограф, могу сделать фотосессию на Бали. Цены от 100$"
    service_type = "photo_video"
    
    print(f"📥 Входящее сообщение: {test_message}")
    print(f"📊 Тип услуги: {service_type}")
    print(f"🔄 Генерация ответа...")
    print()
    
    try:
        response = await generator.generate_selling_response(
            incoming_message=test_message,
            service_type=service_type
        )
        
        if response:
            print("✅ Ответ сгенерирован:")
            print("-" * 80)
            print(response)
            print("-" * 80)
            print()
            print(f"📏 Длина: {len(response)} символов")
            
            # Проверки
            if "@Lead_Hunbot" in response or "Lead_Hunbot" in response:
                print("✅ Содержит упоминание бота")
            else:
                print("⚠️ НЕ содержит упоминание бота")
            
            action_words = ["переходи", "заходи", "проверь", "попробуй", "загляни", "открой", "посмотри"]
            has_action = any(word in response.lower() for word in action_words)
            if has_action:
                print("✅ Содержит призыв к действию")
            else:
                print("ℹ️ Без прямого призыва (это нормально для 30% ответов)")
        else:
            print("❌ Не удалось сгенерировать ответ")
    
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("=" * 80)
    print("🧪 ТЕСТ ChatGPT ГЕНЕРАТОРА ОТВЕТОВ")
    print("=" * 80)
    print()
    asyncio.run(test_single_message())
    print()
    print("=" * 80)

