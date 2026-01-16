#!/usr/bin/env python3
"""
Скрипт для проверки прав на отправку сообщений во всех группах
Проверяет группы со статусом 'new' и помечает недоступные как 'no_write'
"""
import asyncio
import sys
import os
from pathlib import Path

# Добавляем путь к модулям
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.errors import (
    ChatWriteForbiddenError,
    UserBannedInChannelError,
    FloodWaitError,
    UsernameNotOccupiedError,
    ChannelPrivateError,
    UserAlreadyParticipantError,
    RPCError
)

# Импорт модулей БД
try:
    from lexus_db.session import AsyncSessionLocal
    from lexus_db.models import Account, Target
    from sqlalchemy import select, update
    from datetime import datetime
except ImportError:
    print("❌ Ошибка импорта модулей БД. Убедитесь, что вы запускаете скрипт из контейнера или с правильным PYTHONPATH")
    sys.exit(1)

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def check_can_post(client: TelegramClient, entity) -> tuple[bool, str]:
    """
    Проверка прав на отправку сообщений в группе
    
    Returns:
        (can_post: bool, error_message: str)
    """
    try:
        me = await client.get_me()
        permissions = await client.get_permissions(entity, me)
        
        if permissions:
            # Проверяем право на отправку сообщений
            if hasattr(permissions, 'send_messages'):
                if not permissions.send_messages:
                    return False, "Запрещено отправлять сообщения"
            # Проверяем через banned_rights
            elif hasattr(permissions, 'banned_rights') and permissions.banned_rights:
                if hasattr(permissions.banned_rights, 'send_messages'):
                    if permissions.banned_rights.send_messages:
                        return False, "Запрещено отправлять сообщения (banned_rights)"
        
        return True, ""
    except (ChatWriteForbiddenError, UserBannedInChannelError) as e:
        return False, f"Запрещено отправлять сообщения: {str(e)}"
    except Exception as e:
        logger.warning(f"⚠️ Ошибка проверки прав: {e}")
        return True, ""  # В случае ошибки считаем что можно (попробуем постить)


async def check_group_write_access(client: TelegramClient, group_link: str) -> tuple[bool, str]:
    """
    Проверка группы на возможность постинга
    Сначала пытается вступить, затем проверяет права
    
    Returns:
        (can_post: bool, error_message: str)
    """
    try:
        # Получаем entity группы
        entity = await client.get_entity(group_link)
        
        # Пытаемся вступить в группу (если еще не участник)
        try:
            await client(JoinChannelRequest(entity))
            logger.debug(f"  ✅ Вступил в {group_link}")
        except UserAlreadyParticipantError:
            logger.debug(f"  ℹ️ Уже участник {group_link}")
        except FloodWaitError as e:
            raise e  # Пробрасываем FloodWait наверх
        
        # Проверяем права на отправку сообщений
        can_post, error_msg = await check_can_post(client, entity)
        return can_post, error_msg
        
    except (UsernameNotOccupiedError, ChannelPrivateError) as e:
        return False, f"Группа недоступна: {str(e)}"
    except FloodWaitError as e:
        raise e  # Пробрасываем FloodWait наверх
    except Exception as e:
        logger.warning(f"⚠️ Ошибка при проверке {group_link}: {e}")
        return True, ""  # В случае ошибки считаем что можно


async def main():
    """Основная функция"""
    import json
    
    # Загружаем конфигурацию аккаунтов (для Ukraine используем ukraine_accounts_config.json)
    accounts_config_path = Path('ukraine_accounts_config.json')
    if not accounts_config_path.exists():
        accounts_config_path = Path('/app/ukraine_accounts_config.json')
    if not accounts_config_path.exists():
        accounts_config_path = Path('accounts_config.json')
    if not accounts_config_path.exists():
        accounts_config_path = Path('/app/accounts_config.json')
    
    if not accounts_config_path.exists():
        logger.error(f"❌ Файл конфигурации аккаунтов не найден: {accounts_config_path}")
        return
    
    with open(accounts_config_path, 'r', encoding='utf-8') as f:
        accounts_list = json.load(f)
    
    if not accounts_list:
        logger.error("❌ Нет аккаунтов в конфигурации")
        return
    
    # Берем первый доступный аккаунт
    account_config = accounts_list[0]
    session_name = account_config['session_name']
    string_session = account_config.get('string_session')
    api_id = account_config.get('api_id')
    api_hash = account_config.get('api_hash')
    
    if not all([string_session, api_id, api_hash]):
        logger.error(f"❌ Неполная конфигурация аккаунта {session_name}")
        return
    
    logger.info(f"📋 Используем аккаунт: {session_name}")
    
    # Создаем клиент
    client = TelegramClient(
        StringSession(string_session),
        int(api_id),
        api_hash
    )
    
    try:
        await client.connect()
        
        if not await client.is_user_authorized():
            logger.error(f"❌ Аккаунт {session_name} не авторизован")
            return
        
        logger.info("✅ Подключено к Telegram")
        
        # Подключаемся к БД
        async with AsyncSessionLocal() as session:
            # Получаем все группы со статусом 'new'
            stmt = select(Target).where(
                Target.status == 'new',
                Target.niche == 'ukraine_cars'
            ).order_by(Target.id)
            
            result = await session.execute(stmt)
            targets = result.scalars().all()
            
            total = len(targets)
            logger.info(f"📋 Найдено {total} групп для проверки")
            
            checked = 0
            can_post_count = 0
            no_post_count = 0
            error_count = 0
            
            for idx, target in enumerate(targets, 1):
                group_link = target.link
                logger.info(f"\n{'='*60}")
                logger.info(f"📋 [{idx}/{total}] Проверка: {group_link}")
                logger.info(f"{'='*60}")
                
                try:
                    # Проверяем группу
                    can_post, error_msg = await check_group_write_access(client, group_link)
                    
                    if can_post:
                        logger.info(f"  ✅ МОЖНО ПОСТИТЬ: {group_link}")
                        can_post_count += 1
                        # Группа остается со статусом 'new'
                    else:
                        logger.warning(f"  ❌ НЕЛЬЗЯ ПОСТИТЬ: {group_link} - {error_msg}")
                        # Помечаем группу как недоступную для постинга
                        target.status = 'error'
                        target.error_message = f"Нельзя постить: {error_msg}"
                        target.updated_at = datetime.utcnow()
                        await session.commit()
                        no_post_count += 1
                    
                    checked += 1
                    
                    # Пауза между проверками (2-4 секунды)
                    if idx < total:
                        await asyncio.sleep(2)
                
                except FloodWaitError as e:
                    wait_seconds = e.seconds
                    logger.warning(f"  ⏳ FloodWait {wait_seconds} сек. Ждем...")
                    await asyncio.sleep(wait_seconds)
                    # Пропускаем эту группу и пробуем следующую
                    error_count += 1
                    continue
                
                except Exception as e:
                    logger.error(f"  ❌ Ошибка при проверке {group_link}: {e}")
                    error_count += 1
                    continue
            
            # Финальная статистика
            logger.info("\n" + "="*60)
            logger.info("📊 РЕЗУЛЬТАТЫ ПРОВЕРКИ")
            logger.info("="*60)
            logger.info(f"✅ Всего проверено: {checked}")
            logger.info(f"✅ Можно постить: {can_post_count}")
            logger.info(f"❌ Нельзя постить: {no_post_count}")
            logger.info(f"⚠️  Ошибки: {error_count}")
            logger.info(f"📋 Осталось новых групп: {can_post_count}")
            logger.info("="*60)
    
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
    finally:
        await client.disconnect()
        logger.info("✅ Отключено от Telegram")


if __name__ == "__main__":
    asyncio.run(main())
