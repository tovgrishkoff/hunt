#!/usr/bin/env python3
"""
Скрипт для тестирования ChatGPT ответов
"""

import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv

# Загружаем .env
load_dotenv()

from chatgpt_response_generator import ChatGPTResponseGenerator
from smart_response_analyzer import SmartResponseAnalyzer

async def test_chatgpt():
    """Тестирование ChatGPT генерации ответов"""
    
    print("=" * 80)
    print("🧪 ТЕСТИРОВАНИЕ CHATGPT ОТВЕТОВ")
    print("=" * 80)
    print()
    
    # Проверяем API ключ
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("❌ OPENAI_API_KEY не найден в .env файле!")
        return
    else:
        print(f"✅ OPENAI_API_KEY найден: {api_key[:20]}...{api_key[-10:]}")
        print()
    
    # Инициализируем генератор
    print("🔧 Инициализация ChatGPT генератора...")
    generator = ChatGPTResponseGenerator()
    
    if not generator.enabled:
        print("❌ ChatGPT генератор не включен!")
        return
    
    print("✅ ChatGPT генератор инициализирован")
    print()
    
    # Инициализируем анализатор
    print("🔧 Инициализация Smart Response Analyzer...")
    analyzer = SmartResponseAnalyzer(use_chatgpt=True)
    
    if not analyzer.use_chatgpt:
        print("❌ ChatGPT не включен в анализаторе!")
        return
    
    print("✅ Smart Response Analyzer инициализирован")
    print()
    
    # Тестовые сообщения
    test_messages = [
        ("Привет! Я фотограф, могу сделать фотосессию на Бали. Цены от 100$", "photo_video"),
        ("Здравствуйте! Предлагаю аренду виллы на Бали. 3 спальни, бассейн", "real_estate"),
        ("Привет! Делаю маникюр и педикюр. Выезд на дом. Цены от 50$", "beauty"),
        ("+", "default"),  # Простое сообщение как от sofyasvetlaya
        ("🙈", "default"),  # Еще одно простое сообщение
    ]
    
    print("=" * 80)
    print("📨 ТЕСТИРОВАНИЕ ОТВЕТОВ")
    print("=" * 80)
    print()
    
    for i, (message, expected_type) in enumerate(test_messages, 1):
        print(f"\n{'='*80}")
        print(f"ТЕСТ {i}/{len(test_messages)}")
        print(f"{'='*80}")
        print(f"📥 Входящее сообщение: {message}")
        print(f"📋 Ожидаемый тип услуги: {expected_type}")
        print()
        
        # Тестируем через анализатор (как в реальном боте)
        print("🤖 Генерирую ответ через SmartResponseAnalyzer...")
        try:
            response = await analyzer.analyze_message_async(message)
            print(f"✅ Ответ получен!")
            print(f"📤 Ответ ({len(response)} символов):")
            print(f"   {response}")
            print()
            
            # Проверяем, содержит ли ответ упоминание бота
            if "@Lead_Hunbot" in response or "Lead_Hunbot" in response:
                print("✅ Упоминание бота найдено в ответе")
            else:
                print("⚠️ Упоминание бота НЕ найдено в ответе")
            
            # Проверяем, не является ли ответ шаблонным
            is_template = any(
                template in response 
                for template_list in analyzer.responses.values() 
                for template in template_list
            )
            if is_template:
                print("⚠️ Ответ похож на шаблонный (fallback)")
            else:
                print("✅ Ответ уникальный (вероятно от ChatGPT)")
                
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            import traceback
            traceback.print_exc()
        
        print()
        await asyncio.sleep(1)  # Небольшая задержка между запросами
    
    print("=" * 80)
    print("✅ ТЕСТИРОВАНИЕ ЗАВЕРШЕНО")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(test_chatgpt())

