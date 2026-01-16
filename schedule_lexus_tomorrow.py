#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для планирования рассылки Lexus на завтра
Автоматически добавляет группы в targets.txt и group_niches.json
"""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, '.')

from promotion_system import PromotionSystem

async def schedule_lexus_for_tomorrow():
    """Планирование рассылки Lexus на завтра"""
    
    print("=" * 80)
    print("📅 ПЛАНИРОВАНИЕ РАССЫЛКИ LEXUS НА ЗАВТРА")
    print("=" * 80)
    
    # Загружаем прогресс вступления
    progress_file = Path('logs/join_ukraine_cars_groups_progress.json')
    if not progress_file.exists():
        print("❌ Файл прогресса вступления не найден!")
        print("   Сначала запустите join_ukraine_cars_groups.py")
        return
    
    with progress_file.open('r', encoding='utf-8') as f:
        progress = json.load(f)
    
    # Собираем все группы, в которые успешно вступили
    all_joined_groups = set()
    for account_name, account_data in progress.items():
        joined = account_data.get('joined', [])
        for group_link in joined:
            # Извлекаем username из ссылки
            if group_link.startswith('@'):
                all_joined_groups.add(group_link)
            elif 't.me/' in group_link:
                username = '@' + group_link.split('t.me/')[-1].split('/')[0].split('?')[0]
                all_joined_groups.add(username)
    
    if not all_joined_groups:
        print("⚠️ Не найдено групп, в которые успешно вступили")
        return
    
    print(f"\n✅ Найдено {len(all_joined_groups)} групп для добавления")
    
    # Загружаем текущие targets.txt
    targets_file = Path('targets.txt')
    existing_targets = set()
    if targets_file.exists():
        with targets_file.open('r', encoding='utf-8') as f:
            existing_targets = {line.strip() for line in f if line.strip() and not line.strip().startswith('#')}
    
    # Фильтруем новые группы
    new_groups = sorted(all_joined_groups - existing_targets)
    
    if not new_groups:
        print("✅ Все группы уже добавлены в targets.txt")
    else:
        print(f"\n📝 Добавляем {len(new_groups)} новых групп в targets.txt...")
        
        # Создаем backup
        if targets_file.exists():
            backup_file = Path(f'{targets_file}.backup.{datetime.now().strftime("%Y%m%d_%H%M%S")}')
            import shutil
            shutil.copy(targets_file, backup_file)
            print(f"💾 Создан backup: {backup_file}")
        
        # Добавляем новые группы
        with targets_file.open('a', encoding='utf-8') as f:
            f.write('\n')
            f.write('# Украинские группы по продаже машин (добавлено автоматически)\n')
            f.write(f'# Дата добавления: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
            for group in new_groups:
                f.write(f'{group}\n')
        
        print(f"✅ Добавлено {len(new_groups)} групп в targets.txt")
    
    # Обновляем group_niches.json
    niches_file = Path('group_niches.json')
    group_niches = {}
    if niches_file.exists():
        with niches_file.open('r', encoding='utf-8') as f:
            group_niches = json.load(f)
    
    # Добавляем/обновляем нишу для всех групп
    updated_niches = 0
    for group in all_joined_groups:
        if group_niches.get(group) != 'ukraine_cars':
            group_niches[group] = 'ukraine_cars'
            updated_niches += 1
    
    if updated_niches > 0:
        # Создаем backup
        if niches_file.exists():
            backup_file = Path(f'{niches_file}.backup.{datetime.now().strftime("%Y%m%d_%H%M%S")}')
            import shutil
            shutil.copy(niches_file, backup_file)
            print(f"💾 Создан backup group_niches.json: {backup_file}")
        
        # Сохраняем обновленный файл
        with niches_file.open('w', encoding='utf-8') as f:
            json.dump(group_niches, f, ensure_ascii=False, indent=2)
        
        print(f"✅ Обновлено {updated_niches} групп в group_niches.json (ниша: ukraine_cars)")
    
    print("\n" + "=" * 80)
    print("📊 ИТОГИ")
    print("=" * 80)
    print(f"✅ Всего групп: {len(all_joined_groups)}")
    print(f"✅ Новых добавлено в targets.txt: {len(new_groups)}")
    print(f"✅ Обновлено ниш: {updated_niches}")
    
    print("\n" + "=" * 80)
    print("🚀 ГОТОВО К РАССЫЛКЕ")
    print("=" * 80)
    print("\nДля запуска рассылки на завтра используйте:")
    print("  python3 lexus_scheduler.py --post")
    print("\nИли через bash скрипт:")
    print("  ./start_lexus_scheduler.sh")
    print("\nИли через планировщик cron:")
    print("  0 8 * * * cd /path/to/project && python3 lexus_scheduler.py --post")
    print("\nРасписание слотов (Киевское время):")
    print("  - 08:00 (morning)")
    print("  - 12:00 (noon)")
    print("  - 15:00 (afternoon)")
    print("  - 18:00 (evening)")
    print("  - 20:00 (night)")

if __name__ == "__main__":
    asyncio.run(schedule_lexus_for_tomorrow())

