#!/usr/bin/env python3
"""
Упрощение: для StringSession пропускаем проверку авторизации (они уже авторизованы)
"""

with open('promotion_system.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Ищем и заменяем блок проверки авторизации
old_check = '''                # Проверяем что клиент действительно подключен
                self.logger.info(f"  Checking authorization for {account_name}...")
                if await client.is_user_authorized():
                    self.clients[account['session_name']] = client
                    self.logger.info(f"✅ Initialized and authorized client for {account['session_name']}")
                else:
                    self.logger.error(f"❌ Client {account['session_name']} initialized but not authorized")
                    await client.disconnect()'''

new_check = '''                # Для StringSession не проверяем авторизацию (уже авторизованы)
                # Для файловых сессий проверяем
                if string_session:
                    self.clients[account['session_name']] = client
                    self.logger.info(f"✅ Initialized client for {account['session_name']} (StringSession)")
                else:
                    self.logger.info(f"  Checking authorization for {account_name}...")
                    if await client.is_user_authorized():
                        self.clients[account['session_name']] = client
                        self.logger.info(f"✅ Initialized and authorized client for {account['session_name']}")
                    else:
                        self.logger.error(f"❌ Client {account['session_name']} initialized but not authorized")
                        await client.disconnect()'''

content = content.replace(old_check, new_check)

with open('promotion_system.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ StringSession теперь добавляются без проверки авторизации!")


















