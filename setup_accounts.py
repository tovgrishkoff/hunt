import asyncio
import json
import logging
from telethon import TelegramClient

class AccountSetup:
    def __init__(self):
        self.setup_logging()
        self.accounts = []
        
    def setup_logging(self):
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
    
    def load_accounts(self):
        """Загрузка конфигурации аккаунтов"""
        try:
            with open('accounts_config.json', 'r', encoding='utf-8') as f:
                self.accounts = json.load(f)
            self.logger.info(f"Loaded {len(self.accounts)} accounts")
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}")
            return
    
    async def setup_account(self, account):
        """Настройка одного аккаунта"""
        try:
            self.logger.info(f"Setting up account: {account['session_name']}")
            
            # Создаем клиент
            client = TelegramClient(
                f"sessions/{account['session_name']}", 
                account['api_id'], 
                account['api_hash']
            )
            
            # Подключаемся
            await client.connect()
            self.logger.info("Connected to Telegram")
            
            # Проверяем авторизацию
            if await client.is_user_authorized():
                me = await client.get_me()
                self.logger.info(f"✅ Already authorized as @{me.username}")
                await client.disconnect()
                return True
            else:
                self.logger.info("🔐 Need to authorize...")
                
                # Используем номер из конфига
                phone = account['phone']
                self.logger.info(f"📱 Using phone: {phone}")
                
                # Отправляем код
                await client.send_code_request(phone)
                self.logger.info("📱 Code sent to your phone")
                
                # Запрашиваем код
                code = input(f"Enter the code from Telegram for {account['session_name']}: ").strip()
                
                try:
                    # Пытаемся войти с кодом
                    await client.sign_in(phone, code)
                    self.logger.info("✅ Authorization successful!")
                    
                    me = await client.get_me()
                    self.logger.info(f"🎉 Logged in as @{me.username}")
                    
                    await client.disconnect()
                    return True
                    
                except Exception as e:
                    self.logger.error(f"❌ Authorization failed: {e}")
                    
                    # Если нужен пароль от двухфакторной аутентификации
                    if "2FA" in str(e) or "password" in str(e).lower():
                        password = input(f"Enter 2FA password for {account['session_name']}: ").strip()
                        try:
                            await client.sign_in(password=password)
                            self.logger.info("✅ 2FA authorization successful!")
                            
                            me = await client.get_me()
                            self.logger.info(f"🎉 Logged in as @{me.username}")
                            
                            await client.disconnect()
                            return True
                        except Exception as e2:
                            self.logger.error(f"❌ 2FA authorization failed: {e2}")
                            await client.disconnect()
                            return False
                    
                    await client.disconnect()
                    return False
                
        except Exception as e:
            self.logger.error(f"❌ Setup process failed: {e}")
            return False
    
    async def setup_all_accounts(self):
        """Настройка всех аккаунтов"""
        self.logger.info("🚀 Starting account setup...")
        
        # Загружаем конфигурацию
        self.load_accounts()
        
        if not self.accounts:
            self.logger.error("No accounts loaded")
            return
        
        # Настраиваем каждый аккаунт
        for account in self.accounts:
            self.logger.info(f"Processing account: {account['session_name']}")
            success = await self.setup_account(account)
            
            if success:
                self.logger.info(f"✅ Account {account['session_name']} setup complete!")
            else:
                self.logger.error(f"❌ Account {account['session_name']} setup failed")

async def main():
    setup = AccountSetup()
    await setup.setup_all_accounts()

if __name__ == "__main__":
    asyncio.run(main())
