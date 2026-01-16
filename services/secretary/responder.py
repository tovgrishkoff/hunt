"""
Обработчик входящих личных сообщений
"""
import asyncio
import random
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict
from sqlalchemy import func, and_

from telethon import TelegramClient
from telethon.events import NewMessage
from telethon.tl.types import User
from telethon.errors import FloodWaitError, UserBotError

from shared.database.session import SessionLocal
from shared.database.models import Account, DMResponse
from services.secretary.gpt_handler import GPTHandler

logger = logging.getLogger(__name__)

# Получатель пересылки (можно вынести в конфиг)
FORWARD_TO_USERNAME = 'grishkoff'


class MessageResponder:
    """Класс для обработки входящих личных сообщений"""
    
    def __init__(self, client_manager, gpt_handler: GPTHandler, blacklist_path: str = '/app/blacklist.txt', forward_to_username: str = FORWARD_TO_USERNAME):
        self.client_manager = client_manager
        self.gpt_handler = gpt_handler
        self.blacklist_path = blacklist_path
        self.blacklist = self._load_blacklist()
        self.forward_to_username = forward_to_username
        # УБРАНО: self.forward_to_entity - теперь получаем entity для каждого клиента отдельно
        
        # Настройки задержек
        config = gpt_handler.config
        self.typing_delay_min = config.get('typing_delay_min', 5)
        self.typing_delay_max = config.get('typing_delay_max', 15)
        
        # Кеш недавно отвеченных сообщений (избежание рекурсии)
        self.recent_responses = {}  # {(account_id, user_id): timestamp}
        self.recent_response_window = 60  # секунд
        
        # Буфер сообщений для debouncing (накопление сообщений перед обработкой)
        # Структура: {(account_id, user_id): {'timer': Task, 'messages': [{'text': str, 'event': Event}], 'sender': User, 'account': Account, 'client': Client}}
        self.message_buffer = {}
        self.buffer_delay = config.get('message_buffer_delay', 7)  # Задержка в секундах
    
    def _load_blacklist(self) -> set:
        """Загрузка черного списка из файла"""
        blacklist = set()
        try:
            blacklist_file = Path(self.blacklist_path)
            if blacklist_file.exists():
                with open(blacklist_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            blacklist.add(line.lower())
                logger.info(f"✅ Loaded {len(blacklist)} entries from blacklist")
            else:
                logger.warning(f"⚠️ Blacklist file not found: {blacklist_file}")
        except Exception as e:
            logger.error(f"❌ Error loading blacklist: {e}")
        
        return blacklist
    
    def is_blacklisted(self, user_id: int, username: Optional[str] = None) -> bool:
        """
        Проверка, находится ли пользователь в черном списке
        
        Args:
            user_id: ID пользователя
            username: Username пользователя (опционально)
        
        Returns:
            True если в черном списке
        """
        user_id_str = str(user_id)
        username_lower = username.lower() if username else None
        
        return (
            user_id_str in self.blacklist or
            username_lower in self.blacklist or
            (username_lower and f"@{username_lower}" in self.blacklist)
        )
    
    def recently_responded(self, account_id: int, user_id: int) -> bool:
        """
        Проверка, не отвечали ли мы недавно (избежание рекурсии)
        
        Args:
            account_id: ID аккаунта
            user_id: ID пользователя
        
        Returns:
            True если недавно отвечали
        """
        key = (account_id, user_id)
        now = datetime.utcnow()
        
        if key in self.recent_responses:
            last_response_time = self.recent_responses[key]
            if (now - last_response_time).total_seconds() < self.recent_response_window:
                return True
        
        # Очищаем старые записи
        self.recent_responses = {
            k: v for k, v in self.recent_responses.items()
            if (now - v).total_seconds() < self.recent_response_window
        }
        
        return False
    
    def mark_responded(self, account_id: int, user_id: int):
        """Пометить, что мы ответили пользователю"""
        self.recent_responses[(account_id, user_id)] = datetime.utcnow()
    
    async def check_if_active_conversation(self, client: TelegramClient, user: User) -> bool:
        """
        Проверка, идет ли активная переписка (есть ли ответы пользователя после нашего последнего сообщения)
        
        Args:
            client: Telegram клиент
            user: Пользователь
        
        Returns:
            True если идет переписка (пользователь уже ответил после нашего последнего сообщения)
        """
        try:
            # Получаем последние 10 сообщений
            messages = []
            async for message in client.iter_messages(user, limit=10):
                messages.append(message)
            
            if not messages:
                return False
            
            # Ищем наше последнее сообщение (out=True)
            our_last_message_index = None
            for i, msg in enumerate(messages):
                if msg.out:  # Наше сообщение
                    our_last_message_index = i
                    break
            
            # Если нет наших сообщений - это первое сообщение, не переписка
            if our_last_message_index is None:
                return False
            
            # Проверяем, есть ли сообщения от пользователя ПОСЛЕ нашего последнего
            # (сообщения с меньшим индексом = более новые)
            for i in range(our_last_message_index):
                if not messages[i].out:  # Сообщение от пользователя
                    # Есть ответ пользователя после нашего последнего сообщения
                    logger.debug(f"  💬 Found user reply after our last message (message {i} of {len(messages)})")
                    return True
            
            # Нет ответов пользователя после нашего последнего сообщения
            return False
            
        except Exception as e:
            logger.warning(f"  ⚠️ Error checking conversation status: {e}")
            # В случае ошибки считаем, что переписки нет (отвечаем как обычно)
            return False
    
    async def forward_message_to_grishkoff(
        self,
        client: TelegramClient,
        event: NewMessage.Event,
        account: Account,
        sender: User,
        username: str,
        user_id: int,
        message_text: str,
        has_media: bool
    ):
        """
        Пересылка сообщения на @grishkoff
        
        Args:
            client: Telegram клиент
            event: Событие сообщения
            account: Аккаунт из БД
            sender: Отправитель
            username: Username отправителя
            user_id: ID отправителя
            message_text: Текст сообщения
            has_media: Есть ли медиа
        """
        try:
            # ИЗМЕНЕНИЕ: Получаем entity для КОНКРЕТНОГО клиента, а не используем общий
            # Это предотвращает ошибку PeerInvalid для остальных аккаунтов
            try:
                target_entity = await client.get_input_entity(self.forward_to_username)
            except Exception as e:
                logger.error(f"  ❌ Client {account.session_name} cannot find @{self.forward_to_username}: {e}")
                return
            
            # Формируем префикс с информацией об отправителе
            forward_prefix = (
                f"📬 Сообщение для @{self.forward_to_username}\n\n"
                f"От: @{username} (ID: {user_id})\n"
                f"Аккаунт: {account.session_name}\n"
                f"{'Медиа: ✅' if has_media else ''}\n"
                f"{'─' * 40}\n\n"
            )
            
            # Отправляем префикс с информацией
            try:
                await client.send_message(
                    target_entity,
                    forward_prefix,
                    silent=False
                )
                
                # Пересылаем оригинальное сообщение
                await client.forward_messages(
                    target_entity,
                    event.message,
                    silent=True  # Без звука, так как уже отправили префикс
                )
                
                logger.info(f"  ✅ Forwarded message from @{username} to @{self.forward_to_username}")
                
            except FloodWaitError as e:
                logger.warning(f"  ⏳ FloodWait {e.seconds} seconds for forwarding")
                await asyncio.sleep(min(e.seconds, 300))
            except Exception as e:
                logger.error(f"  ❌ Error forwarding message: {e}", exc_info=True)
                
        except Exception as e:
            logger.error(f"  ❌ Error in forward_message_to_grishkoff: {e}", exc_info=True)
    
    async def get_conversation_history(self, client: TelegramClient, user: User, limit: int = 15) -> List[Dict]:
        """
        Получить историю переписки с пользователем (расширенная для контекста)
        
        Args:
            client: Telegram клиент
            user: Пользователь
            limit: Максимум сообщений (по умолчанию 15 для лучшего контекста)
        
        Returns:
            Список сообщений в формате [{"role": "user", "content": "..."}, ...]
        """
        try:
            messages = []
            async for message in client.iter_messages(user, limit=limit, reverse=True):
                if not message.text:
                    continue
                
                # Определяем роль (user или assistant)
                if message.out:
                    role = "assistant"
                else:
                    role = "user"
                
                messages.append({
                    "role": role,
                    "content": message.text
                })
            
            return messages
            
        except Exception as e:
            logger.warning(f"  ⚠️ Error getting conversation history: {e}")
            return []
    
    async def simulate_typing(self, client: TelegramClient, user: User):
        """
        Имитация печатания (typing simulation)
        
        Args:
            client: Telegram клиент
            user: Пользователь
        """
        try:
            # Задержка перед началом печатания
            await asyncio.sleep(random.uniform(1, 3))
            
            # Показываем статус "печатает"
            await client.send_read_acknowledge(user)
            
            # Имитируем печатание (можно использовать action typing если доступно)
            delay = random.uniform(self.typing_delay_min, self.typing_delay_max)
            await asyncio.sleep(delay)
            
        except Exception as e:
            logger.debug(f"  ⚠️ Error simulating typing: {e}")
            # Если не получилось, просто ждем
            await asyncio.sleep(random.uniform(self.typing_delay_min, self.typing_delay_max))
    
    def _get_buffer_key(self, account_id: int, user_id: int) -> tuple:
        """Получить ключ для буфера сообщений"""
        return (account_id, user_id)
    
    async def process_buffered_messages(
        self,
        account_id: int,
        user_id: int,
        sender: User,
        account: Account,
        client: TelegramClient
    ):
        """
        Обработка накопленных сообщений из буфера
        
        Args:
            account_id: ID аккаунта
            user_id: ID пользователя
            sender: Объект пользователя
            account: Аккаунт из БД
            client: Telegram клиент
        """
        logger.info(f"⏰ [DEBUG] Таймер истек для user_id={user_id}, account_id={account_id}. Начинаем обработку буфера.")
        
        try:
            buffer_key = self._get_buffer_key(account_id, user_id)
            logger.debug(f"  📦 [DEBUG] Buffer key: {buffer_key}")
            
            # Получаем сообщения из буфера
            if buffer_key not in self.message_buffer:
                logger.warning(f"⚠️ [DEBUG] Буфер пуст для {buffer_key} (user_id={user_id}), выход.")
                return
            
            buffer_data = self.message_buffer.pop(buffer_key)
            messages = buffer_data.get('messages', [])
            
            logger.info(f"📩 [DEBUG] Накоплено сообщений: {len(messages)} для user_id={user_id}")
            
            if not messages:
                logger.warning(f"⚠️ [DEBUG] Список сообщений пуст для user_id={user_id}")
                return
            
            # Склеиваем все сообщения в один текст
            combined_text = '\n'.join([msg.get('text', '') for msg in messages if msg.get('text')])
            
            logger.info(f"📩 [DEBUG] Склеенный текст (первые 100 символов): {combined_text[:100]}...")
            
            if not combined_text.strip():
                logger.warning(f"⚠️ [DEBUG] Склеенный текст пуст для user_id={user_id}")
                return
            
            username = getattr(sender, 'username', None) or f"ID{user_id}"
            logger.info(f"📨 [DEBUG] Processing {len(messages)} buffered message(s) from @{username}: {combined_text[:100]}...")
            
            # Используем последнее событие для пересылки (если нужно)
            last_event = messages[-1].get('event') if messages else None
            logger.debug(f"  📎 [DEBUG] Last event: {'present' if last_event else 'None'}")
            
            # Проверяем наличие необходимых объектов
            if not client:
                logger.error(f"🔥 [ERROR] client is None для user_id={user_id}")
                return
            
            if not account:
                logger.error(f"🔥 [ERROR] account is None для user_id={user_id}")
                return
            
            if not sender:
                logger.error(f"🔥 [ERROR] sender is None для user_id={user_id}")
                return
            
            logger.info(f"🧠 [DEBUG] Отправляем запрос в _handle_message_internal...")
            
            # Вызываем основную логику обработки с объединенным текстом
            await self._handle_message_internal(
                combined_text=combined_text,
                sender=sender,
                account=account,
                client=client,
                event=last_event,
                user_id=user_id
            )
            
            logger.info(f"✅ [DEBUG] Обработка буфера завершена успешно для user_id={user_id}")
            
        except asyncio.CancelledError:
            logger.warning(f"⏱️ [DEBUG] Таймер отменен для user_id={user_id}")
            raise
        except Exception as e:
            # Детальное логирование ошибки
            logger.error(f"🔥 [ERROR] Ошибка в process_buffered_messages для user_id={user_id}, account_id={account_id}: {e}")
            logger.error(f"🔥 [ERROR] Тип ошибки: {type(e).__name__}")
            import traceback
            error_traceback = traceback.format_exc()
            logger.error(f"🔥 [ERROR] Traceback:\n{error_traceback}")
    
    async def _handle_message_internal(
        self,
        combined_text: str,
        sender: User,
        account: Account,
        client: TelegramClient,
        event: Optional[NewMessage.Event] = None,
        user_id: Optional[int] = None
    ):
        """
        Внутренняя логика обработки сообщения (без буферизации)
        
        Args:
            combined_text: Объединенный текст сообщений
            sender: Отправитель
            account: Аккаунт
            client: Клиент
            event: Событие сообщения (для пересылки)
            user_id: ID пользователя
        """
        try:
            if not user_id:
                user_id = sender.id
            
            username = getattr(sender, 'username', None) or f"ID{user_id}"
            
            # Проверяем, идет ли уже переписка (есть ли ответы пользователя после нашего последнего сообщения)
            is_active_conversation = await self.check_if_active_conversation(client, sender)
            
            # ВАЖНО: Мы убрали return, чтобы бот мог вести диалог (квалифицировать лида или продавать)
            # Бот должен отвечать на ВСЕ сообщения, даже если диалог идет.
            # Это необходимо для задач квалификации (выяснение цены) и продажи.
            if is_active_conversation:
                # Идет переписка - пересылаем админу для мониторинга, НО ПРОДОЛЖАЕМ ОТВЕЧАТЬ
                logger.info(f"  💬 Active conversation detected with @{username} - forwarding to admin, BUT continuing GPT reply")
                if event:
                    try:
                        await self.forward_message_to_grishkoff(
                            client=client,
                            event=event,
                            account=account,
                            sender=sender,
                            username=username,
                            user_id=user_id,
                            message_text=combined_text,
                            has_media=bool(event.message.media) if event else False
                        )
                    except Exception as e:
                        logger.warning(f"  ⚠️ Failed to forward message: {e}")
                        # Не прерываем выполнение, продолжаем отвечать
            
            # ВСЕГДА отвечаем через GPT (не выходим из функции)
            # Это позволяет боту вести диалог для квалификации и продажи
            # Получаем расширенную историю переписки (10-15 сообщений для контекста)
            logger.debug(f"📚 [DEBUG] Получаем историю переписки для @{username}...")
            try:
                conversation_history = await self.get_conversation_history(client, sender, limit=15)
                logger.info(f"📚 [DEBUG] Получена история: {len(conversation_history)} сообщений")
            except Exception as e:
                logger.error(f"🔥 [ERROR] Ошибка при получении истории для @{username}: {e}")
                import traceback
                logger.error(f"🔥 [ERROR] Traceback:\n{traceback.format_exc()}")
                conversation_history = []  # Продолжаем без истории
            
            # Генерируем ответ через GPT с учетом истории
            logger.debug(f"🧠 [DEBUG] Отправляем запрос в GPT для @{username}...")
            try:
                response_text = await self.gpt_handler.generate_response(
                    incoming_message=combined_text,
                    conversation_history=conversation_history,
                    user_info={"id": user_id, "username": username}
                )
                logger.info(f"🧠 [DEBUG] Ответ от GPT получен: {len(response_text)} символов")
            except Exception as e:
                logger.error(f"🔥 [ERROR] Ошибка при генерации ответа GPT для @{username}: {e}")
                import traceback
                logger.error(f"🔥 [ERROR] Traceback:\n{traceback.format_exc()}")
                response_text = "Привет! Спасибо за сообщение. Я сейчас занят, но обязательно отвечу позже! 😊"
            
            # Имитируем печатание
            logger.debug(f"⌨️ [DEBUG] Имитируем печатание для @{username}...")
            await self.simulate_typing(client, sender)
            
            # Отправляем ответ (используем последнее событие или отправляем новое сообщение)
            logger.debug(f"📤 [DEBUG] Отправляем ответ @{username}...")
            try:
                if event:
                    await event.reply(response_text)
                    logger.debug(f"  ✅ [DEBUG] Ответ отправлен через event.reply")
                else:
                    await client.send_message(sender, response_text)
                    logger.debug(f"  ✅ [DEBUG] Ответ отправлен через client.send_message")
                
                logger.info(f"  ✅ Replied to @{username}: {response_text[:100]}...")
                
                # Сохраняем в БД
                db = SessionLocal()
                try:
                    dm_response = DMResponse(
                        account_id=account.id,
                        user_id=user_id,
                        username=username,
                        incoming_message=combined_text[:1000],  # Ограничиваем длину
                        response_text=response_text[:1000],
                        service_type='gpt-4o-mini',
                        sent_at=datetime.utcnow()
                    )
                    db.add(dm_response)
                    db.commit()
                    
                    # Помечаем, что мы ответили
                    self.mark_responded(account.id, user_id)
                    
                    logger.debug(f"  💾 Saved response to DB")
                    
                except Exception as e:
                    db.rollback()
                    logger.error(f"  ❌ Error saving to DB: {e}")
                finally:
                    db.close()
                
            except FloodWaitError as e:
                logger.warning(f"  ⏳ FloodWait {e.seconds} seconds for @{username}")
                await asyncio.sleep(min(e.seconds, 300))
            except Exception as e:
                logger.error(f"  ❌ Error sending reply: {e}", exc_info=True)
                
        except Exception as e:
            logger.error(f"  ❌ Error in _handle_message_internal: {e}", exc_info=True)
    
    async def handle_message(self, event: NewMessage.Event, account: Account, client: TelegramClient):
        """
        Обработка входящего сообщения с буферизацией (debouncing)
        
        Args:
            event: Событие нового сообщения
            account: Аккаунт из БД
            client: Telegram клиент
        """
        try:
            # ЛОГ: Вход в функцию
            message_text_preview = (event.message.text or "")[:50] if event.message else "No text"
            logger.info(f"🔥🔥🔥 [ENTRY] handle_message ВЫЗВАН! sender_id={event.message.sender_id if event.message else 'N/A'}, text={message_text_preview}")
            
            # Получаем информацию о пользователе
            sender = await event.get_sender()
            
            if not sender:
                logger.debug(f"  ⏭️ Skipping - sender is None")
                return
            
            # Проверяем, что это личное сообщение (не группа)
            if not isinstance(sender, User):
                logger.debug(f"  ⏭️ Skipping - not a User instance: {type(sender)}")
                return
            
            # Проверяем, что это не бот
            if getattr(sender, 'bot', False):
                logger.debug(f"  ⏭️ Skipping message from bot: {sender.id}")
                return
            
            user_id = sender.id
            username = getattr(sender, 'username', None) or f"ID{user_id}"
            message_text = event.message.text or ""
            
            logger.info(f"📨 [DEBUG] Пришло сообщение от @{username} (ID: {user_id}): {message_text[:50]}...")
            
            # Проверяем черный список
            if self.is_blacklisted(user_id, username):
                logger.info(f"  🚫 Blocked message from blacklisted user: @{username}")
                return
            
            # ВРЕМЕННО ОТКЛЮЧЕНО для тестирования: Проверяем, не отвечали ли мы недавно (избежание рекурсии)
            # if self.recently_responded(account.id, user_id):
            #     logger.debug(f"  ⏭️ Skipping - recently responded to @{username}")
            #     return
            logger.debug(f"  ✅ [TEST] Проверка recently_responded временно отключена для тестирования")
            
            # Проверяем в БД, не отвечали ли мы совсем недавно (за последнюю секунду)
            db = SessionLocal()
            try:
                one_second_ago = datetime.utcnow() - timedelta(seconds=1)
                recent_response = db.query(DMResponse).filter(
                    and_(
                        DMResponse.account_id == account.id,
                        DMResponse.user_id == user_id,
                        DMResponse.sent_at >= one_second_ago
                    )
                ).first()
                
                if recent_response:
                    logger.debug(f"  ⏭️ Skipping - responded less than 1 second ago to @{username}")
                    return
                
            finally:
                db.close()
            
            logger.debug(f"  📨 Buffering message from @{username}: {message_text[:50]}...")
            
            # БУФЕРИЗАЦИЯ: Добавляем сообщение в буфер
            buffer_key = self._get_buffer_key(account.id, user_id)
            
            # Если есть активный таймер - отменяем его
            if buffer_key in self.message_buffer:
                old_timer = self.message_buffer[buffer_key].get('timer')
                if old_timer and not old_timer.done():
                    old_timer.cancel()
                    logger.debug(f"  ⏱️ Cancelled previous timer for @{username}")
            else:
                # Создаем новую запись в буфере
                self.message_buffer[buffer_key] = {
                    'messages': [],
                    'sender': sender,
                    'account': account,
                    'client': client
                }
            
            # Добавляем сообщение в буфер
            self.message_buffer[buffer_key]['messages'].append({
                'text': message_text,
                'event': event,
                'timestamp': datetime.utcnow()
            })
            
            # Создаем новый таймер для обработки буфера
            async def process_after_delay():
                try:
                    logger.debug(f"⏱️ [DEBUG] Таймер запущен, ждем {self.buffer_delay} секунд для @{username}")
                    await asyncio.sleep(self.buffer_delay)
                    logger.debug(f"⏱️ [DEBUG] Таймер истек, вызываем process_buffered_messages для @{username}")
                    
                    # Убеждаемся, что все параметры на месте
                    if not client:
                        logger.error(f"🔥 [ERROR] client потерян в таймере для @{username}")
                        return
                    if not account:
                        logger.error(f"🔥 [ERROR] account потерян в таймере для @{username}")
                        return
                    if not sender:
                        logger.error(f"🔥 [ERROR] sender потерян в таймере для @{username}")
                        return
                    
                    await self.process_buffered_messages(
                        account_id=account.id,
                        user_id=user_id,
                        sender=sender,
                        account=account,
                        client=client
                    )
                except asyncio.CancelledError:
                    logger.debug(f"⏱️ [DEBUG] Timer cancelled for @{username}")
                except Exception as e:
                    logger.error(f"🔥 [ERROR] Ошибка в process_after_delay для @{username}: {e}")
                    import traceback
                    logger.error(f"🔥 [ERROR] Traceback:\n{traceback.format_exc()}")
            
            timer_task = asyncio.create_task(process_after_delay())
            self.message_buffer[buffer_key]['timer'] = timer_task
            
            logger.debug(f"  ⏱️ Timer started ({self.buffer_delay}s) for @{username}, buffered: {len(self.message_buffer[buffer_key]['messages'])} messages")
            
        except Exception as e:
            logger.error(f"  ❌ Error handling message: {e}", exc_info=True)
    
    def setup_handlers(self):
        """Настройка обработчиков событий для всех клиентов"""
        accounts_map = {}  # {account_name: account}
        
        # Загружаем аккаунты из БД
        db = SessionLocal()
        try:
            accounts = db.query(Account).filter(Account.status == 'active').all()
            for account in accounts:
                accounts_map[account.session_name] = account
        finally:
            db.close()
        
        # Регистрируем обработчики для каждого клиента
        for account_name, client in self.client_manager.clients.items():
            account = accounts_map.get(account_name)
            if not account:
                logger.warning(f"  ⚠️ Account {account_name} not found in DB, skipping handler")
                continue
            
            # === ТЕСТ: Ping-Pong для проверки работы Telethon ===
            # Используем функцию-фабрику для правильного замыкания
            def create_ping_handler(cli, acc_name):
                # ДИАГНОСТИКА: ловим ВСЕ входящие сообщения (private и non-private)
                @cli.on(NewMessage(incoming=True))
                async def debug_all_messages(event):
                    try:
                        text = (
                            getattr(event.message, "message", None)
                            or getattr(event.message, "text", None)
                            or "(no text)"
                        )
                        sender = await event.get_sender()
                        sender_id = sender.id if sender else "Unknown"
                        sender_username = getattr(sender, "username", None) if sender else None
                        logger.info(
                            f"🔍 [DEBUG] {acc_name} получил сообщение "
                            f"от {sender_username or sender_id}: {text[:50]} "
                            f"(is_private={event.is_private})"
                        )

                        # Отвечаем на /ping только в личке
                        if event.is_private and text.strip().lower() == "/ping":
                            logger.info(f"🏓 [PING] PONG received on {acc_name}!")
                            await event.reply(f"Pong! Я работаю на {acc_name}")
                            logger.info(f"🏓 [PING] Ответ отправлен с {acc_name}")
                    except Exception as e:
                        logger.error(f"🔍 [DEBUG] Ошибка в debug_all_messages для {acc_name}: {e}")
                        import traceback
                        logger.error(f"🔍 [DEBUG] Traceback:\n{traceback.format_exc()}")

                return debug_all_messages

            create_ping_handler(client, account_name)
            # ====================================================
            
            # КРИТИЧНО: Создаем правильное замыкание для каждого обработчика
            # Используем функцию-фабрику, чтобы каждая итерация цикла создавала свои переменные
            def create_handler(acc, cli, acc_name):
                @cli.on(NewMessage(incoming=True, func=lambda e: e.is_private))
                async def handler(event):
                    logger.info(f"🔥 [HANDLER] Обработчик сработал для {acc_name}! Событие получено.")
                    logger.info(f"🔥 [HANDLER] event.message.text: {event.message.text if event.message else 'None'}")
                    logger.info(f"🔥 [HANDLER] event.message.sender_id: {event.message.sender_id if event.message else 'None'}")
                    try:
                        await self.handle_message(event, acc, cli)
                        logger.info(f"🔥 [HANDLER] handle_message завершен для {acc_name}")
                    except Exception as e:
                        logger.error(f"🔥 [HANDLER] Ошибка в handle_message для {acc_name}: {e}")
                        import traceback
                        logger.error(f"🔥 [HANDLER] Traceback:\n{traceback.format_exc()}")
                return handler
            
            # Создаем обработчик с правильным замыканием
            create_handler(account, client, account_name)
            
            logger.info(f"  ✅ Registered handler for {account_name} (включая /ping)")
        
        logger.info(f"✅ Registered handlers for {len(self.client_manager.clients)} accounts")

