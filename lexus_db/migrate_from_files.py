#!/usr/bin/env python3
"""
Скрипт миграции данных из файлов в PostgreSQL БД для системы Lexus

Читает:
- targets.txt - список групп
- group_niches.json - маппинг групп на ниши
- group_account_assignments.json - привязка групп к аккаунтам (опционально)
- accounts_config.json - список аккаунтов (для создания записей в accounts)

Импортирует в БД:
- accounts - из accounts_config.json (только Lexus аккаунты)
- targets - из targets.txt и group_niches.json
- Привязки групп к аккаунтам - из group_account_assignments.json (если есть)
"""
import asyncio
import json
import sys
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Optional, Set

# Добавляем корень проекта в путь
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from lexus_db.session import AsyncSessionLocal, init_db, get_database_url
from lexus_db.models import Account, Target
from lexus_db.db_manager import DbManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_accounts_config(config_file: str = 'accounts_config.json') -> list:
    """Загрузка конфигурации аккаунтов"""
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            accounts = json.load(f)
        logger.info(f"✅ Loaded {len(accounts)} accounts from {config_file}")
        return accounts
    except FileNotFoundError:
        logger.error(f"❌ Config file {config_file} not found")
        return []
    except json.JSONDecodeError as e:
        logger.error(f"❌ Invalid JSON in {config_file}: {e}")
        return []


def load_lexus_accounts_config(config_file: str = 'lexus_accounts_config.json') -> Set[str]:
    """Загрузка списка разрешенных аккаунтов для Lexus"""
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        allowed_accounts = set(config.get('allowed_accounts', []))
        logger.info(f"✅ Loaded {len(allowed_accounts)} Lexus accounts from {config_file}")
        return allowed_accounts
    except FileNotFoundError:
        logger.warning(f"⚠️ Config file {config_file} not found, using all accounts")
        return set()
    except json.JSONDecodeError as e:
        logger.warning(f"⚠️ Invalid JSON in {config_file}: {e}, using all accounts")
        return set()


def load_targets(file_path: str = 'targets.txt') -> list:
    """Загрузка списка групп из targets.txt"""
    try:
        targets = []
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    targets.append(line)
        logger.info(f"✅ Loaded {len(targets)} targets from {file_path}")
        return targets
    except FileNotFoundError:
        logger.warning(f"⚠️ File {file_path} not found")
        return []


def load_group_niches(file_path: str = 'group_niches.json') -> Dict[str, str]:
    """Загрузка маппинга групп на ниши"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            niches = json.load(f)
        logger.info(f"✅ Loaded {len(niches)} group-niche mappings from {file_path}")
        return niches
    except FileNotFoundError:
        logger.warning(f"⚠️ File {file_path} not found")
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"❌ Invalid JSON in {file_path}: {e}")
        return {}


def load_group_assignments(file_path: str = 'group_account_assignments.json') -> Dict[str, Dict]:
    """Загрузка привязки групп к аккаунтам"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            assignments = json.load(f)
        logger.info(f"✅ Loaded {len(assignments)} group-account assignments from {file_path}")
        return assignments
    except FileNotFoundError:
        logger.info(f"ℹ️ File {file_path} not found, skipping assignments")
        return {}
    except json.JSONDecodeError as e:
        logger.warning(f"⚠️ Invalid JSON in {file_path}: {e}, skipping assignments")
        return {}


def normalize_group_link(link: str) -> str:
    """Нормализация ссылки на группу"""
    link = link.strip()
    
    if link.startswith('https://'):
        link = link[8:]
    elif link.startswith('http://'):
        link = link[7:]
    
    if link.startswith('t.me/'):
        link = link[5:]
    elif link.startswith('telegram.me/'):
        link = link[12:]
    
    if not link.startswith('@'):
        link = '@' + link
    
    return link


async def migrate_accounts(session, accounts_config: list, lexus_allowed: Set[str]) -> Dict[str, int]:
    """
    Миграция аккаунтов в БД
    
    Returns:
        Словарь {session_name: account_id}
    """
    logger.info("=" * 80)
    logger.info("📥 MIGRATING ACCOUNTS")
    logger.info("=" * 80)
    
    account_id_map = {}
    created_count = 0
    updated_count = 0
    
    # Фильтруем только Lexus аккаунты
    lexus_accounts = [
        acc for acc in accounts_config
        if acc.get('session_name') in lexus_allowed
    ]
    
    if not lexus_allowed:
        logger.warning("⚠️ No Lexus accounts whitelist, migrating ALL accounts")
        lexus_accounts = accounts_config
    
    logger.info(f"📋 Migrating {len(lexus_accounts)} Lexus accounts")
    
    for acc_config in lexus_accounts:
        session_name = acc_config.get('session_name')
        if not session_name:
            logger.warning(f"⚠️ Account without session_name, skipping: {acc_config}")
            continue
        
        # Проверяем, существует ли аккаунт
        from sqlalchemy import select
        stmt = select(Account).where(Account.session_name == session_name)
        result = await session.execute(stmt)
        existing_account = result.scalar_one_or_none()
        
        if existing_account:
            # Обновляем существующий
            existing_account.phone = acc_config.get('phone')
            existing_account.session_string = acc_config.get('string_session')
            existing_account.updated_at = datetime.utcnow()
            account_id_map[session_name] = existing_account.id
            updated_count += 1
            logger.debug(f"  🔄 Updated account: {session_name}")
        else:
            # Создаем новый
            new_account = Account(
                session_name=session_name,
                phone=acc_config.get('phone'),
                session_string=acc_config.get('string_session'),
                status='active',
                daily_posts_count=0,
                last_stats_reset=datetime.utcnow()
            )
            session.add(new_account)
            await session.flush()  # Чтобы получить ID
            account_id_map[session_name] = new_account.id
            created_count += 1
            logger.debug(f"  ✅ Created account: {session_name} (id={new_account.id})")
    
    await session.commit()
    logger.info(f"✅ Accounts migration complete: {created_count} created, {updated_count} updated")
    logger.info(f"   Total accounts in map: {len(account_id_map)}")
    
    return account_id_map


async def migrate_targets(
    session,
    targets_list: list,
    group_niches: Dict[str, str],
    account_id_map: Dict[str, int],
    assignments: Dict[str, Dict]
) -> int:
    """
    Миграция групп в БД
    
    Returns:
        Количество созданных/обновленных групп
    """
    logger.info("=" * 80)
    logger.info("📥 MIGRATING TARGETS (GROUPS)")
    logger.info("=" * 80)
    
    created_count = 0
    updated_count = 0
    assigned_count = 0
    
    from sqlalchemy import select
    
    for target_link in targets_list:
        normalized_link = normalize_group_link(target_link)
        
        # Определяем нишу
        niche = group_niches.get(target_link, group_niches.get(normalized_link, 'ukraine_cars'))
        
        # Проверяем, существует ли группа
        stmt = select(Target).where(Target.link == normalized_link)
        result = await session.execute(stmt)
        existing_target = result.scalar_one_or_none()
        
        if existing_target:
            # Обновляем существующую
            if existing_target.niche != niche:
                existing_target.niche = niche
            existing_target.updated_at = datetime.utcnow()
            updated_count += 1
            target = existing_target
        else:
            # Создаем новую
            target = Target(
                link=normalized_link,
                niche=niche,
                status='new',  # По умолчанию 'new', будет 'joined' после вступления
                daily_posts_in_group=0,
                last_group_stats_reset=datetime.utcnow()
            )
            session.add(target)
            await session.flush()  # Чтобы получить ID
            created_count += 1
        
        # Привязываем к аккаунту, если есть assignment
        assignment = assignments.get(target_link) or assignments.get(normalized_link)
        if assignment:
            assigned_account_name = assignment.get('account_name') or assignment.get('account')
            if assigned_account_name and assigned_account_name in account_id_map:
                account_id = account_id_map[assigned_account_name]
                
                # Парсим joined_at из assignment
                joined_at_str = assignment.get('joined_at') or assignment.get('joined_at_iso')
                if joined_at_str:
                    try:
                        joined_at = datetime.fromisoformat(joined_at_str.replace('Z', '+00:00'))
                    except:
                        joined_at = datetime.utcnow() - timedelta(hours=24)  # По умолчанию минус 24 часа
                else:
                    # Если нет даты вступления, считаем что вступили 24 часа назад (warm-up уже прошел)
                    joined_at = datetime.utcnow() - timedelta(hours=24)
                
                # Привязываем
                target.assigned_account_id = account_id
                target.status = 'joined'
                target.set_warmup_ends_at(joined_at)
                assigned_count += 1
                logger.debug(
                    f"  🔗 Assigned {normalized_link} to {assigned_account_name} "
                    f"(joined_at={joined_at}, warmup_ends_at={target.warmup_ends_at})"
                )
    
    await session.commit()
    logger.info(f"✅ Targets migration complete:")
    logger.info(f"   Created: {created_count}")
    logger.info(f"   Updated: {updated_count}")
    logger.info(f"   Assigned to accounts: {assigned_count}")
    
    return created_count + updated_count


async def main():
    """Основная функция миграции"""
    logger.info("=" * 80)
    logger.info("🚀 LEXUS DATABASE MIGRATION FROM FILES")
    logger.info("=" * 80)
    logger.info(f"Database URL: {get_database_url().replace(get_database_url().split('@')[0].split('//')[1], '***')}")
    
    # Проверяем наличие файлов
    base_dir = Path('.')
    targets_file = base_dir / 'targets.txt'
    niches_file = base_dir / 'group_niches.json'
    accounts_file = base_dir / 'accounts_config.json'
    lexus_config_file = base_dir / 'lexus_accounts_config.json'
    assignments_file = base_dir / 'group_account_assignments.json'
    
    if not targets_file.exists():
        logger.error(f"❌ {targets_file} not found!")
        return
    
    if not niches_file.exists():
        logger.error(f"❌ {niches_file} not found!")
        return
    
    if not accounts_file.exists():
        logger.error(f"❌ {accounts_file} not found!")
        return
    
    # Загружаем данные из файлов
    logger.info("\n📂 Loading data from files...")
    targets_list = load_targets(str(targets_file))
    group_niches = load_group_niches(str(niches_file))
    accounts_config = load_accounts_config(str(accounts_file))
    lexus_allowed = load_lexus_accounts_config(str(lexus_config_file))
    assignments = load_group_assignments(str(assignments_file))
    
    if not targets_list:
        logger.error("❌ No targets to migrate!")
        return
    
    if not accounts_config:
        logger.error("❌ No accounts to migrate!")
        return
    
    # Инициализируем БД
    logger.info("\n🗄️ Initializing database...")
    try:
        await init_db()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize database: {e}", exc_info=True)
        return
    
    # Выполняем миграцию
    async with AsyncSessionLocal() as session:
        try:
            # Мигрируем аккаунты
            account_id_map = await migrate_accounts(session, accounts_config, lexus_allowed)
            
            if not account_id_map:
                logger.error("❌ No accounts migrated, cannot continue!")
                return
            
            # Мигрируем группы
            await migrate_targets(session, targets_list, group_niches, account_id_map, assignments)
            
            logger.info("=" * 80)
            logger.info("✅ MIGRATION COMPLETE!")
            logger.info("=" * 80)
            
        except Exception as e:
            await session.rollback()
            logger.error(f"❌ Migration failed: {e}", exc_info=True)
            raise


if __name__ == "__main__":
    asyncio.run(main())
