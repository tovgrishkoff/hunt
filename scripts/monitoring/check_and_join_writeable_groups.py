#!/usr/bin/env python3
"""
Скрипт для проверки и вступления в группы, где можно постить
- Использует все доступные аккаунты
- Проверяет права ДО вступления (через GetFullChannelRequest)
- Вступает только в группы, где можно постить
- Привязывает к аккаунту и устанавливает warm-up период
"""
import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta

# Добавляем путь к модулям
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import JoinChannelRequest, GetFullChannelRequest
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
    from lexus_db.db_manager import DbManager
    from sqlalchemy import select, update
except ImportError:
    print("❌ Ошибка импорта модулей БД. Убедитесь, что вы запускаете скрипт из контейнера или с правильным PYTHONPATH")
    sys.exit(1)

import logging
import json
import random
from collections import defaultdict
from typing import Dict, List

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def check_can_post_before_join(client: TelegramClient, entity) -> tuple[bool, str]:
    """
    Проверка прав на отправку сообщений ДО вступления (для публичных групп/каналов)
    Использует GetFullChannelRequest для получения default_banned_rights
    
    Returns:
        (can_post: bool, error_message: str)
    """
    try:
        # Для публичных групп/каналов можем проверить default_banned_rights
        if hasattr(entity, 'id'):
            try:
                full_info = await client(GetFullChannelRequest(entity))
                if hasattr(full_info, 'full_chat') and hasattr(full_info.full_chat, 'default_banned_rights'):
                    banned_rights = full_info.full_chat.default_banned_rights
                    if banned_rights and hasattr(banned_rights, 'send_messages'):
                        if banned_rights.send_messages:
                            return False, "По умолчанию запрещено отправлять сообщения (default_banned_rights)"
                # Если default_banned_rights позволяет постить - считаем что можно
                return True, ""
            except Exception as e:
                logger.debug(f"  ⚠️ Не удалось получить full_info: {e}")
                # Если не можем проверить - считаем что можно (попробуем вступить)
                return True, ""
        
        # Если не можем проверить заранее - считаем что можно (попробуем вступить и проверить)
        return True, ""
    except Exception as e:
        logger.warning(f"⚠️ Ошибка проверки прав до вступления: {e}")
        return True, ""  # В случае ошибки считаем что можно


async def check_can_post_after_join(client: TelegramClient, entity) -> tuple[bool, str]:
    """
    Проверка прав на отправку сообщений ПОСЛЕ вступления
    
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
        logger.warning(f"⚠️ Ошибка проверки прав после вступления: {e}")
        return True, ""  # В случае ошибки считаем что можно


async def process_group_with_account(
    client: TelegramClient,
    account_id: int,
    target: Target,
    db_manager: DbManager,
    session
) -> tuple[bool, str]:
    """
    Обработка одной группы с аккаунтом:
    1. Проверяет права ДО вступления (если возможно)
    2. Вступает в группу
    3. Проверяет права ПОСЛЕ вступления
    4. Если можно постить - привязывает к аккаунту с warm-up
    5. Если нельзя - помечает как error
    
    Returns:
        (success: bool, error_message: str)
    """
    group_link = target.link
    
    try:
        # Получаем entity группы
        entity = await client.get_entity(group_link)
        
        # ШАГ 1: Проверяем права ДО вступления (для публичных групп)
        can_post_before, error_before = await check_can_post_before_join(client, entity)
        if not can_post_before:
            logger.warning(f"  ❌ Нельзя постить (проверка до вступления): {error_before}")
            # Помечаем как error БЕЗ вступления
            target.status = 'error'
            target.error_message = error_before
            target.updated_at = datetime.utcnow()
            await session.commit()
            return False, error_before
        
        # ШАГ 2: Вступаем в группу
        try:
            await client(JoinChannelRequest(entity))
            logger.info(f"  ✅ Вступил в {group_link}")
        except UserAlreadyParticipantError:
            logger.info(f"  ℹ️ Уже участник {group_link}")
        except FloodWaitError as e:
            raise e  # Пробрасываем FloodWait наверх
        
        # ШАГ 3: Проверяем права ПОСЛЕ вступления
        can_post_after, error_after = await check_can_post_after_join(client, entity)
        
        if not can_post_after:
            logger.warning(f"  ❌ Нельзя постить (проверка после вступления): {error_after}")
            # Помечаем как error (уже вступили, но нельзя постить)
            target.status = 'error'
            target.error_message = error_after
            target.updated_at = datetime.utcnow()
            await session.commit()
            return False, error_after
        
        # ШАГ 4: Можно постить - привязываем к аккаунту и устанавливаем warm-up
        now = datetime.utcnow()
        await db_manager.assign_group(
            group_link=group_link,
            account_id=account_id,
            joined_at=now
        )
        await session.commit()
        
        logger.info(f"  ✅ Группа {group_link} привязана к аккаунту {account_id}")
        logger.info(f"  ⏰ Warm-up период: 24 часа")
        return True, ""
        
    except (UsernameNotOccupiedError, ChannelPrivateError) as e:
        error_msg = f"Группа недоступна: {str(e)}"
        target.status = 'error'
        target.error_message = error_msg
        target.updated_at = datetime.utcnow()
        await session.commit()
        return False, error_msg
    except FloodWaitError as e:
        raise e  # Пробрасываем наверх
    except Exception as e:
        error_msg = f"Ошибка обработки: {str(e)}"
        logger.error(f"  ❌ {error_msg}")
        target.status = 'error'
        target.error_message = error_msg
        target.updated_at = datetime.utcnow()
        await session.commit()
        return False, error_msg


async def create_client(account_config: dict) -> TelegramClient:
    """Создание TelegramClient для аккаунта"""
    session_name = account_config['session_name']
    string_session = account_config.get('string_session')
    api_id = account_config.get('api_id')
    api_hash = account_config.get('api_hash')
    
    client = TelegramClient(
        StringSession(string_session),
        int(api_id),
        api_hash
    )
    await client.connect()
    
    if not await client.is_user_authorized():
        raise Exception(f"Аккаунт {session_name} не авторизован")
    
    return client


async def main():
    """Основная функция"""
    # Загружаем конфигурацию аккаунтов
    accounts_config_path = Path('ukraine_accounts_config.json')
    if not accounts_config_path.is_file():
        accounts_config_path = Path('/app/ukraine_accounts_config.json')
    if not accounts_config_path.is_file():
        accounts_config_path = Path('accounts_config.json')
    if not accounts_config_path.is_file():
        accounts_config_path = Path('/app/accounts_config.json')
    
    if not accounts_config_path.is_file():
        logger.error(f"❌ Файл конфигурации аккаунтов не найден")
        return
    
    with open(accounts_config_path, 'r', encoding='utf-8') as f:
        accounts_list = json.load(f)
    
    if not accounts_list:
        logger.error("❌ Нет аккаунтов в конфигурации")
        return
    
    # Фильтруем только Ukraine аккаунты (если используем общий конфиг)
    # Ukraine аккаунты: promotion_dao_bro, promotion_alex_ever, promotion_rod_shaihutdinov
    ukraine_accounts = ['promotion_dao_bro', 'promotion_alex_ever', 'promotion_rod_shaihutdinov']
    if len(accounts_list) > 3:  # Если больше 3 аккаунтов - фильтруем
        accounts_list = [acc for acc in accounts_list if acc.get('session_name') in ukraine_accounts]
        logger.info(f"📋 Отфильтровано до {len(accounts_list)} Ukraine аккаунтов")
    
    if not accounts_list:
        logger.error("❌ Нет Ukraine аккаунтов в конфигурации")
        return
    
    logger.info(f"📋 Загружено {len(accounts_list)} аккаунтов: {[acc.get('session_name') for acc in accounts_list]}")
    
    # Подключаемся к БД
    async with AsyncSessionLocal() as session:
        db_manager = DbManager(session)
        
        # Получаем все группы со статусом 'new'
        stmt = select(Target).where(
            Target.status == 'new',
            Target.niche == 'ukraine_cars'
        ).order_by(Target.id)
        
        result = await session.execute(stmt)
        targets = result.scalars().all()
        
        total = len(targets)
        logger.info(f"📋 Найдено {total} групп для обработки")
        
        if total == 0:
            logger.info("✅ Нет групп для обработки")
            return
        
        # Создаем клиенты для всех аккаунтов
        clients = {}
        account_configs = {}
        
        for acc_config in accounts_list:
            try:
                session_name = acc_config['session_name']
                logger.info(f"📱 Подключаемся к аккаунту: {session_name}")
                client = await create_client(acc_config)
                clients[session_name] = client
                account_configs[session_name] = acc_config
                logger.info(f"  ✅ Аккаунт {session_name} подключен")
            except Exception as e:
                logger.error(f"  ❌ Ошибка подключения к {session_name}: {e}")
        
        if not clients:
            logger.error("❌ Не удалось подключиться ни к одному аккаунту")
            return
        
        logger.info(f"✅ Подключено {len(clients)} аккаунтов")
        
        # Получаем ID аккаунтов из БД
        account_ids = {}
        for session_name, acc_config in account_configs.items():
            account = await db_manager.get_account_by_session_name(session_name)
            if account:
                account_ids[session_name] = account.id
        
        if not account_ids:
            logger.error("❌ Не найдены аккаунты в БД")
            return
        
        # Статистика (используем словари для thread-safe операций)
        stats = {
            'processed': 0,
            'joined_count': 0,
            'error_count': 0
        }
        excluded_accounts = {}  # Аккаунты в FloodWait
        
        # Распределяем группы между аккаунтами по кругу (round-robin)
        account_groups: Dict[str, List] = defaultdict(list)
        account_list = list(account_ids.keys())
        
        for idx, target in enumerate(targets):
            account_key = account_list[idx % len(account_list)]
            account_groups[account_key].append((idx + 1, target))
        
        logger.info(f"\n📊 РАСПРЕДЕЛЕНИЕ ГРУПП:")
        for session_name, group_list in account_groups.items():
            logger.info(f"   {session_name}: {len(group_list)} групп")
        
        # Функция worker для обработки групп одним аккаунтом
        async def account_worker(session_name: str, account_id: int, client: TelegramClient, groups_queue: List):
            """Worker для обработки групп одним аккаунтом"""
            worker_processed = 0
            worker_joined = 0
            worker_errors = 0
            
            for global_idx, target in groups_queue:
                group_link = target.link
                logger.info(f"\n{'='*60}")
                logger.info(f"📋 [{global_idx}/{total}] Группа: {group_link}")
                logger.info(f"{'='*60}")
                logger.info(f"  👤 Аккаунт: {session_name} (id={account_id})")
                
                try:
                    # Обрабатываем группу
                    success, error_msg = await process_group_with_account(
                        client, account_id, target, db_manager, session
                    )
                    
                    if success:
                        worker_joined += 1
                        stats['joined_count'] += 1
                        # Пауза после успешного вступления (5-10 минут)
                        pause_seconds = random.randint(300, 600)
                        logger.info(f"  ⏸️  Пауза {pause_seconds} сек ({pause_seconds // 60} мин) перед следующей группой...")
                        await asyncio.sleep(pause_seconds)
                    else:
                        worker_errors += 1
                        stats['error_count'] += 1
                        # Короткая пауза после ошибки
                        await asyncio.sleep(30)
                    
                    worker_processed += 1
                    stats['processed'] += 1
                    
                except FloodWaitError as e:
                    wait_seconds = e.seconds
                    wait_until = datetime.utcnow() + timedelta(seconds=wait_seconds)
                    
                    logger.warning(f"  ⏳ FloodWait {wait_seconds} сек ({wait_seconds // 60} мин) для аккаунта {session_name}")
                    
                    # Помечаем аккаунт как недоступный
                    await db_manager.set_account_flood_wait(account_id, wait_until)
                    excluded_accounts[session_name] = wait_until
                    
                    if wait_seconds <= 600:
                        logger.info(f"  ⏸️  Ждем {wait_seconds} сек...")
                        await asyncio.sleep(wait_seconds)
                        excluded_accounts.pop(session_name, None)
                    else:
                        logger.warning(f"  🔒 Аккаунт {session_name} исключен до {wait_until}")
                        break  # Выходим из worker'а
                    
                except Exception as e:
                    logger.error(f"  ❌ Неожиданная ошибка: {e}", exc_info=True)
                    worker_errors += 1
                    stats['error_count'] += 1
                    await asyncio.sleep(30)
            
            logger.info(f"\n✅ Worker {session_name} завершил работу:")
            logger.info(f"   Обработано: {worker_processed}, Вступили: {worker_joined}, Ошибок: {worker_errors}")
        
        # Запускаем workers последовательно, чтобы избежать конфликтов с DB-сессией
        started = 0
        for session_name, account_id in account_ids.items():
            if session_name in clients and session_name in account_groups:
                client = clients[session_name]
                groups_queue = account_groups[session_name]
                started += 1
                logger.info(f"\n🚀 Запуск worker (последовательно): {session_name}")
                logger.info("="*60)
                await account_worker(session_name, account_id, client, groups_queue)
        
        # Закрываем все клиенты
        for client in clients.values():
            try:
                await client.disconnect()
            except:
                pass
        
        # Финальная статистика
        processed = stats['processed']
        joined_count = stats['joined_count']
        error_count = stats['error_count']
        
        logger.info("\n" + "="*60)
        logger.info("📊 РЕЗУЛЬТАТЫ ОБРАБОТКИ")
        logger.info("="*60)
        logger.info(f"✅ Всего обработано: {processed}")
        logger.info(f"✅ Вступили (можно постить): {joined_count}")
        logger.info(f"❌ Ошибки (нельзя постить): {error_count}")
        logger.info(f"📋 Осталось новых групп: {total - processed}")
        logger.info("="*60)


if __name__ == "__main__":
    asyncio.run(main())
