#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для автоматической отписки от групп, в которые нельзя постить
или где аккаунты забанены
"""

import asyncio
import json
import logging
import re
from pathlib import Path
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import RPCError, FloodWaitError, ChatWriteForbiddenError, UserBannedInChannelError
from telethon.tl.functions.channels import LeaveChannelRequest, GetFullChannelRequest
from telethon.tl.functions.messages import GetFullChatRequest

ADMIN_ID = 210147380

def setup_logging():
    """Настройка логирования"""
    logs_dir = Path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "leave_banned_groups.log"

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

def extract_banned_groups_from_logs(log_file_path):
    """Извлечь забаненные группы из логов"""
    banned_groups = set()
    
    if not log_file_path.exists():
        return banned_groups
    
    patterns = [
        r"You can't write in this chat.*@(\w+)",
        r"You're banned from sending messages.*@(\w+)",
        r"banned from.*@(\w+)",
        r"can't write.*@(\w+)",
        r"private and you lack permission.*@(\w+)",
    ]
    
    try:
        with open(log_file_path, 'r', encoding='utf-8') as f:
            for line in f:
                for pattern in patterns:
                    match = re.search(pattern, line, re.IGNORECASE)
                    if match:
                        group = match.group(1).lower()
                        if group and not group.startswith('+'):
                            banned_groups.add(group)
    except Exception as e:
        logging.warning(f"Ошибка при чтении логов: {e}")
    
    return banned_groups

async def check_can_post(client, group_username, logger):
    """Проверить, можно ли постить в группу"""
    try:
        entity = await client.get_entity(group_username)
        
        # Пробуем получить полную информацию о группе/канале
        try:
            if hasattr(entity, 'broadcast') and entity.broadcast:
                # Это канал - проверяем через GetFullChannelRequest
                try:
                    full_info = await client(GetFullChannelRequest(entity))
                    # Проверяем права на отправку сообщений
                    if hasattr(full_info, 'default_banned_rights'):
                        if full_info.default_banned_rights.send_messages:
                            return False, "no_permission"
                    # Если дошли сюда - можно постить
                    return True, "ok"
                except UserBannedInChannelError:
                    return False, "banned"
                except ChatWriteForbiddenError:
                    return False, "no_permission"
            else:
                # Это группа - проверяем через GetFullChatRequest
                try:
                    full_info = await client(GetFullChatRequest(entity.id))
                    # Если получили информацию - значит не забанены
                    # Но нужно проверить права на отправку
                    # Для групп это сложнее, поэтому пробуем получить участников
                    try:
                        await client.get_participants(entity, limit=1)
                        return True, "ok"
                    except UserBannedInChannelError:
                        return False, "banned"
                    except ChatWriteForbiddenError:
                        return False, "no_permission"
                except UserBannedInChannelError:
                    return False, "banned"
                except ChatWriteForbiddenError:
                    return False, "no_permission"
        except UserBannedInChannelError:
            return False, "banned"
        except ChatWriteForbiddenError:
            return False, "no_permission"
        except RPCError as e:
            error_msg = str(e).lower()
            if "banned" in error_msg or "you're banned" in error_msg:
                return False, "banned"
            elif "can't write" in error_msg or "write in this chat" in error_msg:
                return False, "no_permission"
            elif "private" in error_msg and "permission" in error_msg:
                return False, "no_permission"
            else:
                # Другие ошибки - пробуем еще раз через получение участников
                try:
                    await client.get_participants(entity, limit=1)
                    return True, "ok"
                except:
                    return None, "error"
        except Exception as e:
            logger.debug(f"Ошибка при проверке {group_username}: {e}")
            return None, "error"
            
    except UserBannedInChannelError:
        return False, "banned"
    except ChatWriteForbiddenError:
        return False, "no_permission"
    except RPCError as e:
        error_msg = str(e).lower()
        if "banned" in error_msg:
            return False, "banned"
        elif "private" in error_msg and "permission" in error_msg:
            return False, "no_permission"
        else:
            return None, "error"
    except Exception as e:
        logger.warning(f"⚠️  Ошибка при обработке {group_username}: {e}")
        return None, "error"

async def leave_group(client, group_username, logger):
    """Отписаться от группы"""
    try:
        entity = await client.get_entity(group_username)
        
        # Пытаемся отписаться
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

async def process_account(account, groups_to_check, logger):
    """Обработать один аккаунт: проверить и отписаться от недоступных групп"""
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
        dialog_groups = {}
        
        for dialog in dialogs:
            entity = dialog.entity
            if hasattr(entity, 'username') and entity.username:
                username = entity.username.lower()
                # Проверяем, есть ли эта группа в списке для проверки
                if username in groups_to_check:
                    dialog_groups[username] = entity
        
        if not dialog_groups:
            logger.info(f"ℹ️  {account_name}: нет групп для проверки")
            await client.disconnect()
            return
        
        logger.info(f"📋 {account_name}: найдено {len(dialog_groups)} групп для проверки")
        
        # Проверяем каждую группу
        groups_to_leave = []
        for group_username, entity in dialog_groups.items():
            full_username = f"@{group_username}"
            logger.info(f"🔍 Проверка {full_username}...")
            
            can_post, reason = await check_can_post(client, full_username, logger)
            
            if can_post is False:
                logger.warning(f"❌ {full_username}: нельзя постить (причина: {reason})")
                groups_to_leave.append((full_username, reason))
            elif can_post is True:
                logger.info(f"✅ {full_username}: можно постить")
            else:
                logger.warning(f"⚠️  {full_username}: не удалось проверить")
            
            # Задержка между проверками
            await asyncio.sleep(2)
        
        # Отписываемся от недоступных групп
        if groups_to_leave:
            logger.info(f"🔴 {account_name}: отписка от {len(groups_to_leave)} недоступных групп")
            success_count = 0
            for group_username, reason in groups_to_leave:
                logger.info(f"🔴 Отписка от {group_username} (причина: {reason})...")
                success = await leave_group(client, group_username, logger)
                if success:
                    success_count += 1
                await asyncio.sleep(3)
            
            logger.info(f"✅ {account_name}: отписались от {success_count}/{len(groups_to_leave)} групп")
        else:
            logger.info(f"✅ {account_name}: все группы доступны для постинга")
        
        await client.disconnect()
        
    except FloodWaitError as e:
        logger.error(f"❌ {account_name}: FloodWait {e.seconds} секунд")
    except Exception as e:
        logger.error(f"❌ Ошибка при обработке {account_name}: {e}")
        import traceback
        logger.error(traceback.format_exc())

async def main():
    """Главная функция"""
    logger = setup_logging()
    logger.info("🚀 Запуск скрипта отписки от недоступных групп")
    
    # Загружаем группы из targets.txt
    targets_file = Path('targets.txt')
    groups_to_check = set()
    
    if targets_file.exists():
        with targets_file.open('r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and line.startswith('@'):
                    group = line[1:].lower()
                    if group and not group.startswith('+'):
                        groups_to_check.add(group)
    
    logger.info(f"📊 Найдено {len(groups_to_check)} групп из targets.txt для проверки")
    
    # Также извлекаем забаненные группы из логов
    log_file = Path('logs/promotion.log')
    banned_from_logs = extract_banned_groups_from_logs(log_file)
    if banned_from_logs:
        logger.info(f"📊 Найдено {len(banned_from_logs)} забаненных групп из логов")
        groups_to_check.update(banned_from_logs)
    
    if not groups_to_check:
        logger.info("ℹ️  Нет групп для проверки")
        return
    
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
        await process_account(account, groups_to_check, logger)
        # Задержка между аккаунтами
        await asyncio.sleep(5)
    
    logger.info("✅ Скрипт завершен")

if __name__ == "__main__":
    asyncio.run(main())

