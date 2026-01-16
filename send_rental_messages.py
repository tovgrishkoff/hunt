#!/usr/bin/env python3
"""
Скрипт для рассылки сообщений о сдаче в аренду апартаментов
для новых аккаунтов
"""
import asyncio
import json
import logging
import random
from pathlib import Path
from datetime import datetime
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    FloodWaitError,
    RPCError,
    ChatWriteForbiddenError,
    UserBannedInChannelError
)

# Новые аккаунты для работы
NEW_ACCOUNTS = [
    "promotion_oleg_petrov",
    "promotion_anna_truncher",
    "promotion_artur_biggest",
    "promotion_andrey_virgin"
]

# Сообщения о сдаче в аренду
RENTAL_MESSAGES = [
    """🏠 Сдаю апартаменты в аренду на Бали

📍 Расположение: Убуд / Чангу / Семиньяк
💰 Цена: от $500/месяц
📅 Доступно: долгосрочная аренда

✨ Удобства:
• Wi-Fi
• Кондиционер
• Полностью меблировано
• Кухня
• Близко к пляжу

📱 Пишите в личные сообщения для деталей""",

    """🏡 Апартаменты в аренду на Бали

Ищу ответственных жильцов для долгосрочной аренды.

📍 Районы: Убуд, Чангу, Семиньяк
💰 Стоимость: от $500/месяц
📅 Срок: от 3 месяцев

Включено:
✅ Wi-Fi
✅ Кондиционер
✅ Вся мебель
✅ Кухня со всем необходимым
✅ Близко к пляжу и кафе

Интересует? Напишите в ЛС!""",

    """🏘️ Сдаю апартаменты на Бали

Долгосрочная аренда от $500/месяц

📍 Убуд / Чангу / Семиньяк
📅 От 3 месяцев

В апартаментах:
• Wi-Fi
• Кондиционер
• Полная мебель
• Кухня
• Рядом пляж

Пишите в личные сообщения для просмотра и деталей!""",

    """🏠 Апартаменты в аренду

Ищу жильцов для долгосрочной аренды на Бали.

📍 Районы: Убуд, Чангу, Семиньяк
💰 От $500/месяц
📅 Минимум 3 месяца

Удобства:
✅ Интернет
✅ Кондиционер
✅ Вся мебель
✅ Кухня
✅ Близко к пляжу

Заинтересованы? Напишите мне!"""
]

# Задержки
DELAY_BETWEEN_POSTS = (60, 120)  # 1-2 минуты между постами
DELAY_BETWEEN_ACCOUNTS = (300, 600)  # 5-10 минут между аккаунтами

def setup_logging():
    """Настройка логирования"""
    logs_dir = Path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "rental_messages.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

def parse_proxy(proxy_config):
    """Парсинг прокси"""
    if not proxy_config:
        return None
    
    if isinstance(proxy_config, str):
        try:
            from urllib.parse import urlparse
            parsed = urlparse(proxy_config)
            proxy_type = parsed.scheme.lower()
            host = parsed.hostname
            port = parsed.port or (8080 if proxy_type in ['http', 'https'] else 1080)
            username = parsed.username
            password = parsed.password
            
            if not host or not port:
                return None
            
            if proxy_type in ['http', 'https']:
                proxy_dict = {
                    'proxy_type': 'http',
                    'addr': host,
                    'port': port
                }
                if username:
                    proxy_dict['username'] = username
                if password:
                    proxy_dict['password'] = password
                return proxy_dict
        except Exception:
            return None
    
    return None

async def send_message_to_group(client, account_name, group_username, message, logger):
    """Отправка сообщения в группу"""
    try:
        entity = await client.get_entity(group_username)
        await client.send_message(entity, message)
        logger.info(f"  ✅ Отправлено в @{group_username}")
        return True
    except ChatWriteForbiddenError:
        logger.warning(f"  ⚠️ Нет прав на отправку в @{group_username}")
        return False
    except UserBannedInChannelError:
        logger.warning(f"  ⚠️ Забанен в @{group_username}")
        return False
    except FloodWaitError as e:
        logger.warning(f"  ⚠️ FloodWait: {e.seconds} секунд")
        await asyncio.sleep(e.seconds)
        return False
    except RPCError as e:
        logger.error(f"  ❌ Ошибка: {e}")
        return False
    except Exception as e:
        logger.error(f"  ❌ Неожиданная ошибка: {e}")
        return False

async def send_messages_for_account(account, groups, logger):
    """Отправка сообщений для одного аккаунта"""
    account_name = account['session_name']
    logger.info(f"\n{'='*80}")
    logger.info(f"📱 АККАУНТ: {account_name} ({account.get('nickname', 'N/A')})")
    logger.info(f"{'='*80}")
    
    # Парсим прокси
    proxy = None
    if account.get('proxy'):
        proxy = parse_proxy(account['proxy'])
    
    # Создаем клиент
    string_session = account.get('string_session', '').strip()
    if not string_session or string_session in ['', 'null', 'TO_BE_CREATED']:
        logger.error(f"❌ Нет валидной string_session для {account_name}")
        return
    
    client = TelegramClient(
        StringSession(string_session),
        int(account['api_id']),
        account['api_hash'],
        proxy=proxy
    )
    
    try:
        await client.connect()
        logger.info(f"✅ Подключен {account_name}")
        
        if not await client.is_user_authorized():
            logger.error(f"❌ {account_name} не авторизован")
            return
        
        me = await client.get_me()
        username = getattr(me, 'username', 'No username')
        logger.info(f"👤 Авторизован как: @{username}")
        
        # Выбираем случайное сообщение
        message = random.choice(RENTAL_MESSAGES)
        logger.info(f"📝 Сообщение выбрано (длина: {len(message)} символов)")
        
        # Отправляем в группы
        sent_count = 0
        failed_count = 0
        
        for i, group_link in enumerate(groups, 1):
            # Извлекаем username из ссылки
            group_username = group_link.replace('https://t.me/', '').replace('http://t.me/', '').strip('/')
            if group_username.startswith('+'):
                # Это invite link, пропускаем
                logger.warning(f"  ⚠️ Пропускаю invite link: {group_link}")
                continue
            
            logger.info(f"\n[{i}/{len(groups)}] @{group_username}")
            
            success = await send_message_to_group(client, account_name, group_username, message, logger)
            
            if success:
                sent_count += 1
            else:
                failed_count += 1
            
            # Задержка между постами
            if i < len(groups):
                delay = random.randint(*DELAY_BETWEEN_POSTS)
                logger.info(f"⏸️ Пауза {delay} секунд перед следующим постом...")
                await asyncio.sleep(delay)
        
        logger.info(f"\n{'='*80}")
        logger.info(f"📊 ИТОГИ для {account_name}:")
        logger.info(f"  ✅ Отправлено: {sent_count}")
        logger.info(f"  ❌ Не удалось: {failed_count}")
        logger.info(f"{'='*80}")
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка для {account_name}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.disconnect()
        logger.info(f"🔌 Отключен {account_name}")

async def main():
    """Основная функция"""
    logger = setup_logging()
    
    logger.info("\n" + "="*80)
    logger.info("📨 СКРИПТ РАССЫЛКИ СООБЩЕНИЙ О СДАЧЕ В АРЕНДУ")
    logger.info("="*80)
    
    # Список групп (те же, что в join_groups_for_new_accounts.py)
    NEW_GROUPS = [
        "https://t.me/events_travels_group",
        "https://t.me/russians_in_bali",
        "https://t.me/rent_in_bali",
        "https://t.me/uslugi_na_bali",
        "https://t.me/balichatik",
        "https://t.me/bali_chatus",
        "https://t.me/bali_ua/",
        "https://t.me/balichat_it",
        "https://t.me/balichange",
        "https://t.me/balidating",
        "https://t.me/balimc",
        "https://t.me/bali_visa",
        "https://t.me/balihealth",
        "https://t.me/buildbali",
        "https://t.me/balibc",
        "https://t.me/investbali",
        "https://t.me/BaliStartups",
        "https://t.me/balisp",
        "https://t.me/seobali",
        "https://t.me/balibeauty",
        "https://t.me/baliyoga",
        "http://t.me/balichatarenda",
        "http://t.me/Belkin_Bali_Rent",
        "https://t.me/balichat",
        "http://t.me/balirental",
        "http://t.me/balichatroommates",
        "https://t.me/arenda_bali_1",
        "https://t.me/VillaUbud",
        "http://t.me/balichatsurfing",
        "http://t.me/Arenda_Bali_Villy",
        "https://t.me/balichat_bukit",
        "https://t.me/bali_dom",
        "http://t.me/balichat_photovideo",
        "https://t.me/arendabali",
        "http://t.me/bali_arenda1",
        "https://t.me/cangguchat",
        "https://t.me/balichatservices",
        "https://t.me/blizkie_bali_avito",
        "http://t.me/BaliHouseRent",
        "https://t.me/BaliLoveProp",
        "https://t.me/baliwomens",
        "https://t.me/balichildren",
        "https://t.me/balirentapart",
        "https://t.me/pure_bali",
        "https://t.me/SIBTravel_Bali",
        "https://t.me/balyt",
        "https://t.me/balilv",
        "https://t.me/bali_party",
        "https://t.me/obmen_g_eneg",
        "https://t.me/balifruits",
        "https://t.me/onerealestatebali",
        "https://t.me/jobsbali",
        "https://t.me/balichat_ladymarket",
        "https://t.me/sosedprivetbali",
        "https://t.me/baligames",
        "https://t.me/balisurfer",
        "https://t.me/eventsbali",
        "https://t.me/baliauto",
        "https://t.me/balibike",
        "https://t.me/glavdubai",
        "https://t.me/balisale",
        "https://t.me/baliservice",
        "https://t.me/baliontheway",
        "https://t.me/baliexchanges",
        "https://t.me/balipackage",
        "http://t.me/Belkin_Bali_Service",
        "http://t.me/balioby",
        "https://t.me/toursbali",
        "https://t.me/balifood",
        "http://t.me/lombok_chat",
        "http://t.me/canggu_bali_2016",
        "http://t.me/balichat_woman",
        "http://t.me/gdansk_gdynia_sopot_chat",
        "http://t.me/balibutler",
        "http://t.me/baliof",
        "http://t.me/balichatnash",
        "http://t.me/voprosBali",
        "http://t.me/rabota_bali",
        "https://t.me/balibara",
        "https://t.me/+DXaf8gqY4TA4Yjg6",
        "https://t.me/mafiaonbali",
        "https://t.me/bali_invest_group",
        "https://t.me/baly_ads",
        "https://t.me/surfing_chatik",
        "https://t.me/BikeBalifornia",
        "https://t.me/GiliBali",
        "https://t.me/ChanguBalifornia",
        "https://t.me/bali_kuta",
        "https://t.me/Belkin_Bali_Chat",
        "https://t.me/BaliJob",
        "https://t.me/ArendaBalifornia",
        "https://t.me/ubud_2",
        "https://t.me/balichatgilinow",
        "https://t.me/balichatfit",
        "https://t.me/balichat_amedlovina",
        "https://t.me/balichatparties",
        "https://t.me/bali_russia_choogl",
        "https://t.me/balimotocats",
        "https://t.me/BaliLives",
        "https://t.me/afisha_bali2",
        "https://t.me/balichat_canggu",
        "https://t.me/balichatmoto",
        "https://t.me/networking_bali",
        "https://t.me/surfculture",
        "https://t.me/Bali_Top_Chat",
        "https://t.me/buysellbali",
        "https://t.me/affiliate_marketing_bali",
        "https://t.me/real_estate_balii",
        "https://t.me/villasvalley",
        "https://t.me/balivillla",
        "https://t.me/rentallbali",
        "https://t.me/Villa_Bali_Arenda_1",
        "https://t.me/BALI_BIG_HOUSE",
        "https://t.me/villa_11_20_mln",
        "https://t.me/balilovebike",
        "https://t.me/balibikes",
        "https://t.me/rentbalibike",
        "https://t.me/rent4ubali",
        "https://t.me/WorkExBali",
        "https://t.me/sellersmedia_bali",
        "https://t.me/BaliUrbanNet",
        "https://t.me/bali_money_obmen1",
        "https://t.me/obmen_balii",
        "https://t.me/AsiaObmen",
        "https://t.me/baliiobmen",
        "https://t.me/balimoney",
        "https://t.me/bali_insurance",
        "https://t.me/bali_flights",
        "https://t.me/bali_longstay",
        "https://t.me/bali_startups_founders",
        "https://t.me/bali_digitalnomads",
        "https://t.me/bali_vloggers",
        "https://t.me/bali_job_board",
        "https://t.me/bali_real_estate_news",
        "https://t.me/PhuketParadis",
        "https://t.me/vmestenaphukete",
        "https://t.me/forum_phuket",
        "https://t.me/Phuket_ads_Thailand",
        "https://t.me/samui_live",
        "https://t.me/samui_chat_znakomstva",
        "https://t.me/Samui_tourist"
    ]
    
    logger.info(f"📋 Групп для рассылки: {len(NEW_GROUPS)}")
    logger.info(f"👤 Аккаунтов: {len(NEW_ACCOUNTS)}")
    logger.info("="*80)
    
    # Загружаем аккаунты
    try:
        with open('accounts_config.json', 'r', encoding='utf-8') as f:
            all_accounts = json.load(f)
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки accounts_config.json: {e}")
        return
    
    # Фильтруем только новые аккаунты
    accounts_to_use = [
        acc for acc in all_accounts 
        if acc['session_name'] in NEW_ACCOUNTS
    ]
    
    if not accounts_to_use:
        logger.error("❌ Не найдено новых аккаунтов в конфиге")
        return
    
    logger.info(f"✅ Найдено {len(accounts_to_use)} новых аккаунтов")
    
    # Отправляем сообщения для каждого аккаунта
    for i, account in enumerate(accounts_to_use, 1):
        await send_messages_for_account(account, NEW_GROUPS, logger)
        
        # Задержка между аккаунтами
        if i < len(accounts_to_use):
            delay = random.randint(*DELAY_BETWEEN_ACCOUNTS)
            logger.info(f"\n⏸️ Пауза {delay // 60} минут перед следующим аккаунтом...")
            await asyncio.sleep(delay)
    
    logger.info("\n" + "="*80)
    logger.info("✅ ВСЕ СООБЩЕНИЯ ОТПРАВЛЕНЫ!")
    logger.info("="*80)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️ Прервано пользователем")
    except Exception as e:
        print(f"\n\n❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()


