#!/usr/bin/env python3
"""
Полное исправление метода initialize_clients
"""

# Читаем файл
with open('promotion_system.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Находим и заменяем весь метод initialize_clients (строки 311-344)
# Ищем начало метода
start_idx = None
for i, line in enumerate(lines):
    if 'async def initialize_clients(self):' in line:
        start_idx = i
        break

if start_idx is None:
    print("❌ Метод не найден!")
    exit(1)

# Находим конец метода (следующий def или класс)
end_idx = None
for i in range(start_idx + 1, len(lines)):
    if lines[i].strip().startswith('async def ') or lines[i].strip().startswith('def '):
        end_idx = i
        break

# Новый корректный метод
new_method = '''    async def initialize_clients(self):
        """Инициализация всех клиентов с проверкой подключения"""
        for account in self.accounts:
            try:
                # Преобразуем api_id в int если он строка
                api_id = int(account['api_id'])
                
                # Используем StringSession если доступен, иначе файловую сессию
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
                
                await client.start()
                
                # Проверяем что клиент действительно подключен
                if await client.is_user_authorized():
                    self.clients[account['session_name']] = client
                    self.logger.info(f"✅ Initialized and authorized client for {account['session_name']}")
                else:
                    self.logger.error(f"❌ Client {account['session_name']} initialized but not authorized")
                    await client.disconnect()
            except Exception as e:
                self.logger.error(f"❌ Failed to initialize {account['session_name']}: {e}")
    
'''

# Заменяем метод
lines[start_idx:end_idx] = [new_method]

# Записываем обратно
with open('promotion_system.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("✅ Метод initialize_clients полностью исправлен!")


















