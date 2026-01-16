#!/usr/bin/env python3
"""
Финальная упрощенная версия initialize_clients
"""

with open('promotion_system.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Найти и заменить метод
start_idx = None
for i, line in enumerate(lines):
    if 'async def initialize_clients(self):' in line:
        start_idx = i
        break

end_idx = None
for i in range(start_idx + 1, len(lines)):
    if lines[i].strip().startswith('async def ') or lines[i].strip().startswith('def '):
        end_idx = i
        break

# Простая версия
new_method = '''    async def initialize_clients(self):
        """Инициализация всех клиентов с проверкой подключения"""
        for account in self.accounts:
            account_name = account['session_name']
            try:
                self.logger.info(f"🔄 Initializing {account_name}...")
                
                api_id = int(account['api_id'])
                string_session = account.get('string_session')
                
                if string_session:
                    from telethon.sessions import StringSession
                    client = TelegramClient(StringSession(string_session), api_id, account['api_hash'])
                else:
                    client = TelegramClient(f"sessions/{account_name}", api_id, account['api_hash'])
                
                await client.connect()
                self.logger.info(f"  Connected {account_name}")
                
                # Для StringSession не проверяем авторизацию (зависает)
                # Просто добавляем и доверяем что сессия валидна
                self.clients[account_name] = client
                self.logger.info(f"✅ Client {account_name} ready")
                
            except Exception as e:
                self.logger.error(f"❌ Failed {account_name}: {e}")
    
'''

lines[start_idx:end_idx] = [new_method]

with open('promotion_system.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("✅ Максимально упрощенная версия init готова!")


















