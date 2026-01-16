#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка и вступление в Lexus группы для украинских авто-чатов
"""

import asyncio
import json
import logging
import random
import sys
from pathlib import Path
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    FloodWaitError, 
    UserAlreadyParticipantError,
    UsernameNotOccupiedError,
    ChatAdminRequiredError,
    RPCError,
    ChatWriteForbiddenError,
    UserBannedInChannelError
)
from telethon.tl.functions.channels import JoinChannelRequest, GetFullChannelRequest
from telethon.tl.functions.messages import GetFullChatRequest

sys.path.insert(0, '.')

from promotion_system import PromotionSystem

def setup_logging():
    """Настройка логирования"""
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    
    log_file = log_dir / 'check_lexus_groups.log'
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    return logging.getLogger(__name__)

async def check_and_join_group(client, account_name, group_username, logger):
    """Проверка и вступление в группу"""
    try:
        logger.info(f"  Проверяю {group_username}...")
        
        # Получаем entity
        entity = await client.get_entity(group_username)
        
        # Проверяем, участник ли уже
        try:
            await client.get_participants(entity, limit=1)
            logger.info(f"  ✅ Уже участник {group_username}")
            is_member = True
        except:
            is_member = False
        
        # Если не участник - вступаем
        if not is_member:
            try:
                await client(JoinChannelRequest(entity))
                logger.info(f"  ✅ Вступил в {group_username}")
                await asyncio.sleep(2)
            except UserAlreadyParticipantError:
                logger.info(f"  ℹ️ Уже участник {group_username}")
            except FloodWaitError as e:
                logger.warning(f"  ⚠️ FloodWait {e.seconds} секунд для {group_username}")
                return False
            except Exception as e:
                logger.error(f"  ❌ Ошибка вступления в {group_username}: {e}")
                return False
        
        # Проверяем права на постинг
        try:
            me = await client.get_me()
            permissions = await client.get_permissions(entity, me)
            
            can_send = False
            if permissions:
                if hasattr(permissions, 'send_messages'):
                    can_send = permissions.send_messages
                elif hasattr(permissions, 'banned_rights') and permissions.banned_rights:
                    if hasattr(permissions.banned_rights, 'send_messages'):
                        can_send = not permissions.banned_rights.send_messages
            
            if can_send:
                logger.info(f"  ✅ МОЖНО ПОСТИТЬ в {group_username}")
                return True
            else:
                logger.warning(f"  ⚠️ НЕЛЬЗЯ ПОСТИТЬ в {group_username} - нет прав")
                return False
                
        except UserBannedInChannelError:
            logger.warning(f"  ⚠️ ЗАБАНЕН в {group_username}")
            return False
        except ChatWriteForbiddenError:
            logger.warning(f"  ⚠️ НЕТ ПРАВ на постинг в {group_username}")
            return False
        except Exception as e:
            logger.warning(f"  ⚠️ Не удалось проверить права в {group_username}: {e}")
            # Если не можем проверить, считаем что можно (попробуем постить)
            return True
            
    except UsernameNotOccupiedError:
        logger.warning(f"  ⚠️ Группа {group_username} не найдена")
        return False
    except Exception as e:
        logger.error(f"  ❌ Ошибка для {group_username}: {e}")
        return False

async def main():
    """Основная функция"""
    logger = setup_logging()
    
    logger.info("=" * 80)
    logger.info("🔍 ПРОВЕРКА И ВСТУПЛЕНИЕ В LEXUS ГРУППЫ")
    logger.info("=" * 80)
    
    system = PromotionSystem()
    system.load_accounts()
    await system.initialize_clients()
    
    if not system.clients:
        logger.error("❌ Нет доступных клиентов!")
        return
    
    # Lexus группы
    lexus_groups = [
        "@AutoProdaja_ua",
        "@auto_amerika_europa",
        "@autobazar_com_ua",
        "@autobazar_uaua",
        "@avto_swup",
        "@avtorynok_ua",
        "@bazaravtoukr",
        "@cryptoinfotop",
        "@gruzhelp",
        "@prodaj_avto",
        "@razborkaukraina",
        "@sellautoukraine",
        "@ua_autobazar"
    ]
    
    accounts = system.accounts
    random.shuffle(accounts)
    
    joined_count = 0
    can_post_count = 0
    
    for group_username in lexus_groups:
        logger.info(f"\n[{lexus_groups.index(group_username) + 1}/{len(lexus_groups)}] {group_username}")
        
        # Пробуем через разные аккаунты
        success = False
        for account in accounts:
            account_name = account['session_name']
            
            if account_name not in system.clients:
                continue
            
            client = system.clients[account_name]
            logger.info(f"  Используем аккаунт: {account_name}")
            
            result = await check_and_join_group(client, account_name, group_username, logger)
            
            if result:
                joined_count += 1
                can_post_count += 1
                success = True
                break
            elif result is False:
                # Пробуем следующий аккаунт
                continue
            
            await asyncio.sleep(2)
        
        if not success:
            logger.warning(f"  ❌ Не удалось вступить/проверить {group_username} через все аккаунты")
        
        # Пауза между группами
        await asyncio.sleep(random.randint(10, 20))
    
    logger.info("")
    logger.info("=" * 80)
    logger.info(f"✅ ЗАВЕРШЕНО:")
    logger.info(f"   - Вступили/проверили: {joined_count}/{len(lexus_groups)}")
    logger.info(f"   - Можно постить: {can_post_count}/{len(lexus_groups)}")
    logger.info("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())



