#!/usr/bin/env python3
"""
Скрипт для создания нового списка целевых групп на основе активных групп из логов
"""

import json
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Активные группы из логов (исключая заблокированные)
ACTIVE_GROUPS = [
    1032422089, 1180252758, 2123818093, 2358631846, 1824741898, 1626526675,
    1540608753, 1492919625, 1278052827, 1467162873, 2233860276, 1670908431,
    1919571432, 1858490178, 1894542948, 1609129624, 1141864847, 1394199452,
    1173391726, 1761990621, 1341855810, 1640527500, 2040562327, 1940107962,
    2054222920, 1618739515, 1374655693, 2343300452, 1399990845, 1268089422,
    2307116540, 1269265162, 2371997825, 1703113785, 1276625951, 1302872889,
    1699177401, 1775894772, 1772266000, 1508876175
]

# Заблокированные группы (исключаем их)
BANNED_GROUPS = [1388027785, 1437172130, 2428157434, 1490984268, 1646544705]

def create_new_targets():
    """Создать новый список целевых групп"""
    
    # Фильтруем активные группы (убираем заблокированные)
    filtered_groups = [group_id for group_id in ACTIVE_GROUPS if group_id not in BANNED_GROUPS]
    
    logger.info(f"📊 Активных групп: {len(filtered_groups)}")
    logger.info(f"❌ Заблокированных групп: {len(BANNED_GROUPS)}")
    
    # Создаем новый targets.txt с ID групп
    new_targets = []
    for group_id in filtered_groups:
        new_targets.append(f"ID:{group_id}")
    
    # Сохраняем новый список
    with open('targets_new.txt', 'w', encoding='utf-8') as f:
        for target in new_targets:
            f.write(target + '\n')
    
    logger.info(f"✅ Создан файл targets_new.txt с {len(new_targets)} группами")
    
    # Создаем новый group_niches.json
    # Пока что все группы помечаем как "general", потом можно будет уточнить
    group_niches = {}
    for group_id in filtered_groups:
        group_niches[f"ID:{group_id}"] = "general"
    
    # Сохраняем новый group_niches.json
    with open('group_niches_new.json', 'w', encoding='utf-8') as f:
        json.dump(group_niches, f, ensure_ascii=False, indent=2)
    
    logger.info(f"✅ Создан файл group_niches_new.json с {len(group_niches)} группами")
    
    # Показываем первые 10 групп
    logger.info(f"\n📋 Первые 10 групп:")
    for i, group_id in enumerate(filtered_groups[:10], 1):
        logger.info(f"  {i:2d}. ID:{group_id}")
    
    if len(filtered_groups) > 10:
        logger.info(f"  ... и еще {len(filtered_groups) - 10} групп")
    
    return filtered_groups

def backup_current_files():
    """Создать резервные копии текущих файлов"""
    import shutil
    import os
    from datetime import datetime
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    files_to_backup = ['targets.txt', 'group_niches.json']
    
    for filename in files_to_backup:
        if os.path.exists(filename):
            backup_name = f"{filename}.backup_{timestamp}"
            shutil.copy2(filename, backup_name)
            logger.info(f"📁 Создана резервная копия: {backup_name}")
        else:
            logger.warning(f"⚠️ Файл {filename} не найден")

def main():
    """Основная функция"""
    logger.info("🚀 Создание нового списка целевых групп...")
    
    # Создаем резервные копии
    backup_current_files()
    
    # Создаем новые файлы
    active_groups = create_new_targets()
    
    logger.info(f"\n🎯 ИТОГО:")
    logger.info(f"  • Активных групп: {len(active_groups)}")
    logger.info(f"  • Заблокированных групп: {len(BANNED_GROUPS)}")
    logger.info(f"  • Новые файлы: targets_new.txt, group_niches_new.json")
    
    logger.info(f"\n📝 СЛЕДУЮЩИЕ ШАГИ:")
    logger.info(f"  1. Проверить новые файлы")
    logger.info(f"  2. Переименовать targets_new.txt -> targets.txt")
    logger.info(f"  3. Переименовать group_niches_new.json -> group_niches.json")
    logger.info(f"  4. Перезапустить систему постинга")
    logger.info(f"  5. Проверить логи постинга")

if __name__ == "__main__":
    main()
