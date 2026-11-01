import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, ChatPermissions, ReplyKeyboardMarkup, KeyboardButton
from config import (
    TELEGRAM_BOT_TOKEN,
    ADMIN_CHAT_ID,
    ADMIN_USERNAME,
    SOURCE_CHAT_ID,
    MONITORING_CONFIG,
    NOTIFICATION_SETTINGS,
    DB_DSN,
    TRIAL_DAYS,
    TRIAL_MAX_NICHES,
    SUBSCRIPTION_DAYS,
    SUBSCRIPTION_STARS,
)
from aiogram.types import LabeledPrice, ContentTypes
from database import Database
from datetime import datetime, timezone
from content import get_topic_content, get_available_topics, get_topic_description, get_topic_keywords
from monitor import MessageMonitor
import logging
from utils import is_message_allowed
import json
from patterns import NICHES_KEYWORDS
import os

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Состояния для FSM
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import State, StatesGroup

# Инициализация компонентов
storage = MemoryStorage()
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher(bot, storage=storage)
db = Database(DB_DSN)
monitor = MessageMonitor(bot, db)

# Сохраняем экземпляры в контексте бота для доступа из хендлеров
bot["db"] = db
bot["monitor"] = monitor

# Формируем MONITORING_CONFIG['niches'] из NICHES_KEYWORDS
MONITORING_CONFIG['niches'] = NICHES_KEYWORDS

# Временное хранение выбранных ниш для каждого пользователя
temp_niche_selections = {}

# Описания ниш для пользователей
NICHE_DESCRIPTIONS = {
    "Фотограф": "📸 Профессиональная фотосъемка, фотосессии, свадебная фотография, семейные фото, детская съемка, контент для соцсетей, портреты, рекламная фотография",
    "Видеограф": "🎬 Видеосъемка, монтаж видео, свадебные клипы, рекламные ролики, контент для YouTube/TikTok, съемка с дрона, интервью, подкасты",
    "Недвижимость (Спрос)": "🏠 Поиск жилья в аренду: сниму квартиру, ищу жилье, арендую комнату, нужна квартира, снять виллу, кто сдает жилье",
    "Недвижимость (Предложение)": "🏘️ Сдача жилья в аренду: сдам квартиру, сдаю виллу, сдается комната, освободилась вилла, предлагаю жилье, сдача апартаментов",
    "Маникюр": "💅 Маникюр, педикюр, наращивание ногтей, дизайн ногтей, гель-лак, шеллак, мастера маникюра",
    "Волосы": "💇‍♀️ Стрижки, окрашивание, прически, укладки, наращивание волос, парикмахерские услуги, салоны красоты",
    "Аренда авто": "🚗 Аренда автомобилей, прокат машин, аренда скутеров, водители, трансферы, поездки",
    "Реснички": "👁️ Наращивание ресниц, коррекция, объемные ресницы, дизайн ресниц, мастера по ресницам",
    "Брови": "✏️ Коррекция бровей, татуаж бровей, окрашивание, ламинирование, дизайн бровей",
    "Макияж": "💄 Макияж на свадьбу, вечерний макияж, дневной макияж, визажисты, профессиональный макияж",
    "Косметология": "✨ Чистка лица, пилинг, массаж лица, уход за кожей, омоложение, ботокс, филлеры",
    "Продажа недвижимости": "🏘️ Продажа квартир, домов, апартаментов, вилл, участков, недвижимость, риелторские услуги",
    "Аренда байков": "🏍️ Аренда мотоциклов, прокат байков, аренда скутеров, мототранспорт",
    "Обмен валют": "💱 Обмен валют, курс валют, обменники, конвертация, доллары, евро, рубли",
    "Кальяны": "💨 Кальянные, кальян на дом, кальян с доставкой, кальян-бары, кальянные комнаты",
    "Аренда Playstation": "🎮 Аренда игровых приставок, прокат PS4/PS5, игровые консоли, развлечения",
    "Медиа-студия": "🎭 Аренда студий, фотостудии, видеостудии, съемочные площадки, медиа-услуги",
    "Туризм": "🌴 Туры, экскурсии, гиды, бронирование отелей, трансферы, путешествия, туристические услуги",
    "Транспорт": "🚐 Аренда авто, прокат транспорта, водители, такси, трансферы, поездки, мототранспорт",

}

class RegStates(StatesGroup):
    waiting_for_topic = State()
    waiting_for_keywords = State()
    waiting_for_confirmation = State()
    waiting_for_chats = State()
    waiting_for_notification_settings = State()

class AdminStates(StatesGroup):
    waiting_for_user_message = State()

# Список доступных категорий
CATEGORIES = [
    "авиа", "отели", "виза", "страховка", "экскурсии",
    "трансфер", "аренда", "круизы", "шоппинг", "рестораны"
]

# Список ниш
NICHES = [
    "Фотограф", "Видеограф", "Недвижимость (Спрос)", "Недвижимость (Предложение)", "Маникюр", "Волосы", "Аренда авто",
    "Реснички", "Брови", "Макияж", "Косметология", "Продажа недвижимости", "Аренда байков",
    "Обмен валют", "Кальяны", "Аренда Playstation", "Медиа-студия", "Туризм", "Транспорт"
]

async def create_user_chat(user_id: int, username: str, topic: str) -> int:
    """
    Создает новый чат для пользователя
    :return: ID созданного чата
    """
    try:
        # Создаем название чата
        chat_title = f"Мониторинг: {topic}"
        
        # Создаем чат через создание группы
        chat = await bot.create_chat_invite_link(
            chat_id=ADMIN_CHAT_ID,
            name=chat_title,
            creates_join_request=True
        )
        
        # Отправляем пользователю приглашение
        await bot.send_message(
            user_id,
            f"Я создал для вас чат мониторинга по теме '{topic}'.\n"
            f"Присоединяйтесь: {chat.invite_link}"
        )
        
        # Отправляем приветственное сообщение в админский чат
        description = get_topic_description(topic)
        await bot.send_message(
            ADMIN_CHAT_ID,
            f"🆕 Новый чат мониторинга!\n\n"
            f"Тема: {topic}\n"
            f"Описание: {description}\n\n"
            f"Здесь вы будете получать актуальную информацию из выбранных чатов."
        )
        
        return ADMIN_CHAT_ID
        
    except Exception as e:
        # Если не удалось создать чат, используем личные сообщения
        await bot.send_message(
            user_id,
            f"Я буду отправлять вам информацию по теме '{topic}' в личные сообщения.\n"
            f"Вы будете получать актуальные новости и обсуждения из выбранных чатов."
        )
        return user_id

async def send_topic_content(user_id: int, topic: str, bot: Bot):
    """
    Отправляет контент по теме пользователю
    """
    messages = get_topic_content(topic)
    for message in messages:
        await bot.send_message(user_id, message)
        await asyncio.sleep(1)  # Небольшая задержка между сообщениями

async def notify_admin_about_new_user(user_id: int, username: str, topic: str, bot: Bot):
    if ADMIN_CHAT_ID:
        message = (
            f"🆕 Новый пользователь!\n"
            f"ID: {user_id}\n"
            f"Username: @{username}\n"
            f"Тема мониторинга: {topic}\n"
            f"Дата регистрации: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Написать пользователю", callback_data=f"write_{user_id}")]
        ])
        await bot.send_message(ADMIN_CHAT_ID, message, reply_markup=keyboard)

def get_main_menu() -> ReplyKeyboardMarkup:
    """Создает главное меню с выбором ниши, страны, реферальной программой, статусом и помощью"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🗂 Выбрать нишу")],
            [KeyboardButton(text="🌍 Выбрать страну"), KeyboardButton(text="🎁 Реферальная программа")],
            [KeyboardButton(text="📊 Статус подписки"), KeyboardButton(text="❓ Помощь")]
        ],
        resize_keyboard=True
    )
    return keyboard

def get_topics_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру с темами"""
    topics = get_available_topics()
    keyboard = []
    for topic in topics:
        keyboard.append([InlineKeyboardButton(
            text=f"📌 {topic.capitalize()}",
            callback_data=f"topic_{topic}"
        )])
    keyboard.append([InlineKeyboardButton(
        text="🔙 Назад",
        callback_data="back_to_main"
    )])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_notification_settings() -> InlineKeyboardMarkup:
    """Создает меню настроек уведомлений"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔔 Мгновенно", callback_data="notify_instant")],
        [InlineKeyboardButton(text="📅 Раз в день", callback_data="notify_daily")],
        [InlineKeyboardButton(text="📅 Раз в неделю", callback_data="notify_weekly")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_settings")]
    ])
    return keyboard

def get_keyword_categories_keyboard():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌴 Путешествия", callback_data="category_travel")],
            [InlineKeyboardButton(text="🏠 Недвижимость", callback_data="category_real_estate")],
            [InlineKeyboardButton(text="🚗 Транспорт", callback_data="category_transport")],
            [InlineKeyboardButton(text="🎉 Мероприятия", callback_data="category_events")],
            [InlineKeyboardButton(text="📝 Виза", callback_data="category_visa")],
            [InlineKeyboardButton(text="✅ Готово", callback_data="keywords_done")]
        ]
    )
    return keyboard

def get_keywords_keyboard(category: str):
    """Создает клавиатуру с ключевыми словами для выбранной категории"""
    try:
        keywords = MONITORING_CONFIG["keywords"][category]
        keyboard = []
        
        # Добавляем кнопки для каждого ключевого слова
        for keyword in keywords:
            keyboard.append([InlineKeyboardButton(
                text=f"➕ {keyword}",
                callback_data=f"keyword_{category}_{keyword}"
            )])
        
        # Добавляем кнопку возврата
        keyboard.append([InlineKeyboardButton(
            text="🔙 Назад к категориям",
            callback_data="back_to_categories"
        )])
        
        return InlineKeyboardMarkup(inline_keyboard=keyboard)
    except KeyError:
        # Если категория не найдена, возвращаем пустую клавиатуру
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="🔙 Назад к категориям",
                callback_data="back_to_categories"
            )]
        ])

async def get_niches_keyboard(user_id, db):
    # Получаем временно выбранные ниши (если пользователь в процессе выбора)
    temp_niches = temp_niche_selections.get(user_id, [])
    temp_niches_normalized = [niche.lower() for niche in temp_niches]
    
    # Если есть временные ниши, показываем только их
    if temp_niches:
        all_niches_normalized = temp_niches_normalized
    else:
        # Иначе показываем сохраненные ниши из базы данных
        saved_niches = await db.get_user_niches(user_id)
        all_niches_normalized = [niche.lower() for niche in saved_niches]
    
    keyboard = []
    row = []
    for i, niche in enumerate(NICHES, 1):
        # Показываем как выбранную, если ниша есть в активном списке
        button_text = f"✅ {niche}" if niche.lower() in all_niches_normalized else niche
        row.append(InlineKeyboardButton(text=button_text, callback_data=f"niche_{i}"))
        if i % 2 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([
        InlineKeyboardButton(text="✅ Готово", callback_data="niches_done")
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

async def get_countries_keyboard(user_id, db):
    """Создает клавиатуру выбора стран"""
    # Получаем сохраненные страны пользователя
    saved_countries = []
    if db:
        try:
            saved_countries = await db.get_user_countries(user_id)
            if not isinstance(saved_countries, list):
                saved_countries = []
        except Exception as e:
            # Если метод не реализован или произошла ошибка, возвращаем пустой список
            logger.warning(f"Error getting user countries for {user_id}: {e}")
            saved_countries = []
    
    keyboard = []
    row = []
    
    # Коды = subscribers.countries (как уже лежит в БД у части пользователей)
    countries = [
        ("🇮🇩 Бали", "bali"),
        ("🇹🇭 Таиланд", "thailand"),
        ("🇹🇷 Турция", "turkey"),
        ("🇬🇪 Грузия", "georgia"),
        ("🇻🇳 Вьетнам", "vietnam"),
        ("🇦🇪 Дубай / ОАЭ", "dubai"),
        ("🇷🇺 Россия", "russia"),
        ("🇦🇲 Армения", "armenia"),
        ("🇷🇸 Сербия", "serbia"),
        ("🇮🇳 Гоа / Индия", "goa"),
        ("🇿🇦 Кейптаун / ЮАР", "cape_town"),
        ("🇺🇸 США", "usa"),
    ]
    
    for i, (country_name, country_code) in enumerate(countries, 1):
        # Показываем как выбранную, если страна есть в сохраненных
        button_text = f"✅ {country_name}" if country_code in saved_countries else country_name
        row.append(InlineKeyboardButton(text=button_text, callback_data=f"country_{country_code}"))
        
        if i % 2 == 0:
            keyboard.append(row)
            row = []
    
    if row:
        keyboard.append(row)
    
    keyboard.append([
        InlineKeyboardButton(text="✅ Готово", callback_data="countries_done")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@dp.callback_query_handler(lambda c: c.data == "settings_notifications")
async def settings_notifications(callback_query: types.CallbackQuery):
    await callback_query.message.edit_text(
        "🔔 Настройка частоты уведомлений:\n\n"
        "Выберите, как часто вы хотите получать уведомления:",
        reply_markup=get_notification_settings()
    )

@dp.callback_query_handler(lambda c: c.data.startswith("notify_"))
async def process_notification_setting(callback_query: types.CallbackQuery):
    setting = callback_query.data.replace("notify_", "")
    user_id = callback_query.from_user.id
    
    # Обновляем настройки пользователя
    await db.update_user_settings(user_id, {"notification_frequency": setting})
    
    # Формируем сообщение о выбранной частоте
    frequency_text = {
        "instant": "🔔 Мгновенно",
        "daily": "📅 Раз в день",
        "weekly": "📅 Раз в неделю"
    }.get(setting, "🔔 Мгновенно")
    
    await callback_query.message.edit_text(
        f"✅ Настройки уведомлений обновлены!\n\n"
        f"Частота уведомлений: {frequency_text}\n\n"
        f"Вы будете получать уведомления в соответствии с выбранной частотой.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад к настройкам", callback_data="back_to_settings")]
        ])
    )

def register_handlers(dp: Dispatcher, monitor: MessageMonitor, bot: Bot):
    """Register all message handlers with the dispatcher"""
    # Store instances in dispatcher for handlers to access
    dp["bot"] = bot
    dp["monitor"] = monitor
    
    # Command handlers
    dp.register_message_handler(cmd_start, Command("start"))
    dp.register_message_handler(cmd_status, Command("status"))
    dp.register_message_handler(cmd_menu, Command("menu"))
    dp.register_message_handler(cmd_niche, Command("niche"))
    dp.register_message_handler(cmd_niche, Command("niches"))
    dp.register_message_handler(cmd_subscribe, Command("subscribe"))
    dp.register_message_handler(cmd_subscribe, Command("buy"))
    dp.register_pre_checkout_query_handler(process_pre_checkout_query, lambda q: True)
    dp.register_message_handler(
        process_successful_payment, content_types=ContentTypes.SUCCESSFUL_PAYMENT
    )
    dp.register_callback_query_handler(
        callback_pay_subscribe, lambda c: c.data in ("pay_subscribe", "subscribe")
    )
    dp.register_message_handler(cmd_help, Command("help"))
    dp.register_message_handler(cmd_info, Command("info"))
    dp.register_message_handler(cmd_contact, Command("contact"))
    dp.register_message_handler(cmd_reset, Command("reset"))
    dp.register_message_handler(cmd_admin, Command("admin"))
    dp.register_message_handler(cmd_test, Command("test"))
    dp.register_message_handler(cmd_clear, Command("clear"))
    dp.register_message_handler(cmd_test_messages, Command("test_messages"))
    dp.register_message_handler(show_niches_menu, Command("niches"))
    dp.register_message_handler(cmd_send_reminders, Command("send_reminders"))
    
    # Message handlers
    dp.register_message_handler(show_status, lambda message: message.text == "📊 Статус подписки")
    dp.register_message_handler(show_help, lambda message: message.text == "❓ Помощь")
    
    # Callback query handlers
    dp.register_callback_query_handler(process_category_selection, lambda c: c.data.startswith('category_'))
    dp.register_callback_query_handler(process_keyword_selection, lambda c: c.data.startswith('keyword_'))
    dp.register_callback_query_handler(process_keywords_done, lambda c: c.data == "keywords_done")
    dp.register_callback_query_handler(back_to_categories, lambda c: c.data == "back_to_categories")
    dp.register_callback_query_handler(back_to_menu, lambda c: c.data == "back_to_menu")
    dp.register_callback_query_handler(process_admin_write, lambda c: c.data.startswith('write_'))
    dp.register_callback_query_handler(process_niche_selection, lambda c: c.data.startswith('niche_'))
    dp.register_callback_query_handler(process_niches_done, lambda c: c.data == "niches_done")
    dp.register_callback_query_handler(back_to_main, lambda c: c.data == "back_to_main")
    dp.register_callback_query_handler(back_to_settings, lambda c: c.data == "back_to_settings")
    
    # Обработчики кнопок релевантности
    dp.register_callback_query_handler(handle_relevant_button, lambda c: c.data.startswith('relevant_'))
    dp.register_callback_query_handler(handle_not_relevant_button, lambda c: c.data.startswith('not_relevant_'))
    dp.register_callback_query_handler(handle_spam_button, lambda c: c.data.startswith('spam_'))
    dp.register_callback_query_handler(handle_correct_button, lambda c: c.data.startswith('correct_'))
    
    logger.info("✅ Обработчики кнопок релевантности зарегистрированы")
    
    # Source chat message handler
    dp.register_message_handler(handle_source_chat_message, lambda message: message.chat.id == SOURCE_CHAT_ID)

    # New message handler
    dp.register_message_handler(show_niches_menu_button, lambda message: message.text == "🗂 Выбрать нишу")
    dp.register_callback_query_handler(show_niches_menu_callback, lambda c: c.data == "show_niches_menu")
    
    # Обработчики для выбора стран
    dp.register_message_handler(show_countries_menu, lambda message: message.text == "🌍 Выбрать страну")
    dp.register_callback_query_handler(show_countries_menu_callback, lambda c: c.data == "show_countries_menu")
    dp.register_callback_query_handler(process_country_selection, lambda c: c.data.startswith('country_'))
    dp.register_callback_query_handler(process_countries_done, lambda c: c.data == "countries_done")
    
    # Обработчики для реферальной программы
    dp.register_message_handler(show_referral_program, lambda message: message.text == "🎁 Реферальная программа")

@dp.message_handler(lambda message: message.text == "⚙️ Настройки")
async def show_settings(message: Message):
        await message.answer(
        "⚙️ Настройки мониторинга:\n\n"
        "• 🗂 Мои ниши - управление подписками на ниши\n"
        "• 🔔 Частота уведомлений - настройка частоты получения сообщений\n\n"
        "Выберите, что хотите настроить:",
        reply_markup=get_settings_menu()
    )

@dp.callback_query_handler(lambda c: c.data == "settings_niches")
async def settings_niches(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    selected_niches = await db.get_user_niches(user_id)
    
    if selected_niches:
        text = "🗂 Ваши текущие подписки на ниши:\n\n"
        for niche in selected_niches:
            text += f"• {niche}\n"
        text += "\nНажмите кнопку ниже, чтобы изменить подписки"
    else:
        text = "❌ У вас нет активных подписок на ниши.\nНажмите кнопку ниже, чтобы выбрать ниши"
    
    await callback_query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗂 Выбрать ниши", callback_data="back_to_niches")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_settings")]
        ])
    )

@dp.callback_query_handler(lambda c: c.data == "back_to_niches")
async def back_to_niches(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    
    # Создаем текст с описанием
    intro_text = "🗂 Выберите ниши для мониторинга:\n\n"
    intro_text += "📋 Что вы будете получать:\n"
    intro_text += "• Актуальные предложения в выбранных нишах\n"
    intro_text += "• Уведомления о новых услугах и предложениях\n"
    intro_text += "• Возможность быть в курсе рынка\n\n"
    intro_text += "✅ - уже выбранные ниши\n"
    intro_text += "Нажмите на нишу, чтобы выбрать/отменить выбор\n"
    intro_text += "Нажмите 'Готово', чтобы сохранить изменения\n\n"
    intro_text += "💡 Совет: Выберите несколько ниш для максимального охвата!"
    
    await callback_query.message.edit_text(
        intro_text,
        reply_markup=await get_niches_keyboard(user_id, db)
    )

@dp.message_handler(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    try:
        db = message.bot.get("db")
        if not db:
            logger.error("❌ База данных не инициализирована")
            await message.answer(
                "❌ Ошибка инициализации бота. Пожалуйста, попробуйте позже или обратитесь к администратору."
            )
            return
        
        user = await db.get_user(message.from_user.id)
        if not user:
            # Создаём строку в базе с пустым списком категорий
            try:
                await db.add_subscriber(message.from_user.id, [])
                logger.info(f"✅ Новый пользователь {message.from_user.id} зарегистрирован")
            except Exception as e:
                logger.error(f"❌ Ошибка при создании пользователя {message.from_user.id}: {e}")
                await message.answer(
                    "❌ Ошибка при регистрации. Пожалуйста, попробуйте еще раз или обратитесь к администратору."
                )
                return
            
            await message.answer(
                "👋 *Привет! Я Lead_Hunterbot*\n\n"
                "Я помогу вам получать актуальные предложения и запросы из Telegram-чатов по интересующим вас нишам.\n\n"
                "📋 *КАК НАЧАТЬ РАБОТУ:*\n\n"
                "1️⃣ *ШАГ 1: Выберите ниши* 🗂\n"
                "   👉 Нажмите кнопку *🗂 Выбрать нишу* в меню ниже\n"
                "   👉 Выберите интересующие вас ниши (например: Фотограф, Видеограф, Недвижимость и т.д.)\n"
                "   👉 Нажмите кнопку *✅ Готово* для сохранения\n\n"
                "2️⃣ *ШАГ 2: (Опционально) Фильтрация по странам* 🌍\n"
                "   👉 Если хотите получать уведомления только из определенных стран:\n"
                "      • Нажмите кнопку *🌍 Выбрать страну*\n"
                "      • Выберите нужные страны (Бали, Таиланд, Вьетнам, Дубай и др.)\n"
                "      • Нажмите *✅ Готово*\n"
                "   👉 Если не выберете страны - будете получать уведомления из *всех* стран\n\n"
                "✅ *ГОТОВО!* После этого вы начнете получать уведомления о новых сообщениях в выбранных нишах.\n\n"
                "💡 *ВАЖНО:*\n"
                "• Без выбора ниш вы *не будете* получать уведомления!\n"
                f"• На триале можно выбрать до *{TRIAL_MAX_NICHES} ниш*\n"
                f"• *{TRIAL_DAYS}-дневный триал* начнётся после выбора ниш и «✅ Готово»\n\n"
                "❓ Если возникнут вопросы, нажмите кнопку *❓ Помощь* в меню.",
                reply_markup=get_main_menu(),
                parse_mode="Markdown"
            )
            return
        
        # Выбор страны теперь опциональный - убрали проверку
        
        await message.answer(
            "Вы уже зарегистрированы! Используйте меню для навигации.",
            reply_markup=get_main_menu()
        )
    except Exception as e:
        logger.error(f"❌ Критическая ошибка в /start для пользователя {message.from_user.id}: {e}", exc_info=True)
        try:
            await message.answer(
                "❌ Произошла ошибка при запуске бота. Пожалуйста, попробуйте еще раз через несколько секунд.\n\n"
                "Если проблема сохраняется, обратитесь к администратору."
            )
        except:
            pass

@dp.message_handler(lambda message: message.text == "🎯 Выбрать тему")
async def choose_topic(message: Message, state: FSMContext):
    await message.answer(
        "📌 Выберите интересующую вас тему:",
        reply_markup=get_topics_keyboard()
    )
    await state.set_state(RegStates.waiting_for_topic)

@dp.callback_query_handler(lambda c: c.data.startswith('topic_'))
async def process_topic_selection(callback_query: types.CallbackQuery, state: FSMContext):
    db = callback_query.bot.get("db")
    topic = callback_query.data.replace('topic_', '')
    description = get_topic_description(topic)
    
    # Создаем клавиатуру подтверждения
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_{topic}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="back_to_topics")
        ]
    ])
    
    await callback_query.message.edit_text(
        f"📌 Вы выбрали тему: {topic.capitalize()}\n\n"
        f"📝 Описание: {description}\n\n"
        f"Вы будете получать:\n"
        f"• Актуальные новости и обсуждения\n"
        f"• Полезные советы и рекомендации\n"
        f"• Информацию о ценах и трендах\n\n"
        f"Подтвердите выбор:",
        reply_markup=keyboard
    )

@dp.callback_query_handler(lambda c: c.data.startswith('confirm_'))
async def confirm_topic(callback_query: types.CallbackQuery, state: FSMContext):
    db = callback_query.bot.get("db")
    topic = callback_query.data.replace('confirm_', '')
    user_id = callback_query.from_user.id
    username = callback_query.from_user.username or ""
    await db.add_subscriber(user_id, [topic])
    try:
        await send_topic_content(user_id, topic, callback_query.bot)
        await callback_query.message.edit_text(
            f"✅ Регистрация успешно завершена!\n\n"
            f"📌 Тема мониторинга: {topic.capitalize()}\n"
            f"⏳ Триал активирован на 7 дней\n\n"
            f"Я буду отправлять вам актуальную информацию в личные сообщения.\n"
            f"Используйте меню для навигации.",
            reply_markup=None
        )
    except Exception as e:
        await callback_query.message.edit_text(
            f"✅ Регистрация успешно завершена!\n\n"
            f"📌 Тема мониторинга: {topic.capitalize()}\n"
            f"⏳ Триал активирован на 7 дней\n\n"
            f"К сожалению, произошла ошибка при настройке.\n"
            f"Администратор свяжется с вами в ближайшее время.",
            reply_markup=None
        )
        if ADMIN_CHAT_ID:
            await callback_query.bot.send_message(
                ADMIN_CHAT_ID,
                f"❌ Ошибка при настройке для пользователя {user_id}:\n{str(e)}"
            )
    await notify_admin_about_new_user(user_id, username, topic, callback_query.bot)
    await state.clear()

@dp.callback_query_handler(lambda c: c.data == "back_to_topics")
async def back_to_topics(callback_query: types.CallbackQuery):
    await callback_query.message.edit_text(
        "📌 Выберите интересующую вас тему:",
        reply_markup=get_topics_keyboard()
    )

@dp.callback_query_handler(lambda c: c.data == "back_to_main")
async def back_to_main(callback_query: types.CallbackQuery):
    try:
        # Удаляем старое сообщение
        await callback_query.message.delete()
        
        # Отправляем новое сообщение с главным меню
        await callback_query.message.answer(
            "🏠 Главное меню\n\nВыберите действие:",
            reply_markup=get_main_menu()
        )
        await callback_query.answer()
    except Exception as e:
        logger.error(f"Error in back_to_main: {e}")
        # Если не удалось удалить сообщение, просто отправляем новое
        await callback_query.message.answer(
            "🏠 Главное меню\n\nВыберите действие:",
            reply_markup=get_main_menu()
        )
        await callback_query.answer()

@dp.message_handler(lambda message: message.text == "📊 Статус подписки")
async def show_status(message: types.Message):
    db = message.bot.get("db")
    user_niches = await db.get_user_niches(message.from_user.id)
    status_text = "📊 Ваши подписки на ниши:\n"
    if user_niches:
        status_text += "\n".join(f"• {n}" for n in user_niches)
    else:
        status_text += "\n❌ Нет активных подписок. Используйте '🗂 Выбрать нишу'."
    await message.answer(status_text, reply_markup=get_main_menu())

@dp.message_handler(lambda message: message.text == "❓ Помощь")
async def show_help(message: Message):
    help_text = "🤖 *Как пользоваться ботом:*\n\n"
    help_text += "1. 🗂 Выберите ниши для мониторинга\n"
    help_text += "2. ⏳ Получите 7-дневный триал\n"
    help_text += "3. 📨 Получайте актуальную информацию\n"
    help_text += "4. 📊 Следите за статусом подписки\n\n"
    
    help_text += "📋 *Доступные ниши для мониторинга:*\n\n"
    
    # Добавляем описания всех ниш
    for niche in NICHES:
        if niche in NICHE_DESCRIPTIONS:
            description = NICHE_DESCRIPTIONS[niche]
            help_text += f"• *{niche}*: {description}\n\n"
    
    help_text += "💡 *Совет:* Вы можете выбрать несколько ниш одновременно!\n\n"
    help_text += "📞 *Контакты менеджера для связи:*\n\n"
    help_text += "👤 Менеджер: @huansya0\n"
    help_text += "💬 По всем вопросам обращайтесь к менеджеру в Telegram\n\n"
    help_text += "❓ Если у вас возникли вопросы или проблемы, напишите менеджеру - он поможет!"
    
    await message.answer(help_text, parse_mode="Markdown", reply_markup=get_main_menu())

@dp.message_handler(Command("status"))
async def cmd_status(message: Message):
    """Показать статус подписки (alias на существующий обработчик)."""
    try:
        logger.info(f"/status from {message.from_user.id} in chat {message.chat.id}")
        await show_status(message)
    except Exception:
        await message.answer("❌ Не удалось получить статус. Попробуйте позже.")

@dp.message_handler(commands=["menu"])
async def cmd_menu(message: Message):
    """Показать список команд и навигацию."""
    logger.info(f"/menu from {message.from_user.id} in chat {message.chat.id}")
    # Если команда пришла из группы — предлагаем открыть личный чат
    if message.chat.type != 'private':
        try:
            bot_username = message.bot.get("username")
            if not bot_username:
                me = await message.bot.get_me()
                bot_username = me.username
                message.bot["username"] = bot_username
            deep_link = f"https://t.me/{bot_username}?start=menu"
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton("Открыть меню в личке", url=deep_link)]])
            await message.reply("Откройте меню в личных сообщениях с ботом:", reply_markup=keyboard)
            return
        except Exception:
            pass
    menu_text = (
        "📋 Команды:\n\n"
        "• /menu — показать это меню\n"
        "• /niche — выбрать ниши (или /niches)\n"
        "• /status — статус подписки\n"
        "• /subscribe — оформить подписку\n"
        "• /help — помощь\n"
        "• /info — информация о боте\n"
        "• /contact — контакты менеджера\n\n"
        "Также доступны кнопки внизу экрана."
    )
    await message.answer(menu_text, reply_markup=get_main_menu())

@dp.message_handler(commands=["niche", "niches"])
async def cmd_niche(message: Message):
    """Открыть меню выбора ниш (alias на существующее меню)."""
    try:
        logger.info(f"/niche from {message.from_user.id} in chat {message.chat.id}")
        await show_niches_menu_button(message)
    except Exception:
        await message.answer("❌ Не удалось открыть меню ниш. Попробуйте позже.")

async def send_subscription_invoice(telegram_bot: Bot, chat_id: int, user_id: int):
    """Инвойс Telegram Stars (XTR)."""
    await telegram_bot.send_invoice(
        chat_id=chat_id,
        title="Lead Hunter — подписка",
        description=f"Доступ к лидам на {SUBSCRIPTION_DAYS} дней, все ниши без ограничений.",
        payload=f"sub_{user_id}_{SUBSCRIPTION_DAYS}d",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=f"Подписка {SUBSCRIPTION_DAYS} дн.", amount=SUBSCRIPTION_STARS)],
    )


@dp.message_handler(commands=["subscribe", "subsribe", "buy"])
async def cmd_subscribe(message: Message):
    """Оформление подписки: Stars или менеджер."""
    logger.info(f"/subscribe from {message.from_user.id} in chat {message.chat.id}")
    db = message.bot.get("db")
    st = await db.get_subscription_status(message.from_user.id)
    subscription_info = (
        f"💳 Оформление подписки\n\n"
        f"Ваш ID: `{message.from_user.id}`\n\n"
    )
    if st.get("subscription_active"):
        subscription_info += "✅ У вас уже активна платная подписка.\n"
    elif st.get("trial_active"):
        subscription_info += (
            f"⏳ Триал: осталось {st.get('trial_days_left')} дн., "
            f"лидов за триал: {st.get('trial_leads_count', 0)}\n\n"
        )
    subscription_info += (
        f"⚡ Оплата в 1 клик — {SUBSCRIPTION_STARS} ⭐ на {SUBSCRIPTION_DAYS} дн.\n"
        f"Или менеджер @huansya0 (укажите ID).\n"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"⭐ Оплатить {SUBSCRIPTION_STARS} Stars", callback_data="pay_subscribe")],
            [InlineKeyboardButton(text="📋 Меню", callback_data="back_to_main")],
        ]
    )
    await message.answer(subscription_info, parse_mode="Markdown", reply_markup=kb)


@dp.callback_query_handler(lambda c: c.data in ("pay_subscribe", "subscribe"))
async def callback_pay_subscribe(callback_query: types.CallbackQuery):
    await callback_query.answer()
    try:
        await send_subscription_invoice(
            callback_query.bot,
            callback_query.message.chat.id,
            callback_query.from_user.id,
        )
    except Exception as e:
        logger.error(f"Invoice error: {e}")
        await callback_query.message.answer(
            "Не удалось выставить счёт. Напишите @huansya0 или /subscribe позже."
        )


@dp.pre_checkout_query_handler(lambda q: True)
async def process_pre_checkout_query(pre_checkout_query: types.PreCheckoutQuery):
    await pre_checkout_query.bot.answer_pre_checkout_query(
        pre_checkout_query.id, ok=True
    )


@dp.message_handler(content_types=ContentTypes.SUCCESSFUL_PAYMENT)
async def process_successful_payment(message: Message):
    db = message.bot.get("db")
    pay = message.successful_payment
    user_id = message.from_user.id
    days = SUBSCRIPTION_DAYS
    if pay.invoice_payload and "d" in pay.invoice_payload:
        try:
            part = pay.invoice_payload.split("_")[-1]
            days = int(part.replace("d", ""))
        except ValueError:
            pass
    await db.activate_subscription(
        user_id, days=days, payment_ref=pay.telegram_payment_charge_id
    )
    await message.answer(
        f"✅ Оплата принята! Подписка активна на {days} дн.\n"
        "Можете выбрать любое количество ниш в 🗂 Выбрать нишу.",
        reply_markup=get_main_menu(),
    )
    logger.info(f"Stars payment ok user={user_id} charge={pay.telegram_payment_charge_id}")

@dp.message_handler(commands=["help"])
async def cmd_help(message: Message):
    """Помощь (alias на существующий обработчик)."""
    try:
        logger.info(f"/help from {message.from_user.id} in chat {message.chat.id}")
        await show_help(message)
    except Exception:
        await message.answer("🤖 Используйте /menu чтобы увидеть доступные команды.")

@dp.message_handler(commands=["info"])
async def cmd_info(message: Message):
    """Информация о боте/сервисе."""
    logger.info(f"/info from {message.from_user.id} in chat {message.chat.id}")
    info_text = (
        "ℹ️ Информация:\n\n"
        "Бот мониторит чаты и присылает сообщения по выбранным нишам.\n"
        "Настройте ниши через /niche, оформите подписку через /subscribe.\n"
        "Отмечайте релевантность в уведомлениях — это улучшит персональную выдачу."
    )
    await message.answer(info_text, reply_markup=get_main_menu())

@dp.message_handler(commands=["contact"])
async def cmd_contact(message: Message):
    """Контакты менеджера/поддержки."""
    manager_username = "huansya0"
    logger.info(f"/contact from {message.from_user.id} in chat {message.chat.id}")
    contact_text = (
        "📞 Контакты:\n\n"
        f"Менеджер: @{manager_username}\n"
        "Укажите ваш ID (видно в /subscribe) и желаемые ниши."
    )
    await message.answer(contact_text, reply_markup=get_main_menu())

@dp.message_handler(Command("reset"))
async def cmd_reset(message: Message):
    """
    Команда для сброса триала
    """
    db = message.bot.get("db")
    user = await db.get_user(message.from_user.id)
    
    # Если пользователь не зарегистрирован
    if not user:
        await message.answer("Вы не зарегистрированы. Используйте /start для регистрации.")
        return
    
    # Проверяем, является ли пользователь администратором
    is_admin = str(message.from_user.id) == str(ADMIN_CHAT_ID)
    
    # Если это администратор, можно сбросить триал любого пользователя
    if is_admin:
        try:
            # Проверяем, указан ли ID пользователя
            args = message.text.split()
            if len(args) > 1:
                target_user_id = int(args[1])
                # Удаляем пользователя из базы
                await db.delete_user(target_user_id)
                await message.answer(f"✅ Триал для пользователя {target_user_id} сброшен.")
            else:
                # Если ID не указан, сбрасываем свой триал
                await db.delete_user(message.from_user.id)
                await message.answer("✅ Ваш триал сброшен. Используйте /start для новой регистрации.")
        except Exception as e:
            await message.answer(f"❌ Ошибка при сбросе триала: {str(e)}")
    else:
        # Для обычных пользователей проверяем, истек ли триал
        trial_until = datetime.fromisoformat(user[4])
        now = datetime.now()
        
        if now >= trial_until:
            # Если триал истек, позволяем сбросить
            try:
                await db.delete_user(message.from_user.id)
                await message.answer("✅ Ваш триал сброшен. Используйте /start для новой регистрации.")
            except Exception as e:
                await message.answer(f"❌ Ошибка при сбросе триала: {str(e)}")
        else:
            # Если триал еще активен, предлагаем дождаться его окончания
            await message.answer(
                f"Ваш триал еще активен до {trial_until.strftime('%d.%m.%Y %H:%M')}.\n"
                f"Вы сможете сбросить триал после его окончания."
            )

# Admin commands
@dp.message_handler(Command("admin"))
async def cmd_admin(message: Message):
    db = message.bot.get("db")
    if str(message.from_user.id) == str(ADMIN_CHAT_ID):
        users = await db.get_all_users()
        if not users:
            await message.answer("Нет зарегистрированных пользователей.")
            return
        
        text = "📊 Список пользователей:\n\n"
        for user in users:
            user_id, username, niche, registered_at, trial_until, subscription = user
            status = "✅ Подписка" if subscription else "⏳ Триал"
            text += f"ID: {user_id}\nUsername: @{username}\nНиша: {niche}\nСтатус: {status}\n\n"
        
        await message.answer(text)

@dp.callback_query_handler(lambda c: c.data.startswith('write_'))
async def process_admin_write(callback_query: types.CallbackQuery, state: FSMContext):
    if str(callback_query.from_user.id) != str(ADMIN_CHAT_ID):
        return
    
    db = callback_query.bot.get("db")
    user_id = int(callback_query.data.split('_')[1])
    await state.update_data(admin_write_user_id=user_id)
    await state.set_state(AdminStates.waiting_for_user_message)
    await callback_query.message.answer("Введите сообщение для пользователя:")

@dp.message_handler(state=AdminStates.waiting_for_user_message)
async def process_admin_message(message: Message, state: FSMContext):
    if str(message.from_user.id) != str(ADMIN_CHAT_ID):
        return
    
    db = message.bot.get("db")
    data = await state.get_data()
    user_id = data.get('admin_write_user_id')
    
    try:
        await bot.send_message(user_id, f"📨 Сообщение от администратора:\n\n{message.text}")
        await message.answer("✅ Сообщение отправлено пользователю")
    except Exception as e:
        await message.answer(f"❌ Ошибка при отправке сообщения: {str(e)}")
    
    await state.clear()

@dp.message_handler(Command("test"))
async def cmd_test(message: Message):
    """
    Тестовая команда для администратора
    """
    db = message.bot.get("db")
    if str(message.from_user.id) != str(ADMIN_CHAT_ID):
        await message.answer("Эта команда доступна только администратору.")
        return

    try:
        # Получаем всех пользователей
        users = await db.get_all_users()
        if not users:
            await message.answer("В базе нет пользователей.")
            return

        # Формируем список пользователей
        text = "📊 Список пользователей:\n\n"
        for user in users:
            user_id, username, topic, registered_at, trial_until, subscription = user
            status = "✅ Подписка" if subscription else "⏳ Триал"
            text += f"ID: {user_id}\nUsername: @{username}\nТема: {topic}\nСтатус: {status}\n\n"

        # Добавляем инструкции
        text += "\nКоманды для тестирования:\n"
        text += "/reset [ID] - сбросить триал пользователя\n"
        text += "/start - начать регистрацию заново\n"
        text += "/status - проверить статус"

        await message.answer(text)
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

@dp.message_handler(Command("clear"))
async def cmd_clear(message: Message):
    """
    Команда для очистки базы данных (только для администратора)
    """
    db = message.bot.get("db")
    if str(message.from_user.id) != str(ADMIN_CHAT_ID):
        await message.answer("Эта команда доступна только администратору.")
        return

    try:
        await db.clear_users()
        await message.answer("✅ База данных очищена. Все пользователи удалены.")
    except Exception as e:
        await message.answer(f"❌ Ошибка при очистке базы: {str(e)}")

@dp.message_handler(Command("clean_duplicates"))
async def cmd_clean_duplicates(message: Message):
    """Очищает дубликаты ниш у всех пользователей"""
    if str(message.from_user.id) != str(ADMIN_CHAT_ID):
        await message.answer("Эта команда доступна только администратору.")
        return

    try:
        db = message.bot.get("db")
        users = await db.get_all_users()
        cleaned_count = 0
        
        for user in users:
            user_id = user['user_id']
            cleaned_categories = await db.clean_duplicate_niches(user_id)
            if cleaned_categories:
                cleaned_count += 1
        
        await message.answer(f"✅ Очищены дубликаты у {cleaned_count} пользователей")
    except Exception as e:
        await message.answer(f"❌ Ошибка при очистке дубликатов: {str(e)}")

@dp.message_handler(lambda message: message.chat.id == SOURCE_CHAT_ID)
async def handle_source_chat_message(message: Message):
    # Проверяем, разрешено ли сообщение
    if not is_message_allowed(message.text, message.from_user.username):
        return
    
    # Безопасное получение username (у некоторых его нет)
    sender_username = None
    if message.from_user and hasattr(message.from_user, 'username'):
        sender_username = message.from_user.username
        
    # Обрабатываем сообщение через монитор
    await monitor.handle_source_message(
        message_text=message.text,
        sender_username=sender_username
    )

@dp.message_handler(lambda message: message.text == "⏸ Пауза")
async def toggle_pause(message: Message):
    db = message.bot.get("db")
    user = await db.get_user(message.from_user.id)
    if not user:
        await message.answer(
            "Вы не зарегистрированы. Используйте кнопку '🎯 Выбрать тему' для регистрации.",
            reply_markup=get_main_menu()
        )
        return
    
    # TODO: Получить текущий статус паузы из базы данных
    is_paused = False  # Временная заглушка
    
    if is_paused:
        # TODO: Снять паузу
        await message.answer(
            "✅ Мониторинг возобновлен!",
            reply_markup=get_main_menu()
        )
    else:
        # TODO: Поставить на паузу
        await message.answer(
            "⏸ Мониторинг приостановлен.\n"
            "Нажмите кнопку '⏸ Пауза' снова для возобновления.",
            reply_markup=get_main_menu()
        )

@dp.callback_query_handler(lambda c: c.data == "back_to_settings")
async def back_to_settings(callback_query: types.CallbackQuery):
    await callback_query.message.edit_text(
        "⚙️ Настройки мониторинга:\n\n"
        "Выберите, что хотите настроить:",
        reply_markup=get_settings_menu()
    )

@dp.message_handler(lambda message: message.text == "🔍 Выбрать ключевые слова")
async def select_keywords(message: types.Message):
    await message.answer(
        "Выберите категорию ключевых слов:",
        reply_markup=get_keyword_categories_keyboard()
    )

@dp.callback_query_handler(lambda c: c.data.startswith('category_'))
async def process_category_selection(callback_query: types.CallbackQuery):
    category = callback_query.data.split('_')[1]
    await callback_query.message.edit_text(
        f"Выберите ключевые слова из категории {category}:",
        reply_markup=get_keywords_keyboard(category)
    )

@dp.callback_query_handler(lambda c: c.data.startswith('keyword_'))
async def process_keyword_selection(callback_query: types.CallbackQuery):
    db = callback_query.bot.get("db")
    _, category, keyword = callback_query.data.split('_')
    user_id = callback_query.from_user.id
    await db.add_user_keyword(user_id, category, keyword)
    user_keywords = await db.get_user_keywords(user_id)
    
    # Формируем сообщение с текущими выбранными ключевыми словами
    keywords_text = "Ваши выбранные ключевые слова:\n\n"
    for cat, words in user_keywords.items():
        keywords_text += f"📌 {cat}:\n"
        for word in words:
            keywords_text += f"• {word}\n"
        keywords_text += "\n"
    
    await callback_query.message.edit_text(
        f"{keywords_text}\nВыберите еще ключевые слова или нажмите 'Готово'",
        reply_markup=get_keyword_categories_keyboard()
    )

@dp.callback_query_handler(lambda c: c.data == "keywords_done")
async def process_keywords_done(callback_query: types.CallbackQuery):
    db = callback_query.bot.get("db")
    user_id = callback_query.from_user.id
    user_keywords = await db.get_user_keywords(user_id)
    
    if not user_keywords:
        await callback_query.message.edit_text(
            "Вы не выбрали ни одного ключевого слова. Пожалуйста, выберите хотя бы одно.",
            reply_markup=get_keyword_categories_keyboard()
        )
        return
    
    # Формируем итоговое сообщение
    keywords_text = "✅ Вы выбрали следующие ключевые слова:\n\n"
    for category, words in user_keywords.items():
        keywords_text += f"📌 {category}:\n"
        for word in words:
            keywords_text += f"• {word}\n"
        keywords_text += "\n"
    
    keywords_text += "Теперь вы будете получать уведомления при появлении сообщений с этими ключевыми словами."
    
    await callback_query.message.edit_text(
        keywords_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Вернуться в меню", callback_data="back_to_menu")]
        ])
    )

@dp.callback_query_handler(lambda c: c.data == "back_to_categories")
async def back_to_categories(callback_query: types.CallbackQuery):
    await callback_query.message.edit_text(
        "Выберите категорию ключевых слов:",
        reply_markup=get_keyword_categories_keyboard()
    )

@dp.callback_query_handler(lambda c: c.data == "back_to_menu")
async def back_to_menu(callback_query: types.CallbackQuery):
    await callback_query.message.answer(
        "Главное меню:",
        reply_markup=get_main_menu()
    )
    await callback_query.message.delete()

@dp.message_handler(Command("test_messages"))
async def cmd_test_messages(message: Message):
    """Отправляет тестовые сообщения пользователю"""
    global monitor
    if not monitor:
        await message.answer("❌ Ошибка: монитор не инициализирован")
        return

    user = await db.get_user(message.from_user.id)
    if not user:
        await message.answer("Вы не зарегистрированы. Используйте /start для регистрации.")
        return

    # Тестовые сообщения по разным темам
    test_messages = [
        "🏖️ Новая вилла в Чангу! 3 спальни, бассейн, океанский вид. Аренда от $2000/месяц.",
        "🚗 Аренда скутера на Бали - от 100к рупий в день. Доставка в любую точку острова.",
        "📸 Фотосессия на закате в Убуде. Профессиональный фотограф, 2 часа съемки.",
        "🎉 Вечеринка в Семиньяке в эту субботу! DJ, открытый бар, пляжный закат.",
        "🏠 Продается вилла в Джимбаране. 4 спальни, сад, бассейн. $450,000.",
        "🚐 Трансфер из аэропорта в Убуд - 300к рупий. Комфортный минивэн, русскоговорящий водитель.",
        "📝 Помощь в продлении визы на Бали. Все документы, сопровождение в иммиграции.",
        "🌴 Экскурсия на вулкан Батур. Встреча рассвета, завтрак, горячие источники.",
        "🏡 Аренда апартаментов в Семиньяке. 2 спальни, 5 минут до пляжа. $800/месяц.",
        "🎭 Свадебная церемония на пляже. Организация, декор, фотограф, видео."
    ]

    await message.answer("📨 Отправляю тестовые сообщения...")
    
    for msg in test_messages:
        # Имитируем обработку сообщения через монитор
        await monitor.handle_source_message(
            message_text=msg,
            sender_username=None  # Тестовые сообщения без отправителя
        )
        await asyncio.sleep(2)  # Небольшая задержка между сообщениями
    
    await message.answer("✅ Тестовые сообщения отправлены!")

@dp.message_handler(commands=["niches"])
async def show_niches_menu(message: types.Message):
    db = message.bot.get("db")
    user_id = message.from_user.id
    
    # Выбор страны теперь опциональный - убрали проверку
    
    await message.answer(
        "Выберите ниши для мониторинга:\n"
        "✅ - уже выбранные ниши\n"
        "Нажмите на нишу, чтобы выбрать/отменить выбор\n"
        "Нажмите 'Готово', когда закончите выбор",
        reply_markup=await get_niches_keyboard(user_id, db)
    )

@dp.callback_query_handler(lambda c: c.data == "show_niches_menu")
async def show_niches_menu_callback(callback_query: types.CallbackQuery):
    """Обработчик для кнопки выбора ниш из меню"""
    # КРИТИЧНО: Отвечаем на callback сразу, чтобы предотвратить зависание интерфейса
    await callback_query.answer(cache_time=0)
    
    db = callback_query.bot.get("db")
    user_id = callback_query.from_user.id
    
    # Проверяем, является ли пользователь администратором
    is_admin = str(user_id) == str(ADMIN_CHAT_ID) or callback_query.from_user.username == ADMIN_USERNAME
    
    paid = await db.has_active_subscription(user_id)
    st = await db.get_subscription_status(user_id)
    
    intro_text = "🗂 Выберите ниши для мониторинга:\n\n"
    intro_text += "📋 Что вы будете получать:\n"
    intro_text += "• Актуальные предложения в выбранных нишах\n"
    intro_text += "• Уведомления о новых услугах и предложениях\n"
    intro_text += "• Возможность быть в курсе рынка\n\n"
    
    if not paid and not is_admin:
        intro_text += (
            f"⏳ Без подписки — до {TRIAL_MAX_NICHES} ниш на триале ({TRIAL_DAYS} дн. после «Готово»).\n"
        )
        if st.get("trial_not_started"):
            intro_text += "Триал ещё не начат — выберите ниши и нажмите «✅ Готово».\n"
        intro_text += "Оформите подписку для безлимита.\n\n"
    elif is_admin:
        intro_text += "👑 Вы администратор - можете выбрать любое количество ниш.\n\n"
    
    intro_text += "✅ - уже выбранные ниши\n"
    intro_text += "Нажмите на нишу, чтобы выбрать/отменить выбор\n"
    intro_text += "Нажмите 'Готово', чтобы сохранить изменения"
    
    if paid or is_admin:
        intro_text += "\n\n💡 Совет: Выберите несколько ниш для максимального охвата!"
    
    try:
        await callback_query.message.edit_text(
            intro_text,
            reply_markup=await get_niches_keyboard(user_id, db)
        )
    except Exception as e:
        logger.error(f"Error in show_niches_menu_callback: {e}")
        # Если не удалось отредактировать сообщение, отправляем новое
        await callback_query.message.answer(
            intro_text,
            reply_markup=await get_niches_keyboard(user_id, db)
        )

@dp.message_handler(lambda message: message.text == "🗂 Выбрать нишу")
async def show_niches_menu_button(message: types.Message):
    db = message.bot.get("db")
    user_id = message.from_user.id
    
    # Выбор страны теперь опциональный - убрали проверку
    
    # Проверяем, является ли пользователь администратором
    is_admin = str(user_id) == str(ADMIN_CHAT_ID) or message.from_user.username == ADMIN_USERNAME
    
    paid = await db.has_active_subscription(user_id)
    st = await db.get_subscription_status(user_id)
    
    intro_text = "🗂 Выберите ниши для мониторинга:\n\n"
    intro_text += "📋 Что вы будете получать:\n"
    intro_text += "• Актуальные предложения в выбранных нишах\n"
    intro_text += "• Уведомления о новых услугах и предложениях\n"
    intro_text += "• Возможность быть в курсе рынка\n\n"
    
    if not paid and not is_admin:
        intro_text += (
            f"⏳ Без подписки — до {TRIAL_MAX_NICHES} ниш на триале ({TRIAL_DAYS} дн. после «Готово»).\n"
        )
        if st.get("trial_not_started"):
            intro_text += "Триал ещё не начат — выберите ниши и нажмите «✅ Готово».\n"
        intro_text += "Оформите подписку для безлимита.\n\n"
    elif is_admin:
        intro_text += "👑 Вы администратор - можете выбрать любое количество ниш.\n\n"
    
    intro_text += "✅ - уже выбранные ниши\n"
    intro_text += "Нажмите на нишу, чтобы выбрать/отменить выбор\n"
    intro_text += "Нажмите 'Готово', чтобы сохранить изменения"
    
    if paid or is_admin:
        intro_text += "\n\n💡 Совет: Выберите несколько ниш для максимального охвата!"
    
    await message.answer(
        intro_text,
        reply_markup=await get_niches_keyboard(message.from_user.id, db)
    )

@dp.callback_query_handler(lambda c: c.data.startswith('niche_'))
async def process_niche_selection(callback_query: types.CallbackQuery):
    try:
        user_id = callback_query.from_user.id
        niche_index = int(callback_query.data.replace('niche_', '')) - 1
        niche = NICHES[niche_index]
        
        db = callback_query.bot.get("db")
        
        # Проверяем, является ли пользователь администратором
        is_admin = str(user_id) == str(ADMIN_CHAT_ID) or callback_query.from_user.username == ADMIN_USERNAME
        
        paid = await db.has_active_subscription(user_id)
        
        # Инициализируем временное хранение для пользователя, если его нет
        if user_id not in temp_niche_selections:
            # Если временного хранения нет, копируем сохраненные ниши из базы
            saved_niches = await db.get_user_niches(user_id)
            temp_niche_selections[user_id] = saved_niches.copy()
        
        # Проверяем, есть ли ниша во временном хранении
        temp_niches = temp_niche_selections[user_id]
        temp_niches_normalized = [n.lower() for n in temp_niches]
        
        if niche.lower() in temp_niches_normalized:
            # Удаляем нишу из временного хранения
            temp_niche_selections[user_id] = [n for n in temp_niches if n.lower() != niche.lower()]
            logger.info(f"🗑️ Временно удалена ниша '{niche}' у пользователя {user_id}")
        else:
            if not paid and len(temp_niches) >= TRIAL_MAX_NICHES and not is_admin:
                await callback_query.answer(
                    f"⏳ На триале — до {TRIAL_MAX_NICHES} ниш. Оформите подписку (/subscribe) для безлимита.",
                    show_alert=True,
                )
                return
            
            # Добавляем нишу во временное хранение
            temp_niche_selections[user_id].append(niche)
            logger.info(f"➕ Временно добавлена ниша '{niche}' пользователю {user_id} (paid={paid})")
        
        # Получаем обновленную клавиатуру
        db = callback_query.bot.get("db")
        new_keyboard = await get_niches_keyboard(user_id, db)
        
        # Обновляем сообщение с новой клавиатурой
        try:
            await callback_query.message.edit_text(
                "Выберите ниши для мониторинга:\n"
                "✅ - уже выбранные ниши\n"
                "Нажмите на нишу, чтобы выбрать/отменить выбор\n"
                "Нажмите 'Готово', чтобы сохранить изменения",
                reply_markup=new_keyboard
            )
        except Exception as edit_error:
            # Если сообщение не изменилось, просто отвечаем
            logger.warning(f"Message not modified: {edit_error}")
            await callback_query.answer("✅ Настройки обновлены")
            return
            
        await callback_query.answer()
    except Exception as e:
        logger.error(f"Error in process_niche_selection: {e}")
        await callback_query.answer("Произошла ошибка при выборе ниши", show_alert=True)

@dp.callback_query_handler(lambda c: c.data == "niches_done")
async def process_niches_done(callback_query: types.CallbackQuery):
    try:
        db = callback_query.bot.get("db")
        user_id = callback_query.from_user.id
        
        # Получаем временно выбранные ниши
        temp_niches = temp_niche_selections.get(user_id, [])
        logger.info(f"🔍 Временные ниши для пользователя {user_id}: {temp_niches}")
        
        # Сохраняем временные ниши в базу данных
        logger.info(f"💾 Сохраняем ниши в базу данных для пользователя {user_id}: {temp_niches}")
        trial_started = False
        if temp_niches:
            before = await db.get_subscription_status(user_id)
            await db.update_user_niches(user_id, temp_niches)
            after = await db.get_subscription_status(user_id)
            trial_started = before.get("trial_not_started") and after.get("trial_active")
        else:
            await db.update_user_niches(user_id, temp_niches)
        
        saved_niches = await db.get_user_niches(user_id)
        logger.info(f"✅ Проверка сохраненных ниш для пользователя {user_id}: {saved_niches}")
        
        if temp_niches:
            logger.info(f"💾 Сохранены ниши для пользователя {user_id}: {temp_niches}")
            text = "✅ Ваши ниши успешно сохранены:\n\n" + "\n".join(f"• {n}" for n in temp_niches)
            if trial_started:
                text += (
                    f"\n\n🎁 Триал на {TRIAL_DAYS} дн. начался! "
                    f"Лиды пойдут в выбранные ниши."
                )
        else:
            logger.info(f"🗑️ Очищены ниши у пользователя {user_id}")
            text = "❌ Вы не выбрали ни одной ниши. Используйте кнопку '🗂 Выбрать нишу' для выбора ниш."
        
        # Очищаем временное хранение
        if user_id in temp_niche_selections:
            del temp_niche_selections[user_id]
            logger.info(f"🧹 Очищено временное хранение для пользователя {user_id}")
        
        await callback_query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 В главное меню", callback_data="back_to_main")]
            ])
        )
        await callback_query.answer("✅ Ниши сохранены!")
    except Exception as e:
        logger.error(f"Error in process_niches_done: {e}")
        await callback_query.answer("Произошла ошибка при сохранении ниш", show_alert=True)

# ==================== ФУНКЦИИ ДЛЯ ВЫБОРА СТРАН ====================

@dp.callback_query_handler(lambda c: c.data == "show_countries_menu")
async def show_countries_menu_callback(callback_query: types.CallbackQuery):
    """Обработчик для кнопки выбора страны из меню ниш"""
    # КРИТИЧНО: Отвечаем на callback сразу, чтобы предотвратить зависание интерфейса
    await callback_query.answer(cache_time=0)
    
    db = callback_query.bot.get("db")
    
    # Создаем текст с инструкцией (опциональный выбор)
    intro_text = "🌍 Фильтрация по странам (опционально):\n\n"
    intro_text += "📋 Как это работает:\n"
    intro_text += "• Если вы не выберете страны - вы будете получать уведомления из всех стран\n"
    intro_text += "• Если выберете страны - вы будете получать уведомления только из выбранных стран\n"
    intro_text += "• Вы можете в любой момент изменить выбор или снять все страны\n\n"
    intro_text += "✅ - уже выбранные страны\n"
    intro_text += "Нажмите на страну, чтобы выбрать/отменить выбор\n"
    intro_text += "Нажмите 'Готово', чтобы сохранить изменения\n\n"
    intro_text += "💡 Совет: Используйте фильтр по странам, чтобы фокусироваться на интересующих вас регионах!"
    
    try:
        await callback_query.message.edit_text(
            intro_text,
            reply_markup=await get_countries_keyboard(callback_query.from_user.id, db)
        )
    except Exception as e:
        logger.error(f"Error in show_countries_menu_callback: {e}")
        # Если не удалось отредактировать сообщение, отправляем новое
        await callback_query.message.answer(
            intro_text,
            reply_markup=await get_countries_keyboard(callback_query.from_user.id, db)
        )

@dp.message_handler(lambda message: message.text == "🌍 Выбрать страну")
async def show_countries_menu(message: types.Message):
    db = message.bot.get("db")
    
    # Создаем текст с инструкцией (опциональный выбор)
    intro_text = "🌍 Фильтрация по странам (опционально):\n\n"
    intro_text += "📋 Как это работает:\n"
    intro_text += "• Если вы не выберете страны - вы будете получать уведомления из всех стран\n"
    intro_text += "• Если выберете страны - вы будете получать уведомления только из выбранных стран\n"
    intro_text += "• Вы можете в любой момент изменить выбор или снять все страны\n\n"
    intro_text += "✅ - уже выбранные страны\n"
    intro_text += "Нажмите на страну, чтобы выбрать/отменить выбор\n"
    intro_text += "Нажмите 'Готово', чтобы сохранить изменения\n\n"
    intro_text += "💡 Совет: Используйте фильтр по странам, чтобы фокусироваться на интересующих вас регионах!"
    
    await message.answer(
        intro_text,
        reply_markup=await get_countries_keyboard(message.from_user.id, db)
    )

@dp.callback_query_handler(lambda c: c.data.startswith('country_'))
async def process_country_selection(callback_query: types.CallbackQuery):
    # КРИТИЧНО: Отвечаем на callback сразу, чтобы предотвратить зависание интерфейса
    await callback_query.answer(cache_time=0)
    
    try:
        user_id = callback_query.from_user.id
        country_code = callback_query.data.replace('country_', '')
        
        db = callback_query.bot.get("db")
        
        # Получаем текущие страны пользователя
        try:
            current_countries = await db.get_user_countries(user_id)
        except Exception:
            current_countries = []
        
        # Проверяем, есть ли страна в текущих
        if country_code in current_countries:
            # Удаляем страну
            current_countries.remove(country_code)
            logger.info(f"🗑️ Удалена страна '{country_code}' у пользователя {user_id}")
        else:
            # Добавляем страну
            current_countries.append(country_code)
            logger.info(f"➕ Добавлена страна '{country_code}' пользователю {user_id}")
        
        # Сохраняем изменения в базу данных
        try:
            await db.update_user_countries(user_id, current_countries)
        except Exception as e:
            logger.warning(f"⚠️ Метод update_user_countries не реализован: {e}")
        
        # Получаем обновленную клавиатуру
        new_keyboard = await get_countries_keyboard(user_id, db)
        
        # Обновляем сообщение с новой клавиатурой
        try:
            await callback_query.message.edit_text(
                "🌍 Фильтрация по странам (опционально):\n\n"
                "📋 Как это работает:\n"
                "• Если вы не выберете страны - вы будете получать уведомления из всех стран\n"
                "• Если выберете страны - вы будете получать уведомления только из выбранных стран\n"
                "• Вы можете в любой момент изменить выбор или снять все страны\n\n"
                "✅ - уже выбранные страны\n"
                "Нажмите на страну, чтобы выбрать/отменить выбор\n"
                "Нажмите 'Готово', чтобы сохранить изменения\n\n"
                "💡 Совет: Используйте фильтр по странам, чтобы фокусироваться на интересующих вас регионах!",
                reply_markup=new_keyboard
            )
        except Exception as edit_error:
            # Если сообщение не изменилось, логируем предупреждение
            logger.warning(f"Message not modified: {edit_error}")
        
    except Exception as e:
        logger.error(f"Error in process_country_selection: {e}")
        # Не пытаемся ответить на callback повторно - уже ответили в начале функции

@dp.callback_query_handler(lambda c: c.data == "countries_done")
async def process_countries_done(callback_query: types.CallbackQuery):
    # КРИТИЧНО: Отвечаем на callback сразу, чтобы предотвратить зависание интерфейса
    await callback_query.answer("✅ Страны сохранены!")
    
    try:
        db = callback_query.bot.get("db")
        user_id = callback_query.from_user.id
        
        # Получаем выбранные страны
        try:
            selected_countries = await db.get_user_countries(user_id)
        except Exception:
            selected_countries = []
        
        # Формируем названия стран для отображения
        country_names = {
            "bali": "🇮🇩 Бали",
            "thailand": "🇹🇭 Таиланд",
            "turkey": "🇹🇷 Турция",
            "georgia": "🇬🇪 Грузия"
        }
        
        selected_names = [country_names.get(code, code) for code in selected_countries]
        
        if selected_names:
            message_text = (
                f"✅ Фильтрация по странам настроена!\n\n"
                f"Выбранные страны: {', '.join(selected_names)}\n"
                f"Теперь вы будете получать уведомления только из выбранных стран.\n\n"
                f"💡 Чтобы получать уведомления из всех стран, просто снимите все страны."
            )
        else:
            message_text = (
                "✅ Фильтрация по странам отключена!\n\n"
                "Теперь вы будете получать уведомления из всех стран.\n\n"
                "💡 Чтобы настроить фильтрацию, выберите интересующие вас страны."
            )
        
        await callback_query.message.edit_text(
            message_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 В главное меню", callback_data="back_to_main")]
            ])
        )
        
    except Exception as e:
        logger.error(f"Error in process_countries_done: {e}")
        # Не пытаемся ответить на callback повторно - уже ответили в начале функции

# ==================== ФУНКЦИИ ДЛЯ РЕФЕРАЛЬНОЙ ПРОГРАММЫ ====================

@dp.message_handler(lambda message: message.text == "🎁 Реферальная программа")
async def show_referral_program(message: Message):
    """Показывает реферальную программу с готовым шаблоном"""
    db = message.bot.get("db")
    user_id = message.from_user.id
    
    try:
        # Получаем баланс и реферальный код
        balance_info = await db.get_user_balance(user_id)
        referral_code = balance_info.get('referral_code', '')
        total_referrals = balance_info.get('total_referrals', 0)
    except Exception:
        # Если метод не реализован, используем заглушки
        referral_code = f"REF{user_id}"
        total_referrals = 0
    
    # Создаём ссылку
    bot_info = await message.bot.me
    bot_username = bot_info.username
    referral_link = f"https://t.me/{bot_username}?start={referral_code}"
    
    # Формируем красивое сообщение
    referral_text = f"""🎁 <b>+7 дней премиум-подписки за каждого друга!</b>

👥 <b>Уже приглашено:</b> {total_referrals}
Продолжайте делиться этим полезным ботом и пользуйтесь премиумом бесплатно! 🚀

Чтобы вам было удобнее, мы подготовили готовый шаблон — просто отправьте его друзьям:
━━━━━━━━━━━━━━━━

Привет! 👋 Советую попробовать сервис, который находит клиентов 24/7 в 1000+ чатах твоего города! 🎯

По моей реферальной ссылке ты получишь 6 дней Премиум 🔷 подписки бесплатно! Попробуй! 🔥

👉 {referral_link}

━━━━━━━━━━━━━━━━

<b>💎 КАК ЭТО РАБОТАЕТ:</b>

1️⃣ Отправь шаблон другу
2️⃣ Друг регистрируется по ссылке
3️⃣ Друг оплачивает первую подписку
4️⃣ Вы оба получаете по <b>$5</b> на баланс! 🎉

<b>🔗 Ваша реферальная ссылка:</b>
<code>{referral_link}</code>

<b>Или используй код:</b> <code>{referral_code}</code>

<i>💡 Чем больше друзей приведёшь, тем больше заработаешь!</i>"""
    
    await message.answer(referral_text, parse_mode='HTML', disable_web_page_preview=True, reply_markup=get_main_menu())

def detect_niches_from_message(message_text):
    """
    Определяет список ниш, к которым относится сообщение, по ключевым словам из MONITORING_CONFIG.
    Возвращает список названий ниш.
    """
    niches_found = set()
    text = message_text.lower()
    for niche, keywords in MONITORING_CONFIG.get('niches', {}).items():
        for kw in keywords:
            if kw.lower() in text:
                niches_found.add(niche)
    return list(niches_found)

def _create_message_hash(message_text: str, sender_id: int = 0) -> str:
    """
    Создает уникальный хеш сообщения на основе текста и отправителя
    (используется для проверки релевантности)
    """
    import hashlib
    # Нормализуем текст: убираем лишние пробелы, приводим к нижнему регистру
    normalized_text = ' '.join(message_text.lower().split())
    # Создаем хеш из нормализованного текста и ID отправителя
    hash_input = f"{normalized_text}:{sender_id}"
    return hashlib.md5(hash_input.encode('utf-8')).hexdigest()

async def check_new_messages(db, monitor):
    """Проверка новых сообщений и отправка уведомлений по нишам"""
    while True:
        try:
            messages = await db.get_unprocessed_messages()
            for message in messages:
                message_id = message.get('id') if isinstance(message, dict) else message[0]
                message_text = message.get('message_text') if isinstance(message, dict) else message[4]
                # Определяем ниши по тексту сообщения
                niches = detect_niches_from_message(message_text)
                for niche in niches:
                    subscribers = await db.get_subscribers_for_niche(niche)
                    for subscriber_id in subscribers:
                        # Создаем хеш сообщения для проверки релевантности (sender_id неизвестен, используем 0)
                        message_hash = _create_message_hash(message_text, 0)
                        
                        # Проверяем, не был ли этот message_id помечен как нерелевантный для этого пользователя
                        if is_message_marked_as_not_relevant(message_hash, str(subscriber_id)):
                            logger.info(f"🚫 Пропуск отправки сообщения {message_hash} пользователю {subscriber_id} (помечено как нерелевантное)")
                            continue
                        
                        try:
                            notification = (
                                f"🔔 Новое сообщение по нише {niche}:\n\n"
                                f"📝 Сообщение:\n{message_text}\n\n"
                                f"🔗 Ссылка: {message.get('message_link') if isinstance(message, dict) else message[5]}"
                            )
                            await monitor.bot.send_message(subscriber_id, notification)
                        except Exception as e:
                            logging.error(f"Ошибка отправки сообщения подписчику {subscriber_id}: {e}")
                    await db.mark_message_as_processed(message_id)
            await asyncio.sleep(10)
        except Exception as e:
            logging.error(f"Ошибка в check_new_messages: {e}")
            await asyncio.sleep(10)

async def on_startup(dp: Dispatcher):
    """Инициализация при запуске бота"""
    try:
        bot = dp["bot"]
        db = dp["db"]
        monitor = dp["monitor"]
        await db.connect()
        logger.info("Database connected successfully")
        await monitor.initialize()
        logger.info("Monitor initialized successfully")
        asyncio.create_task(check_new_messages(db, monitor))
        logger.info("Background tasks started")
        
        # Устанавливаем команды меню
        from aiogram.types import BotCommand
        commands = [
            BotCommand(command="menu", description="📋 Меню команд"),
            BotCommand(command="niche", description="🗂 Выбрать ниши"),
            BotCommand(command="status", description="📊 Статус подписки"),
            BotCommand(command="subscribe", description="💳 Оформить подписку"),
            BotCommand(command="help", description="❓ Помощь"),
            BotCommand(command="info", description="ℹ️ Информация о боте"),
            BotCommand(command="contact", description="📞 Контакты менеджера"),
        ]
        await bot.set_my_commands(commands)
        logger.info("Bot commands menu set successfully")
    except Exception as e:
        logger.error(f"Error during startup: {e}")
        raise

async def on_shutdown(dp: Dispatcher):
    """Очистка при выключении бота"""
    try:
        # Получаем экземпляры из диспетчера
        db = dp["db"]
        monitor = dp["monitor"]
        
        # Закрываем соединение с базой данных
        await db.close()
        logger.info("Database connection closed")
        
        # Очищаем ресурсы монитора
        await monitor.cleanup()
        logger.info("Monitor resources cleaned up")
        
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

@dp.message_handler(Command("monitor_status"))
async def cmd_monitor_status(message: Message):
    """Проверяет статус монитора"""
    if str(message.from_user.id) != str(ADMIN_CHAT_ID):
        await message.answer("Эта команда доступна только администратору.")
        return

    try:
        monitor = message.bot.get("monitor")
        status = await monitor.get_status()
        
        text = "📊 Статус монитора:\n\n"
        text += f"👥 Активных подписчиков: {status['active_subscribers']}\n"
        text += f"📌 Отслеживаемых тем: {len(status['monitored_topics'])}\n"
        text += f"🔍 Активных паттернов: {status['active_patterns']}\n"
        text += f"💾 Размер кэша сообщений: {status['message_cache_size']}\n"
        text += f"✅ Монитор инициализирован: {'Да' if status['is_initialized'] else 'Нет'}\n"
        
        await message.answer(text)
    except Exception as e:
        await message.answer(f"❌ Ошибка при получении статуса монитора: {str(e)}")

@dp.message_handler(Command("ai_stats"))
async def cmd_ai_stats(message: Message):
    """Показывает статистику AI классификатора"""
    try:
        if not monitor.ai_classifier:
            await message.answer("❌ AI классификатор не инициализирован")
            return
        
        cache_stats = monitor.ai_classifier.get_cache_stats()
        learning_stats = monitor.ai_classifier.get_learning_stats()
        
        stats_text = (
            "🤖 **Статистика AI классификатора**\n\n"
            f"📊 **Кэш:**\n"
            f"• Размер кэша: {cache_stats['cache_size']}\n"
            f"• Время кэширования: {cache_stats['cache_duration']} сек\n\n"
            f"📚 **Обучение:**\n"
            f"• Всего примеров: {learning_stats.get('total_examples', 0)}\n"
            f"• Исправлений: {learning_stats.get('corrections_count', 0)}\n"
            f"• Точность: {learning_stats.get('accuracy_rate', 0):.1f}%\n"
            f"• Всего классификаций: {learning_stats.get('total_classifications', 0)}\n"
            f"• Правильных: {learning_stats.get('correct_classifications', 0)}\n\n"
            "💡 Используйте /ai_correct для исправления ошибок"
        )
        
        await message.answer(stats_text, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения статистики AI: {e}")
        await message.answer("❌ Ошибка получения статистики")

@dp.message_handler(Command("ai_correct"))
async def cmd_ai_correct(message: Message, state: FSMContext):
    """Начинает процесс исправления классификации"""
    try:
        # Проверяем права администратора
        if str(message.from_user.id) != ADMIN_CHAT_ID and message.from_user.username != ADMIN_USERNAME:
            await message.answer("❌ У вас нет прав для этой команды")
            return
        
        await message.answer(
            "🔧 **Исправление классификации AI**\n\n"
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
        
        await state.set_state("waiting_for_correction")
        
    except Exception as e:
        logger.error(f"❌ Ошибка начала исправления: {e}")
        await message.answer("❌ Ошибка начала исправления")

@dp.message_handler(state="waiting_for_correction")
async def process_ai_correction(message: Message, state: FSMContext):
    """Обрабатывает исправление классификации"""
    try:
        if message.text == "/cancel":
            await state.finish()
            await message.answer("❌ Исправление отменено")
            return
        
        # Парсим сообщение
        parts = message.text.split(" | ")
        if len(parts) != 2:
            await message.answer(
                "❌ Неверный формат. Используйте:\n"
                "`текст_сообщения | исправленная_классификация`"
            )
            return
        
        original_text, correction = parts
        
        # Парсим исправление
        correction_parts = correction.split(":")
        if len(correction_parts) < 2:
            await message.answer(
                "❌ Неверный формат исправления. Используйте:\n"
                "`ТИП:НИША:СРОЧНОСТЬ:БЮДЖЕТ`"
            )
            return
        
        message_type = correction_parts[0]
        niche = correction_parts[1]
        urgency = correction_parts[2] if len(correction_parts) > 2 else "не срочно"
        budget = correction_parts[3] if len(correction_parts) > 3 else ""
        
        # Валидируем данные
        valid_types = ["ПОИСК", "ПРЕДЛОЖЕНИЕ", "ОБЩЕНИЕ", "СПАМ"]
        valid_niches = [
            "Фотограф", "Видеограф", "Недвижимость (Спрос)", "Недвижимость (Предложение)", "Маникюр", "Волосы", 
            "Аренда авто", "Реснички", "Брови", "Макияж", "Косметология", 
            "Продажа недвижимости", "Аренда байков", "Обмен валют", "Кальяны", 
            "Аренда Playstation", "Медиа-студия", "Туризм", "Транспорт"
        ]
        
        if message_type not in valid_types:
            await message.answer(f"❌ Неверный тип: {message_type}. Допустимые: {', '.join(valid_types)}")
            return
        
        if niche not in valid_niches:
            await message.answer(f"❌ Неверная ниша: {niche}. Допустимые: {', '.join(valid_niches)}")
            return
        
        # Создаем исправленную классификацию
        corrected_result = {
            "message_type": message_type,
            "is_spam": message_type == "СПАМ",
            "niches": [niche] if niche else [],
            "context": f"Исправлено администратором: {message_type} - {niche}",
            "urgency": urgency,
            "budget": budget,
            "confidence": 95,
            "reason": f"Исправлено администратором: {message_type} - {niche}"
        }
        
        # Сохраняем исправление
        if monitor.ai_classifier:
            monitor.ai_classifier.correct_classification(original_text, corrected_result)
            
            await message.answer(
                f"✅ **Исправление сохранено!**\n\n"
                f"📝 **Текст:** {original_text[:100]}...\n"
                f"🔧 **Исправление:**\n"
                f"• Тип: {message_type}\n"
                f"• Ниша: {niche}\n"
                f"• Срочность: {urgency}\n"
                f"• Бюджет: {budget or 'не указан'}\n\n"
                f"🤖 AI будет учитывать это исправление в будущих классификациях"
            )
        else:
            await message.answer("❌ AI классификатор не инициализирован")
        
        await state.finish()
        
    except Exception as e:
        logger.error(f"❌ Ошибка обработки исправления: {e}")
        await message.answer("❌ Ошибка обработки исправления")
        await state.finish()

@dp.message_handler(Command("ai_export"))
async def cmd_ai_export(message: Message):
    """Экспортирует данные обучения AI"""
    try:
        # Проверяем права администратора
        if str(message.from_user.id) != ADMIN_CHAT_ID and message.from_user.username != ADMIN_USERNAME:
            await message.answer("❌ У вас нет прав для этой команды")
            return
        
        if not monitor.ai_classifier:
            await message.answer("❌ AI классификатор не инициализирован")
            return
        
        # Экспортируем данные
        filename = f"ai_learning_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        monitor.ai_classifier.export_learning_data(filename)
        
        # Отправляем файл
        with open(filename, 'rb') as f:
            await message.answer_document(
                types.InputFile(f, filename),
                caption="📤 **Экспорт данных обучения AI**\n\n"
                "Файл содержит все примеры классификации и исправления"
            )
        
        # Удаляем временный файл
        os.remove(filename)
        
    except Exception as e:
        logger.error(f"❌ Ошибка экспорта данных AI: {e}")
        await message.answer("❌ Ошибка экспорта данных")

@dp.message_handler(Command("send_reminders"))
async def cmd_send_reminders(message: Message):
    """Отправляет напоминания пользователям о необходимости выбрать страну и ниши"""
    logger.info(f"🔔 Команда /send_reminders получена от пользователя {message.from_user.id} (username: {message.from_user.username})")
    logger.info(f"🔍 ADMIN_CHAT_ID: {ADMIN_CHAT_ID}, ADMIN_USERNAME: {ADMIN_USERNAME}")
    logger.info(f"🔍 Сравнение: {str(message.from_user.id)} == {str(ADMIN_CHAT_ID)} = {str(message.from_user.id) == str(ADMIN_CHAT_ID)}")
    
    if str(message.from_user.id) != str(ADMIN_CHAT_ID) and message.from_user.username != ADMIN_USERNAME:
        logger.warning(f"❌ Доступ запрещен для пользователя {message.from_user.id}")
        await message.answer("Эта команда доступна только администратору.")
        return
    
    logger.info(f"✅ Администратор подтвержден, начинаю отправку напоминаний...")
    await message.answer("🔄 Начинаю отправку напоминаний...")
    
    try:
        db = message.bot.get("db")
        users = await db.get_all_users()
        
        now = datetime.now(timezone.utc)
        stats = {
            'total': 0,
            'sent': 0,
            'errors': 0,
            'no_niches': 0,
            'trial_no_setup': 0,
            'no_setup': 0
        }
        
        for user in users:
            stats['total'] += 1
            user_id = user['user_id']
            if user.get("bot_blocked"):
                continue
            categories = json.loads(user.get('categories', '[]')) if user.get('categories') else []
            countries = json.loads(user.get('countries', '[]')) if user.get('countries') else []
            subscription_active = user.get('subscription_active', False)
            trial_until_str = user.get('trial_until')
            
            # Парсим trial_until
            trial_until = None
            if trial_until_str:
                try:
                    if isinstance(trial_until_str, str):
                        trial_until = datetime.fromisoformat(trial_until_str.replace('Z', '+00:00'))
                    else:
                        trial_until = trial_until_str
                except:
                    pass
            
            # Определяем статус
            is_trial = not subscription_active and trial_until and trial_until > now
            has_niches = len(categories) > 0
            has_countries = len(countries) > 0
            
            # Определяем, кому нужно отправить напоминание
            needs_reminder = False
            reminder_type = None
            
            # Убрали проверку на отсутствие стран - выбор страны теперь опциональный
            if not has_niches and has_countries:
                # Есть страны, но нет ниш
                needs_reminder = True
                reminder_type = 'no_niches'
                stats['no_niches'] += 1
            elif not has_niches and not has_countries:
                # Нет ни стран, ни ниш - отправляем инструкцию всем
                needs_reminder = True
                if is_trial:
                    reminder_type = 'trial_no_setup'
                    stats['trial_no_setup'] += 1
                else:
                    reminder_type = 'no_setup'
                    stats['no_setup'] = stats.get('no_setup', 0) + 1
            
            if needs_reminder:
                try:
                    if reminder_type == 'no_niches':
                        message_text = (
                            "⚠️ **Важное напоминание!**\n\n"
                            "Вы выбрали страну, но не выбрали ниши.\n\n"
                            "📋 **Инструкция:**\n"
                            "1️⃣ Нажмите на кнопку **🗂 Выбрать нишу**\n"
                            "2️⃣ Выберите интересующие вас ниши\n"
                            "3️⃣ Нажмите **✅ Готово**\n\n"
                            "💡 **Важно:** Без выбора ниш вы не будете получать уведомления!\n\n"
                            f"🎁 На триале — до {TRIAL_MAX_NICHES} ниш ({TRIAL_DAYS} дн. после «Готово»)."
                        )
                    elif reminder_type == 'trial_no_setup':
                        message_text = (
                            "👋 **Добро пожаловать в Lead_Hunterbot!**\n\n"
                            "Вы зарегистрированы, но еще не настроили бота.\n\n"
                            "📋 **Инструкция по настройке:**\n\n"
                            "1️⃣ **Выберите ниши** 🗂\n"
                            "   Нажмите кнопку **🗂 Выбрать нишу**\n"
                            "   Выберите интересующие вас ниши\n"
                            "   Нажмите **✅ Готово**\n\n"
                            "2️⃣ **Фильтрация по странам (опционально)** 🌍\n"
                            "   Нажмите кнопку **🌍 Выбрать страну**\n"
                            "   Если не выберете страны - будете получать уведомления из всех стран\n"
                            "   Если выберете страны - будете получать только из выбранных стран\n\n"
                            "💡 **Важно:** Без выбора ниш вы не будете получать уведомления!\n\n"
                            f"⏳ **{TRIAL_DAYS}-дневный триал** начнётся после выбора ниш.\n"
                            f"🎁 На триале — до {TRIAL_MAX_NICHES} ниш. Подписка — без лимита (/subscribe)."
                        )
                    else:  # no_setup
                        message_text = (
                            "👋 **Добро пожаловать в Lead_Hunterbot!**\n\n"
                            "Вы зарегистрированы, но еще не настроили бота.\n\n"
                            "📋 **Инструкция по настройке:**\n\n"
                            "1️⃣ **Выберите ниши** 🗂\n"
                            "   Нажмите кнопку **🗂 Выбрать нишу**\n"
                            "   Выберите интересующие вас ниши\n"
                            "   Нажмите **✅ Готово**\n\n"
                            "2️⃣ **Фильтрация по странам (опционально)** 🌍\n"
                            "   Нажмите кнопку **🌍 Выбрать страну**\n"
                            "   Если не выберете страны - будете получать уведомления из всех стран\n"
                            "   Если выберете страны - будете получать только из выбранных стран\n\n"
                            "💡 **Важно:** Без выбора ниш вы не будете получать уведомления!\n\n"
                            "💎 Оформите подписку для выбора нескольких ниш и получения всех уведомлений."
                        )
                    
                    # Формируем клавиатуру в зависимости от типа напоминания
                    keyboard_buttons = []
                    if reminder_type in ['trial_no_setup', 'no_setup']:
                        keyboard_buttons.append([InlineKeyboardButton(text="🌍 Выбрать страну", callback_data="show_countries_menu")])
                    if reminder_type in ['no_niches', 'trial_no_setup', 'no_setup']:
                        keyboard_buttons.append([InlineKeyboardButton(text="🗂 Выбрать нишу", callback_data="show_niches_menu")])
                    
                    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
                    
                    await message.bot.send_message(
                        user_id,
                        message_text,
                        parse_mode="Markdown",
                        reply_markup=keyboard
                    )
                    
                    stats['sent'] += 1
                    logger.info(f"✅ Напоминание отправлено пользователю {user_id} (тип: {reminder_type})")
                    
                    # Небольшая задержка, чтобы не перегрузить API
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    stats['errors'] += 1
                    logger.error(f"❌ Ошибка отправки напоминания пользователю {user_id}: {e}")
        
        # Отправляем статистику администратору
        stats_text = (
            "📊 **СТАТИСТИКА ОТПРАВКИ НАПОМИНАНИЙ**\n\n"
            f"👥 Всего пользователей: {stats['total']}\n"
            f"✅ Отправлено напоминаний: {stats['sent']}\n"
            f"❌ Ошибок: {stats['errors']}\n\n"
            f"📋 **Детализация:**\n"
            f"   • Нет ниш (есть страны): {stats['no_niches']}\n"
            f"   • Триал без настройки: {stats['trial_no_setup']}\n"
            f"   • Без настройки (не триал): {stats.get('no_setup', 0)}"
        )
        
        await message.answer(stats_text, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при отправке напоминаний: {e}")
        await message.answer(f"❌ Ошибка при отправке напоминаний: {str(e)}")

@dp.message_handler(Command("ai_clear"))
async def cmd_ai_clear(message: Message):
    """Очищает кэш AI классификатора"""
    try:
        # Проверяем права администратора
        if str(message.from_user.id) != ADMIN_CHAT_ID and message.from_user.username != ADMIN_USERNAME:
            await message.answer("❌ У вас нет прав для этой команды")
            return
        
        if not monitor.ai_classifier:
            await message.answer("❌ AI классификатор не инициализирован")
            return
        
        # Очищаем кэш
        monitor.ai_classifier.clear_cache()
        
        await message.answer("🧹 **Кэш AI классификатора очищен!**\n\n"
                           "Следующие запросы будут обрабатываться заново")
        
    except Exception as e:
        logger.error(f"❌ Ошибка очистки кэша AI: {e}")
        await message.answer("❌ Ошибка очистки кэша")

# Обработчики для кнопок релевантности
async def handle_relevant_button(callback_query: types.CallbackQuery):
    """Обрабатывает нажатие кнопки 'Релевантно'"""
    logger.info(f"🔍 Получен callback для кнопки 'Релевантно': {callback_query.data}")
    try:
        # Парсим данные из callback_data
        parts = callback_query.data.split('_')
        if len(parts) >= 3:
            message_id = parts[1]
            user_id = parts[2]
            
            # Проверяем, что пользователь нажал на свою кнопку
            if str(callback_query.from_user.id) == user_id:
                # Сохраняем положительную оценку
                await save_relevance_feedback(message_id, user_id, True, is_spam=False)
                
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

async def handle_not_relevant_button(callback_query: types.CallbackQuery):
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
                await save_relevance_feedback(message_id, user_id, False, is_spam=False)
                
                # Проверяем, не заблокировано ли сообщение глобально
                is_blocked = is_message_globally_blocked(message_id)
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

async def handle_spam_button(callback_query: types.CallbackQuery):
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
                await save_relevance_feedback(message_id, user_id, False, is_spam=True)
                
                # Обновляем сообщение с retry логикой
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        await callback_query.message.edit_reply_markup(
                            InlineKeyboardMarkup(inline_keyboard=[
                                [InlineKeyboardButton("🚫 Отмечено как спам (заблокировано)", callback_data="confirmed_spam")]
                            ])
                        )
                        break
                    except Exception as e:
                        if attempt < max_retries - 1:
                            await asyncio.sleep(1)  # Ждем перед повтором
                            logger.warning(f"⚠️ Повторная попытка обновить кнопку (попытка {attempt + 1}/{max_retries})")
                        else:
                            logger.error(f"❌ Не удалось обновить кнопку после {max_retries} попыток: {e}")
                
                # Отправляем ответ с retry логикой
                try:
                    await callback_query.answer("🚫 Сообщение отмечено как спам и заблокировано глобально")
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось отправить ответ на callback: {e}")
                
                logger.warning(f"🚫 Пользователь {user_id} отметил сообщение {message_id} как СПАМ (глобальная блокировка)")
            else:
                try:
                    await callback_query.answer("❌ Это не ваше сообщение")
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось отправить ответ на callback: {e}")
                
    except Exception as e:
        logger.error(f"❌ Ошибка обработки кнопки 'Отметить как спам': {e}")
        try:
            await callback_query.answer("❌ Ошибка обработки")
        except:
            pass  # Игнорируем ошибку, если не удалось отправить ответ

async def handle_correct_button(callback_query: types.CallbackQuery):
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
                
                # Устанавливаем состояние ожидания исправления
                from aiogram.dispatcher import FSMContext
                state = FSMContext(storage, callback_query.from_user.id, callback_query.from_user.id)
                await state.set_state("waiting_for_correction")
                
                await callback_query.answer("📝 Ожидаю ваше исправление...")
                logger.info(f"🔧 Пользователь {user_id} запросил исправление классификации для сообщения {message_id}")
            else:
                await callback_query.answer("❌ Это не ваше сообщение")
                
    except Exception as e:
        logger.error(f"❌ Ошибка обработки кнопки 'Исправить': {e}")
        await callback_query.answer("❌ Ошибка обработки")

def is_message_marked_as_not_relevant(message_id: str, user_id: str) -> bool:
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

def is_message_globally_blocked(message_id: str, spam_threshold: int = 2) -> bool:
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

async def save_relevance_feedback(message_id: str, user_id: str, is_relevant: bool, is_spam: bool = False):
    """Сохраняет обратную связь о релевантности"""
    try:
        from datetime import datetime
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

def main():
    """Основная функция запуска бота"""
    try:
        # Инициализация компонентов
        storage = MemoryStorage()
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        dp = Dispatcher(bot, storage=storage)
        db = Database(DB_DSN)
        monitor = MessageMonitor(bot, db)

        # Сохраняем экземпляры в контексте бота для доступа из хендлеров
        bot["db"] = db
        bot["monitor"] = monitor

        # Сохраняем экземпляры в диспетчере
        dp["bot"] = bot
        dp["monitor"] = monitor
        dp["db"] = db
        
        # Регистрируем хендлеры
        register_handlers(dp, monitor, bot)
        
        # Запускаем бота
        from aiogram import executor
        executor.start_polling(
            dp,
            skip_updates=True,
            on_startup=on_startup,
            on_shutdown=on_shutdown
        )
    except Exception as e:
        logger.error(f"Error in main: {e}")
        raise

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise 