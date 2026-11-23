from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import PeerChannel, PeerChat, PeerUser
from telethon.tl.functions.messages import ExportChatInviteRequest
import re
import hashlib
from patterns import PATTERNS
from datetime import datetime, timedelta
import asyncio
import logging
import json
from config import API_ID, API_HASH, PHONE_NUMBER, MONITORING_CONFIG, BOT_TOKEN, DB_DSN
import os
from urllib.parse import urlparse
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

# Дедуп: несколько слушателей могут сидеть в одних чатах.
# Lock MUST be created once at import — lazy init raced and let duplicates through.
_SEEN_MSG_LOCK = asyncio.Lock()
_SEEN_MSG_KEYS: dict[tuple[str, int], datetime] = {}
_SEEN_TEXT_KEYS: dict[tuple[str, str], datetime] = {}
_CHAT_OWNER: dict[str, str] = {}
_SEEN_MSG_TTL = timedelta(minutes=30)
_SEEN_TEXT_TTL = timedelta(minutes=15)
_DEDUP_SKIP_LOG_EVERY = int(os.getenv("DEDUP_SKIP_LOG_EVERY", "50"))
_dedup_skip_count = 0

LISTENER_ACCOUNTS_FILE = os.getenv(
    "LISTENER_ACCOUNTS_FILE", "/app/data/listener_accounts.json"
)
# Cap extra Telethon clients (RAM). 0 = unlimited from JSON.
MAX_EXTRA_LISTENERS = int(os.getenv("MAX_EXTRA_LISTENERS", "14"))
# Pause between connecting listeners to avoid burst CPU/proxy load.
LISTENER_CONNECT_DELAY_SEC = float(os.getenv("LISTENER_CONNECT_DELAY_SEC", "1.5"))
# Truncate noisy per-message body logs (full text still goes to classifier).
MONITOR_LOG_TEXT_CHARS = int(os.getenv("MONITOR_LOG_TEXT_CHARS", "160"))
# One listener owns a chat for the process lifetime (others ignore that chat).
CROSS_LISTENER_CHAT_OWNER = os.getenv(
    "CROSS_LISTENER_CHAT_OWNER", "1"
).strip().lower() in ("1", "true", "yes", "on")


def _proxy_from_cfg(proxy_cfg) -> tuple | None:
    """Telethon HTTP proxy tuple from dict or URL string."""
    if not proxy_cfg:
        return None
    try:
        import socks
    except ImportError as e:
        raise RuntimeError("PySocks is required for listener proxies") from e

    if isinstance(proxy_cfg, str):
        u = urlparse(proxy_cfg)
        if not u.hostname or not u.port:
            return None
        return (
            socks.HTTP,
            u.hostname,
            int(u.port),
            True,
            u.username,
            u.password,
        )

    if isinstance(proxy_cfg, dict):
        return (
            socks.HTTP,
            proxy_cfg["addr"],
            int(proxy_cfg["port"]),
            True,
            proxy_cfg.get("username"),
            proxy_cfg.get("password"),
        )
    return None


def _load_extra_listeners(path: str) -> list[dict]:
    if not path or not os.path.exists(path):
        logger.info(f"[Monitor] Extra listeners file not found: {path}")
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, list):
            logger.warning("[Monitor] listener_accounts.json must be a list")
            return []
        out = []
        skipped_disabled = 0
        for row in raw:
            if not isinstance(row, dict):
                continue
            if row.get("disabled") is True:
                skipped_disabled += 1
                continue
            if not row.get("string_session") or not row.get("session_name"):
                continue
            out.append(row)
        if skipped_disabled:
            logger.info(
                "[Monitor] Skipped %s disabled listener account(s)",
                skipped_disabled,
            )
        total = len(out)
        if MAX_EXTRA_LISTENERS > 0 and total > MAX_EXTRA_LISTENERS:
            logger.warning(
                "[Monitor] Truncating listeners %s → %s (MAX_EXTRA_LISTENERS)",
                total,
                MAX_EXTRA_LISTENERS,
            )
            out = out[:MAX_EXTRA_LISTENERS]
        logger.info(
            f"[Monitor] Loaded {len(out)} extra listener account(s) from {path}"
            + (f" (of {total} in file)" if total != len(out) else "")
        )
        return out
    except Exception as e:
        logger.error(f"[Monitor] Failed to load listeners from {path}: {e}")
        return []


def _normalize_chat_id(raw_chat_id) -> str:
    """Unify Telethon chat ids across clients (-100… / positive channel id)."""
    if raw_chat_id is None:
        return "0"
    if hasattr(raw_chat_id, "channel_id"):
        raw_chat_id = raw_chat_id.channel_id
    elif hasattr(raw_chat_id, "chat_id"):
        raw_chat_id = raw_chat_id.chat_id
    elif hasattr(raw_chat_id, "user_id"):
        raw_chat_id = raw_chat_id.user_id
    try:
        n = abs(int(raw_chat_id))
    except (TypeError, ValueError):
        return str(raw_chat_id)
    s = str(n)
    if len(s) > 3 and s.startswith("100"):
        s = s[3:]
    return s


def _text_fingerprint(text: str) -> str:
    normalized = " ".join((text or "").lower().split())
    if not normalized:
        return ""
    if len(normalized) > 500:
        normalized = normalized[:500]
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()


def _log_dedup_skip(reason: str, label: str, chat_id: str, detail: str = "") -> None:
    global _dedup_skip_count
    _dedup_skip_count += 1
    if _dedup_skip_count == 1 or _dedup_skip_count % _DEDUP_SKIP_LOG_EVERY == 0:
        logger.info(
            "[Monitor/%s] dedup-skip #%s (%s) chat=%s %s",
            label,
            _dedup_skip_count,
            reason,
            chat_id,
            detail,
        )


async def _claim_chat_owner(chat_id: str, label: str) -> bool:
    """True если этот listener владеет чатом; False — чат уже за другим."""
    if not CROSS_LISTENER_CHAT_OWNER:
        return True
    async with _SEEN_MSG_LOCK:
        owner = _CHAT_OWNER.get(chat_id)
        if owner is None:
            _CHAT_OWNER[chat_id] = label
            return True
        return owner == label


async def _mark_message_seen(
    chat_id: str, message_id: int, text: str = ""
) -> bool:
    """True если сообщение новое и его надо обработать; False если дубль."""
    now = datetime.utcnow()
    msg_key = (str(chat_id), int(message_id)) if message_id else None
    fp = _text_fingerprint(text) if text else ""
    text_key = (str(chat_id), fp) if fp else None

    async with _SEEN_MSG_LOCK:
        stale_msg = [
            k for k, ts in _SEEN_MSG_KEYS.items() if now - ts > _SEEN_MSG_TTL
        ]
        for k in stale_msg:
            _SEEN_MSG_KEYS.pop(k, None)
        stale_text = [
            k for k, ts in _SEEN_TEXT_KEYS.items() if now - ts > _SEEN_TEXT_TTL
        ]
        for k in stale_text:
            _SEEN_TEXT_KEYS.pop(k, None)

        if msg_key and msg_key in _SEEN_MSG_KEYS:
            return False
        if text_key and text_key in _SEEN_TEXT_KEYS:
            return False

        if msg_key:
            _SEEN_MSG_KEYS[msg_key] = now
        if text_key:
            _SEEN_TEXT_KEYS[text_key] = now
        return True


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
    # Primary file-session listener (legacy single monitor account)
    session_path = "../monitor_session.session"
    if not os.path.exists(session_path):
        session_path = "monitor_session"

    primary = TelegramClient(session_path, API_ID, API_HASH)
    await primary.connect()
    if not await primary.is_user_authorized():
        await primary.start(phone=PHONE_NUMBER)
    me = await primary.get_me()
    logger.info(
        "Primary Telethon listener up as %s (id=%s)",
        getattr(me, "username", None) or getattr(me, "first_name", "?"),
        getattr(me, "id", "?"),
    )

    clients: list[TelegramClient] = [primary]
    listener_labels: dict[int, str] = {id(primary): "primary_monitor_session"}

    # Extra write-banned / spam-limited accounts → listen-only
    for idx, row in enumerate(_load_extra_listeners(LISTENER_ACCOUNTS_FILE)):
        name = row["session_name"]
        if idx > 0 and LISTENER_CONNECT_DELAY_SEC > 0:
            await asyncio.sleep(LISTENER_CONNECT_DELAY_SEC)
        try:
            proxy = _proxy_from_cfg(row.get("proxy"))
            api_id = int(row.get("api_id") or API_ID)
            api_hash = str(row.get("api_hash") or API_HASH)
            client = TelegramClient(
                StringSession(row["string_session"]),
                api_id,
                api_hash,
                proxy=proxy,
            )
            await client.connect()
            if not await client.is_user_authorized():
                logger.error("[Monitor] Listener %s not authorized — skip", name)
                await client.disconnect()
                continue
            me = await client.get_me()
            clients.append(client)
            listener_labels[id(client)] = name
            logger.info(
                "[Monitor] Extra listener UP: %s as %s (id=%s)",
                name,
                getattr(me, "username", None) or getattr(me, "first_name", "?"),
                getattr(me, "id", "?"),
            )
        except Exception as e:
            logger.error("[Monitor] Failed to start listener %s: %s", name, e)

    logger.info("[Monitor] Total live listeners: %s", len(clients))

    db = Database(DB_DSN)
    await db.connect()

    openai_api_key = os.getenv("OPENAI_API_KEY")
    if openai_api_key:
        logger.info("🔑 OpenAI API ключ найден, AI классификатор будет активирован")
    else:
        logger.info(
            "⚠️ OpenAI API ключ не найден, будет использована только базовая классификация"
        )

    main_bot_token = BOT_TOKEN or os.getenv("BOT_TOKEN")
    if not main_bot_token:
        raise RuntimeError("BOT_TOKEN is not set — cannot send lead notifications")
    bot = Bot(token=main_bot_token)
    logger.info("🔔 Бот уведомлений инициализирован (token from env/config)")

    monitor = MessageMonitor(bot, db, openai_api_key)
    await monitor.initialize()
    logger.info("База данных и монитор успешно инициализированы")

    subscribers = await db.get_all_users()
    for user in subscribers:
        logger.info(f"Пользователь {user['user_id']} подписан на: {user['categories']}")

    async def handler(event):
        client = event.client
        label = listener_labels.get(id(client), "unknown")
        try:
            # Dedup BEFORE get_chat/get_sender — cheap, no await race window.
            chat_id = _normalize_chat_id(
                getattr(event, "chat_id", None)
                or getattr(event.message, "peer_id", None)
                or 0
            )
            msg_id = int(getattr(event.message, "id", 0) or 0)
            raw_text = event.message.text or ""

            if not await _claim_chat_owner(chat_id, label):
                owner = _CHAT_OWNER.get(chat_id, "?")
                _log_dedup_skip("chat-owner", label, chat_id, f"owner={owner}")
                return

            if not await _mark_message_seen(chat_id, msg_id, raw_text):
                _log_dedup_skip(
                    "msg",
                    label,
                    chat_id,
                    f"msg_id={msg_id}",
                )
                return

            chat = await event.get_chat()
            # Keep known_chats key stable with normalized id
            chat_id = _normalize_chat_id(getattr(chat, "id", chat_id))
            chat_title = chat.title if hasattr(chat, "title") else "Private Chat"
            logger.info(
                f"[Monitor/{label}] Получено сообщение в чате: {chat_title} (ID: {chat_id})"
            )
            if MONITOR_LOG_TEXT_CHARS > 0 and len(raw_text) > MONITOR_LOG_TEXT_CHARS:
                log_text = raw_text[:MONITOR_LOG_TEXT_CHARS] + "…"
            else:
                log_text = raw_text
            logger.info(f"[Monitor/{label}] Текст сообщения: {log_text}")

            sender = await event.get_sender()
            sender_username = sender.username if hasattr(sender, "username") else None
            sender_id = sender.id if hasattr(sender, "id") else None
            sender_first_name = (
                sender.first_name if hasattr(sender, "first_name") else None
            )
            sender_last_name = (
                sender.last_name if hasattr(sender, "last_name") else None
            )
            sender_is_bot = bool(getattr(sender, "bot", False))

            if sender_is_bot:
                logger.info(
                    f"🚫 Пропускаем сообщение от бота @{sender_username or ''} (ID: {sender_id})"
                )
                return

            if chat_id not in known_chats:
                known_chats[chat_id] = {
                    "title": chat_title,
                    "type": "Private",
                    "first_seen": str(event.message.date),
                }
                monitored_chats.append(chat_id)
                with open("known_chats.json", "w", encoding="utf-8") as f:
                    json.dump(known_chats, f, ensure_ascii=False, indent=2)
                logger.info(f"Добавлен новый чат: {chat_title} (ID: {chat_id})")

            if chat_id not in monitored_chats:
                logger.info(f"Чат {chat_id} не в списке мониторинга, пропускаем")
                return

            if event.message.text and is_spam(event.message.text):
                logger.info(
                    f"🚫 Спам отфильтрован на раннем этапе, сообщение пропущено: {event.message.text[:100]}..."
                )
                return

            message_link = None
            chat_username = None
            chat_join_link = None
            if hasattr(event.message, "id"):
                try:
                    thread_id = _get_thread_id_from_event(event)
                    try:
                        entity = await client.get_entity(chat.id)
                        if hasattr(entity, "username") and entity.username:
                            chat_username = entity.username
                            chat_join_link = f"https://t.me/{chat_username}"
                            if thread_id:
                                message_link = f"https://t.me/{chat_username}/{thread_id}/{event.message.id}"
                            else:
                                message_link = (
                                    f"https://t.me/{chat_username}/{event.message.id}"
                                )
                            logger.info(
                                f"[Monitor] Сформирована ссылка для публичного чата: {message_link}"
                            )
                        else:
                            chat_id_int = abs(chat.id) if chat.id < 0 else chat.id
                            if chat_id_int >= 1000000000000:
                                chat_id_for_link = str(chat_id_int)[4:]
                            else:
                                chat_id_for_link = str(chat_id_int)

                            if chat_id_for_link.isdigit():
                                if thread_id:
                                    message_link = f"https://t.me/c/{chat_id_for_link}/{thread_id}/{event.message.id}"
                                else:
                                    message_link = f"https://t.me/c/{chat_id_for_link}/{event.message.id}"
                                logger.info(
                                    f"[Monitor] Сформирована ссылка для приватного чата: {message_link} (ID чата: {chat_id_for_link})"
                                )
                                chat_join_link = await _get_join_link_if_available(
                                    client, chat
                                )
                            else:
                                logger.warning(
                                    f"[Monitor] Некорректный ID чата для ссылки: {chat_id_for_link}"
                                )
                    except Exception as e:
                        logger.warning(
                            f"[Monitor] Не удалось получить entity для чата {chat.id}: {e}"
                        )
                        if hasattr(chat, "username") and chat.username:
                            chat_username = chat.username
                            chat_join_link = f"https://t.me/{chat_username}"
                            if thread_id:
                                message_link = f"https://t.me/{chat_username}/{thread_id}/{event.message.id}"
                            else:
                                message_link = (
                                    f"https://t.me/{chat_username}/{event.message.id}"
                                )
                        else:
                            chat_id_str = str(abs(chat.id))
                            if chat_id_str.startswith("100"):
                                chat_id_for_link = chat_id_str[3:]
                            else:
                                chat_id_for_link = chat_id_str

                            if chat_id_for_link.isdigit():
                                if thread_id:
                                    message_link = f"https://t.me/c/{chat_id_for_link}/{thread_id}/{event.message.id}"
                                else:
                                    message_link = f"https://t.me/c/{chat_id_for_link}/{event.message.id}"
                                chat_join_link = await _get_join_link_if_available(
                                    client, chat
                                )
                except Exception as e:
                    logger.error(f"[Monitor] Ошибка при формировании ссылки: {e}")
                    message_link = None

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
            logger.error(f"Ошибка при обработке сообщения ({label}): {e}")

    for client in clients:
        client.add_event_handler(handler, events.NewMessage())

    logger.info("[Monitor] Запуск %s Telethon listener(s)...", len(clients))
    try:
        await asyncio.gather(*(c.run_until_disconnected() for c in clients))
    finally:
        for client in clients:
            try:
                await client.disconnect()
            except Exception:
                pass
        await db.close()
        await bot.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Монитор остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")