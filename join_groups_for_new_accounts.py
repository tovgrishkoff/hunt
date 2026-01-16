#!/usr/bin/env python3
"""
Скрипт для вступления новых аккаунтов в группы
- Вступает в группы с задержками
- Обрабатывает капчу (пересылает админу)
- Дает аккаунтам отлежаться после вступления
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
    UserAlreadyParticipantError,
    InviteHashExpiredError,
    UsernameNotOccupiedError,
    ChatAdminRequiredError,
    RPCError
)
from telethon.tl.functions.messages import CheckChatInviteRequest, ImportChatInviteRequest
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.types import ChatInvite

# ID админа для пересылки капчи
ADMIN_ID = 210147380

# Новые аккаунты для работы
NEW_ACCOUNTS = [
    "promotion_oleg_petrov",
    "promotion_anna_truncher",
    "promotion_artur_biggest",
    "promotion_andrey_virgin"
]

# Новые группы для вступления
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

# Настройки задержек
DELAY_BETWEEN_JOINS = (30, 60)  # Случайная задержка между вступлениями (секунды)
DELAY_BETWEEN_ACCOUNTS = (300, 600)  # Задержка между аккаунтами (5-10 минут)
REST_AFTER_JOINING = (3600, 7200)  # Отлежка после вступления (1-2 часа)

# Файл для сохранения прогресса
PROGRESS_FILE = Path("logs/join_groups_progress.json")

def setup_logging():
    """Настройка логирования"""
    logs_dir = Path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "join_groups.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

def load_progress():
    """Загрузка сохраненного прогресса"""
    if PROGRESS_FILE.exists():
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.warning(f"⚠️ Не удалось загрузить прогресс: {e}")
    return {}

def save_progress(progress):
    """Сохранение прогресса"""
    try:
        with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
            json.dump(progress, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"❌ Не удалось сохранить прогресс: {e}")

def update_progress(progress, account_name, group_link, status):
    """Обновление прогресса для конкретной группы"""
    if account_name not in progress:
        progress[account_name] = {
            'joined': [],
            'failed': [],
            'last_group': None
        }
    
    if status == 'joined':
        if group_link not in progress[account_name]['joined']:
            progress[account_name]['joined'].append(group_link)
        # Удаляем из failed, если был там
        if group_link in progress[account_name]['failed']:
            progress[account_name]['failed'].remove(group_link)
    elif status == 'failed':
        if group_link not in progress[account_name]['failed']:
            progress[account_name]['failed'].append(group_link)
    
    progress[account_name]['last_group'] = group_link
    save_progress(progress)

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
        except Exception as e:
            return None
    
    return None

async def send_captcha_to_admin(client, account_name, group_link, captcha_message):
    """Пересылка капчи админу через Telethon (без Bot API)"""
    logger = logging.getLogger(__name__)
    try:
        message = (
            f"🔐 КАПЧА для {account_name}\n"
            f"Группа: {group_link}\n"
            f"\n{captcha_message}"
        )
        await client.send_message(ADMIN_ID, message)
        logger.info(f"✅ Капча отправлена админу (ADMIN_ID={ADMIN_ID})")
        return True
    except Exception as e:
        logger.error(f"❌ Не удалось отправить капчу админу: {e}")
        return False

async def join_group(client, account_name, group_link, logger):
    """Вступление в группу с обработкой капчи"""
    try:
        # Извлекаем username или invite hash из ссылки
        if '+' in group_link:
            # Это invite link с hash
            invite_hash = group_link.split('+')[-1]
            logger.info(f"  Вступаю через invite hash: {invite_hash[:20]}...")
            
            try:
                # Проверяем invite
                invite = await client(CheckChatInviteRequest(invite_hash))
                
                if isinstance(invite, ChatInvite):
                    # Нужно принять приглашение
                    await client(ImportChatInviteRequest(invite_hash))
                    logger.info(f"  ✅ Вступил в группу через invite")
                    return True
                else:
                    # Уже участник
                    logger.info(f"  ℹ️ Уже участник группы")
                    return True
                    
            except InviteHashExpiredError:
                logger.warning(f"  ⚠️ Invite hash истек")
                return False
            except UserAlreadyParticipantError:
                logger.info(f"  ℹ️ Уже участник")
                return True
            except FloodWaitError as e:
                wait_seconds = e.seconds
                wait_minutes = wait_seconds // 60
                logger.warning(f"  ⚠️ FloodWait: {wait_seconds} секунд ({wait_minutes} минут)")
                logger.info(f"  💡 FloodWait только для этого аккаунта! Можно переключиться на другой аккаунт")
                # Возвращаем специальный код для переключения аккаунта
                return ("FLOOD_WAIT", wait_seconds)
            except RPCError as e:
                error_msg = str(e)
                if "CAPTCHA" in error_msg or "captcha" in error_msg.lower():
                    logger.warning(f"  🔐 Требуется капча!")
                    await send_captcha_to_admin(client, account_name, group_link, error_msg)
                    return False
                else:
                    logger.error(f"  ❌ Ошибка: {e}")
                    return False
        
        else:
            # Это username группы/канала
            username = group_link.replace('https://t.me/', '').replace('http://t.me/', '').strip('/')
            logger.info(f"  Вступаю в группу: @{username}")
            
            try:
                entity = await client.get_entity(username)
                # Используем JoinChannelRequest для публичных групп/каналов
                await client(JoinChannelRequest(entity))
                logger.info(f"  ✅ Вступил в группу @{username}")
                return True
            except UserAlreadyParticipantError:
                logger.info(f"  ℹ️ Уже участник @{username}")
                return True
            except FloodWaitError as e:
                wait_seconds = e.seconds
                wait_minutes = wait_seconds // 60
                logger.warning(f"  ⚠️ FloodWait: {wait_seconds} секунд ({wait_minutes} минут)")
                logger.info(f"  💡 FloodWait только для этого аккаунта! Можно переключиться на другой аккаунт")
                # Возвращаем специальный код для переключения аккаунта
                return ("FLOOD_WAIT", wait_seconds)
            except UsernameNotOccupiedError:
                logger.warning(f"  ⚠️ Группа @{username} не найдена")
                return False
            except RPCError as e:
                error_msg = str(e)
                if "CAPTCHA" in error_msg or "captcha" in error_msg.lower():
                    logger.warning(f"  🔐 Требуется капча!")
                    await send_captcha_to_admin(client, account_name, group_link, error_msg)
                    return False
                else:
                    logger.error(f"  ❌ Ошибка: {e}")
                    return False
                    
    except Exception as e:
        logger.error(f"  ❌ Неожиданная ошибка: {e}")
        return False

async def join_groups_for_account(account, groups, progress, logger):
    """Вступление в группы для одного аккаунта"""
    account_name = account['session_name']
    logger.info(f"\n{'='*80}")
    logger.info(f"📱 АККАУНТ: {account_name} ({account.get('nickname', 'N/A')})")
    logger.info(f"{'='*80}")
    
    # Фильтруем группы - пропускаем уже обработанные
    if account_name in progress:
        joined_groups = set(progress[account_name].get('joined', []))
        remaining_groups = [g for g in groups if g not in joined_groups]
        
        if remaining_groups:
            logger.info(f"📊 Прогресс: уже вступил в {len(joined_groups)} групп")
            logger.info(f"📋 Осталось: {len(remaining_groups)} групп")
            groups = remaining_groups
        else:
            logger.info(f"✅ Все группы уже обработаны для {account_name}!")
            return 0
    else:
        logger.info(f"📋 Начинаем с начала: {len(groups)} групп")
    
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
        
        # Вступаем в группы
        joined_count = 0
        failed_count = 0
        flood_wait_seconds = 0
        
        total_groups = len(groups)
        already_joined = len(progress.get(account_name, {}).get('joined', [])) if account_name in progress else 0
        
        for i, group_link in enumerate(groups, 1):
            current_num = already_joined + i
            logger.info(f"\n[{current_num}/{len(NEW_GROUPS)}] {group_link}")
            
            result = await join_group(client, account_name, group_link, logger)
            
            # Обрабатываем результат и сохраняем прогресс
            if result == True:
                joined_count += 1
                update_progress(progress, account_name, group_link, 'joined')
            elif isinstance(result, tuple) and result[0] == "FLOOD_WAIT":
                # Получен FloodWait - сохраняем время и переключаемся на другой аккаунт
                flood_wait_seconds = result[1]
                wait_minutes = flood_wait_seconds // 60
                logger.warning(f"\n⏸️ Аккаунт {account_name} заблокирован на {wait_minutes} минут")
                logger.info(f"💡 Переключаемся на другой аккаунт, вернемся к этому позже")
                update_progress(progress, account_name, group_link, 'failed')
                failed_count += 1
                break  # Прерываем цикл для этого аккаунта
            else:
                failed_count += 1
                update_progress(progress, account_name, group_link, 'failed')
            
            # Задержка между вступлениями (только если не FloodWait)
            if i < len(groups) and not (isinstance(result, tuple) and result[0] == "FLOOD_WAIT"):
                delay = random.randint(*DELAY_BETWEEN_JOINS)
                logger.info(f"⏸️ Пауза {delay} секунд перед следующей группой...")
                await asyncio.sleep(delay)
        
        logger.info(f"\n{'='*80}")
        logger.info(f"📊 ИТОГИ для {account_name}:")
        logger.info(f"  ✅ Вступил: {joined_count}")
        logger.info(f"  ❌ Не удалось: {failed_count}")
        if flood_wait_seconds > 0:
            wait_minutes = flood_wait_seconds // 60
            logger.info(f"  ⏸️ FloodWait: {wait_minutes} минут (можно переключиться на другой аккаунт)")
        logger.info(f"{'='*80}")
        
        # Если был FloodWait - не делаем отлежку, просто возвращаемся
        if flood_wait_seconds > 0:
            logger.info(f"\n💡 Аккаунт {account_name} временно заблокирован, переключаемся на другой")
            return flood_wait_seconds  # Возвращаем время блокировки
        
        # Отлежка после вступления (только если не было FloodWait)
        rest_time = random.randint(*REST_AFTER_JOINING)
        logger.info(f"\n💤 Отлежка {rest_time // 60} минут для {account_name}...")
        await asyncio.sleep(rest_time)
        return 0  # Нет блокировки
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка для {account_name}: {e}")
    finally:
        await client.disconnect()
        logger.info(f"🔌 Отключен {account_name}")

async def main():
    """Основная функция"""
    logger = setup_logging()
    
    logger.info("\n" + "="*80)
    logger.info("🚀 СКРИПТ ВСТУПЛЕНИЯ В ГРУППЫ ДЛЯ НОВЫХ АККАУНТОВ")
    logger.info("="*80)
    logger.info(f"📋 Групп для вступления: {len(NEW_GROUPS)}")
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
    logger.info(f"\n💡 ВАЖНО: FloodWait действует только для конкретного аккаунта!")
    logger.info(f"   Если один аккаунт заблокирован, другие могут продолжать работу.")
    logger.info("="*80)
    
    # Загружаем сохраненный прогресс
    progress = load_progress()
    if progress:
        total_joined = sum(len(p.get('joined', [])) for p in progress.values())
        logger.info(f"📊 Загружен сохраненный прогресс: {total_joined} групп уже обработано")
    
    # Вступаем в группы для каждого аккаунта
    # Если аккаунт получил FloodWait - переключаемся на следующий
    account_flood_waits = {}  # Словарь для отслеживания FloodWait по аккаунтам
    
    for i, account in enumerate(accounts_to_use, 1):
        account_name = account['session_name']
        
        # Проверяем, не заблокирован ли аккаунт
        if account_name in account_flood_waits:
            wait_until = account_flood_waits[account_name]
            wait_remaining = (wait_until - datetime.now()).total_seconds()
            if wait_remaining > 0:
                wait_minutes = int(wait_remaining // 60)
                logger.info(f"\n⏸️ Аккаунт {account_name} еще заблокирован на {wait_minutes} минут, пропускаем...")
                continue
            else:
                # Блокировка истекла
                del account_flood_waits[account_name]
                logger.info(f"\n✅ Блокировка для {account_name} истекла, продолжаем...")
        
        flood_wait_seconds = await join_groups_for_account(account, NEW_GROUPS, progress, logger)
        
        # Если получили FloodWait - сохраняем время блокировки
        if flood_wait_seconds and flood_wait_seconds > 0:
            wait_until = datetime.now().timestamp() + flood_wait_seconds
            account_flood_waits[account_name] = datetime.fromtimestamp(wait_until)
            wait_minutes = flood_wait_seconds // 60
            logger.info(f"\n⏸️ Аккаунт {account_name} заблокирован до {datetime.fromtimestamp(wait_until).strftime('%H:%M:%S')}")
            logger.info(f"   Переключаемся на следующий аккаунт...")
        else:
            # Задержка между аккаунтами (только если не было FloodWait)
            if i < len(accounts_to_use):
                delay = random.randint(*DELAY_BETWEEN_ACCOUNTS)
                logger.info(f"\n⏸️ Пауза {delay // 60} минут перед следующим аккаунтом...")
                await asyncio.sleep(delay)
    
    logger.info("\n" + "="*80)
    logger.info("✅ ВСЕ АККАУНТЫ ОБРАБОТАНЫ!")
    logger.info("="*80)

if __name__ == "__main__":
    logger = None
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️ Прервано пользователем")
    except Exception as e:
        print(f"\n\n❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()




