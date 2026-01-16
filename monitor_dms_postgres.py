import asyncio
import random
import json
import logging
import os
from pathlib import Path
from datetime import datetime
from telethon import TelegramClient, events
from telethon.errors import RPCError
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Настройка базы данных PostgreSQL
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://telegram:telegram_password@localhost:5433/telegram_sessions')
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class DMResponse(Base):
    __tablename__ = "dm_responses"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    username = Column(String)
    response_sent = Column(Boolean, default=False)
    response_text = Column(String)
    sent_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

# Создаем таблицы
Base.metadata.create_all(bind=engine)

class PostgresDMResponder:
    def __init__(self):
        self.accounts = []
        self.clients = {}
        self.responses = []
        self.blacklist = set()
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
            self.logger.info(f"Loaded {len(self.accounts)} accounts")
        except FileNotFoundError:
            self.logger.error(f"Config file {config_file} not found")
            return
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in {config_file}: {e}")
            return

    def load_responses(self, responses_file='dm_responses.txt'):
        """Загрузка ответов для автоответчика"""
        path = Path(responses_file)
        if not path.exists():
            self.logger.warning(f"Responses file {responses_file} not found.")
            self.responses = []
            return
        with path.open('r', encoding='utf-8') as f:
            lines = [line.strip() for line in f.readlines()]
        self.responses = [line for line in lines if line]
        self.logger.info(f"Loaded {len(self.responses)} responses")

    def load_blacklist(self, blacklist_file='blacklist_accounts.txt'):
        """Загрузка черного списка аккаунтов"""
        path = Path(blacklist_file)
        if not path.exists():
            self.logger.warning(f"Blacklist file {blacklist_file} not found.")
            return
        with path.open('r', encoding='utf-8') as f:
            lines = [line.strip() for line in f.readlines()]
        self.blacklist = {line for line in lines if line}
        self.logger.info(f"Loaded {len(self.blacklist)} blacklisted accounts")

    def check_response_sent(self, user_id: str):
        """Проверка, был ли уже отправлен ответ пользователю"""
        db = SessionLocal()
        try:
            response = db.query(DMResponse).filter(
                DMResponse.user_id == str(user_id),
                DMResponse.response_sent == True
            ).first()
            return response is not None
        finally:
            db.close()

    def mark_response_sent(self, user_id: str, username: str, response_text: str):
        """Отметка, что ответ был отправлен"""
        db = SessionLocal()
        try:
            response = DMResponse(
                user_id=str(user_id),
                username=username,
                response_sent=True,
                response_text=response_text,
                sent_at=datetime.utcnow()
            )
            db.add(response)
            db.commit()
        finally:
            db.close()

    async def handle_new_message(self, event, client_name):
        """Обработка нового сообщения"""
        try:
            sender = await event.get_sender()
            if not sender:
                return

            user_id = sender.id
            username = getattr(sender, 'username', 'No username')
            
            # Проверяем черный список
            if username in self.blacklist or str(user_id) in self.blacklist:
                self.logger.info(f"🚫 Skipping blacklisted user: {username} ({user_id})")
                return

            # Проверяем, не отправляли ли уже ответ
            if self.check_response_sent(user_id):
                self.logger.info(f"⏭️ Already responded to {username} ({user_id})")
                return

            # Выбираем случайный ответ
            if not self.responses:
                self.logger.warning("No responses available")
                return

            response_text = random.choice(self.responses)
            
            # Отправляем ответ
            await event.respond(response_text)
            
            # Отмечаем, что ответ отправлен
            self.mark_response_sent(user_id, username, response_text)
            
            self.logger.info(f"✅ Responded to {username} ({user_id}) via {client_name}: {response_text}")
            
        except RPCError as e:
            self.logger.error(f"RPCError responding to {username}: {e}")
        except Exception as e:
            self.logger.error(f"Error handling message from {username}: {e}")

    async def initialize_clients(self):
        """Инициализация всех клиентов"""
        for account in self.accounts:
            try:
                api_id = int(account['api_id'])
                
                client = TelegramClient(
                    f"sessions/{account['session_name']}", 
                    api_id, 
                    account['api_hash']
                )
                await client.connect()
                
                if await client.is_user_authorized():
                    self.clients[account['session_name']] = client
                    me = await client.get_me()
                    username = getattr(me, 'username', 'No username')
                    self.logger.info(f"✅ Initialized AUTHORIZED client for {account['session_name']} (@{username})")
                    
                    # Регистрируем обработчик событий
                    @client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
                    async def handler(event):
                        await self.handle_new_message(event, account['session_name'])
                        
                else:
                    self.logger.info(f"❌ Skipping UNAUTHORIZED client {account['session_name']}")
                    await client.disconnect()
                    
            except Exception as e:
                self.logger.error(f"❌ Failed to initialize {account['session_name']}: {e}")

    async def run(self):
        """Запуск автоответчика"""
        self.logger.info("🤖 Starting PostgreSQL DM Responder...")
        
        self.load_accounts()
        self.load_responses()
        self.load_blacklist()
        
        await self.initialize_clients()
        
        if not self.clients:
            self.logger.error("❌ No authorized clients available")
            return
        
        self.logger.info(f"🎉 DM Responder ready with {len(self.clients)} authorized accounts!")
        self.logger.info("👂 Listening for new DMs...")
        
        # Запускаем все клиенты
        try:
            await asyncio.gather(*[client.run_until_disconnected() for client in self.clients.values()])
        except KeyboardInterrupt:
            self.logger.info("🛑 Stopping DM Responder...")
        finally:
            # Закрываем все соединения
            for client in self.clients.values():
                await client.disconnect()

async def main():
    responder = PostgresDMResponder()
    await responder.run()

if __name__ == "__main__":
    asyncio.run(main())
