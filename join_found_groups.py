#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для вступления в найденные группы из search_rental_groups.py
Использует ту же логику что и join_groups_for_new_accounts.py, но читает группы из logs/new_groups_to_join.json
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

# Аккаунты для вступления в группы (можно использовать все или только новые)
# Если хотите использовать только новые аккаунты, замените на список из join_groups_for_new_accounts.py
USE_ALL_ACCOUNTS = True  # Если True - использует все аккаунты из accounts_config.json

def setup_logging():
    """Настройка логирования"""
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    
    log_file = log_dir / 'join_found_groups.log'
    
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
    progress_file = Path('logs/join_found_groups_progress.json')
    if progress_file.exists():
        try:
            with progress_file.open('r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Ошибка загрузки прогресса: {e}")
    return {}

def save_progress(progress):
    """Сохранение прогресса"""
    progress_file = Path('logs/join_found_groups_progress.json')
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
                return ("FLOOD_WAIT", wait_seconds)
            except RPCError as e:
                error_msg = str(e)
                if "CAPTCHA" in error_msg or "капча" in error_msg.lower():
                    logger.warning(f"  🔐 Требуется капча")
                    await send_captcha_to_admin(client, account_name, group_link, error_msg)
                    return False
                logger.error(f"  ❌ Ошибка RPC: {e}")
                return False
        else:
            # Это обычная ссылка с username
            username = group_link.replace('https://t.me/', '').replace('http://t.me/', '').replace('@', '').rstrip('/')
            logger.info(f"  Вступаю через username: @{username}")
            
            try:
                await client(JoinChannelRequest(username))
                logger.info(f"  ✅ Вступил в группу @{username}")
                return True
            except UserAlreadyParticipantError:
                logger.info(f"  ℹ️ Уже участник @{username}")
                return True
            except UsernameNotOccupiedError:
                logger.warning(f"  ⚠️ Группа @{username} не найдена")
                return False
            except FloodWaitError as e:
                wait_seconds = e.seconds
                wait_minutes = wait_seconds // 60
                logger.warning(f"  ⚠️ FloodWait: {wait_seconds} секунд ({wait_minutes} минут)")
                return ("FLOOD_WAIT", wait_seconds)
            except ChatAdminRequiredError:
                logger.warning(f"  ⚠️ Нет доступа к группе @{username}")
                return False
            except RPCError as e:
                error_msg = str(e)
                if "CAPTCHA" in error_msg or "капча" in error_msg.lower():
                    logger.warning(f"  🔐 Требуется капча")
                    await send_captcha_to_admin(client, account_name, group_link, error_msg)
                    return False
                logger.error(f"  ❌ Ошибка RPC: {e}")
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
        return 0
    
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
            return 0
        
        me = await client.get_me()
        username = getattr(me, 'username', 'No username')
        logger.info(f"👤 Авторизован как: @{username}")
        
        # Инициализируем прогресс для аккаунта если нужно
        if account_name not in progress:
            progress[account_name] = {'joined': [], 'failed': []}
        
        # Вступаем в группы
        joined_count = 0
        failed_count = 0
        flood_wait_seconds = 0
        
        total_groups = len(groups)
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
        logger.error(f"❌ Ошибка при работе с {account_name}: {e}")
        return 0
    finally:
        await client.disconnect()
        logger.info(f"🔌 Отключен {account_name}")

async def main():
    """Основная функция"""
    logger = setup_logging()
    
    logger.info("\n" + "="*80)
    logger.info("🚀 ВСТУПЛЕНИЕ В НАЙДЕННЫЕ ГРУППЫ")
    logger.info("="*80)
    
    # Загружаем найденные группы
    new_groups_file = Path('logs/new_groups_to_join.json')
    if not new_groups_file.exists():
        logger.error(f"❌ Файл с найденными группами не найден: {new_groups_file}")
        logger.info("💡 Сначала запустите: python3 search_rental_groups.py")
        return
    
    try:
        with new_groups_file.open('r', encoding='utf-8') as f:
            new_groups_data = json.load(f)
        
        # Извлекаем ссылки
        group_links = [g['link'] for g in new_groups_data]
        logger.info(f"📋 Загружено групп для вступления: {len(group_links)}")
        
        # Показываем топ-10
        logger.info(f"\n📊 Топ-10 групп по количеству участников:")
        for i, group in enumerate(new_groups_data[:10], 1):
            logger.info(f"   {i:2}. {group['username']:35} - {group['members_count']:5} участников")
        
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки найденных групп: {e}")
        return
    
    # Загружаем аккаунты
    try:
        with open('accounts_config.json', 'r', encoding='utf-8') as f:
            all_accounts = json.load(f)
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки accounts_config.json: {e}")
        return
    
    # Выбираем аккаунты
    if USE_ALL_ACCOUNTS:
        accounts_to_use = all_accounts
        logger.info(f"✅ Используем все аккаунты: {len(accounts_to_use)}")
    else:
        # Можно указать конкретные аккаунты
        target_accounts = [
            "promotion_oleg_petrov",
            "promotion_anna_truncher",
            "promotion_artur_biggest",
            "promotion_andrey_virgin"
        ]
        accounts_to_use = [
            acc for acc in all_accounts 
            if acc['session_name'] in target_accounts
        ]
        logger.info(f"✅ Используем выбранные аккаунты: {len(accounts_to_use)}")
    
    if not accounts_to_use:
        logger.error("❌ Не найдено аккаунтов для работы")
        return
    
    logger.info(f"\n💡 ВАЖНО: FloodWait действует только для конкретного аккаунта!")
    logger.info(f"   Если один аккаунт заблокирован, другие могут продолжать работу.")
    logger.info("="*80)
    
    # Загружаем сохраненный прогресс
    progress = load_progress()
    if progress:
        total_joined = sum(len(p.get('joined', [])) for p in progress.values())
        logger.info(f"📊 Загружен сохраненный прогресс: {total_joined} групп уже обработано")
    
    # Вступаем в группы для каждого аккаунта
    total_joined_all = 0
    for i, account in enumerate(accounts_to_use, 1):
        logger.info(f"\n{'='*80}")
        logger.info(f"👤 АККАУНТ {i}/{len(accounts_to_use)}: {account['session_name']}")
        logger.info(f"{'='*80}")
        
        joined = await join_groups_for_account(account, group_links, progress, logger)
        total_joined_all += joined
        
        # Отлежка между аккаунтами (1-2 минуты)
        if i < len(accounts_to_use):
            delay = random.randint(60, 120)
            logger.info(f"\n⏳ Задержка {delay} секунд перед следующим аккаунтом...")
            await asyncio.sleep(delay)
    
    logger.info("\n" + "="*80)
    logger.info("📊 ИТОГОВАЯ СТАТИСТИКА")
    logger.info("="*80)
    logger.info(f"✅ Всего вступили в групп: {total_joined_all}")
    logger.info(f"📋 Всего групп в списке: {len(group_links)}")
    logger.info("="*80)

if __name__ == "__main__":
    logger = None
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        if logger:
            logger.info("\n⚠️ Прервано пользователем")
        print("\n⚠️ Прервано пользователем")
    except Exception as e:
        if logger:
            logger.error(f"\n❌ Критическая ошибка: {e}")
        print(f"\n❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()







