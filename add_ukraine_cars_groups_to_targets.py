#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Автоматическое добавление найденных украинских авто-групп в targets.txt и group_niches.json
Запускается после успешного вступления в группы
"""

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

def add_groups_to_targets():
    """Добавление найденных групп в targets.txt и group_niches.json"""
    logger = setup_logging()
    
    logger.info("=" * 80)
    logger.info("📝 ДОБАВЛЕНИЕ УКРАИНСКИХ АВТО-ГРУПП В РАССЫЛКУ")
    logger.info("=" * 80)
    
    found_file = Path('logs/found_ukraine_cars_groups.json')
    targets_file = Path('targets.txt')
    niches_file = Path('group_niches.json')
    
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
    add_groups_to_targets()


