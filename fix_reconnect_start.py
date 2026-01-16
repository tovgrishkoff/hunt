#!/usr/bin/env python3
"""
Исправление reconnect_client: использовать connect() для StringSession
"""

with open('promotion_system.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Находим метод reconnect_client и исправляем await client.start()
new_lines = []
in_reconnect = False
for i, line in enumerate(lines):
    if 'async def reconnect_client' in line:
        in_reconnect = True
    
    # Заменяем await client.start() в reconnect_client
    if in_reconnect and '            await client.start()' in line:
        # Добавляем логику с проверкой string_session
        new_lines.append('            # Для StringSession просто подключаемся (уже авторизованы)\n')
        new_lines.append('            if string_session:\n')
        new_lines.append('                await client.connect()\n')
        new_lines.append('            else:\n')
        new_lines.append('                await client.start(phone=lambda: None)\n')
        in_reconnect = False  # Только одна замена в этом методе
        continue
    
    new_lines.append(line)

with open('promotion_system.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("✅ reconnect_client исправлен!")


















