#!/usr/bin/env python3
"""
Тестовая отправка алерта администратору
"""

import asyncio
import json
from alert_system import AlertSystem

async def test_alert():
    # Загружаем конфигурацию аккаунтов
    with open('accounts_config.json', 'r', encoding='utf-8') as f:
        accounts = json.load(f)
    
    if not accounts:
        print("❌ No accounts found in config")
        return
    
    # Используем первый аккаунт для отправки тестового алерта
    first_account = accounts[0]
    
    print(f"🔧 Initializing alert system using account: {first_account['session_name']}")
    
    # Создаем систему алертов
    alert = AlertSystem(admin_id=210147380)
    
    # Инициализируем
    success = await alert.initialize(
        api_id=int(first_account['api_id']),
        api_hash=first_account['api_hash'],
        string_session=first_account.get('string_session'),
        session_name=f"test_alert_{first_account['session_name']}"
    )
    
    if not success:
        print("❌ Failed to initialize alert system")
        return
    
    print("✅ Alert system initialized")
    print("📤 Sending test alert...")
    
    # Отправляем тестовое уведомление
    test_message = """
🧪 **ТЕСТОВОЕ УВЕДОМЛЕНИЕ**

Это тестовое сообщение от системы постинга.

Если вы видите это сообщение - система алертов работает корректно! ✅

**Вы будете получать уведомления о:**
- Отключении аккаунтов
- Ошибках постинга
- Критических проблемах системы
- Успешном запуске

**Настройки:**
- Ваш ID: 210147380
- Cooldown между алертами: 30 минут
- Используемый аккаунт: {account}
""".format(account=first_account['session_name'])
    
    result = await alert.send_alert(
        "test_notification",
        test_message,
        force=True  # Игнорировать cooldown для теста
    )
    
    if result:
        print("✅ Test alert sent successfully!")
        print(f"📱 Check your Telegram (ID: 210147380)")
    else:
        print("❌ Failed to send test alert")
    
    # Закрываем соединение
    await alert.close()
    print("🔚 Test completed")

if __name__ == "__main__":
    asyncio.run(test_alert())


