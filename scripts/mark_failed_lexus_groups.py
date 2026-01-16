#!/usr/bin/env python3
"""
Пометка групп Lexus как недоступных на основе ошибок из логов
"""
import sys
import re
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.database.session import SessionLocal, init_db
from shared.database.models import Group
from sqlalchemy import func

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def mark_failed_lexus_groups():
    """Пометить группы с ошибками как недоступные"""
    logger.info("=" * 80)
    logger.info("🔍 ПОМЕТКА ПРОБЛЕМНЫХ ГРУПП LEXUS")
    logger.info("=" * 80)
    
    init_db()
    db = SessionLocal()
    
    try:
        # Получаем все группы с нишей ukraine_cars
        ukraine_groups = db.query(Group).filter(
            Group.username.like('@%')
        ).all()
        
        # Список групп, которые нужно пометить (из логов)
        # Группы с ошибками "You can't write" или "Invalid channel"
        problem_groups = []
        
        # Читаем логи за последние 3 часа
        import subprocess
        result = subprocess.run(
            ['docker', 'logs', 'lexus-scheduler', '--since', '3h'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            log_content = result.stdout
            
            # Ищем группы с ошибками
            pattern = r"failed for (@\w+): (You can't write|Invalid channel)"
            matches = re.findall(pattern, log_content)
            
            # Считаем количество ошибок для каждой группы
            group_errors = {}
            for group, error_type in matches:
                if group not in group_errors:
                    group_errors[group] = {'write_forbidden': 0, 'invalid_channel': 0}
                if "can't write" in error_type:
                    group_errors[group]['write_forbidden'] += 1
                elif "Invalid" in error_type:
                    group_errors[group]['invalid_channel'] += 1
            
            logger.info(f"📋 Найдено проблемных групп в логах: {len(group_errors)}")
            
            # Помечаем группы
            marked = 0
            for group_username, errors in group_errors.items():
                group = db.query(Group).filter(Group.username == group_username).first()
                if not group:
                    logger.warning(f"  ⚠️ Группа {group_username} не найдена в БД")
                    continue
                
                # Если есть ошибки "can't write" для обоих аккаунтов - помечаем как banned
                total_errors = errors['write_forbidden'] + errors['invalid_channel']
                if total_errors >= 2:  # Ошибки от обоих аккаунтов
                    try:
                        if group.status != 'banned':
                            group.status = 'banned'
                            group.can_post = False
                            db.commit()
                            marked += 1
                            logger.info(f"  🚫 Помечена как banned: {group_username} ({total_errors} ошибок)")
                    except Exception as e:
                        logger.error(f"  ❌ Ошибка обновления {group_username}: {e}")
                        db.rollback()
        
        logger.info(f"\n✅ Помечено как banned: {marked} групп")
        
        # Статистика
        stats = db.query(Group.status, func.count(Group.id)).group_by(Group.status).all()
        logger.info("\n📊 Статистика по статусам:")
        for status, count in stats:
            logger.info(f"   {status}: {count}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    try:
        mark_failed_lexus_groups()
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)
