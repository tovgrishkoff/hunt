from telethon import TelegramClient, events
from telethon.tl.types import PeerChannel, PeerChat, PeerUser
import re
import html
from patterns import PATTERNS, NICHES_KEYWORDS
from datetime import datetime
import asyncio
import logging
import json
from config import API_ID, API_HASH, PHONE_NUMBER, MONITORING_CONFIG, BOT_TOKEN, DB_DSN
from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher.filters import Command
from aiogram.types import Message
from database import Database
from content import MONITORING_TOPICS
from typing import Dict, List, Set
from ai_classifier import AIClassifier
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.exceptions import TelegramAPIError

logger = logging.getLogger(__name__)

class MessageMonitor:
    def __init__(self, bot: Bot, db, openai_api_key: str = None):
        self.bot = bot
        self.db = db
        self.listening_chats = MONITORING_CONFIG["listening_chats"]
        self.disallowed_keywords = MONITORING_CONFIG["disallowed_keywords"]
        self.disallowed_users = MONITORING_CONFIG["disallowed_users"]
        self.user_keywords: Dict[int, Dict[str, List[str]]] = {}
        self.topic_keywords: Dict[str, Set[str]] = {}
        self.user_topics: Dict[int, Set[str]] = {}
        self.user_settings: Dict[int, Dict] = {}
        self.message_queue: Dict[int, List[str]] = {}
        self.message_cache: Dict[str, Set[int]] = {}  # Cache for processed messages
        self.subscribers: Dict[int, Set[str]] = {}  # user_id -> set of niches
        self.patterns = NICHES_KEYWORDS  # Используем NICHES_KEYWORDS вместо PATTERNS
        self._load_topics()
        
        # Улучшенная дедупликация сообщений
        self.message_hashes: Dict[str, datetime] = {}  # message_hash -> timestamp
        self.duplicate_window = 3600  # 1 час - окно для дедупликации
        
        # AI классификатор (опционально)
        self.ai_classifier = None
        if openai_api_key:
            try:
                self.ai_classifier = AIClassifier(openai_api_key)
                logger.info("🤖 AI классификатор инициализирован")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось инициализировать AI классификатор: {e}")
                self.ai_classifier = None

    def _create_message_hash(self, message_text: str, sender_id: int) -> str:
        """
        Создает уникальный хеш сообщения на основе текста и отправителя
        """
        import hashlib
        # Нормализуем текст: убираем лишние пробелы, приводим к нижнему регистру
        normalized_text = ' '.join(message_text.lower().split())
        # Создаем хеш из нормализованного текста и ID отправителя
        hash_input = f"{normalized_text}:{sender_id}"
        return hashlib.md5(hash_input.encode('utf-8')).hexdigest()

    def _escape_html(self, value: str) -> str:
        """Экранирует HTML, чтобы ссылки/текст не ломались в parse_mode=HTML."""
        return html.escape(str(value), quote=True)

    def _is_duplicate_message(self, message_text: str, sender_id: int) -> bool:
        """
        Проверяет, является ли сообщение дубликатом
        """
        message_hash = self._create_message_hash(message_text, sender_id)
        current_time = datetime.now()
        
        # Проверяем, есть ли такой хеш в кэше
        if message_hash in self.message_hashes:
            # Проверяем, не устарел ли хеш
            if (current_time - self.message_hashes[message_hash]).total_seconds() < self.duplicate_window:
                logger.info(f"🔄 Найден дубликат сообщения от пользователя {sender_id}")
                return True
        
        # Если хеша нет или он устарел, обновляем кэш
        self.message_hashes[message_hash] = current_time
        
        # Очищаем старые хеши (старше 24 часов)
        old_hashes = []
        for hash_key, timestamp in self.message_hashes.items():
            if (current_time - timestamp).total_seconds() > 86400:  # 24 часа
                old_hashes.append(hash_key)
        
        for hash_key in old_hashes:
            del self.message_hashes[hash_key]
        
        return False

    async def _hybrid_classify_message(self, message_text: str, sender_username: str = None) -> Dict:
        """
        Гибридная классификация:
        1) Спам-фильтр (дешево)
        2) Паттерны + intent (дешево, бесплатно)
        3) AI (дорого, только как fallback)
        """
        # 1. Быстрая проверка на спам
        if self.is_spam_message(message_text):
            return {
                "message_type": "СПАМ",
                "is_spam": True,
                "niches": [],
                "context": "Отфильтровано спам-фильтрами",
                "urgency": "не срочно",
                "budget": "",
                "confidence": 95,
                "reason": "Отфильтровано спам-фильтрами"
            }
        
        # 1.1. Проверка на информационные сообщения от ботов (правила чата, инструкции)
        text_lower = message_text.lower()
        informational_patterns = [
            r'уважаемые\s+участники\s+чата',
            r'наш\s+чат\s+—\s+площадка',
            r'правила\s+публикации',
            r'правила\s+чата',
            r'соблюдайте.*правила',
            r'бот.*поможет',
            r'ботик.*помоги',
            r'наш\s+помощник.*бот',
            r'для\s+безопасности\s+введены\s+меры',
            r'автоматизированная\s+модерация',
            r'профессиональные\s+участники',
            r'платные\s+пакеты',
            r'бесплатных\s+тариф',
            r'информация\s+о\s+правилах',
        ]
        
        # Проверяем, является ли это информационным сообщением
        is_informational = False
        for pattern in informational_patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                is_informational = True
                break
        
        # Если это информационное сообщение И от бота - блокируем
        if is_informational and sender_username:
            username_lower = sender_username.lower()
            if 'bot' in username_lower or 'informant' in username_lower or 'keeper' in username_lower:
                logger.info(f"🚫 Информационное сообщение от бота {sender_username}, блокируем")
                return {
                    "message_type": "ОБЩЕНИЕ",
                    "is_spam": True,
                    "niches": [],
                    "context": "Информационное сообщение от бота",
                    "urgency": "не срочно",
                    "budget": "",
                    "confidence": 100,
                    "reason": "Информационное сообщение от бота"
                }

        # 1.2. Дополнительные дешёвые спам-проверки (до паттернов/AI)
        text = text_lower
        work_spam_patterns = [
            r'шабашк.*на\s+сейчас',
            r'зп\s+\d+.*р.*день',
            r'закину\s+на\s+такс',
            r'ставь\s*\+\s*менеджер',
            r'без\s+сложност',
            r'шабашк.*зп',
            r'зп.*\d+.*день.*без',
            r'шабашк.*зп.*\d+.*р',
        ]
        
        for pattern in work_spam_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                logger.info(f"🚫 Спам о работе обнаружен: {pattern}")
                return {
                    "message_type": "СПАМ",
                    "is_spam": True,
                    "niches": [],
                    "context": "Спам о работе",
                    "urgency": "не срочно",
                    "budget": "",
                    "confidence": 95,
                    "reason": "Спам о работе (шабашка, зп, такси)"
                }
        
        # 1.3. Проверка на спам о репликах/копиях брендов (до паттернов/AI)
        replica_spam_patterns = [
            r'реплик.*lux.*бренд',
            r'1:1\s*реплик',
            r'копии\s*ааа',
            r'копии\s*аа\b',
            r'реплик.*бренд',
            r'worldwide\s+shipping',
            r'прямые\s+поставщики',
            r'поиск\s+по\s+фото',
            r'полное\s+сопровождени',
        ]
        
        # Проверяем, есть ли признаки реплик/копий брендов
        has_replica_keywords = any(re.search(pattern, text, re.IGNORECASE) for pattern in replica_spam_patterns)
        # Также проверяем комбинацию: реплика/копия + доставка (не транспорт!)
        has_replica_and_delivery = (re.search(r'реплик|копии.*аа', text, re.IGNORECASE) and 
                                    re.search(r'доставк|shipping', text, re.IGNORECASE))
        
        if has_replica_keywords or has_replica_and_delivery:
            logger.info(f"🚫 Спам о репликах/копиях брендов обнаружен")
            return {
                "message_type": "СПАМ",
                "is_spam": True,
                "niches": [],
                "context": "Спам о репликах/копиях брендов",
                "urgency": "не срочно",
                "budget": "",
                "confidence": 95,
                "reason": "Спам о репликах/копиях брендов (не транспорт)"
            }

        # 2. PRE-FILTER: паттерны (бесплатно)
        found_niches = set()

        for niche, patterns in self.patterns.items():
            for pattern in patterns:
                try:
                    if re.search(pattern, text):
                        # Исключение 1: "Продажа недвижимости" - если это поиск фрилансера/работника в контексте недвижимости
                        if niche == "Продажа недвижимости" and self._is_freelancer_context(text):
                            logger.info(f"🔍 Пропускаем нишу '{niche}' - это поиск фрилансера, а не недвижимости")
                            continue
                        
                        # Исключение 2: "Фотограф" - если это продажа телефона с упоминанием камеры
                        if niche == "Фотограф" and self._is_phone_sale_context(text):
                            logger.info(f"🔍 Пропускаем нишу '{niche}' - это продажа телефона, а не поиск фотографа")
                            continue
                        
                        found_niches.add(niche)
                        break
                except Exception as e:
                    logger.error(f"❌ Ошибка при проверке паттерна '{pattern}' для ниши '{niche}': {e}")

        if found_niches:
            found_niches = self._filter_real_estate_niches_by_negative_keywords(
                message_text, found_niches
            )

        # ==> ТОЧКА ВОЗВРАТА 1: ниши найдены паттернами -> AI не нужен
        if found_niches:
            logger.info(
                f"✅ Pre-filter: ниши найдены по паттернам: {found_niches}. AI не вызываем."
            )

            msg_type = "ОБЩЕНИЕ"
            if any(
                w in text
                for w in ["ищу", "нужен", "нужна", "нужны", "требуется", "найти", "куплю", "сниму"]
            ):
                msg_type = "ПОИСК"
            elif any(
                w in text
                for w in ["предлагаю", "сдам", "продам", "делаю", "работаю", "услуги", "оказываю"]
            ):
                msg_type = "ПРЕДЛОЖЕНИЕ"

            return {
                "message_type": msg_type,
                "is_spam": False,
                "niches": list(found_niches),
                "context": f"Найдены паттерны: {', '.join(found_niches)}",
                "urgency": "не срочно",
                "budget": "",
                "confidence": 100,
                "reason": "Pre-filter: ниши найдены паттернами, AI не нужен",
            }

        # 3. INTENT FILTER (бесплатно): если нет маркеров поиска/коммерции — это просто чат
        intent_keywords = [
            # RU: поиск/потребность
            r'ищ[уею]', r'нужен', r'нужна', r'нужны', r'требуется', r'посоветуйте',
            r'нужно',
            r'\bхочу\b', r'\bхотим\b', r'хотел(а|и|ось)?',
            r'подскажите', r'где\s+найти', r'кто\s+знает', r'есть\s+ли',
            r'контакт(ы)?', r'как\s+связаться', r'подскажите\s+контакт(ы)?',
            r'в\s+лс', r'в\s+личк', r'в\s+директ',
            # RU: коммерция
            r'куплю', r'продам', r'сдам', r'сниму', r'аренд[ау]', r'цена', r'стоимость',
            r'бюджет', r'прайс', r'услуг[аи]', r'заказ', r'обмен', r'сколько\s+стоит',
            # EN: intent/commerce
            r'\blooking for\b', r'\bneed\b', r'\bwant\b', r'\brent\b', r'\bbuy\b', r'\bsell\b',
            r'\bprice\b', r'\bcost\b', r'\bbudget\b',
            # Срочность/контакты/деньги
            r'срочно', r'сегодня', r'сейчас', r'\$', r'\busd\b', r'\bidr\b', r'₽',
        ]
        has_intent = any(re.search(kw, text, re.IGNORECASE) for kw in intent_keywords)
        if not has_intent:
            return {
                "message_type": "ОБЩЕНИЕ",
                "is_spam": False,
                "niches": [],
                "context": "Обычное общение (pre-filter: нет маркеров поиска/коммерции)",
                "urgency": "не срочно",
                "budget": "",
                "confidence": 0,
                "reason": "Pre-filter: нет intent-маркеров, AI пропущен",
            }

        # 4. AI FALLBACK (дорого): паттерны не сработали, но intent есть
        if self.ai_classifier:
            logger.info("🤔 Паттерны не справились, но есть intent. Вызываем AI...")
            try:
                ai_result = await self.ai_classifier.classify_message(message_text)

                # Пост-фильтр: минус-слова для недвижимости ("матрас" != недвижимость)
                if ai_result.get("niches"):
                    filtered_niches = self._filter_real_estate_niches_by_negative_keywords(
                        message_text, set(ai_result.get("niches", []))
                    )
                    ai_result["niches"] = list(filtered_niches)

                # На всякий случай приводим поля к ожидаемому формату
                ai_result.setdefault("message_type", "ОБЩЕНИЕ")
                ai_result.setdefault("is_spam", False)
                ai_result.setdefault("niches", [])
                ai_result.setdefault("context", "AI fallback")
                ai_result.setdefault("urgency", "не срочно")
                ai_result.setdefault("budget", "")
                ai_result.setdefault("confidence", 0)
                ai_result.setdefault("reason", "AI fallback")
                return ai_result
            except Exception as e:
                logger.error(f"❌ Ошибка AI: {e}")

        # Fallback, если AI отключен/сломался
        return {
            "message_type": "ОБЩЕНИЕ",
            "is_spam": False,
            "niches": [],
            "context": "Fallback: AI недоступен/ошибка, паттерны не сработали",
            "urgency": "не срочно",
            "budget": "",
            "confidence": 0,
            "reason": "Fallback (ничего не найдено)",
        }

    def _is_freelancer_context(self, text_lower: str) -> bool:
        """
        Признаки поиска фрилансера/исполнителя в контексте тематики (не поиск недвижимости).
        """
        is_freelancer_search = re.search(
            r'фрілансер|фрилансер|переводчик|перекладач|дизайнер|таргетолог|'
            r'оформлювати|контент|пости|каруселі|canva|instagram',
            text_lower,
            re.IGNORECASE,
        )
        has_real_estate_in_context = re.search(
            r'нерухомість|недвижимость|инвестиц', text_lower, re.IGNORECASE
        )
        return bool(is_freelancer_search and has_real_estate_in_context)

    def _is_phone_sale_context(self, text_lower: str) -> bool:
        """
        Продажа телефона/техники с упоминанием камеры (не запрос фотографа).
        """
        is_phone_sale = re.search(
            r'iphone|айфон|телефон|смартфон|продам.*\d+\s*(gb|гб|mln|млн)',
            text_lower,
            re.IGNORECASE,
        )
        has_camera = re.search(r'камер(а|ы|е|ой|у|ах)', text_lower, re.IGNORECASE)
        return bool(is_phone_sale and has_camera)

    def _load_topics(self):
        """Загружает темы и ключевые слова из content.py"""
        for topic, data in MONITORING_TOPICS.items():
            self.topic_keywords[topic] = set(data["keywords"])

    async def update_user_data(self):
        """Обновляет данные пользователей из базы"""
        users = await self.db.get_all_users()
        for user_data in users:
            user_id = user_data['user_id']
            # Получаем список ниш (categories)
            categories = json.loads(user_data.get('categories', '[]'))
            if user_id not in self.user_topics:
                self.user_topics[user_id] = set()
            for cat in categories:
                self.user_topics[user_id].add(cat.lower())
            # Обновляем настройки
            settings = json.loads(user_data.get('settings', '{}'))
            self.user_settings[user_id] = settings or {
                "notification_frequency": "instant",
                "is_paused": False,
                "custom_keywords": set()
            }
            # Инициализируем очередь сообщений
            if user_id not in self.message_queue:
                self.message_queue[user_id] = []

    async def process_message(self, message_text: str, chat_title: str = None, message_link: str = None):
        """
        Анализирует текст сообщения, определяет категории (ниши) и рассылает только тем, кто подписан на найденные ниши
        """
        if not message_text:
            return

        logger.info(f"🔍 Анализ сообщения из чата: {chat_title}")
        text = message_text.lower()
        found_niches = set()

        # Поиск по паттернам
        for niche, patterns in self.patterns.items():
            for pattern in patterns:
                try:
                    if re.search(pattern, text):
                        found_niches.add(niche)
                        logger.info(f"✅ Найдена ниша: {niche}")
                        break
                except Exception as e:
                    logger.error(f"❌ Ошибка при проверке паттерна '{pattern}' для ниши '{niche}': {e}")

        if not found_niches:
            logger.info("❌ Категории не найдены, сообщение не будет разослано")
            return

        logger.info(f"📊 Найдено ниш: {found_niches}")
        
        # Рассылка только тем, кто подписан на найденные ниши
        for user_id, user_niches in self.subscribers.items():
            if found_niches & user_niches:
                try:
                    user = await self.db.get_user(user_id)
                    if not user:
                        logger.warning(f"⚠️ Пользователь {user_id} не найден в базе")
                        continue

                    notification = (
                        f"🔔 Новое сообщение в категориях: {', '.join(found_niches)}\n\n"
                        f"📝 {message_text}\n\n"
                        f"💬 Чат: {chat_title or 'Неизвестный чат'}\n"
                    )
                    if message_link:
                        notification += f"🔗 Ссылка: {message_link}"

                    await self.bot.send_message(user_id, notification)
                    logger.info(f"✅ Уведомление отправлено пользователю {user_id}")
                except Exception as e:
                    logger.error(f"❌ Ошибка отправки уведомления пользователю {user_id}: {e}")

    async def schedule_daily_digest(self, user_id: int):
        """Планирует ежедневный дайджест"""
        while True:
            # Ждем до следующего дня
            now = datetime.now()
            next_day = now.replace(hour=20, minute=0, second=0, microsecond=0)
            if next_day <= now:
                next_day += timedelta(days=1)
            
            wait_seconds = (next_day - now).total_seconds()
            await asyncio.sleep(wait_seconds)
            
            # Отправляем дайджест
            if user_id in self.message_queue and self.message_queue[user_id]:
                messages = self.message_queue[user_id]
                self.message_queue[user_id] = []
                
                digest = (
                    "📊 Ежедневный дайджест:\n\n"
                    f"За последние 24 часа найдено {len(messages)} сообщений:\n\n"
                )
                
                # Добавляем первые 5 сообщений
                for msg in messages[:5]:
                    digest += f"• {msg}\n\n"
                
                if len(messages) > 5:
                    digest += f"... и еще {len(messages) - 5} сообщений"
                
                await self.bot.send_message(user_id, digest)

    async def schedule_weekly_digest(self, user_id: int):
        """Планирует еженедельный дайджест"""
        while True:
            # Ждем до следующего понедельника
            now = datetime.now()
            next_monday = now.replace(hour=20, minute=0, second=0, microsecond=0)
            while next_monday.weekday() != 0:  # 0 = понедельник
                next_monday += timedelta(days=1)
            
            if next_monday <= now:
                next_monday += timedelta(days=7)
            
            wait_seconds = (next_monday - now).total_seconds()
            await asyncio.sleep(wait_seconds)
            
            # Отправляем дайджест
            if user_id in self.message_queue and self.message_queue[user_id]:
                messages = self.message_queue[user_id]
                self.message_queue[user_id] = []
                
                digest = (
                    "📊 Еженедельный дайджест:\n\n"
                    f"За последнюю неделю найдено {len(messages)} сообщений:\n\n"
                )
                
                # Группируем сообщения по темам
                topics = {}
                for msg in messages:
                    for topic in self.user_topics[user_id]:
                        if topic in msg.lower():
                            if topic not in topics:
                                topics[topic] = []
                            topics[topic].append(msg)
                
                # Добавляем статистику по темам
                for topic, msgs in topics.items():
                    digest += f"📌 {topic.capitalize()}: {len(msgs)} сообщений\n"
                
                digest += "\n💡 Используйте /settings для изменения частоты уведомлений"
                
                await self.bot.send_message(user_id, digest)

    def is_spam_message(self, message_text: str) -> bool:
        """Проверяет, является ли сообщение спамом"""
        if not message_text:
            return True

        text_lower = message_text.lower()
        
        # Проверка на минимальную длину
        if len(message_text) < 10:
            logger.info("❌ Сообщение слишком короткое")
            return True

        # Проверка на максимальную длину
        if len(message_text) > 1000:
            logger.info("❌ Сообщение слишком длинное")
            return True

        # Проверка на количество эмодзи
        emoji_count = sum(1 for c in message_text if ord(c) > 0x1F600)
        if emoji_count > 3:
            logger.info(f"❌ Слишком много эмодзи: {emoji_count}")
            return True

        # Проверка на спам-слова
        spam_keywords = [
            # Финансовые схемы
            "криптовалюта", "бинарные опционы", "быстрый заработок", "инвестиции",
            "казино", "ставки", "лотерея", "розыгрыш", "приз", "выигрыш",
            "бесплатно", "акция", "скидка", "распродажа", "купи", "продай",
            "заработок", "деньги", "кредит", "займ",
            
            # Реплики и копии брендов
            "реплика", "копии ааа", "копии аа", "1:1 реплика", "lux бренд",
            "реплика lux", "копии бренд", "реплики бренд", "worldwide shipping",
            "прямые поставщики", "поиск по фото", "полное сопровождение", 
            
            # Банковские карты и личные кабинеты
            "личный кабинет", "лк", "sberbank", "сбербанк", "втб", "альфа банк",
            "продам личный кабинет", "куплю личный кабинет", "продам лк", "куплю лк",
            "продам карту", "куплю карту", "пластик карту", "пластиковая карта",
            "продам пушкинскую карту", "куплю пушкинскую карту", "оплата на любую карту",
            "swift", "sepa", "банковская карта", "дебетовая карта", "кредитная карта",
            
            # Пробив и мошенничество
            "пробив по линии", "пробив по базе", "пробив по фнс", "пробив по мвд",
            "пробив по гибдд", "пробив по загс", "пробив по пфр", "пробив по налоговой",
            "пробив по полиции", "пробив", "база данных", "личные данные",
            
            # Подозрительные предложения работы
            "онлайн-подработка", "без опыта", "личные данные не нужны", 
            "гарант всегда за", "моментальная оплата", "оплата моментальная",
            "оплата на карту", "оплата на любую карту", "работа на дому", 
            "удаленная работа", "фриланс", "млм", "пирамида", "сетевой маркетинг",
            "шабашка", "шабашк", "закину на такси", "закину на такс", 
            "ставь +", "ставь плюс", "менеджеру @", "менеджер @",
            
            # Спам и реклама
            "инвайт", "рассылка", "парсинг", "боты — технические решения", 
            "дизайн — графика", "новые пользователи без накруток", "накрутка",
            "пиши: @", "контакты: @", "контакт: @", "пиши в лс", "пишите в лс",
            "пишите: @", "по всем вопросам обращаться", "по всем вопросам пишите",
            "по всем вопросам в лс", "подробности в лс", "подробности в личку",
            
            # Подозрительные символы и паттерны
            "🔤🔤🔤🔤", "🇷🇺", "🇺🇸", "🇪🇺", "💳", "💸", "💰", "🤑",
            
            # Наркотики и подозрительные вещества
            "поника", "вдова головы", "боливия", "первый", "гарантия сьема",
            "недорого с доставкой", "отзывы и гарантия", "пишите😉", "ещё есть",
            "наркотик", "вещество", "трава", "марихуана", "кокаин", "героин",
            "амфетамин", "экстази", "лсд", "мефедрон", "соль", "спайс", "микс",
            "гашиш", "анаша", "план", "дрова", "дурь", "дурман", "шишки",
            "сорт", "гидропоника", "скунс", "джа", "травка", "зелень",

            # Sex / Adult / Dating spam
            "вирт", "секс", "интим", "эскорт", "шлюх", "проститут", "сосочк",
            "порно", "porn", "sex", "nudes", "слив", "onlyfans", "онлифанс",
            "вебкам", "webcam", "приват", "private", "сиськи", "попка",
            "оргазм", "мастурб", "минет", "куни", "bdsm", "бдсм", "голые",
            "dating", "знакомства для секса", "свидания", "любовницы",
            "элитный отдых", "досуг", "выезд", "апартаменты", "содержанки",
            "массаж с окончанием", "релакс", "tinder", "мамба", "pure",
            "xxx", "18+", "эротик", "нюдс", "папик", "спонсор"
        ]

        for keyword in spam_keywords:
            if keyword in text_lower:
                logger.info(f"❌ Найдено спам-слово: {keyword}")
                return True

        # Проверка без пробелов (разрядка/обфускация)
        text_no_spaces = re.sub(r"\s+", "", text_lower)
        if any(word in text_no_spaces for word in ["порно", "интим", "секс", "вирт", "досуг"]):
            logger.info("❌ Найдено спам-слово в тексте без пробелов")
            return True

        # Приватные ссылки t.me/+ с adult-контекстом
        if "t.me/+" in message_text and any(
            w in text_lower for w in ["видео", "video", "pack", "пак", "слив", "nude", "нюд"]
        ):
            logger.info("❌ Приватная ссылка t.me/+ с adult-контекстом")
            return True

        # Проверка на повторяющиеся символы
        if re.search(r'(.)\1{4,}', message_text):
            logger.info("❌ Обнаружены повторяющиеся символы")
            return True

        # Проверка на URL (но не блокируем просто @username, только если это спам-паттерн)
        url_patterns = [
            r'https?://\S+',  # HTTP/HTTPS ссылки
            r't\.me/\S+',     # Telegram ссылки
        ]
        has_url = any(re.search(pattern, message_text) for pattern in url_patterns)
        
        # Если есть URL И это похоже на спам (много @username или спам-слова), блокируем
        # Но не блокируем, если это информационное сообщение (может содержать ссылки на правила)
        if has_url:
            username_count = len(re.findall(r'@\w+', message_text))
            # Блокируем только если много @username (спам) И нет признаков информационного сообщения
            if username_count > 2 and not any(word in text_lower for word in ['правила', 'чат', 'участники', 'информация']):
                logger.info(f"❌ Обнаружены URL и много @username ({username_count}), блокируем")
                return True

        # Проверка на подозрительные паттерны
        suspicious_patterns = [
            r'продам.*лк.*sberbank',  # Продам ЛК Sberbank
            r'продам.*карту.*город',   # Продам карту в город
            r'пластик.*карта.*город',  # Пластик карта в город
            r'🔤🔤🔤🔤',              # Повторяющиеся символы
            r'🇷🇺.*продам',           # Флаг + продам
            r'🇺🇸.*продам',           # Флаг + продам
            r'🇪🇺.*продам',           # Флаг + продам
            
            # Наркотики и подозрительные вещества
            r'поника.*вдова.*головы',  # Поника (вдова головы)
            r'боливия.*первый',        # Боливия первый
            r'гарантия.*сьема',        # Гарантия сьема
            r'недорого.*доставка',     # Недорого с доставкой
            r'отзывы.*гарантия',       # Отзывы и гарантия
            r'пишите😉',               # Пишите с эмодзи
            r'ещё.*есть',              # Ещё есть
            r'доставка.*наркотик',     # Доставка наркотиков
            r'продам.*вещество',       # Продам вещество
            r'сорт.*качество',         # Сорт качества
            r'гидропоника',            # Гидропоника
            r'скунс.*сорт',            # Скунс сорт
            
            # Спам о работе (шабашка, зп, такси)
            r'шабашк.*на\s+сейчас',    # Шабашка на сейчас
            r'зп\s+\d+.*р.*день',      # Зп XXXXр день
            r'закину\s+на\s+такс',    # Закину на такси
            r'ставь\s*\+\s*менеджер',  # Ставь + менеджеру
            r'без\s+сложност',         # Без сложности
            r'шабашк.*зп',             # Шабашка + зп
            r'зп.*\d+.*день.*без',     # Зп + день + без опыта

            # Adult / разрядка / obfuscation
            r'п\s*о\s*р\s*н\s*о',
            r'с\s*е\s*к\s*с',
            r'и\s*н\s*т\s*и\s*м',
            r'д\s*о\s*с\s*у\s*г',
            r'в\s*и\s*р\s*т',
            
            # Реплики и копии брендов (спам о товарах)
            r'реплик.*lux.*бренд',     # Реплика LUX брендов
            r'1:1\s*реплик',           # 1:1 РЕПЛИКА
            r'копии\s*ааа',            # Копии ААА
            r'копии\s*аа\b',           # Копии АА
            r'реплик.*бренд',          # Реплика брендов
            r'worldwide\s+shipping',   # WORLDWIDE SHIPPING
            r'прямые\s+поставщики',    # Прямые поставщики
            r'поиск\s+по\s+фото',      # Поиск по фото
            r'полное\s+сопровождени',  # Полное сопровождение
        ]
        
        for pattern in suspicious_patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                logger.info(f"❌ Обнаружен подозрительный паттерн: {pattern}")
                return True

        # Проверка на слишком много флагов
        flag_count = text_lower.count('🇷🇺') + text_lower.count('🇺🇸') + text_lower.count('🇪🇺')
        if flag_count > 1:
            logger.info(f"❌ Слишком много флагов: {flag_count}")
            return True

        return False

    async def handle_source_message(self, message_text: str, chat_title: str = None, message_link: str = None):
        """Обработка сообщения из исходного чата"""
        if not message_text:
            return

        logger.info(f"📥 Получено новое сообщение из чата: {chat_title}")
        logger.info(f"📝 Текст сообщения: {message_text[:100]}...")

        # Проверка на спам
        if self.is_spam_message(message_text):
            logger.info(f"🚫 Сообщение отфильтровано как спам: {message_text[:100]}...")
            return

        # Create a unique message identifier
        message_id = f"{chat_title}:{message_text}"
        
        # Check if we've already processed this message
        if message_id in self.message_cache:
            logger.info(f"🔄 Сообщение уже было обработано ранее: {message_id}")
            return
            
        # Initialize cache for this message
        self.message_cache[message_id] = set()
        
        # Keep only last 1000 messages in cache to prevent memory issues
        if len(self.message_cache) > 1000:
            # Remove oldest message
            oldest_key = next(iter(self.message_cache))
            del self.message_cache[oldest_key]
            logger.info(f"🧹 Удалено старое сообщение из кэша: {oldest_key}")

        # For each niche, send to subscribers who haven't received this message yet
        for niche in NICHES_KEYWORDS.keys():
            subscribers = await self.db.get_subscribers_for_niche(niche)
            logger.info(f"🔍 Проверка ниши '{niche}': найдено {len(subscribers)} подписчиков")
            
            safe_chat = self._escape_html(chat_title or "Неизвестный чат")
            safe_text = self._escape_html(message_text)
            notification = (
                f"🔔 Новое сообщение по нише <b>{self._escape_html(niche)}</b>:\n\n"
                f"💬 Чат: {safe_chat}\n\n"
                f"📝 Сообщение:\n{safe_text}\n\n"
            )
            if message_link:
                safe_link = self._escape_html(message_link)
                notification += f"🔗 Ссылка: <a href=\"{safe_link}\">{safe_link}</a>"
                
            # Создаем хеш сообщения для проверки релевантности (sender_id неизвестен, используем 0)
            message_hash = self._create_message_hash(message_text, 0)
            
            # Проверяем глобальную блокировку (если сообщение помечено как спам или нерелевантное несколько раз)
            if self._is_message_globally_blocked(message_hash):
                logger.warning(f"🚫 Сообщение {message_hash} заблокировано глобально, не отправляем никому")
                continue
            
            for subscriber_id in subscribers:
                # Skip if subscriber already received this message
                if subscriber_id in self.message_cache[message_id]:
                    logger.info(f"⏭️ Пропуск отправки подписчику {subscriber_id} (уже получил)")
                    continue
                
                # Проверяем, не был ли этот message_id помечен как нерелевантный для этого пользователя
                if self._is_message_marked_as_not_relevant(message_hash, str(subscriber_id)):
                    logger.info(f"🚫 Пропуск отправки сообщения {message_hash} пользователю {subscriber_id} (помечено как нерелевантное)")
                    continue
                
                # Дополнительная проверка глобальной блокировки (на случай, если блокировка произошла во время рассылки)
                if self._is_message_globally_blocked(message_hash):
                    logger.warning(f"🚫 Сообщение {message_hash} заблокировано глобально во время рассылки, прекращаем отправку")
                    break
                    
                try:
                    await self.bot.send_message(
                        subscriber_id,
                        notification,
                        parse_mode="HTML"
                    )
                    # Mark subscriber as having received this message
                    self.message_cache[message_id].add(subscriber_id)
                    logger.info(f"✅ Сообщение успешно отправлено подписчику {subscriber_id}")
                except Exception as e:
                    logger.error(f"❌ Ошибка отправки сообщения подписчику {subscriber_id}: {e}")

    async def update_user_keywords(self):
        """Обновляет список ключевых слов для всех пользователей"""
        users = await self.db.get_all_users()
        for user in users:
            self.user_keywords[user['user_id']] = await self.db.get_user_keywords(user['user_id'])

    def should_monitor_message(self, message: Message) -> bool:
        """
        Проверяет, нужно ли мониторить сообщение
        """
        # Проверяем, что сообщение из нужного чата
        if not message.chat.username or message.chat.username.lower() not in [chat.lower() for chat in self.listening_chats]:
            return False
            
        # Проверяем, что отправитель не в списке запрещенных
        if message.from_user and message.from_user.username and message.from_user.username.lower() in [user.lower() for user in self.disallowed_users]:
            return False
            
        # Проверяем на запрещенные ключевые слова
        if message.text:
            message_lower = message.text.lower()
            for keyword in self.disallowed_keywords:
                if re.search(keyword, message_lower, re.IGNORECASE):
                    return False
                    
        return True
    
    async def find_matching_users(self, message: Message) -> Set[int]:
        """Находит пользователей, которым нужно отправить уведомление"""
        matching_users = set()
        
        if not message.text:
            return matching_users
            
        text_lower = message.text.lower()
        
        # Проверяем каждое ключевое слово каждого пользователя
        for user_id, keywords in self.user_keywords.items():
            for category, words in keywords.items():
                if any(word.lower() in text_lower for word in words):
                    matching_users.add(user_id)
                    break
        
        return matching_users

    async def send_notification(self, user_id: int, message: Message):
        """Отправляет уведомление пользователю"""
        settings = self.user_settings.get(user_id, {})
        frequency = settings.get("notification_frequency", "instant")
        
        # Получаем подписки пользователя
        user_niches = await self.db.get_user_niches(user_id)
        niches_text = "\n\n🎯 Ваши подписки: " + (", ".join(user_niches) if user_niches else "нет активных подписок")
        
        # Форматируем сообщение
        formatted_message = (
            f"📨 Новое сообщение:\n\n"
            f"{message.text}\n"
            f"{niches_text}\n\n"
            f"💡 Используйте /settings для настройки уведомлений"
        )
        
        if frequency == "instant":
            # Отправляем мгновенно
            await self.bot.send_message(user_id, formatted_message)
        else:
            # Добавляем в очередь
            self.message_queue[user_id].append(formatted_message)
            
            # Если это первое сообщение в очереди, запускаем таймер
            if len(self.message_queue[user_id]) == 1:
                if frequency == "daily":
                    await self.schedule_daily_digest(user_id)
                elif frequency == "weekly":
                    await self.schedule_weekly_digest(user_id)

    async def handle_message(self, message: Message):
        """Обрабатывает входящее сообщение"""
        if not self.should_monitor_message(message):
            return
            
        # Находим пользователей, которым нужно отправить уведомление
        matching_users = await self.find_matching_users(message)
        
        # Отправляем уведомления
        for user_id in matching_users:
            await self.send_notification(user_id, message)

    async def initialize(self):
        """Загрузить подписчиков и их ниши из базы"""
        logger.info("=== Начало инициализации монитора ===")
        logger.info("Загрузка подписчиков и их ниш...")
        users = await self.db.get_all_users()
        for user in users:
            user_id = user['user_id']
            niches = await self.db.get_user_niches(user_id)
            self.subscribers[user_id] = set(niches)
        logger.info(f"Загружено {len(self.subscribers)} подписчиков")
        await self.update_user_data()
        await self.update_user_keywords()
        logger.info("=== Монитор успешно инициализирован ===")

    async def get_status(self) -> dict:
        """Возвращает текущий статус монитора"""
        return {
            "active_subscribers": len(self.subscribers),
            "monitored_topics": list(self.topic_keywords.keys()),
            "active_patterns": len(self.patterns),
            "message_cache_size": len(self.message_cache),
            "is_initialized": bool(self.subscribers)
        }

    async def start(self):
        """Запускает мониторинг"""
        logger.info("=== Запуск мониторинга ===")
        # Обновляем данные пользователей
        await self.update_user_data()
        # Запускаем обновление ключевых слов
        asyncio.create_task(self.update_user_keywords())
        logger.info("=== Мониторинг запущен ===")

    async def update_subscribers(self):
        """Обновить подписчиков и их ниши из базы (можно вызывать периодически)"""
        await self.initialize() 

    async def process_message_from_subscriber(self, message_text: str, chat_title: str = None, message_link: str = None, sender_username: str = None, sender_id: int = None, sender_first_name: str = None, sender_last_name: str = None):
        """Обработка сообщения, полученного от подписчика"""
        if not message_text:
            logger.warning("❌ Пустое сообщение, пропускаем")
            return

        logger.info("=== Начало обработки сообщения ===")
        logger.info(f"📝 Текст сообщения: {message_text[:100]}...")
        logger.info(f"💬 Чат: {chat_title}")
        logger.info(f"👤 Отправитель: {sender_username} (ID: {sender_id})")

        # Проверка на ботов-отправителей (блокируем повторяющиеся сообщения от ботов)
        if sender_username:
            username_lower = sender_username.lower()
            # Проверяем, является ли отправитель ботом
            if 'bot' in username_lower or 'informant' in username_lower or 'keeper' in username_lower or 'hunter' in username_lower:
                # Для ботов используем более строгую дедупликацию (только по тексту, без sender_id)
                bot_message_hash = self._create_message_hash(message_text, 0)
                if bot_message_hash in self.message_hashes:
                    current_time = datetime.now()
                    if (current_time - self.message_hashes[bot_message_hash]).total_seconds() < self.duplicate_window * 24:  # 24 часа для ботов
                        logger.info(f"🔄 Сообщение от бота {sender_username} уже было обработано ранее (дедупликация ботов)")
                        return
                self.message_hashes[bot_message_hash] = datetime.now()

        # Проверяем на дубликаты с улучшенной логикой
        if self._is_duplicate_message(message_text, sender_id):
            logger.info(f"🔄 Сообщение от пользователя {sender_id} уже было обработано ранее")
            return

        # Гибридная классификация сообщения
        classification_result = await self._hybrid_classify_message(message_text, sender_username)

        # Проверка на спам
        if classification_result.get('is_spam', False):
            logger.info(f"🚫 Сообщение отфильтровано как спам: {classification_result.get('reason', 'Неизвестная причина')}")
            return

        # Получаем найденные ниши и дополнительную информацию
        found_niches = set(classification_result.get('niches', []))
        confidence = classification_result.get('confidence', 0)
        reason = classification_result.get('reason', 'Неизвестная причина')
        message_type = classification_result.get('message_type', 'ОБЩЕНИЕ')
        context = classification_result.get('context', '')
        urgency = classification_result.get('urgency', 'не срочно')
        budget = classification_result.get('budget', '')

        if not found_niches:
            logger.info("❌ Категории не найдены, сообщение не будет разослано")
            return

        logger.info(f"📊 Найдено ниш: {found_niches} (тип: {message_type}, уверенность: {confidence}%, причина: {reason})")
        
        # Определяем страну чата по названию чата
        chat_country = self._get_country_from_chat_title(chat_title) if chat_title else None
        if chat_country:
            logger.info(f"🌍 Страна определена по названию чата '{chat_title}': {chat_country}")
        else:
            # Если не определили по названию, по умолчанию считаем что это Бали (для обратной совместимости)
            chat_country = "Бали"
            logger.info(f"🌍 Страна не определена по названию чата, используем 'Бали' по умолчанию")
        
        # Получаем всех подписчиков для найденных ниш с учетом страны
        all_subscribers = set()
        for niche in found_niches:
            subscribers = await self.db.get_subscribers_for_niche(niche, country=chat_country)
            logger.info(f"👥 Найдено {len(subscribers)} подписчиков для ниши '{niche}'" + (f" и страны '{chat_country}'" if chat_country else "") + f": {subscribers}")
            all_subscribers.update(subscribers)
        
        if not all_subscribers:
            logger.info("❌ Подписчики не найдены, сообщение не будет разослано")
            return

        logger.info(f"👥 Всего найдено {len(all_subscribers)} уникальных подписчиков: {all_subscribers}")
        
        # Формируем информацию об отправителе
        sender_info = ""
        if sender_first_name or sender_last_name:
            full_name = f"{sender_first_name or ''} {sender_last_name or ''}".strip()
            sender_info = f"👤 {full_name}"
            if sender_username:
                sender_info += f" (@{sender_username})"
        elif sender_username:
            sender_info = f"👤 @{sender_username}"
        
        # Создаем уникальный ID для сообщения для кнопок
        message_id = self._create_message_hash(message_text, sender_id or 0)
        
        # Проверяем глобальную блокировку (если сообщение помечено как спам или нерелевантное несколько раз)
        if self._is_message_globally_blocked(message_id):
            logger.warning(f"🚫 Сообщение {message_id} заблокировано глобально, не отправляем никому")
            return
        
        # Рассылка всем подписчикам найденных ниш
        for user_id in all_subscribers:
            try:
                user = await self.db.get_user(user_id)
                if not user:
                    logger.warning(f"⚠️ Пользователь {user_id} не найден в базе")
                    continue

                # Получаем ниши пользователя для логирования
                user_niches = await self.db.get_user_niches(user_id)
                logger.info(f"📋 Пользователь {user_id} подписан на ниши: {user_niches}")

                # Проверяем, есть ли пересечение ниш
                common_niches = set(n.lower() for n in user_niches) & set(n.lower() for n in found_niches)
                if not common_niches:
                    logger.info(f"⚠️ У пользователя {user_id} нет общих ниш с найденными")
                    continue

                # Проверяем, не был ли этот message_id помечен как нерелевантный для этого пользователя
                if self._is_message_marked_as_not_relevant(message_id, str(user_id)):
                    logger.info(f"🚫 Пропуск отправки сообщения {message_id} пользователю {user_id} (помечено как нерелевантное)")
                    continue
                
                # Дополнительная проверка глобальной блокировки (на случай, если блокировка произошла во время рассылки)
                if self._is_message_globally_blocked(message_id):
                    logger.warning(f"🚫 Сообщение {message_id} заблокировано глобально во время рассылки, прекращаем отправку")
                    return

                # Формируем улучшенное уведомление с дополнительной информацией
                notification = "🔔 <b>Новое сообщение</b>\n\n"
                
                # Добавляем тип сообщения
                type_emoji = {
                    "ПОИСК": "🔍",
                    "ПРЕДЛОЖЕНИЕ": "💼", 
                    "ОБЩЕНИЕ": "💬",
                    "СПАМ": "🚫"
                }
                type_emoji_str = type_emoji.get(message_type, "💬")
                notification += (
                    f"{type_emoji_str} <b>Тип:</b> {self._escape_html(message_type)}\n"
                )
                
                # Добавляем ниши
                notification += (
                    f"📂 <b>Категории:</b> {self._escape_html(', '.join(common_niches))}\n"
                )
                
                # Добавляем срочность если есть
                if urgency != "не срочно":
                    notification += f"⚡ <b>Срочность:</b> {self._escape_html(urgency)}\n"
                
                # Добавляем бюджет если есть
                if budget:
                    notification += f"💰 <b>Бюджет:</b> {self._escape_html(budget)}\n"
                
                # Добавляем контекст если есть
                if context and context != "Обычное общение":
                    notification += f"📝 <b>Контекст:</b> {self._escape_html(context)}\n"
                
                notification += (
                    f"\n📄 <b>Сообщение:</b>\n{self._escape_html(message_text)}\n\n"
                )
                
                if sender_info:
                    notification += f"{self._escape_html(sender_info)}\n\n"
                
                notification += (
                    f"💬 <b>Чат:</b> {self._escape_html(chat_title or 'Неизвестный чат')}"
                )
                
                if message_link:
                    safe_link = self._escape_html(message_link)
                    notification += f"\n🔗 <b>Ссылка:</b> <a href=\"{safe_link}\">{safe_link}</a>"

                # Создаем кнопки для оценки релевантности
                keyboard = InlineKeyboardMarkup(row_width=2)
                keyboard.add(
                    InlineKeyboardButton("✅ Релевантно", callback_data=f"relevant_{message_id}_{user_id}"),
                    InlineKeyboardButton("❌ Не релевантно", callback_data=f"not_relevant_{message_id}_{user_id}")
                )
                
                # Добавляем кнопку для отметки как спам
                keyboard.add(
                    InlineKeyboardButton("🚫 Отметить как спам", callback_data=f"spam_{message_id}_{user_id}")
                )
                
                # Добавляем кнопку для исправления классификации
                keyboard.add(
                    InlineKeyboardButton("🔧 Исправить классификацию", callback_data=f"correct_{message_id}_{user_id}")
                )

                await self.bot.send_message(
                    user_id, 
                    notification,
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
                logger.info(f"✅ Уведомление с кнопками отправлено пользователю {user_id}")
                
            except Exception as e:
                logger.error(f"❌ Ошибка отправки уведомления пользователю {user_id}: {e}")
        
        logger.info("=== Обработка сообщения завершена ===")

    async def cleanup(self):
        """Очищает ресурсы при завершении работы"""
        try:
            # Очищаем все очереди и кэши
            self.message_queue.clear()
            self.message_cache.clear()
            self.message_hashes.clear()  # Очищаем хеши сообщений
            self.user_keywords.clear()
            self.topic_keywords.clear()
            self.user_topics.clear()
            self.user_settings.clear()
            self.subscribers.clear()
            
            # Очищаем AI классификатор
            if self.ai_classifier:
                self.ai_classifier.clear_cache()
            
            logger.info("✅ Ресурсы монитора успешно очищены")
        except Exception as e:
            logger.error(f"❌ Ошибка при очистке ресурсов монитора: {e}")

    # Обработчики для кнопок релевантности
    async def handle_relevant_button(self, callback_query: types.CallbackQuery):
        """Обрабатывает нажатие кнопки 'Релевантно'"""
        try:
            # Парсим данные из callback_data
            parts = callback_query.data.split('_')
            if len(parts) >= 3:
                message_id = parts[1]
                user_id = parts[2]
                
                # Проверяем, что пользователь нажал на свою кнопку
                if str(callback_query.from_user.id) == user_id:
                    # Сохраняем положительную оценку
                    await self.save_relevance_feedback(message_id, user_id, True)
                    
                    # Обновляем сообщение
                    await callback_query.message.edit_reply_markup(
                        InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton("✅ Релевантно (подтверждено)", callback_data="confirmed_relevant")]
                        ])
                    )
                    
                    await callback_query.answer("✅ Спасибо! Ваша оценка учтена")
                    logger.info(f"✅ Пользователь {user_id} подтвердил релевантность сообщения {message_id}")
                else:
                    await callback_query.answer("❌ Это не ваше сообщение")
                    
        except Exception as e:
            logger.error(f"❌ Ошибка обработки кнопки 'Релевантно': {e}")
            await callback_query.answer("❌ Ошибка обработки")

    async def handle_not_relevant_button(self, callback_query: types.CallbackQuery):
        """Обрабатывает нажатие кнопки 'Не релевантно'"""
        try:
            # Парсим данные из callback_data
            parts = callback_query.data.split('_')
            if len(parts) >= 3:
                message_id = parts[1]
                user_id = parts[2]
                
                # Проверяем, что пользователь нажал на свою кнопку
                if str(callback_query.from_user.id) == user_id:
                    # Сохраняем отрицательную оценку
                    await self.save_relevance_feedback(message_id, user_id, False, is_spam=False)
                    
                    # Проверяем, не заблокировано ли сообщение глобально
                    is_blocked = self._is_message_globally_blocked(message_id)
                    blocked_text = "\n\n🚫 Сообщение заблокировано глобально (превышен порог отметок)" if is_blocked else ""
                    
                    # Обновляем сообщение
                    await callback_query.message.edit_reply_markup(
                        InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton("❌ Не релевантно (подтверждено)", callback_data="confirmed_not_relevant")]
                        ])
                    )
                    
                    await callback_query.answer(f"✅ Спасибо! Ваша оценка учтена{blocked_text}")
                    logger.info(f"❌ Пользователь {user_id} отметил сообщение {message_id} как нерелевантное")
                    
                    if is_blocked:
                        logger.warning(f"🚫 Сообщение {message_id} заблокировано глобально после отметки пользователем {user_id}")
                else:
                    await callback_query.answer("❌ Это не ваше сообщение")
                    
        except Exception as e:
            logger.error(f"❌ Ошибка обработки кнопки 'Не релевантно': {e}")
            await callback_query.answer("❌ Ошибка обработки")

    async def handle_spam_button(self, callback_query: types.CallbackQuery):
        """Обрабатывает нажатие кнопки 'Отметить как спам'"""
        try:
            # Парсим данные из callback_data
            parts = callback_query.data.split('_')
            if len(parts) >= 3:
                message_id = parts[1]
                user_id = parts[2]
                
                # Проверяем, что пользователь нажал на свою кнопку
                if str(callback_query.from_user.id) == user_id:
                    # Сохраняем как спам (глобальная блокировка)
                    await self.save_relevance_feedback(message_id, user_id, False, is_spam=True)
                    
                    # Обновляем сообщение
                    await callback_query.message.edit_reply_markup(
                        InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton("🚫 Отмечено как спам (заблокировано)", callback_data="confirmed_spam")]
                        ])
                    )
                    
                    await callback_query.answer("🚫 Сообщение отмечено как спам и заблокировано глобально")
                    logger.warning(f"🚫 Пользователь {user_id} отметил сообщение {message_id} как СПАМ (глобальная блокировка)")
                else:
                    await callback_query.answer("❌ Это не ваше сообщение")
                    
        except Exception as e:
            logger.error(f"❌ Ошибка обработки кнопки 'Отметить как спам': {e}")
            await callback_query.answer("❌ Ошибка обработки")

    async def handle_correct_button(self, callback_query: types.CallbackQuery):
        """Обрабатывает нажатие кнопки 'Исправить классификацию'"""
        try:
            # Парсим данные из callback_data
            parts = callback_query.data.split('_')
            if len(parts) >= 3:
                message_id = parts[1]
                user_id = parts[2]
                
                # Проверяем, что пользователь нажал на свою кнопку
                if str(callback_query.from_user.id) == user_id:
                    # Отправляем инструкцию по исправлению
                    await callback_query.message.answer(
                        "🔧 **Исправление классификации**\n\n"
                        "Отправьте сообщение в формате:\n"
                        "`текст_сообщения | исправленная_классификация`\n\n"
                        "**Пример:**\n"
                        "`Ищу фотографа на свадьбу | ПОИСК:Фотограф:срочно:500$`\n\n"
                        "**Формат исправления:**\n"
                        "`ТИП:НИША:СРОЧНОСТЬ:БЮДЖЕТ`\n\n"
                        "Типы: ПОИСК, ПРЕДЛОЖЕНИЕ, ОБЩЕНИЕ, СПАМ\n"
                        "Ниши: Фотограф, Видеограф, и т.д.\n"
                        "Срочность: срочно/не срочно\n"
                        "Бюджет: сумма или пусто\n\n"
                        "Отправьте /cancel для отмены"
                    )
                    
                    await callback_query.answer("📝 Ожидаю ваше исправление...")
                    logger.info(f"🔧 Пользователь {user_id} запросил исправление классификации для сообщения {message_id}")
                else:
                    await callback_query.answer("❌ Это не ваше сообщение")
                    
        except Exception as e:
            logger.error(f"❌ Ошибка обработки кнопки 'Исправить': {e}")
            await callback_query.answer("❌ Ошибка обработки")

    def _is_message_marked_as_not_relevant(self, message_id: str, user_id: str) -> bool:
        """
        Проверяет, был ли message_id помечен как нерелевантный для конкретного пользователя
        """
        try:
            feedback_file = "relevance_feedback.json"
            try:
                with open(feedback_file, 'r', encoding='utf-8') as f:
                    feedbacks = json.load(f)
            except FileNotFoundError:
                return False
            
            # Проверяем, есть ли запись с этим message_id и user_id, где is_relevant = False
            for feedback in feedbacks:
                if (feedback.get("message_id") == message_id and 
                    feedback.get("user_id") == str(user_id) and 
                    feedback.get("is_relevant") == False):
                    logger.info(f"🚫 Сообщение {message_id} помечено как нерелевантное для пользователя {user_id}")
                    return True
            
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка проверки релевантности сообщения: {e}")
            return False

    def _is_message_globally_blocked(self, message_id: str, spam_threshold: int = 2) -> bool:
        """
        Проверяет, заблокировано ли сообщение глобально (помечено как спам/нерелевантное N раз)
        
        Args:
            message_id: ID сообщения для проверки
            spam_threshold: Количество отметок "не релевантно" для глобальной блокировки (по умолчанию 2)
        
        Returns:
            True если сообщение заблокировано глобально, False иначе
        """
        try:
            feedback_file = "relevance_feedback.json"
            try:
                with open(feedback_file, 'r', encoding='utf-8') as f:
                    feedbacks = json.load(f)
            except FileNotFoundError:
                return False
            
            # Подсчитываем количество отметок "не релевантно" для этого сообщения
            not_relevant_count = 0
            is_spam_marked = False
            
            for feedback in feedbacks:
                if feedback.get("message_id") == message_id:
                    if feedback.get("is_relevant") == False:
                        not_relevant_count += 1
                    # Проверяем, помечено ли как спам
                    if feedback.get("is_spam", False):
                        is_spam_marked = True
            
            # Если помечено как спам или превышен порог, блокируем глобально
            if is_spam_marked:
                logger.info(f"🚫 Сообщение {message_id} заблокировано глобально (помечено как спам)")
                return True
            
            if not_relevant_count >= spam_threshold:
                logger.info(f"🚫 Сообщение {message_id} заблокировано глобально ({not_relevant_count} отметок 'не релевантно')")
                return True
            
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка проверки глобальной блокировки сообщения: {e}")
            return False

    async def save_relevance_feedback(self, message_id: str, user_id: str, is_relevant: bool, is_spam: bool = False):
        """Сохраняет обратную связь о релевантности"""
        try:
            # Здесь можно сохранить в базу данных или файл
            feedback_data = {
                "message_id": message_id,
                "user_id": user_id,
                "is_relevant": is_relevant,
                "is_spam": is_spam,
                "timestamp": datetime.now().isoformat()
            }
            
            # Сохраняем в файл для простоты (можно заменить на базу данных)
            feedback_file = "relevance_feedback.json"
            try:
                with open(feedback_file, 'r', encoding='utf-8') as f:
                    feedbacks = json.load(f)
            except FileNotFoundError:
                feedbacks = []
            
            # Проверяем, нет ли уже такой записи (чтобы не дублировать)
            existing = False
            for i, fb in enumerate(feedbacks):
                if (fb.get("message_id") == message_id and 
                    fb.get("user_id") == str(user_id)):
                    # Обновляем существующую запись
                    feedbacks[i] = feedback_data
                    existing = True
                    break
            
            if not existing:
                feedbacks.append(feedback_data)
            
            with open(feedback_file, 'w', encoding='utf-8') as f:
                json.dump(feedbacks, f, ensure_ascii=False, indent=2)
            
            logger.info(f"💾 Сохранена обратная связь: {feedback_data}")
            
            # Если сообщение помечено как спам, логируем это
            if is_spam:
                logger.warning(f"🚫 Сообщение {message_id} помечено как СПАМ пользователем {user_id}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения обратной связи: {e}")

    def _get_country_from_chat_title(self, chat_title: str) -> str:
        """
        Определяет страну по названию чата
        Используется, когда chat_id недоступен
        """
        if not chat_title:
            return None
        
        chat_title_lower = chat_title.lower()
        
        # Маппинг ключевых слов в названиях чатов на страны
        country_keywords = {
            "Бали": ["бали", "bali", "индонези", "ubud", "чангу", "семеньяк", "кута"],
            "Таиланд": ["таиланд", "thailand", "пхукет", "phuket", "самуи", "samui", "паттай", "pattaya"],
            "Турция": ["турци", "turkey", "турк", "антали", "antalya", "стамбул", "istanbul"],
            "Грузия": ["грузи", "georgia", "тбилиси", "tbilisi", "батуми", "batumi"]
        }
        
        for country, keywords in country_keywords.items():
            if any(keyword in chat_title_lower for keyword in keywords):
                logger.info(f"🌍 Страна '{country}' определена по названию чата '{chat_title}'")
                return country
        
        return None

async def main():
    # Инициализация Telethon клиента
    client = TelegramClient('monitor_session', API_ID, API_HASH)
    await client.start()
    logger.info("Telethon клиент успешно запущен")

    # Инициализация базы и монитора
    # Используем токен основного бота для отправки уведомлений
    main_bot_token = '7135926908:AAF5r7P-PtPTy2L8SZOm2tNQxqraMHkZyzA'
    bot = Bot(token=main_bot_token)
    db = Database(dsn=DB_DSN)
    await db.connect()
    monitor = MessageMonitor(bot, db)
    await monitor.initialize()
    logger.info("База данных и монитор успешно инициализированы") 