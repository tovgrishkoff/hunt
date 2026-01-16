#!/usr/bin/env python3
"""
Добавление подробного логирования и таймаутов
"""

with open('promotion_system.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Найти и заменить метод initialize_clients
start_idx = None
for i, line in enumerate(lines):
    if 'async def initialize_clients(self):' in line:
        start_idx = i
        break

# Найти конец метода
end_idx = None
for i in range(start_idx + 1, len(lines)):
    if lines[i].strip().startswith('async def ') or lines[i].strip().startswith('def '):
        end_idx = i
        break

# Новый метод с логированием
new_method = '''    async def initialize_clients(self):
        """Инициализация всех клиентов с проверкой подключения"""
        for account in self.accounts:
            account_name = account['session_name']
            self.logger.info(f"🔄 Starting initialization for {account_name}...")
            try:
                # Преобразуем api_id в int если он строка
                api_id = int(account['api_id'])
                self.logger.info(f"  API ID: {api_id}")
                
                # Используем StringSession если доступен, иначе файловую сессию
                string_session = account.get('string_session')
                if string_session:
                    self.logger.info(f"  Using StringSession for {account_name}")
                    from telethon.sessions import StringSession
                    client = TelegramClient(
                        StringSession(string_session),
                        api_id,
                        account['api_hash']
                    )
                else:
                    self.logger.info(f"  Using file session for {account_name}")
                    client = TelegramClient(
                        f"sessions/{account['session_name']}", 
                        api_id, 
                        account['api_hash']
                    )
                
                self.logger.info(f"  Client created for {account_name}, connecting...")
                
                # Для StringSession просто подключаемся (уже авторизованы)
                if string_session:
                    try:
                        await asyncio.wait_for(client.connect(), timeout=10.0)
                        self.logger.info(f"  ✅ Connected {account_name}")
                    except asyncio.TimeoutError:
                        self.logger.error(f"  ⏱️ Connection timeout for {account_name}")
                        continue
                else:
                    try:
                        # Для файловых сессий: подключаемся без интерактивного ввода
                        await asyncio.wait_for(client.start(phone=lambda: None), timeout=10.0)
                        self.logger.info(f"  ✅ Started {account_name}")
                    except asyncio.TimeoutError:
                        self.logger.error(f"  ⏱️ Start timeout for {account_name}")
                        continue
                
                # Проверяем что клиент действительно подключен
                self.logger.info(f"  Checking authorization for {account_name}...")
                if await client.is_user_authorized():
                    self.clients[account['session_name']] = client
                    self.logger.info(f"✅ Initialized and authorized client for {account['session_name']}")
                else:
                    self.logger.error(f"❌ Client {account['session_name']} initialized but not authorized")
                    await client.disconnect()
            except Exception as e:
                self.logger.error(f"❌ Failed to initialize {account['session_name']}: {e}")
                import traceback
                self.logger.error(f"   Traceback: {traceback.format_exc()}")
    
'''

# Заменяем
lines[start_idx:end_idx] = [new_method]

with open('promotion_system.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("✅ Добавлено подробное логирование и таймауты!")


















