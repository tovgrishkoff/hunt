import asyncio
import json
import logging
from datetime import datetime
from telethon import TelegramClient, events
from telethon.tl.types import User

class DMMonitor:
    def __init__(self):
        self.setup_logging()
        self.accounts = []
        self.clients = {}
        self.responses = []
        self.blacklist = []
        self.load_config()
        
    def setup_logging(self):
        """Настройка логирования"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('dm_monitor.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def load_config(self):
        """Загрузка конфигурации"""
        try:
            with open('accounts_config.json', 'r', encoding='utf-8') as f:
                self.accounts = json.load(f)
            self.logger.info(f"Loaded {len(self.accounts)} accounts for DM monitoring")
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}")
            return
            
        # Загружаем шаблоны ответов
        self.load_responses()
        
        # Загружаем черный список
        self.load_blacklist()
    
    def load_responses(self):
        """Загрузка шаблонов ответов"""
        try:
            with open('dm_responses.txt', 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f.readlines()]
            self.responses = [line for line in lines if line]
            self.logger.info(f"Loaded {len(self.responses)} response templates")
        except FileNotFoundError:
            # Создаем файл с примерами ответов
            self.create_default_responses()
    
    def create_default_responses(self):
        """Создание шаблонов ответов по умолчанию"""
        default_responses = [
            "Привет! Спасибо за отклик. Расскажите подробнее о ваших услугах/условиях?",
            "Здравствуйте! Интересует ваш опыт и портфолио. Можете скинуть примеры работ?",
            "Привет! Какие у вас расценки и сроки выполнения?",
            "Спасибо за предложение! Есть ли у вас рекомендации от предыдущих клиентов?",
            "Интересно! Можете рассказать о процессе работы и что входит в стоимость?",
        ]
        
        with open('dm_responses.txt', 'w', encoding='utf-8') as f:
            for response in default_responses:
                f.write(response + '\n')
        
        self.responses = default_responses
        self.logger.info("Created default response templates")
    
    def load_blacklist(self):
        """Загрузка черного списка аккаунтов"""
        try:
            with open('blacklist_accounts.txt', 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f.readlines()]
            self.blacklist = [line for line in lines if line and not line.startswith('#')]
            self.logger.info(f"Loaded {len(self.blacklist)} blacklisted accounts")
        except FileNotFoundError:
            self.blacklist = []
            self.logger.info("No blacklist file found, using empty blacklist")
    
    async def initialize_clients(self):
        """Инициализация клиентов"""
        for account in self.accounts:
            try:
                api_id = int(account['api_id'])
                session_name = account['session_name']
                
                # Приоритет: используем string_session из конфига, если есть
                string_session = account.get('string_session')
                client = None
                
                if string_session and string_session not in ['', 'TO_BE_CREATED', 'null', None]:
                    # Убеждаемся, что string_session это строка
                    if isinstance(string_session, str):
                        session_cleaned = string_session.strip()
                        if session_cleaned:
                            from telethon.sessions import StringSession
                            try:
                                self.logger.info(f"  Using StringSession for {session_name}")
                                session_obj = StringSession(session_cleaned)
                                client = TelegramClient(
                                    session_obj, 
                                    api_id, 
                                    account['api_hash']
                                )
                            except Exception as session_error:
                                self.logger.error(f"  Failed to create StringSession for {session_name}: {session_error}")
                                raise
                
                if not client:
                    # Fallback: используем файловую сессию
                    self.logger.info(f"  Using file session for {session_name}")
                    client = TelegramClient(
                        f"sessions/{session_name}", 
                        api_id, 
                        account['api_hash']
                    )
                
                await client.connect()
                
                # Проверяем авторизацию только для файловых сессий
                if not string_session or string_session in ['', 'TO_BE_CREATED', 'null', None]:
                    if not await client.is_user_authorized():
                        self.logger.warning(f"⚠️ Client {session_name} is not authorized, skipping")
                        await client.disconnect()
                        continue
                
                self.clients[session_name] = client
                me = await client.get_me()
                self.logger.info(f"✅ Initialized client for {session_name} (@{me.username if me.username else me.id})")
            except Exception as e:
                self.logger.error(f"❌ Failed to initialize {account['session_name']}: {e}")
    
    def get_response_template(self, message_text: str):
        """Выбор подходящего шаблона ответа на основе входящего сообщения"""
        message_lower = message_text.lower()
        
        # Простая логика выбора ответа
        if any(word in message_lower for word in ['фото', 'фотограф', 'съемка']):
            return "Спасибо за отклик! Можете показать портфолио и рассказать о расценках?"
        elif any(word in message_lower for word in ['видео', 'видеограф', 'монтаж']):
            return "Интересно! Какие у вас примеры работ и условия сотрудничества?"
        elif any(word in message_lower for word in ['вилла', 'дом', 'аренда', 'жилье']):
            return "Спасибо! Можете рассказать подробнее о вариантах и ценах?"
        else:
            # Возвращаем случайный шаблон
            import random
            return random.choice(self.responses)
    
    async def handle_new_message(self, event, account_name):
        """Обработка нового личного сообщения"""
        try:
            # Получаем информацию о сообщении
            sender = await event.get_sender()
            message = event.message
            
            # Проверяем, что это личное сообщение от пользователя
            if not isinstance(sender, User):
                return
            
            # ЗАЩИТА ОТ ЦИКЛИЧЕСКИХ ОТВЕТОВ
            # Получаем список всех наших аккаунтов
            our_accounts = []
            for account in self.accounts:
                try:
                    client = self.clients[account['session_name']]
                    me = await client.get_me()
                    our_accounts.append(me.id)
                    our_accounts.append(me.username)
                except:
                    pass
            
            # Проверяем, не пишет ли нам другой наш аккаунт
            if sender.id in our_accounts or (sender.username and sender.username in our_accounts):
                self.logger.info(f"🚫 Ignoring message from our own account @{sender.username or sender.id}")
                return
            
            # Проверяем черный список
            sender_username = f"@{sender.username}" if sender.username else None
            if (sender_username and sender_username in self.blacklist) or str(sender.id) in self.blacklist:
                self.logger.info(f"🚫 Ignoring message from blacklisted account @{sender.username or sender.id}")
                return
            
            # Проверяем, не содержит ли сообщение ключевые слова наших автоответчиков
            message_text = message.text or ""
            if any(keyword in message_text.lower() for keyword in ['@lead_hunbot', 'lead_hunbot', 'автоответчик', 'бот']):
                self.logger.info(f"🚫 Ignoring message with bot keywords from @{sender.username or sender.id}")
                return
            
            # Логируем входящее сообщение
            self.logger.info(f"📨 New DM to {account_name} from @{sender.username or sender.id}: {message.text[:100]}...")
            
            # Выбираем шаблон ответа
            response_text = self.get_response_template(message.text)
            
            # Отправляем ответ
            await event.respond(response_text)
            self.logger.info(f"📤 {account_name} replied to @{sender.username or sender.id}")
            
        except Exception as e:
            self.logger.error(f"❌ Error handling message in {account_name}: {e}")
    
    async def start_monitoring(self):
        """Запуск мониторинга личных сообщений для всех аккаунтов"""
        self.logger.info("🔍 Starting DM monitoring for all accounts...")
        
        # Инициализируем клиенты
        await self.initialize_clients()
        
        if not self.clients:
            self.logger.error("❌ No clients initialized. Cannot start monitoring.")
            return
        
        # Регистрируем обработчики для каждого клиента
        for account_name, client in self.clients.items():
            # Создаем отдельный обработчик для каждого клиента
            async def create_handler(client_name, client_obj):
                @client_obj.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
                async def handler(event):
                    await self.handle_new_message(event, client_name)
                return handler
            
            await create_handler(account_name, client)
            self.logger.info(f"✅ Registered DM handler for {account_name}")
        
        self.logger.info(f"🎉 DM monitoring started for {len(self.clients)} accounts! Waiting for messages...")
        
        # Держим скрипт запущенным
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("🛑 Monitoring stopped by user")
        finally:
            # Закрываем все клиенты
            for client in self.clients.values():
                await client.disconnect()

async def main():
    monitor = DMMonitor()
    await monitor.start_monitoring()

if __name__ == "__main__":
    asyncio.run(main())
