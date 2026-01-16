#!/usr/bin/env python3
"""
Проверка доступных групп для постинга Lexus сегодня
"""
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
import pytz

sys.path.insert(0, str(Path(__file__).parent.parent))

# Проверяем конфигурацию
niches_file = Path('group_niches.json')
targets_file = Path('targets.txt')
history_file = Path('logs/group_post_history.json')

print("=" * 80)
print("🚗 ПРОВЕРКА ДОСТУПНЫХ ГРУПП ДЛЯ LEXUS")
print("=" * 80)

# 1. Проверяем группы с нишей ukraine_cars
if not niches_file.exists():
    print("❌ group_niches.json не найден")
    sys.exit(1)

with open(niches_file, 'r') as f:
    niches = json.load(f)

ukraine_cars_groups = [g for g, n in niches.items() if n == 'ukraine_cars']
print(f"\n✅ Всего групп с нишей 'ukraine_cars': {len(ukraine_cars_groups)}")

# 2. Проверяем, какие группы в targets.txt
if targets_file.exists():
    with open(targets_file, 'r') as f:
        targets = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
    print(f"✅ Всего групп в targets.txt: {len(targets)}")
    
    # Группы ukraine_cars, которые есть в targets.txt
    ukraine_in_targets = [g for g in ukraine_cars_groups if g in targets]
    print(f"✅ Ukraine cars групп в targets.txt: {len(ukraine_in_targets)}")
    
    if len(ukraine_in_targets) < len(ukraine_cars_groups):
        print(f"⚠️  {len(ukraine_cars_groups) - len(ukraine_in_targets)} групп с нишей ukraine_cars НЕТ в targets.txt")
        print(f"   Это означает, что они не будут использоваться планировщиком!")
else:
    print("❌ targets.txt не найден")
    targets = []
    ukraine_in_targets = []

# 3. Проверяем историю постов за сегодня
today = datetime.now(pytz.timezone('Europe/Kiev')).date()
today_posts = {}
groups_with_history = set()

if history_file.exists() and history_file.stat().st_size > 0:
    try:
        with open(history_file, 'r') as f:
            history = json.load(f)
        
        for group, accounts_data in history.items():
            groups_with_history.add(group)
            if isinstance(accounts_data, dict):
                posts_today = 0
                for account, timestamps in accounts_data.items():
                    if isinstance(timestamps, list):
                        for ts in timestamps:
                            try:
                                post_time = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                                if post_time.date() == today:
                                    posts_today += 1
                            except:
                                pass
                today_posts[group] = posts_today
        
        groups_with_posts = sum(1 for v in today_posts.values() if v > 0)
        groups_available = sum(1 for g in ukraine_in_targets if today_posts.get(g, 0) < 2)
        groups_limit_reached = sum(1 for g in ukraine_in_targets if today_posts.get(g, 0) >= 2)
        
        print(f"\n📊 СТАТИСТИКА ЗА СЕГОДНЯ ({today}):")
        print(f"   Групп с постами сегодня: {groups_with_posts}")
        print(f"   Групп доступных для постинга (<2 постов): {groups_available}")
        print(f"   Групп с достигнутым лимитом (≥2 постов): {groups_limit_reached}")
        
        # Группы, доступные для первого слота (08:00)
        available_for_posting = [g for g in ukraine_in_targets if today_posts.get(g, 0) < 2]
        print(f"\n✅ ГОТОВЫ К ПОСТИНГУ СЕГОДНЯ: {len(available_for_posting)} групп")
        if available_for_posting:
            print("   Первые 10 групп:")
            for i, group in enumerate(available_for_posting[:10], 1):
                posts = today_posts.get(group, 0)
                print(f"   {i}. {group} ({posts}/2 постов сегодня)")
    except Exception as e:
        print(f"⚠️  Ошибка при чтении истории: {e}")
        available_for_posting = ukraine_in_targets
        print(f"   Предполагаем, что все {len(ukraine_in_targets)} групп доступны")
else:
    print(f"\n⚠️  История постов не найдена или пуста")
    print(f"   Предполагаем, что все {len(ukraine_in_targets)} групп доступны для первого постинга")
    available_for_posting = ukraine_in_targets

# 4. Итоговый вывод
print("\n" + "=" * 80)
print("📋 ИТОГОВЫЙ СТАТУС:")
print("=" * 80)

if available_for_posting:
    print(f"✅ ДА, есть {len(available_for_posting)} групп для постинга сегодня!")
    print(f"\n⏰ Следующий слот: 08:00 (Киев)")
    print(f"   Система будет постить в доступные группы")
else:
    print("❌ НЕТ доступных групп для постинга сегодня")
    print("   Все группы уже достигли лимита (2 поста в день)")

print("=" * 80)
