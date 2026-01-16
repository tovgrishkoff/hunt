#!/usr/bin/env python3
"""
Исправление: добавляет поддержку string_session в initialize_clients
"""

# Читаем файл
with open('promotion_system.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Находим метод initialize_clients (строка 311)
# Заменяем строки 318-322 на новый код

old_code_start = 318
old_code_end = 323

new_code = '''                # Используем StringSession если доступен, иначе файловую сессию
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
                    )
'''

# Заменяем строки
lines[old_code_start - 1:old_code_end] = [new_code]

# Записываем обратно
with open('promotion_system.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("✅ Файл исправлен!")
print("📝 Добавлена поддержка string_session в initialize_clients")


















