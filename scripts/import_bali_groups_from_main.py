#!/usr/bin/env python3
"""
Импорт групп по Бали из основной системы в систему Бали
"""
import sys
import subprocess
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

# Импорт для БД Бали
import os
os.environ['DATABASE_URL'] = 'postgresql://telegram_user_bali:telegram_password_bali@localhost:5438/telegram_promotion_bali'

from shared.database.session import SessionLocal as BaliSessionLocal
from shared.database.models import Group as BaliGroup, Account as BaliAccount

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_main_db_groups():
    """Получить группы из основной БД через docker exec"""
    # Пробуем найти контейнер основной системы
    result = subprocess.run(['docker', 'ps', '--format', '{{.Names}}'], capture_output=True, text=True)
    container_name = None
    for name in ['telegram-combine-postgres', 'telegram-postgres', 'telegram_promotion_system-postgres-1']:
        if name in result.stdout:
            container_name = name
            break
    
    if not container_name:
        logger.error("Контейнер основной БД не найден. Доступные контейнеры:")
        logger.error(result.stdout)
        return []
    
    logger.info(f"Используется контейнер: {container_name}")
    
    cmd = [
        'docker', 'exec', '-i', container_name,
        'psql', '-U', 'telegram_user', '-d', 'telegram_promotion', '-t', '-A', '-F', '|',
        '-c', """
        SELECT 
            COALESCE(username, ''),
            COALESCE(title, ''),
            COALESCE(niche, ''),
            COALESCE(status, ''),
            can_post,
            joined_at,
            warm_up_until,
            assigned_account_id,
            members_count,
            created_at
        FROM groups 
        WHERE (niche LIKE '%bali%' OR LOWER(username) LIKE '%bali%')
        ORDER BY username;
        """
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return parse_groups_output(result.stdout)
    except subprocess.CalledProcessError as e:
        logger.error(f"Ошибка при получении групп из основной БД: {e}")
        logger.error(f"Stdout: {e.stdout}")
        logger.error(f"Stderr: {e.stderr}")
        return []
    except FileNotFoundError:
        logger.error("Docker не найден или контейнер telegram-postgres не запущен")
        return []


def parse_groups_output(output):
    """Распарсить вывод psql"""
    groups = []
    for line in output.strip().split('\n'):
        if not line or line.startswith('(') or '|' not in line:
            continue
        parts = line.split('|')
        if len(parts) >= 10:
            try:
                groups.append({
                    'username': parts[0].strip() if parts[0] else None,
                    'title': parts[1].strip() if parts[1] else None,
                    'niche': parts[2].strip() if parts[2] else 'bali',
                    'status': parts[3].strip() if parts[3] else 'new',
                    'can_post': parts[4].strip() == 't',
                    'joined_at': parse_date(parts[5].strip()) if parts[5].strip() else None,
                    'warm_up_until': parse_date(parts[6].strip()) if parts[6].strip() else None,
                    'assigned_account_id': int(parts[7]) if parts[7].strip() and parts[7].strip().isdigit() else None,
                    'members_count': int(parts[8]) if parts[8].strip() and parts[8].strip().isdigit() else None,
                    'created_at': parse_date(parts[9].strip()) if parts[9].strip() else None
                })
            except Exception as e:
                logger.warning(f"Ошибка парсинга строки: {line[:50]}... - {e}")
    return groups


def parse_date(date_str):
    """Парсинг даты"""
    if not date_str or date_str.strip() == '':
        return None
    try:
        # Пробуем разные форматы
        for fmt in ['%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d']:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except:
                continue
        return None
    except:
        return None


def get_account_mapping(bali_db):
    """Получить маппинг аккаунтов между БД"""
    mapping = {}
    
    # Пробуем найти контейнер основной системы
    result = subprocess.run(['docker', 'ps', '--format', '{{.Names}}'], capture_output=True, text=True)
    container_name = None
    for name in ['telegram-combine-postgres', 'telegram-postgres', 'telegram_promotion_system-postgres-1']:
        if name in result.stdout:
            container_name = name
            break
    
    if not container_name:
        logger.warning("Контейнер основной БД не найден, маппинг аккаунтов будет пустым")
        return {}
    
    # Получаем аккаунты из основной БД через docker exec
    cmd = [
        'docker', 'exec', '-i', container_name,
        'psql', '-U', 'telegram_user', '-d', 'telegram_promotion', '-t', '-A', '-F', '|',
        '-c', "SELECT id, session_name FROM accounts WHERE status = 'active' ORDER BY session_name;"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        main_accounts = {}
        for line in result.stdout.strip().split('\n'):
            if '|' in line:
                parts = line.split('|')
                if len(parts) >= 2:
                    main_id = int(parts[0].strip())
                    session_name = parts[1].strip()
                    main_accounts[main_id] = session_name
    except:
        logger.warning("Не удалось получить аккаунты из основной БД")
        return {}
    
    # Получаем аккаунты из БД Бали
    bali_accounts = {acc.session_name: acc.id for acc in bali_db.query(BaliAccount).all()}
    
    # Создаём маппинг
    for main_id, session_name in main_accounts.items():
        if session_name in bali_accounts:
            mapping[main_id] = bali_accounts[session_name]
            logger.info(f"  ✅ {session_name}: {main_id} → {bali_accounts[session_name]}")
    
    return mapping


def import_groups():
    """Импортировать группы по Бали из основной системы"""
    logger.info("=" * 80)
    logger.info("🔄 ИМПОРТ ГРУПП ПО БАЛИ ИЗ ОСНОВНОЙ СИСТЕМЫ")
    logger.info("=" * 80)
    
    bali_db = BaliSessionLocal()
    
    try:
        # Получаем группы из основной системы
        logger.info("\n📥 Получение групп из основной системы...")
        main_groups = get_main_db_groups()
        
        logger.info(f"📊 Найдено групп по Бали в основной системе: {len(main_groups)}")
        
        if len(main_groups) == 0:
            logger.warning("⚠️  Группы не найдены в основной системе")
            return
        
        # Получаем маппинг аккаунтов
        logger.info("\n📋 Маппинг аккаунтов:")
        account_mapping = get_account_mapping(bali_db)
        
        imported = 0
        updated = 0
        skipped = 0
        
        logger.info(f"\n🔄 Импорт групп...")
        
        for main_group in main_groups:
            if not main_group['username']:
                continue
                
            try:
                # Проверяем, есть ли уже в БД Бали
                existing = bali_db.query(BaliGroup).filter(
                    BaliGroup.username == main_group['username']
                ).first()
                
                if existing:
                    # Обновляем существующую
                    existing.title = main_group['title'] or existing.title
                    existing.status = main_group['status']
                    existing.can_post = main_group['can_post']
                    existing.joined_at = main_group['joined_at']
                    existing.warm_up_until = main_group['warm_up_until']
                    
                    # Маппим аккаунт
                    if main_group['assigned_account_id'] and main_group['assigned_account_id'] in account_mapping:
                        existing.assigned_account_id = account_mapping[main_group['assigned_account_id']]
                    
                    existing.members_count = main_group['members_count']
                    existing.niche = 'bali'
                    existing.updated_at = datetime.utcnow()
                    
                    updated += 1
                    logger.info(f"  ✅ Обновлена: {main_group['username']} (статус: {main_group['status']}, вступил: {main_group['joined_at'] is not None})")
                else:
                    # Создаём новую
                    new_group = BaliGroup(
                        username=main_group['username'],
                        title=main_group['title'] or f"Group: {main_group['username']}",
                        niche='bali',
                        status=main_group['status'],
                        can_post=main_group['can_post'],
                        joined_at=main_group['joined_at'],
                        warm_up_until=main_group['warm_up_until'],
                        members_count=main_group['members_count'],
                        created_at=main_group['created_at'] or datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    
                    # Маппим аккаунт
                    if main_group['assigned_account_id'] and main_group['assigned_account_id'] in account_mapping:
                        new_group.assigned_account_id = account_mapping[main_group['assigned_account_id']]
                    
                    bali_db.add(new_group)
                    imported += 1
                    logger.info(f"  ✅ Импортирована: {main_group['username']} (статус: {main_group['status']}, вступил: {main_group['joined_at'] is not None})")
                
                bali_db.commit()
                
            except Exception as e:
                bali_db.rollback()
                logger.error(f"  ❌ Ошибка при импорте {main_group.get('username', 'unknown')}: {e}")
                skipped += 1
        
        logger.info("")
        logger.info("=" * 80)
        logger.info("📊 ИТОГИ ИМПОРТА:")
        logger.info(f"   ✅ Импортировано: {imported}")
        logger.info(f"   🔄 Обновлено: {updated}")
        logger.info(f"   ⚠️  Пропущено: {skipped}")
        logger.info("=" * 80)
        
        # Статистика после импорта
        logger.info("\n📊 Статистика групп в БД Бали:")
        total = bali_db.query(BaliGroup).filter(BaliGroup.niche == 'bali').count()
        active = bali_db.query(BaliGroup).filter(
            BaliGroup.niche == 'bali',
            BaliGroup.status == 'active'
        ).count()
        joined = bali_db.query(BaliGroup).filter(
            BaliGroup.niche == 'bali',
            BaliGroup.joined_at.isnot(None)
        ).count()
        
        logger.info(f"   Всего групп: {total}")
        logger.info(f"   Активных: {active}")
        logger.info(f"   Вступили: {joined}")
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
        bali_db.rollback()
    finally:
        bali_db.close()


if __name__ == "__main__":
    import_groups()
