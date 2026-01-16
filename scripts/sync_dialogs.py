#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Синхронизация существующих групп из Telegram с базой данных
Импортирует все группы, где аккаунты уже состоят, и помечает их как активные
"""
import asyncio
import sys
import logging
from pathlib import Path
from datetime import datetime, timedelta
from telethon.tl.types import Channel, Chat

# Добавляем корень проекта в PYTHONPATH
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from shared.database.session import SessionLocal
from shared.database.models import Group, Account
from shared.telegram.client_manager import TelegramClientManager

# Настройка логирования
log_dir = Path('/app/logs')
if not log_dir.exists():
    log_dir = project_root / 'logs'
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(str(log_dir / 'sync_dialogs.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


async def sync_existing_chats():
    """Синхронизация диалогов из Telegram с базой данных"""
    
    db = SessionLocal()
    client_manager = TelegramClientManager()
    
    try:
        # 1. Загружаем аккаунты и создаем клиенты
        logger.info("🔄 Загружаю аккаунты из базы данных...")
        await client_manager.load_accounts_from_db(db)
        clients = client_manager.clients
        
        if not clients:
            logger.error("❌ Нет доступных аккаунтов для синхронизации")
            return
        
        logger.info(f"✅ Загружено {len(clients)} аккаунтов")
        logger.info("=" * 80)
        
        total_added = 0
        total_updated = 0
        total_skipped = 0
        
        # 2. Обрабатываем каждый аккаунт
        for session_name, client in clients.items():
            try:
                # Проверяем подключение
                if not client.is_connected():
                    logger.info(f"📱 Подключаюсь к аккаунту: {session_name}")
                    await client.connect()
                
                # Получаем информацию об аккаунте
                try:
                    me = await client.get_me()
                    account_name = me.username or me.first_name or session_name
                    logger.info(f"📱 Сканирую чаты для: {account_name} ({session_name})")
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось получить информацию об аккаунте {session_name}: {e}")
                    continue
                
                # Получаем аккаунт из БД для привязки групп
                db_account = db.query(Account).filter(Account.session_name == session_name).first()
                if not db_account:
                    logger.warning(f"⚠️ Аккаунт {session_name} не найден в БД, пропускаю")
                    continue
                
                # Получаем диалоги (группы и каналы)
                groups_processed = 0
                async for dialog in client.iter_dialogs():
                    entity = dialog.entity
                    
                    # Нас интересуют только группы и каналы (не личные чаты)
                    if not isinstance(entity, (Channel, Chat)):
                        continue
                    
                    # Пропускаем, если мы вышли из группы или нас забанили
                    if isinstance(entity, Channel):
                        if getattr(entity, 'left', False) or getattr(entity, 'kicked', False):
                            total_skipped += 1
                            continue
                    
                    # Получаем username группы
                    group_username = getattr(entity, 'username', None)
                    if not group_username:
                        # Пропускаем группы без username (приватные группы сложнее обрабатывать)
                        total_skipped += 1
                        continue
                    
                    # Формируем username с @
                    if not group_username.startswith('@'):
                        group_username = f'@{group_username}'
                    
                    group_title = getattr(entity, 'title', 'Unknown')
                    
                    # Получаем количество участников, если доступно
                    members_count = None
                    if isinstance(entity, Channel):
                        members_count = getattr(entity, 'participants_count', None)
                    elif isinstance(entity, Chat):
                        members_count = getattr(entity, 'participants_count', None)
                    
                    # Проверяем, есть ли группа в БД
                    db_group = db.query(Group).filter(Group.username == group_username).first()
                    
                    # Ставим дату вступления 3 дня назад, чтобы обойти warm-up
                    past_date = datetime.utcnow() - timedelta(days=3)
                    warm_up_until = past_date  # Warm-up уже прошел
                    
                    if not db_group:
                        # ДОБАВЛЯЕМ НОВУЮ ГРУППУ (существующая в ТГ, но новая в БД)
                        try:
                            new_group = Group(
                                username=group_username,
                                title=group_title,
                                niche='general',  # По умолчанию, можно изменить позже
                                assigned_account_id=db_account.id,
                                status='active',  # СРАЗУ АКТИВНА
                                joined_at=past_date,
                                warm_up_until=warm_up_until,
                                can_post=True,
                                members_count=members_count
                            )
                            db.add(new_group)
                            db.commit()
                            total_added += 1
                            groups_processed += 1
                            logger.info(f"  ➕ Добавлена существующая группа: {group_username} ({group_title})")
                        except Exception as e:
                            db.rollback()
                            logger.error(f"  ❌ Ошибка при добавлении {group_username}: {e}")
                            continue
                    else:
                        # ОБНОВЛЯЕМ СУЩЕСТВУЮЩУЮ ГРУППУ
                        updated = False
                        try:
                            if db_group.status != 'active':
                                db_group.status = 'active'
                                updated = True
                            
                            if not db_group.can_post:
                                db_group.can_post = True
                                updated = True
                            
                            # Если даты вступления нет, ставим старую
                            if not db_group.joined_at:
                                db_group.joined_at = past_date
                                db_group.warm_up_until = warm_up_until
                                updated = True
                            
                            # Обновляем информацию о группе
                            if db_group.title != group_title:
                                db_group.title = group_title
                                updated = True
                            
                            if members_count and (not db_group.members_count or db_group.members_count != members_count):
                                db_group.members_count = members_count
                                updated = True
                            
                            # Привязываем к аккаунту, если не привязана
                            if not db_group.assigned_account_id:
                                db_group.assigned_account_id = db_account.id
                                updated = True
                            
                            if updated:
                                db.commit()
                                total_updated += 1
                                groups_processed += 1
                                logger.info(f"  🔄 Активирована группа из базы: {group_username}")
                        
                        except Exception as e:
                            db.rollback()
                            logger.error(f"  ❌ Ошибка при обновлении {group_username}: {e}")
                            continue
                
                logger.info(f"  ✅ Обработано групп для {account_name}: {groups_processed}")
                
            except Exception as e:
                logger.error(f"❌ Ошибка при обработке аккаунта {session_name}: {e}", exc_info=True)
                continue
        
        # Итоги
        logger.info("")
        logger.info("=" * 80)
        logger.info("✅ ИТОГ СИНХРОНИЗАЦИИ:")
        logger.info(f"   ➕ Добавлено новых (забытых) групп: {total_added}")
        logger.info(f"   🔄 Активировано старых групп: {total_updated}")
        logger.info(f"   ⏭️  Пропущено (без username или недоступные): {total_skipped}")
        logger.info(f"   📊 Всего обработано: {total_added + total_updated}")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
    finally:
        db.close()


if __name__ == "__main__":
    try:
        asyncio.run(sync_existing_chats())
    except KeyboardInterrupt:
        logger.info("🛑 Синхронизация прервана пользователем")
    except Exception as e:
        logger.error(f"❌ Фатальная ошибка: {e}", exc_info=True)
        sys.exit(1)
