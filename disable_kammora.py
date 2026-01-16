#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для отключения рассылки Kammora (апартаменты сданы)
Изменяет нишу всех групп с 'kammora' на 'disabled_kammora'
"""

import json
import shutil
from pathlib import Path
from datetime import datetime

def disable_kammora():
    """Отключение рассылки Kammora"""
    
    niches_file = Path('group_niches.json')
    if not niches_file.exists():
        print("❌ Файл group_niches.json не найден!")
        return
    
    # Загружаем текущие ниши
    with niches_file.open('r', encoding='utf-8') as f:
        group_niches = json.load(f)
    
    # Создаем backup
    backup_file = Path(f'{niches_file}.backup.{datetime.now().strftime("%Y%m%d_%H%M%S")}')
    shutil.copy(niches_file, backup_file)
    print(f"💾 Создан backup: {backup_file}")
    
    # Изменяем все группы с нишей 'kammora' на 'disabled_kammora'
    updated_count = 0
    for group, niche in group_niches.items():
        if niche == 'kammora':
            group_niches[group] = 'disabled_kammora'
            updated_count += 1
    
    # Сохраняем обновленный файл
    with niches_file.open('w', encoding='utf-8') as f:
        json.dump(group_niches, f, ensure_ascii=False, indent=2)
    
    print("=" * 80)
    print("✅ РАССЫЛКА KAMMORA ОТКЛЮЧЕНА")
    print("=" * 80)
    print(f"📊 Обновлено групп: {updated_count}")
    print(f"📝 Все группы с нишей 'kammora' изменены на 'disabled_kammora'")
    print("\n💡 Система больше не будет отправлять объявления Kammora в эти группы")
    print("💡 Для повторного включения можно изменить 'disabled_kammora' обратно на 'kammora'")

if __name__ == "__main__":
    disable_kammora()


