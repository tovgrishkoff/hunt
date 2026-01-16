#!/usr/bin/env python3
import asyncio
from telethon import TelegramClient
import json
import sys

async def send_test():
    try:
        with open('/app/accounts_config.json', 'r') as f:
            acc = json.load(f)[0]
        
        print(f"Using account: {acc['session_name']}")
        
        client = TelegramClient(
            f'/app/sessions/{acc["session_name"]}',
            int(acc['api_id']),
            acc['api_hash']
        )
        
        await client.start()
        print("Client started")
        
        test_msg = '''🧪 **ТЕСТОВОЕ УВЕДОМЛЕНИЕ ОТ СИСТЕМЫ ПОСТИНГА**

Если вы видите это сообщение - система алертов работает корректно! ✅

**Вы будете получать уведомления о:**
• ❌ Проблемах с аккаунтами
• ⚠️ Ошибках постинга  
• ✅ Успешном запуске системы
• 🔴 Критических сбоях

**Ваш ID:** 210147380
**Cooldown:** 30 минут между одинаковыми алертами

Система готова к работе! 🚀'''
        
        await client.send_message(210147380, test_msg)
        print('✅ Тестовое сообщение отправлено на ID: 210147380')
        
        await client.disconnect()
        print('✅ Done!')
        
    except Exception as e:
        print(f'❌ Error: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(send_test())


