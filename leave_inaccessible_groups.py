#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для отписки от групп, в которые аккаунты не могут писать
"""

import asyncio
import json
import logging
from pathlib import Path
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import RPCError, FloodWaitError
from telethon.tl.functions.channels import LeaveChannelRequest
from telethon.tl.functions.messages import DeleteChatUserRequest

ADMIN_ID = 210147380

def setup_logging():
    """Настройка логирования"""
    logs_dir = Path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "leave_groups.log"

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

def normalize_group(link):
    """Нормализация группы для сравнения"""
    link = link.strip()
    if link.startswith('@'):
        return link[1:].lower()
    if 't.me/' in link:
        tail = link.split('t.me/', 1)[1].split('/')[0].split('?')[0].rstrip('/')
        return tail.lower() if tail and not tail.startswith('+') else link
    return link.lower()

def get_failed_groups():
    """Получить список групп, в которые не могут писать (failed)"""
    progress_path = Path('logs/join_groups_progress.json')
    failed_all = set()
    
    if not progress_path.exists():
        return failed_all
    
    with progress_path.open('r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Собираем все failed группы из всех аккаунтов
    for acc, info in data.items():
        for item in info.get('failed', []):
            normalized = normalize_group(item)
            if normalized and not normalized.startswith('+'):
                failed_all.add(normalized)
    
    return failed_all

async def leave_group(client, group_username, logger):
    """Отписаться от группы"""
    try:
        # Получаем entity группы
        entity = await client.get_entity(group_username)
        
        # Пытаемся отписаться
        # Для каналов/супергрупп используем LeaveChannelRequest
        # Для обычных чатов используем delete_dialog
        try:
            await client(LeaveChannelRequest(entity))
            logger.info(f"✅ Успешно отписались от {group_username}")
            return True
        except Exception as e:
            # Если это не канал, пробуем delete_dialog
            try:
                await client.delete_dialog(entity)
                logger.info(f"✅ Успешно удалили диалог с {group_username}")
                return True
            except Exception as e2:
                logger.warning(f"⚠️  Не удалось отписаться от {group_username}: {e2}")
                return False
                
    except Exception as e:
        logger.warning(f"⚠️  Ошибка при обработке {group_username}: {e}")
        return False

async def process_account(account, failed_groups, logger):
    """Обработать один аккаунт: отписаться от failed групп"""
    account_name = account['session_name']
    logger.info(f"🔄 Обработка аккаунта: {account_name}")
    
    try:
        api_id = int(account['api_id'])
        string_session = account.get('string_session')
        
        if not string_session or string_session in ['', 'TO_BE_CREATED', 'null', None]:
            logger.warning(f"⚠️  У {account_name} нет string_session, пропускаем")
            return
        
        # Создаем клиент
        client = TelegramClient(StringSession(string_session), api_id, account['api_hash'])
        await client.connect()
        
        if not await client.is_user_authorized():
            logger.warning(f"⚠️  {account_name} не авторизован, пропускаем")
            await client.disconnect()
            return
        
        logger.info(f"✅ {account_name} подключен")
        
        # Получаем список диалогов аккаунта
        dialogs = await client.get_dialogs()
        dialog_usernames = set()
        
        for dialog in dialogs:
            entity = dialog.entity
            if hasattr(entity, 'username') and entity.username:
                dialog_usernames.add(entity.username.lower())
            elif hasattr(entity, 'id'):
                # Для групп без username можем использовать ID, но проще по username
                pass
        
        # Находим пересечение: failed группы, в которых состоит аккаунт
        groups_to_leave = failed_groups & dialog_usernames
        
        if not groups_to_leave:
            logger.info(f"ℹ️  {account_name}: нет failed групп для отписки")
            await client.disconnect()
            return
        
        logger.info(f"📋 {account_name}: найдено {len(groups_to_leave)} групп для отписки")
        
        # Отписываемся от каждой группы с задержкой
        success_count = 0
        for group in sorted(groups_to_leave):
            group_username = f"@{group}"
            logger.info(f"🔴 Отписка от {group_username}...")
            
            success = await leave_group(client, group_username, logger)
            if success:
                success_count += 1
            
            # Задержка между отписками
            await asyncio.sleep(2)
        
        logger.info(f"✅ {account_name}: отписались от {success_count}/{len(groups_to_leave)} групп")
        
        await client.disconnect()
        
    except FloodWaitError as e:
        logger.error(f"❌ {account_name}: FloodWait {e.seconds} секунд")
    except Exception as e:
        logger.error(f"❌ Ошибка при обработке {account_name}: {e}")

async def main():
    """Главная функция"""
    logger = setup_logging()
    logger.info("🚀 Запуск скрипта отписки от нерабочих групп")
    
    # Загружаем failed группы
    failed_groups = get_failed_groups()
    if not failed_groups:
        logger.info("ℹ️  Нет failed групп для обработки")
        return
    
    logger.info(f"📊 Найдено {len(failed_groups)} failed групп: {sorted(failed_groups)}")
    
    # Загружаем аккаунты
    config_file = Path('accounts_config.json')
    if not config_file.exists():
        logger.error("❌ Файл accounts_config.json не найден")
        return
    
    with config_file.open('r', encoding='utf-8') as f:
        accounts = json.load(f)
    
    logger.info(f"📋 Загружено {len(accounts)} аккаунтов")
    
    # Обрабатываем каждый аккаунт
    for account in accounts:
        await process_account(account, failed_groups, logger)
        # Задержка между аккаунтами
        await asyncio.sleep(3)
    
    logger.info("✅ Скрипт завершен")

if __name__ == "__main__":
    asyncio.run(main())

