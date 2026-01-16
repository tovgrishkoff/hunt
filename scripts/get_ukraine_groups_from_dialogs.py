#!/usr/bin/env python3
"""
Получение групп из диалогов Ukraine аккаунтов и добавление их в БД для постинга
"""
import sys
import os
import asyncio
import logging
from pathlib import Path
from datetime import datetime
from telethon.tl.types import Channel, Chat

sys.path.insert(0, str(Path(__file__).parent.parent))

# Устанавливаем переменные для Ukraine БД
os.environ['DATABASE_URL'] = 'postgresql://telegram_user_ukraine:telegram_password_ukraine@localhost:5439/ukraine_db'
os.environ['POSTGRES_HOST'] = 'localhost'
os.environ['POSTGRES_PORT'] = '5439'
os.environ['POSTGRES_USER'] = 'telegram_user_ukraine'
os.environ['POSTGRES_PASSWORD'] = 'telegram_password_ukraine'
os.environ['POSTGRES_DB'] = 'ukraine_db'

from lexus_db.models import Account, Target
from lexus_db.session import AsyncSessionLocal
from shared.telegram.client_manager import TelegramClientManager
from sqlalchemy import select
from telethon import TelegramClient
from telethon.sessions import StringSession

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def get_groups_from_dialogs():
    """Получить группы из диалогов Ukraine аккаунтов"""
    logger.info("=" * 80)
    logger.info("🔄 ПОЛУЧЕНИЕ ГРУПП ИЗ ДИАЛОГОВ (UKRAINE)")
    logger.info("=" * 80)
    
    # Ukraine аккаунты
    ukraine_accounts = ['promotion_dao_bro', 'promotion_alex_ever', 'promotion_rod_shaihutdinov']
    
    async with AsyncSessionLocal() as session:
        # Получаем аккаунты из БД
        result = await session.execute(
            select(Account).where(Account.session_name.in_(ukraine_accounts))
        )
        accounts = result.scalars().all()
        
        if not accounts:
            logger.error("❌ Ukraine аккаунты не найдены в БД")
            return
        
        logger.info(f"✅ Найдено {len(accounts)} Ukraine аккаунтов")
        
        # Создаем клиенты
        clients_data = {}
        for account in accounts:
            if not account.string_session:
                logger.warning(f"⚠️ У {account.session_name} нет string_session, пропускаем")
                continue
            
            try:
                session_obj = StringSession(account.string_session.strip())
                client = TelegramClient(
                    session_obj,
                    account.api_id,
                    account.api_hash
                )
                await client.connect()
                
                if await client.is_user_authorized():
                    clients_data[account.session_name] = (client, account.id)
                    logger.info(f"✅ Подключен: {account.session_name}")
                else:
                    await client.disconnect()
                    logger.warning(f"⚠️ {account.session_name} не авторизован")
            except Exception as e:
                logger.error(f"❌ Ошибка подключения {account.session_name}: {e}")
        
        if not clients_data:
            logger.error("❌ Нет подключенных аккаунтов")
            return
        
        total_added = 0
        total_updated = 0
        
        # Получаем группы из диалогов каждого аккаунта
        for session_name, (client, account_id) in clients_data.items():
            try:
                logger.info(f"\n📱 Обработка аккаунта: {session_name}")
                
                # Получаем диалоги
                dialogs = await client.get_dialogs(limit=200)
                groups_found = 0
                
                for dialog in dialogs:
                    entity = dialog.entity
                    
                    # Нас интересуют только группы и каналы
                    if not isinstance(entity, (Channel, Chat)):
                        continue
                    
                    # Пропускаем, если мы вышли из группы
                    if isinstance(entity, Channel):
                        if getattr(entity, 'left', False) or getattr(entity, 'kicked', False):
                            continue
                    
                    # Получаем username группы
                    username = getattr(entity, 'username', None)
                    if not username:
                        continue
                    
                    username = f"@{username.lower()}"
                    title = getattr(entity, 'title', 'No title')
                    
                    # Проверяем, существует ли группа в БД
                    result = await session.execute(
                        select(Target).where(Target.username == username)
                    )
                    existing_group = result.scalar_one_or_none()
                    
                    if existing_group:
                        # Обновляем существующую группу
                        needs_update = False
                        if existing_group.status != 'joined':
                            existing_group.status = 'joined'
                            needs_update = True
                        if existing_group.assigned_account_id != account_id:
                            existing_group.assigned_account_id = account_id
                            needs_update = True
                        if existing_group.niche != 'ukraine_cars':
                            existing_group.niche = 'ukraine_cars'
                            needs_update = True
                        if not existing_group.can_post:
                            existing_group.can_post = True
                            needs_update = True
                        
                        if needs_update:
                            existing_group.title = title
                            existing_group.joined_at = datetime.utcnow()
                            existing_group.warm_up_until = datetime.utcnow()  # Уже прогреты
                            existing_group.updated_at = datetime.utcnow()
                            total_updated += 1
                            logger.info(f"  ✅ Обновлена: {title} (@{username})")
                    else:
                        # Создаем новую группу
                        new_group = Target(
                            username=username,
                            title=title,
                            niche='ukraine_cars',
                            status='joined',
                            assigned_account_id=account_id,
                            can_post=True,
                            joined_at=datetime.utcnow(),
                            warm_up_until=datetime.utcnow(),  # Уже прогреты
                            created_at=datetime.utcnow(),
                            updated_at=datetime.utcnow()
                        )
                        session.add(new_group)
                        total_added += 1
                        groups_found += 1
                        logger.info(f"  ✅ Добавлена: {title} (@{username})")
                
                await session.commit()
                logger.info(f"✅ {session_name}: добавлено {groups_found} новых групп")
                
            except Exception as e:
                logger.error(f"❌ Ошибка при обработке {session_name}: {e}", exc_info=True)
                await session.rollback()
            finally:
                try:
                    await client.disconnect()
                except:
                    pass
        
        logger.info("")
        logger.info("=" * 80)
        logger.info(f"✅ СИНХРОНИЗАЦИЯ ЗАВЕРШЕНА")
        logger.info("=" * 80)
        logger.info(f"📊 Добавлено новых групп: {total_added}")
        logger.info(f"📊 Обновлено существующих: {total_updated}")
        logger.info("=" * 80)


if __name__ == "__main__":
    try:
        asyncio.run(get_groups_from_dialogs())
    except KeyboardInterrupt:
        logger.info("\n🛑 Прервано пользователем")
    except Exception as e:
        logger.error(f"\n❌ Критическая ошибка: {e}", exc_info=True)
