#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Автоматическое добавление найденных украинских авто-групп в targets.txt и group_niches.json
Запускается после успешного вступления в группы
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from datetime import datetime

def setup_logging():
    """Настройка логирования"""
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    
    log_file = log_dir / 'add_ukraine_cars_to_targets.log'
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    return logging.getLogger(__name__)

def add_groups_to_targets(sync_assigned: bool = False):
    """Добавление найденных групп в targets.txt и group_niches.json"""
    logger = setup_logging()
    
    logger.info("=" * 80)
    logger.info("📝 ДОБАВЛЕНИЕ УКРАИНСКИХ АВТО-ГРУПП В РАССЫЛКУ")
    logger.info("=" * 80)
    
    found_file = Path('logs/found_ukraine_cars_groups.json')
    targets_file = Path('targets.txt')
    niches_file = Path('group_niches.json')
    assignments_file = Path('group_account_assignments.json')
    
    if not found_file.exists():
        logger.warning(f"⚠️ Файл {found_file} не найден! Группы еще не найдены.")
        return
    
    # Загружаем найденные группы
    try:
        with found_file.open('r', encoding='utf-8') as f:
            found_groups = json.load(f)
    except Exception as e:
        logger.error(f"❌ Ошибка при загрузке {found_file}: {e}")
        return
    
    if not found_groups:
        logger.info("ℹ️ Нет найденных групп для добавления")
        return
    
    logger.info(f"📋 Найдено групп в файле: {len(found_groups)}")

    # Загружаем список закрепленных (вступленных) групп, если есть
    assigned_groups = None
    if assignments_file.exists():
        try:
            with assignments_file.open('r', encoding='utf-8') as f:
                assignments = json.load(f)
            assigned_groups = {g for g in assignments.keys() if g}
            logger.info(f"🔗 Закрепленных групп (assignments): {len(assigned_groups)}")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка при загрузке {assignments_file}: {e}")
            assigned_groups = None

    # Если есть assignments — добавляем только реально вступленные группы
    if assigned_groups is not None:
        found_groups = [g for g in found_groups if g.get('username') in assigned_groups]
        logger.info(f"✅ После фильтра assignments: {len(found_groups)} групп")
    
    # Загружаем существующие targets
    existing_targets = set()
    if targets_file.exists():
        try:
            with targets_file.open('r', encoding='utf-8') as f:
                existing_targets = {line.strip() for line in f if line.strip() and not line.strip().startswith('#')}
        except Exception as e:
            logger.warning(f"⚠️ Ошибка при загрузке {targets_file}: {e}")
    
    logger.info(f"📋 Уже в targets.txt: {len(existing_targets)} групп")
    
    # Загружаем существующие ниши
    existing_niches = {}
    if niches_file.exists():
        try:
            with niches_file.open('r', encoding='utf-8') as f:
                existing_niches = json.load(f)
        except Exception as e:
            logger.warning(f"⚠️ Ошибка при загрузке {niches_file}: {e}")

    # Список ukraine_cars групп до синхронизации (для корректной очистки targets)
    ukraine_targets_before_sync = {
        g for g in existing_targets if existing_niches.get(g) == 'ukraine_cars'
    }
    
    # Создаем backup
    if targets_file.exists():
        backup_file = Path(f'targets.txt.backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}')
        try:
            import shutil
            shutil.copy2(targets_file, backup_file)
            logger.info(f"💾 Создан backup: {backup_file}")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось создать backup: {e}")
    
    if niches_file.exists():
        backup_file = Path(f'group_niches.json.backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}')
        try:
            import shutil
            shutil.copy2(niches_file, backup_file)
            logger.info(f"💾 Создан backup: {backup_file}")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось создать backup: {e}")
    
    # Добавляем новые группы
    added_count = 0
    updated_niches = {}
    
    for group in found_groups:
        username = group.get('username', '')
        if not username:
            continue
        
        # Пропускаем, если уже есть в targets.txt
        if username in existing_targets:
            # Но обновляем нишу, если нужно
            if username not in existing_niches or existing_niches.get(username) != 'ukraine_cars':
                updated_niches[username] = 'ukraine_cars'
            continue
        
        # Добавляем в targets.txt
        try:
            with targets_file.open('a', encoding='utf-8') as f:
                f.write(f"{username}\n")
            existing_targets.add(username)
            added_count += 1
            logger.info(f"✅ Добавлена группа: {username} (ниша: ukraine_cars)")
        except Exception as e:
            logger.error(f"❌ Ошибка при добавлении {username} в targets.txt: {e}")
            continue
        
        # Добавляем нишу
        updated_niches[username] = 'ukraine_cars'
    
    # Обновляем group_niches.json
    existing_niches.update(updated_niches)

    # Опционально синхронизируем ukraine_cars по assignments
    if sync_assigned and assigned_groups is not None:
        # Удаляем ukraine_cars, которых нет в assignments
        to_remove = [
            g for g, niche in existing_niches.items()
            if niche == 'ukraine_cars' and g not in assigned_groups
        ]
        for g in to_remove:
            del existing_niches[g]
        logger.info(f"🧹 Удалено ukraine_cars ниш: {len(to_remove)} (нет в assignments)")

        # Очищаем targets.txt от ukraine_cars, которые не в assignments
        if targets_file.exists():
            filtered_targets = []
            removed_targets = 0
            for line in existing_targets:
                if line in ukraine_targets_before_sync and line not in assigned_groups:
                    removed_targets += 1
                    continue
                filtered_targets.append(line)
            try:
                with targets_file.open('w', encoding='utf-8') as f:
                    for group in filtered_targets:
                        f.write(f"{group}\n")
                existing_targets = set(filtered_targets)
                logger.info(f"🧹 Удалено из targets.txt ukraine_cars групп: {removed_targets}")
            except Exception as e:
                logger.error(f"❌ Ошибка при обновлении {targets_file}: {e}")
    try:
        with niches_file.open('w', encoding='utf-8') as f:
            json.dump(existing_niches, f, ensure_ascii=False, indent=2)
        logger.info(f"✅ Обновлен group_niches.json: добавлено/обновлено {len(updated_niches)} групп с нишей 'ukraine_cars'")
    except Exception as e:
        logger.error(f"❌ Ошибка при обновлении group_niches.json: {e}")
    
    logger.info("")
    logger.info("=" * 80)
    logger.info(f"✅ ЗАВЕРШЕНО:")
    logger.info(f"   - Добавлено новых групп в targets.txt: {added_count}")
    logger.info(f"   - Обновлено ниш в group_niches.json: {len(updated_niches)}")
    logger.info("=" * 80)
    
    return added_count, len(updated_niches)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Добавление/синхронизация ukraine_cars групп")
    parser.add_argument(
        "--sync-assigned",
        action="store_true",
        help="Синхронизировать ukraine_cars по group_account_assignments.json (очистить лишние)",
    )
    args = parser.parse_args()
    add_groups_to_targets(sync_assigned=args.sync_assigned)


