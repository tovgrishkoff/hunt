#!/usr/bin/env python3
"""
Исправление: добавляет поддержку string_session в reconnect_client
"""

# Читаем файл
with open('promotion_system.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Старый код в reconnect_client
old_reconnect_code = '''            # Создаем новый клиент
            api_id = int(account['api_id'])
            client = TelegramClient(
                f"sessions/{account['session_name']}", 
                api_id, 
                account['api_hash']
            )'''

# Новый код с поддержкой string_session
new_reconnect_code = '''            # Создаем новый клиент
            api_id = int(account['api_id'])
            
            # Используем StringSession если доступен
            string_session = account.get('string_session')
            if string_session:
                from telethon.sessions import StringSession
                client = TelegramClient(
                    StringSession(string_session),
                    api_id,
                    account['api_hash']
                )
            else:
                client = TelegramClient(
                    f"sessions/{account['session_name']}", 
                    api_id, 
                    account['api_hash']
                )'''

# Заменяем
content = content.replace(old_reconnect_code, new_reconnect_code)

# Записываем обратно
with open('promotion_system.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ Метод reconnect_client исправлен!")
print("📝 Добавлена поддержка string_session")


















