#!/usr/bin/env python3
"""
Тестовый скрипт для проверки отправки кода
Показывает детальную информацию о результате
"""
import asyncio
from telethon import TelegramClient

async def test_send_code(phone, api_id, api_hash, session_name):
    """Тест отправки кода с детальной информацией"""
    print(f"\n{'='*80}")
    print(f"🧪 ТЕСТ: Отправка кода для {phone}")
    print(f"{'='*80}")
    print(f"API ID: {api_id}")
    print(f"Session: {session_name}")
    print()
    
    import os
    os.makedirs("sessions", exist_ok=True)
    
    client = TelegramClient(f"sessions/test_{session_name}", api_id, api_hash)
    
    try:
        print("🔐 Подключение...")
        await client.connect()
        print("✅ Подключено")
        
        print(f"\n📲 Отправка кода на {phone}...")
        result = await client.send_code_request(phone)
        
        print("\n" + "="*80)
        print("📊 РЕЗУЛЬТАТ ОТПРАВКИ КОДА:")
        print("="*80)
        print(f"Тип: {result.type}")
        print(f"Phone code hash: {result.phone_code_hash}")
        print(f"Next type: {getattr(result, 'next_type', 'N/A')}")
        print(f"Timeout: {getattr(result, 'timeout', 'N/A')}")
        print("="*80)
        
        if result.type:
            print(f"\n✅ Код должен быть отправлен через: {result.type}")
            print("   Проверьте Telegram/SMS")
        else:
            print("\n⚠️ Тип доставки не определен")
        
        await client.disconnect()
        return True
        
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        await client.disconnect()
        return False

# Тестируем один из аккаунтов
if __name__ == "__main__":
    # Artur Biggest
    asyncio.run(test_send_code(
        phone="+380931849825",
        api_id=34601626,
        api_hash="eba8c7b793884b92a65c48436b646600",
        session_name="test_artur"
    ))

