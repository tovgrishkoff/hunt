#!/usr/bin/env python3
"""
Простой автоответчик на личные сообщения с использованием String Sessions
Отвечает на входящие DM от пользователей, которые пишут после постов в группах
"""

import asyncio
import json
import logging
import random
from pathlib import Path
from datetime import datetime
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import RPCError

class SimpleAutoresponder:
    def __init__(self):
        self.accounts = []
        self.clients = {}
        self.responses = []
        self.blacklist = set()
        self.responded_users = set()  # Простой кэш отвеченных пользователей
        self.setup_logging()
        
    def setup_logging(self):
        """Настройка логирования"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('autoresponder.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
    def load_accounts(self, config_file='accounts_config.json'):
        """Загрузка конфигурации аккаунтов"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                self.accounts = json.load(f)
            self.logger.info(f"📋 Loaded {len(self.accounts)} accounts")
        except Exception as e:
            self.logger.error(f"❌ Error loading accounts: {e}")
            
    def load_responses(self, responses_file='smart_dm_responses.txt'):
        """Загрузка шаблонов ответов"""
        try:
            path = Path(responses_file)
            if not path.exists():
                # Создаем файл по умолчанию
                self.create_default_responses(responses_file)
                
            with open(responses_file, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f if line.strip()]
            self.responses = lines
            self.logger.info(f"📝 Loaded {len(self.responses)} response templates")
        except Exception as e:
            self.logger.error(f"❌ Error loading responses: {e}")
            
    def create_default_responses(self, filename):
        """Создание стандартных ответов"""
        default_responses = [
            "Привет! Спасибо за интерес 😊 Расскажите подробнее, что именно вас интересует?",
            "Здравствуйте! Буду рад помочь. Какие детали вас интересуют?",
            "Привет! Спасибо, что написали. Можете описать подробнее ваш запрос?",
            "Здравствуйте! С удовольствием отвечу на ваши вопросы. Что конкретно вас интересует?",
            "Привет! Благодарю за обращение 👍 Опишите, пожалуйста, что вам нужно?",
        ]
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write('\n'.join(default_responses))
        self.logger.info(f"✅ Created default responses file: {filename}")
        
    def load_blacklist(self, blacklist_file='blacklist.txt'):
        """Загрузка черного списка"""
        try:
            path = Path(blacklist_file)
            if path.exists():
                with open(blacklist_file, 'r', encoding='utf-8') as f:
                    self.blacklist = set(line.strip() for line in f if line.strip() and not line.startswith('#'))
                self.logger.info(f"🚫 Loaded {len(self.blacklist)} blacklisted users")
        except Exception as e:
            self.logger.warning(f"⚠️ Could not load blacklist: {e}")
            
    async def initialize_clients(self):
        """Инициализация клиентов с String Sessions"""
        for account in self.accounts:
            account_name = account['session_name']
            try:
                api_id = int(account['api_id'])
                api_hash = account['api_hash']
                string_session = account.get('string_session')
                
                if string_session:
                    # Используем String Session
                    client = TelegramClient(StringSession(string_session), api_id, api_hash)
                    self.logger.info(f"🔄 Initializing {account_name} with StringSession...")
                else:
                    # Используем файловую сессию
                    client = TelegramClient(f"sessions/{account_name}", api_id, api_hash)
                    self.logger.info(f"🔄 Initializing {account_name} with file session...")
                
                await client.connect()
                
                if not await client.is_user_authorized():
                    self.logger.error(f"❌ {account_name} not authorized. Skipping...")
                    continue
                
                # Регистрируем обработчик входящих сообщений
                @client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
                async def handle_new_message(event):
                    await self.handle_dm(event, account_name)
                
                self.clients[account_name] = client
                me = await client.get_me()
                self.logger.info(f"✅ {account_name} connected as @{me.username}")
                
            except Exception as e:
                self.logger.error(f"❌ Failed to initialize {account_name}: {e}")
                
    async def handle_dm(self, event, account_name):
        """Обработка входящего личного сообщения"""
        try:
            sender = await event.get_sender()
            sender_id = sender.id
            username = sender.username or f"id{sender_id}"
            message_text = event.message.text
            
            # Проверяем черный список
            if username in self.blacklist or str(sender_id) in self.blacklist:
                self.logger.info(f"🚫 Blocked user {username} - in blacklist")
                return
            
            # Проверяем, отвечали ли уже
            user_key = f"{account_name}:{sender_id}"
            if user_key in self.responded_users:
                self.logger.info(f"⏭️ Already responded to {username} from {account_name}")
                return
            
            # Выбираем случайный ответ
            response = random.choice(self.responses)
            
            # Задержка для естественности (3-7 секунд)
            delay = random.uniform(3, 7)
            await asyncio.sleep(delay)
            
            # Отправляем ответ
            await event.reply(response)
            
            # Помечаем пользователя
            self.responded_users.add(user_key)
            
            self.logger.info(f"✅ [{account_name}] Responded to @{username}: {response[:50]}...")
            self.logger.info(f"   Incoming message: {message_text[:80]}...")
            
        except RPCError as e:
            self.logger.error(f"❌ RPC Error in handle_dm: {e}")
        except Exception as e:
            self.logger.error(f"❌ Error handling DM: {e}")
            
    async def run(self):
        """Запуск автоответчика"""
        self.logger.info("🚀 Starting Simple Autoresponder...")
        
        # Загружаем конфигурацию
        self.load_accounts()
        self.load_responses()
        self.load_blacklist()
        
        # Инициализируем клиенты
        await self.initialize_clients()
        
        if not self.clients:
            self.logger.error("❌ No clients initialized. Exiting.")
            return
        
        self.logger.info(f"✅ Autoresponder running with {len(self.clients)} account(s)")
        self.logger.info(f"📨 Monitoring private messages...")
        
        # Держим бота запущенным
        try:
            await asyncio.gather(*[client.run_until_disconnected() for client in self.clients.values()])
        except KeyboardInterrupt:
            self.logger.info("🛑 Shutting down...")
        finally:
            for client in self.clients.values():
                await client.disconnect()

if __name__ == "__main__":
    responder = SimpleAutoresponder()
    asyncio.run(responder.run())

