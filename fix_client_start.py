#!/usr/bin/env python3
"""
Исправление: использовать connect() для StringSession вместо start()
"""

with open('promotion_system.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Старый код
old_code = '''                else:
                    client = TelegramClient(
                        f"sessions/{account['session_name']}", 
                        api_id, 
                        account['api_hash']
                    )
                
                await client.start()'''

# Новый код с разными методами для StringSession и файлов
new_code = '''                else:
                    client = TelegramClient(
                        f"sessions/{account['session_name']}", 
                        api_id, 
                        account['api_hash']
                    )
                
                # Для StringSession просто подключаемся (уже авторизованы)
                # Для файловых сессий нужен start() но без интерактивности
                if string_session:
                    await client.connect()
                else:
                    # Для файловых сессий: подключаемся без интерактивного ввода
                    await client.start(phone=lambda: None)'''

content = content.replace(old_code, new_code)

with open('promotion_system.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ Исправлено: StringSession используют connect(), файлы - start()")


















