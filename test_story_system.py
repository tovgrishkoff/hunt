#!/usr/bin/env python3
"""
Тестовый скрипт для проверки системы Stories
Запускает ОДИН цикл и показывает результаты
"""

import asyncio
import sys
sys.path.insert(0, '/home/tovgrishkoff/PIAR/telegram_promotion_system')

from story_engagement_system import StoryEngagementSystem

# Целевые чаты для теста
TEST_CHATS = [
    '@bali_ubud_changu',
    '@canggu_people',
]

async def test_run():
    """Тестовый запуск"""
    print("\n" + "="*60)
    print("🧪 ТЕСТОВЫЙ ЗАПУСК СИСТЕМЫ STORIES")
    print("="*60 + "\n")
    
    system = StoryEngagementSystem()
    
    try:
        print("📱 Инициализация аккаунтов...")
        await system.initialize()
        
        print("\n🎯 Запуск ОДНОГО тестового цикла...")
        print(f"📋 Целевые чаты: {', '.join(TEST_CHATS)}\n")
        
        result = await system.run_engagement_cycle(TEST_CHATS)
        
        print("\n" + "="*60)
        print("📊 РЕЗУЛЬТАТЫ ТЕСТА")
        print("="*60)
        print(f"✅ Просмотрено Stories: {result['total_stories']}")
        print(f"❤️ Поставлено реакций: {result['total_reactions']}")
        print("="*60 + "\n")
        
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await system.close()
        print("👋 Тест завершен\n")

if __name__ == '__main__':
    asyncio.run(test_run())

