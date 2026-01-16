import asyncio
import random
import json
import logging
from datetime import datetime, timedelta
from telethon import TelegramClient
from telethon.tl.functions.account import UpdateProfileRequest

class PromotionSystem:
    def __init__(self):
        self.accounts = []
        self.clients = {}
        self.account_usage = {}
        self.posted_messages = {}
        self.setup_logging()
        
    def setup_logging(self):
        """Настройка логирования"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('promotion.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def load_accounts(self, config_file='accounts_config.json'):
        """Загрузка конфигурации аккаунтов"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                self.accounts = json.load(f)
            
            for account in self.accounts:
                self.account_usage[account['session_name']] = 0
                
            self.logger.info(f"Loaded {len(self.accounts)} accounts")
            
        except FileNotFoundError:
            self.logger.error(f"Config file {config_file} not found")
            self.create_default_config(config_file)
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in {config_file}: {e}")
            self.create_default_config(config_file)
    
    def create_default_config(self, config_file):
        """Создание конфигурации по умолчанию"""
        default_config = [
            {
                "phone": "+79001234567",
                "api_id": 7444016141,
                "api_hash": "9be03fb41eea0e14119fe4f908d6e741",
                "session_name": "account1",
                "nickname": "Алексей_Москва",
                "bio": "Ищу специалистов в разных областях"
            }
        ]
        
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=2, ensure_ascii=False)
            
        self.logger.info(f"Created default config file {config_file}")
        self.accounts = default_config
    
    async def initialize_clients(self):
        """Инициализация всех клиентов"""
        for account in self.accounts:
            try:
                # Преобразуем api_id в int если он строка
                api_id = int(account['api_id'])
                
                # Создаем клиент с дополнительными параметрами
                client = TelegramClient(
                    f"sessions/{account['session_name']}", 
                    api_id, 
                    account['api_hash'],
                    device_model='Desktop',
                    system_version='macOS',
                    app_version='1.0.0',
                    lang_code='en'
                )
                
                # Запускаем клиент
                await client.start()
                self.clients[account['session_name']] = client
                self.logger.info(f"✅ Initialized client for {account['session_name']}")
                
            except Exception as e:
                self.logger.error(f"❌ Failed to initialize {account['session_name']}: {e}")
                # Пробуем альтернативный способ
                await self.try_alternative_connection(account)
    
    async def try_alternative_connection(self, account):
        """Альтернативный способ подключения"""
        try:
            api_id = int(account['api_id'])
            
            # Создаем клиент с минимальными параметрами
            client = TelegramClient(
                f"sessions/{account['session_name']}", 
                api_id, 
                account['api_hash']
            )
            
            # Пробуем подключиться
            await client.connect()
            
            if await client.is_user_authorized():
                await client.start()
                self.clients[account['session_name']] = client
                self.logger.info(f"✅ Alternative connection successful for {account['session_name']}")
            else:
                self.logger.error(f"❌ User not authorized for {account['session_name']}")
                
        except Exception as e:
            self.logger.error(f"❌ Alternative connection failed for {account['session_name']}: {e}")
    
    async def test_connection(self):
        """Тест подключения аккаунта"""
        try:
            for account_name, client in self.clients.items():
                if client.is_connected():
                    me = await client.get_me()
                    self.logger.info(f"✅ Account {account_name} connected as @{me.username}")
                    return True
        except Exception as e:
            self.logger.error(f"❌ Connection test failed: {e}")
            return False
    
    async def run(self):
        """Запуск системы продвижения"""
        self.logger.info(" Starting Promotion System...")
        
        # Загружаем конфигурацию
        self.load_accounts()
        
        # Инициализируем клиенты
        await self.initialize_clients()
        
        # Тестируем подключение
        if await self.test_connection():
            self.logger.info("�� System ready! Use test_connection() to verify")
        else:
            self.logger.error("❌ System failed to initialize")

# Функция для запуска
async def main():
    promotion_system = PromotionSystem()
    await promotion_system.run()

if __name__ == "__main__":
    asyncio.run(main())
