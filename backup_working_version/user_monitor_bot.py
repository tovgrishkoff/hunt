from telethon import TelegramClient, events
from telethon.tl.types import PeerChannel, PeerChat, PeerUser
from telethon.tl.functions.messages import ExportChatInviteRequest
import re
from patterns import PATTERNS
from datetime import datetime
import asyncio
import logging
import json
from config import API_ID, API_HASH, PHONE_NUMBER, MONITORING_CONFIG, BOT_TOKEN, DB_DSN
import os
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from database import Database
from monitor import MessageMonitor
from content import MONITORING_TOPICS
# from mvp_release.patterns import PATTERNS, NICHES_KEYWORDS

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Загрузка известных чатов
try:
    with open('known_chats.json', 'r', encoding='utf-8') as f:
        known_chats = json.load(f)
        monitored_chats = list(known_chats.keys())
        logger.info(f"Загружено {len(monitored_chats)} чатов для мониторинга")
except FileNotFoundError:
    known_chats = {}
    monitored_chats = []
    logger.info("Файл known_chats.json не найден, начинаем с пустого списка чатов")

# Ваш Telegram ID для теста
test_user_id = 210147380

# Быстрые стоп-фразы для приветствий/сервисных ботов (не лиды)
STOP_PHRASES = [
    "добро пожаловать в группу",
    "welcome to",
    "chatkeeperbot",
    "научись работать с данными",
    "вступил в группу",
    "joined the group",
]

# Кэш инвайт-ссылок, чтобы не экспортировать заново на каждое сообщение
INVITE_LINK_CACHE: dict[str, str] = {}

def is_spam(text: str) -> bool:
    """
    Быстрая проверка на очевидный спам (продажа документов, реклама обмена валют).
    Возвращает True, если сообщение явный спам и должно быть заблокировано.
    """
    if not text:
        return False
    
    text_lower = text.lower()

    # 0. Стоп-фразы (приветствия ботов, авто-сервисные сообщения)
    if any(phrase in text_lower for phrase in STOP_PHRASES):
        logger.info(f"🚫 Спам отфильтрован (стоп-фраза): {text[:80]}...")
        return True
    
    # 1. Проверка на продажу документов - уникальные маркеры, которых нет в обычных чатах Бали
    spam_keywords = [
        'мед книжка', 'мед карта', 'снилс', 'инн', 'корочка сварщика', 'корочка альпиниста',
        'трудовой договор', 'трудовая книжка', 'студенческий билет', 'свидетельство о рождении',
        'аттестат', 'метрика', 'доверенност', 'согласия',
        'получению водительских прав', 'новые или дубликат', 'открытие категории',
        'миграционка', 'регистратура', 'под заказ любой документ', 'и другие документы',
        'предоставлю услуги по',
        # Комбинации стран + права + паспорт
        'рус права', 'узб права', 'тадж права', 'киргиз права', 'казак права', 'укр права',
        'азер права', 'армен права', 'грузия права', 'чехия id', 'польша права id',
        'франция id пас', 'литва id', 'эстония id', 'румыния id', 'австрия id',
        'германия id', 'берлин id пас', 'бъалгария id', 'брюссель права id',
        'нидерландия пас', 'бельгия id', 'канада id пас', 'италия пас', 'эмираты'
    ]
    
    # Проверяем наличие спам-ключевых слов
    for keyword in spam_keywords:
        if keyword in text_lower:
            logger.info(f"🚫 Спам отфильтрован (ключевое слово '{keyword}'): {text[:50]}...")
            return True
    
    # 2. Проверка комбинаций: много флагов стран + документы = спам
    flag_count = len(re.findall(r'[🇷🇺🇺🇿🇹🇯🇵🇼🇰🇿🇺🇦🇦🇿🇦🇲🇬🇪🇨🇿🇵🇱🇫🇷🇱🇹🇪🇪🇪🇺🇷🇴🇦🇹🇩🇪🇵🇫🇧🇬🇧🇪🇵🇾🇨🇦🇮🇹🇦🇪]', text))
    document_emoji_count = len(re.findall(r'[📕📙📘📜📃💳]', text))
    document_keywords_count = len(re.findall(r'\b(прав|пас|id|диплом|аттестат|инн|снилс|миграционк|патент|корочк|свидетельств|мед\s+книжк|мед\s+карт|трудовой|студенческ)\b', text_lower))
    
    # Если много флагов И документов - это точно спам
    if flag_count > 5 and (document_keywords_count > 3 or document_emoji_count > 2):
        logger.info(f"🚫 Спам отфильтрован (много флагов {flag_count} + документов {document_keywords_count}): {text[:50]}...")
        return True
    
    # 3. Проверка на рекламу обмена валют (ХАНИ МАНИ и подобные)
    currency_spam_keywords = [
        'хани мани', 'hani mani', 'безопасные денежные переводы', 'безопасные переводы',
        'нужно поменять валюту', 'твоё решение', 'твое решение', 'спектр услуг',
        'доп услуги', 'время работы: 9:00-22:00', 'возникли вопросы',
        'обращайтесь только по указанному контакту', 'часто мошенники используют похожие названия'
    ]
    
    for keyword in currency_spam_keywords:
        if keyword in text_lower:
            logger.info(f"🚫 Спам отфильтрован (реклама обмена валют '{keyword}'): {text[:50]}...")
            return True
    
    # 4. Проверка на телефонные номера в конце сообщения (признак спама)
    if re.search(r'\+7\d{10}|\+\d{10,15}', text):
        # Проверяем контекст - если это просто телефон без контекста документов/валют, не блокируем
        if document_keywords_count > 2 or flag_count > 3:
            logger.info(f"🚫 Спам отфильтрован (телефон + контекст документов/валют): {text[:50]}...")
            return True
    
    return False


def _get_thread_id_from_event(event) -> int | None:
    """
    Возвращает thread_id (top message id) для форумных топиков, если доступно.
    Для корневого сообщения топика (forum_topic=True) thread_id = message.id.
    """
    try:
        reply_to = getattr(event.message, "reply_to", None)
        if reply_to:
            top_id = getattr(reply_to, "reply_to_top_id", None)
            if top_id:
                return int(top_id)
            if getattr(reply_to, "forum_topic", False) and getattr(event.message, "id", None):
                return int(event.message.id)
    except Exception:
        return None
    return None


async def _get_join_link_if_available(client: TelegramClient, chat) -> str | None:
    """
    Пытается получить invite link для приватных чатов (если доступно боту/аккаунту).
    Возвращает None, если прав нет или ссылка недоступна.
    """
    chat_id = str(getattr(chat, "id", ""))
    if chat_id and chat_id in INVITE_LINK_CACHE:
        return INVITE_LINK_CACHE[chat_id]

    try:
        exported = await client(ExportChatInviteRequest(peer=chat))
        link = getattr(exported, "link", None)
        if link:
            INVITE_LINK_CACHE[chat_id] = link
            return link
    except Exception as e:
        logger.info(f"[Monitor] Invite link недоступен для чата {chat_id}: {e}")
    return None

async def main():
    # Инициализация Telethon клиента
    # Используем сессию из корневой директории, если она есть и авторизована
    session_path = '../monitor_session.session'
    if not os.path.exists(session_path):
        session_path = 'monitor_session'
    
    client = TelegramClient(session_path, API_ID, API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        await client.start(phone=PHONE_NUMBER)
    logger.info("Telethon клиент успешно запущен")

    # Инициализация базы данных
    db = Database(DB_DSN)
    await db.connect()
    
    # Получаем OpenAI API ключ из переменной окружения
    openai_api_key = os.getenv('OPENAI_API_KEY')
    if openai_api_key:
        logger.info("🔑 OpenAI API ключ найден, AI классификатор будет активирован")
    else:
        logger.info("⚠️ OpenAI API ключ не найден, будет использована только базовая классификация")
    
    # Создаем бота ТОЛЬКО для отправки сообщений (без polling)
    # Используем токен основного бота для отправки уведомлений
    main_bot_token = '8233775715:AAGABqq1Qibf2RmxZm-tB97dtMNxLyqs0y8'
    bot = Bot(token=main_bot_token)
    
    # Создаем монитор
    monitor = MessageMonitor(bot, db, openai_api_key)
    await monitor.initialize()
    logger.info("База данных и монитор успешно инициализированы")

    # Выводим всех подписчиков и их категории
    subscribers = await db.get_all_users()
    for user in subscribers:
        logger.info(f"Пользователь {user['user_id']} подписан на: {user['categories']}")

    # Убираем диспетчер и polling - кнопки будут обрабатываться в основном боте

    @client.on(events.NewMessage())
    async def handler(event):
        try:
            chat = await event.get_chat()
            chat_id = str(chat.id)
            chat_title = chat.title if hasattr(chat, 'title') else 'Private Chat'
            logger.info(f"[Monitor] Получено сообщение в чате: {chat_title} (ID: {chat_id})")
            logger.info(f"[Monitor] Текст сообщения: {event.message.text}")

            # Получаем информацию об отправителе
            sender = await event.get_sender()
            sender_username = sender.username if hasattr(sender, 'username') else None
            sender_id = sender.id if hasattr(sender, 'id') else None
            sender_first_name = sender.first_name if hasattr(sender, 'first_name') else None
            sender_last_name = sender.last_name if hasattr(sender, 'last_name') else None
            sender_is_bot = bool(getattr(sender, "bot", False))

            # 1) Проверка is_bot: сообщения от ботов игнорируем сразу (приветствия/админ-боты)
            if sender_is_bot:
                logger.info(
                    f"🚫 Пропускаем сообщение от бота @{sender_username or ''} (ID: {sender_id})"
                )
                return

            # Сохраняем новый чат, если он ещё не известен
            if chat_id not in known_chats:
                known_chats[chat_id] = {
                    'title': chat_title,
                    'type': 'Private',
                    'first_seen': str(event.message.date)
                }
                monitored_chats.append(chat_id)
                with open('known_chats.json', 'w', encoding='utf-8') as f:
                    json.dump(known_chats, f, ensure_ascii=False, indent=2)
                logger.info(f"Добавлен новый чат: {chat_title} (ID: {chat_id})")

            # Только для чатов из списка мониторинга
            if chat_id not in monitored_chats:
                logger.info(f"Чат {chat_id} не в списке мониторинга, пропускаем")
                return

            # --- БЫСТРАЯ ПРОВЕРКА НА СПАМ (до всех остальных проверок) ---
            if event.message.text and is_spam(event.message.text):
                logger.info(f"🚫 Спам отфильтрован на раннем этапе, сообщение пропущено: {event.message.text[:100]}...")
                return
            # -----------------------------------------------------------------

            # Формируем ссылку на конкретное сообщение
            message_link = None
            chat_username = None
            chat_join_link = None
            if hasattr(event.message, 'id'):
                try:
                    thread_id = _get_thread_id_from_event(event)
                    # Пытаемся получить username чата через get_entity
                    try:
                        entity = await client.get_entity(chat.id)
                        if hasattr(entity, 'username') and entity.username:
                            chat_username = entity.username
                            chat_join_link = f"https://t.me/{chat_username}"
                            if thread_id:
                                message_link = f"https://t.me/{chat_username}/{thread_id}/{event.message.id}"
                            else:
                                message_link = f"https://t.me/{chat_username}/{event.message.id}"
                            logger.info(f"[Monitor] Сформирована ссылка для публичного чата: {message_link}")
                        else:
                            # Для приватных чатов используем правильный формат
                            chat_id_int = abs(chat.id) if chat.id < 0 else chat.id
                            # Убираем префикс -100 для супергрупп
                            if chat_id_int >= 1000000000000:
                                chat_id_for_link = str(chat_id_int)[4:]  # Убираем первые 4 цифры (1000)
                            else:
                                chat_id_for_link = str(chat_id_int)
                            
                            if chat_id_for_link.isdigit():
                                if thread_id:
                                    message_link = f"https://t.me/c/{chat_id_for_link}/{thread_id}/{event.message.id}"
                                else:
                                    message_link = f"https://t.me/c/{chat_id_for_link}/{event.message.id}"
                                logger.info(f"[Monitor] Сформирована ссылка для приватного чата: {message_link} (ID чата: {chat_id_for_link})")
                                chat_join_link = await _get_join_link_if_available(client, chat)
                            else:
                                logger.warning(f"[Monitor] Некорректный ID чата для ссылки: {chat_id_for_link}")
                    except Exception as e:
                        logger.warning(f"[Monitor] Не удалось получить entity для чата {chat.id}: {e}")
                        # Fallback: используем старый метод
                        if hasattr(chat, 'username') and chat.username:
                            chat_username = chat.username
                            chat_join_link = f"https://t.me/{chat_username}"
                            if thread_id:
                                message_link = f"https://t.me/{chat_username}/{thread_id}/{event.message.id}"
                            else:
                                message_link = f"https://t.me/{chat_username}/{event.message.id}"
                        else:
                            chat_id_str = str(abs(chat.id))
                            if chat_id_str.startswith('100'):
                                chat_id_for_link = chat_id_str[3:]  # Убираем '100'
                            else:
                                chat_id_for_link = chat_id_str
                            
                            if chat_id_for_link.isdigit():
                                if thread_id:
                                    message_link = f"https://t.me/c/{chat_id_for_link}/{thread_id}/{event.message.id}"
                                else:
                                    message_link = f"https://t.me/c/{chat_id_for_link}/{event.message.id}"
                                chat_join_link = await _get_join_link_if_available(client, chat)
                except Exception as e:
                    logger.error(f"[Monitor] Ошибка при формировании ссылки: {e}")
                    message_link = None

            # Обрабатываем сообщение через монитор
            await monitor.process_message_from_subscriber(
                message_text=event.message.text,
                chat_title=chat_title,
                message_link=message_link,
                chat_username=chat_username,
                chat_join_link=chat_join_link,
                sender_username=sender_username,
                sender_id=sender_id,
                sender_first_name=sender_first_name,
                sender_last_name=sender_last_name,
                sender_is_bot=sender_is_bot,
            )
            logger.info("Сообщение успешно обработано монитором")

        except Exception as e:
            logger.error(f"Ошибка при обработке сообщения: {e}")

    logger.info("[Monitor] Запуск Telethon-клиента...")
    
    # Запускаем Telethon клиент
    await client.run_until_disconnected()
    await db.close()
    await bot.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Монитор остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")