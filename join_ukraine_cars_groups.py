#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для вступления в найденные украинские группы по продаже автомобилей
Использует ту же логику что и join_found_groups.py, но читает группы из logs/found_ukraine_cars_groups.json
"""

import asyncio
import json
import logging
import random
import sys
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

# Используем все аккаунты из accounts_config.json
USE_ALL_ACCOUNTS = True

def setup_logging():
    """Настройка логирования"""
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    
    log_file = log_dir / 'join_ukraine_cars_groups.log'
    
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
    progress_file = Path('logs/join_ukraine_cars_groups_progress.json')
    if progress_file.exists():
        try:
            with progress_file.open('r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Ошибка загрузки прогресса: {e}")
    return {}

def save_progress(progress):
    """Сохранение прогресса"""
    progress_file = Path('logs/join_ukraine_cars_groups_progress.json')
    progress_file.parent.mkdir(exist_ok=True)
    try:
        with progress_file.open('w', encoding='utf-8') as f:
            json.dump(progress, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Ошибка сохранения прогресса: {e}")

def parse_proxy(proxy_str):
    """Парсинг прокси строки"""
    try:
        if not proxy_str or proxy_str in ['', 'null', 'None']:
            return None
        
        # Формат: type://user:pass@host:port
        if '://' in proxy_str:
            parts = proxy_str.split('://')
            proxy_type = parts[0]
            auth_part = parts[1]
            
            if '@' in auth_part:
                auth, host_port = auth_part.split('@')
                user, password = auth.split(':')
                host, port = host_port.split(':')
            else:
                user = password = None
                host, port = auth_part.split(':')
            
            proxy_dict = {
                'proxy_type': proxy_type,
                'addr': host,
                'port': int(port)
            }
            
            if user and password:
                proxy_dict['username'] = user
                proxy_dict['password'] = password
            
            return proxy_dict
    except Exception as e:
        print(f"Ошибка парсинга прокси: {e}")
    return None

async def send_captcha_to_admin(client, account_name, group_link, captcha_message):
    """Пересылка капчи админу"""
    try:
        await client.send_message(ADMIN_ID, f"🔐 КАПЧА для {account_name}\n\nГруппа: {group_link}\n\n{captcha_message}")
        return True
    except Exception as e:
        logger.error(f"Ошибка отправки капчи админу: {e}")
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
                logger.warning(f"  ⚠️ Ошибка RPC: {error_msg}")
                
                # Обработка капчи
                if "captcha" in error_msg.lower() or "CAPTCHA" in error_msg:
                    logger.warning(f"  🔐 Обнаружена капча для {group_link}")
                    await send_captcha_to_admin(client, account_name, group_link, error_msg)
                    return False
                
                return False
        else:
            # Это username или обычная ссылка
            # Извлекаем username из ссылки
            username = group_link.replace('https://t.me/', '').replace('http://t.me/', '').replace('@', '').strip()
            
            if not username:
                logger.error(f"  ❌ Не удалось извлечь username из {group_link}")
                return False
            
            logger.info(f"  Вступаю через username: @{username}")
            
            try:
                entity = await client.get_entity(username)
                await client(JoinChannelRequest(entity))
                logger.info(f"  ✅ Вступил в группу @{username}")
                return True
            except UserAlreadyParticipantError:
                logger.info(f"  ℹ️ Уже участник группы @{username}")
                return True
            except FloodWaitError as e:
                wait_seconds = e.seconds
                wait_minutes = wait_seconds // 60
                logger.warning(f"  ⚠️ FloodWait: {wait_seconds} секунд ({wait_minutes} минут)")
                logger.info(f"  💡 FloodWait только для этого аккаунта! Можно переключиться на другой аккаунт")
                return ("FLOOD_WAIT", wait_seconds)
            except UsernameNotOccupiedError:
                logger.warning(f"  ⚠️ Группа @{username} не найдена или недоступна")
                return False
            except ChatAdminRequiredError:
                logger.warning(f"  ⚠️ Нужны права админа для вступления в @{username}")
                return False
            except RPCError as e:
                error_msg = str(e)
                logger.warning(f"  ⚠️ Ошибка RPC: {error_msg}")
                
                # Обработка капчи
                if "captcha" in error_msg.lower() or "CAPTCHA" in error_msg:
                    logger.warning(f"  🔐 Обнаружена капча для {group_link}")
                    await send_captcha_to_admin(client, account_name, group_link, error_msg)
                    return False
                
                return False
                
    except Exception as e:
        logger.error(f"  ❌ Неожиданная ошибка при вступлении в {group_link}: {e}")
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
        return 0
    
    client = TelegramClient(
        StringSession(string_session),
        int(account['api_id']),
        account['api_hash'],
        proxy=proxy
    )
    
    try:
        await client.connect()
        
        if not await client.is_user_authorized():
            logger.error(f"❌ Аккаунт {account_name} не авторизован!")
            return 0
        
        logger.info(f"✅ Подключен и авторизован: {account_name}")
        
        joined_count = 0
        failed_count = 0
        flood_wait_seconds = 0
        total_groups = len(groups)
        
        # Инициализируем прогресс для аккаунта, если его нет
        if account_name not in progress:
            progress[account_name] = {'joined': [], 'failed': []}
        
        already_joined = len(progress[account_name].get('joined', []))
        
        for i, group_link in enumerate(groups, 1):
            current_num = already_joined + i
            logger.info(f"\n[{current_num}/{already_joined + total_groups}] {group_link}")
            
            result = await join_group(client, account_name, group_link, logger)
            
            # Обрабатываем результат
            if result == True:
                joined_count += 1
                progress[account_name]['joined'].append(group_link)
                save_progress(progress)
            elif isinstance(result, tuple) and result[0] == "FLOOD_WAIT":
                flood_wait_seconds = result[1]
                logger.warning(f"⏳ FloodWait {flood_wait_seconds} секунд - переключаемся на другой аккаунт")
                progress[account_name]['failed'].append(group_link)
                save_progress(progress)
                break  # Прерываем цикл для этого аккаунта
            else:
                failed_count += 1
                progress[account_name]['failed'].append(group_link)
                save_progress(progress)
            
            # Задержка между вступлениями (30-60 секунд)
            if i < total_groups:
                delay = random.randint(30, 60)
                logger.info(f"  ⏳ Задержка {delay} секунд перед следующим вступлением...")
                await asyncio.sleep(delay)
        
        logger.info(f"\n📊 Результаты для {account_name}:")
        logger.info(f"   ✅ Вступил в: {joined_count} групп")
        logger.info(f"   ❌ Неудачно: {failed_count} групп")
        if flood_wait_seconds > 0:
            logger.info(f"   ⏳ FloodWait: {flood_wait_seconds} секунд")
        
        return joined_count
        
    except Exception as e:
        logger.error(f"❌ Исключение для аккаунта {account_name}: {e}")
        return 0
    finally:
        await client.disconnect()
        logger.info(f"🔌 Отключен {account_name}")

async def main():
    """Основная функция"""
    logger = setup_logging()
    
    logger.info("\n" + "="*80)
    logger.info("🚗 ВСТУПЛЕНИЕ В УКРАИНСКИЕ ГРУППЫ ПО ПРОДАЖЕ АВТОМОБИЛЕЙ")
    logger.info("="*80)
    logger.info(f"📅 Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*80)
    
    # Загружаем найденные группы
    groups_file = Path('logs/found_ukraine_cars_groups.json')
    if not groups_file.exists():
        logger.error(f"❌ Файл {groups_file} не найден! Сначала запустите search_ukraine_cars_groups.py")
        return
    
    try:
        with groups_file.open('r', encoding='utf-8') as f:
            groups_data = json.load(f)
    except Exception as e:
        logger.error(f"❌ Ошибка чтения файла {groups_file}: {e}")
        return
    
    # Извлекаем список групп (username)
    groups = [group['username'] for group in groups_data if group.get('username')]
    
    if not groups:
        logger.warning("⚠️ Не найдено групп для вступления")
        return
    
    logger.info(f"📋 Загружено {len(groups)} групп для вступления")
    
    # Загружаем аккаунты
    accounts_file = Path('accounts_config.json')
    if not accounts_file.exists():
        logger.error(f"❌ Файл {accounts_file} не найден!")
        return
    
    try:
        with accounts_file.open('r', encoding='utf-8') as f:
            accounts = json.load(f)
    except Exception as e:
        logger.error(f"❌ Ошибка чтения {accounts_file}: {e}")
        return
    
    if USE_ALL_ACCOUNTS:
        accounts_to_use = accounts
    else:
        # Можно добавить фильтрацию для конкретных аккаунтов
        accounts_to_use = accounts
    
    logger.info(f"👥 Используем {len(accounts_to_use)} аккаунтов")
    
    # Загружаем прогресс
    progress = load_progress()
    
    # Вступаем в группы для каждого аккаунта
    total_joined = 0
    for account in accounts_to_use:
        try:
            joined = await join_groups_for_account(account, groups, progress, logger)
            total_joined += joined
        except Exception as e:
            logger.error(f"❌ Ошибка при обработке аккаунта {account.get('session_name', 'unknown')}: {e}")
    
    logger.info("\n" + "="*80)
    logger.info(f"✅ ЗАВЕРШЕНО: Всего вступили в {total_joined} групп")
    logger.info("="*80)

if __name__ == "__main__":
    asyncio.run(main())


