#!/usr/bin/env python3
"""
Импорт групп из targets.txt и group_niches.json в PostgreSQL БД
"""
import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.database.session import SessionLocal, init_db
from shared.database.models import Group
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def import_groups(base_dir: Path, niche: str = 'cars'):
    """
    Импортирует группы из targets.txt и group_niches.json
    
    Args:
        base_dir: Базовая директория проекта
        niche: Ниша для групп (по умолчанию 'cars')
    """
    logger.info("=" * 80)
    logger.info(f"📥 IMPORTING GROUPS (niche: {niche})")
    logger.info("=" * 80)
    
    # Инициализация БД
    try:
        init_db()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize database: {e}")
        return
    
    targets_file = base_dir / "targets.txt"
    niches_file = base_dir / "group_niches.json"
    
    # Читаем targets.txt
    groups_list = []
    if targets_file.exists():
        logger.info(f"📄 Reading {targets_file}")
        with open(targets_file, 'r', encoding='utf-8') as f:
            for line in f:
                username = line.strip()
                if username and username.startswith('@'):
                    groups_list.append(username)
        logger.info(f"Found {len(groups_list)} groups in targets.txt")
    else:
        logger.warning(f"⚠️ {targets_file} not found")
        return
    
    # Читаем group_niches.json
    niches_map = {}
    if niches_file.exists():
        logger.info(f"📄 Reading {niches_file}")
        with open(niches_file, 'r', encoding='utf-8') as f:
            niches_map = json.load(f)
        logger.info(f"Found {len(niches_map)} group niches")
    else:
        logger.warning(f"⚠️ {niches_file} not found, using default niche for all groups")
    
    db = SessionLocal()
    try:
        imported = 0
        updated = 0
        skipped = 0
        
        for username in groups_list:
            try:
                # Определяем нишу для группы
                group_niche = niches_map.get(username, niche)
                
                # Если ниша не соответствует требуемой - пропускаем (или меняем нишу)
                if niche != 'all' and group_niche != niche:
                    skipped += 1
                    continue
                
                # Проверяем, есть ли уже такая группа
                existing = db.query(Group).filter(Group.username == username).first()
                
                if existing:
                    # Обновляем существующую группу
                    existing.niche = group_niche
                    existing.status = 'active'  # Активируем группу
                    updated += 1
                else:
                    # Создаем новую группу
                    new_group = Group(
                        username=username,
                        niche=group_niche,
                        status='active',
                        can_post=True
                    )
                    db.add(new_group)
                    imported += 1
                
                # Коммитим после каждой группы (для безопасности)
                db.commit()
                
            except Exception as e:
                db.rollback()
                logger.error(f"❌ Error processing {username}: {e}")
                skipped += 1
        
        logger.info("=" * 80)
        logger.info(f"✅ Import completed:")
        logger.info(f"   - Imported: {imported}")
        logger.info(f"   - Updated: {updated}")
        logger.info(f"   - Skipped: {skipped}")
        logger.info(f"   - Total processed: {len(groups_list)}")
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Error during import: {e}")
    finally:
        db.close()


def import_assignments(base_dir: Path):
    """
    Импортирует привязки аккаунтов к группам из group_account_assignments.json (если существует)
    """
    assignments_file = base_dir / "group_account_assignments.json"
    
    if not assignments_file.exists():
        logger.info("ℹ️ group_account_assignments.json not found, skipping assignments import")
        return
    
    logger.info(f"📄 Reading assignments from {assignments_file}")
    
    with open(assignments_file, 'r', encoding='utf-8') as f:
        assignments = json.load(f)
    
    db = SessionLocal()
    try:
        from shared.database.models import Account
        
        updated = 0
        
        for username, data in assignments.items():
            try:
                # Находим группу
                group = db.query(Group).filter(Group.username == username).first()
                if not group:
                    logger.warning(f"⚠️ Group {username} not found in DB, skipping")
                    continue
                
                # Находим аккаунт
                account_name = data.get('account')
                if not account_name:
                    continue
                
                account = db.query(Account).filter(Account.session_name == account_name).first()
                if not account:
                    logger.warning(f"⚠️ Account {account_name} not found in DB, skipping")
                    continue
                
                # Обновляем привязку
                group.assigned_account_id = account.id
                
                # Парсим даты
                if data.get('joined_at'):
                    try:
                        group.joined_at = datetime.fromisoformat(data['joined_at'].replace('Z', '+00:00'))
                    except:
                        pass
                
                if data.get('warm_up_until'):
                    try:
                        group.warm_up_until = datetime.fromisoformat(data['warm_up_until'].replace('Z', '+00:00'))
                    except:
                        pass
                
                db.commit()
                updated += 1
                
            except Exception as e:
                db.rollback()
                logger.error(f"❌ Error processing assignment for {username}: {e}")
        
        logger.info(f"✅ Updated {updated} group assignments")
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Error importing assignments: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Import groups from targets.txt')
    parser.add_argument('--niche', default='cars', help='Niche to import (default: cars)')
    parser.add_argument('--all', action='store_true', help='Import all niches')
    args = parser.parse_args()
    
    base_dir = Path(__file__).parent.parent
    
    niche = 'all' if args.all else args.niche
    import_groups(base_dir, niche=niche)
    
    # Пытаемся импортировать привязки
    import_assignments(base_dir)

