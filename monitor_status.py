#!/usr/bin/env python3
"""
Скрипт мониторинга статуса групп в системе Telegram Promotion для Бали

Использование:
    python monitor_status.py

Выводит статистику по группам и прогноз времени до завершения очереди.
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
from sqlalchemy import func

# Добавляем путь к проекту
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from shared.database.session import SessionLocal
from shared.database.models import Group


def format_time(hours, minutes):
    """Форматирование времени для вывода"""
    if hours > 0:
        return f"{hours} часов {minutes} минут"
    elif minutes > 0:
        return f"{minutes} минут"
    else:
        return "< 1 минуты"


def main():
    """Основная функция мониторинга"""
    db = SessionLocal()
    
    try:
        # Получаем статистику по статусам
        stats = db.query(
            Group.status,
            func.count(Group.id).label('count')
        ).filter(
            Group.niche == 'bali'
        ).group_by(Group.status).all()
        
        # Преобразуем в словарь для удобства
        status_counts = {status: count for status, count in stats}
        
        # Подсчитываем группы готовые к постингу
        ready_for_posting = db.query(func.count(Group.id)).filter(
            Group.niche == 'bali',
            Group.status == 'active',
            Group.can_post == True,
            Group.warm_up_until <= datetime.utcnow()
        ).scalar()
        
        # Количество новых групп для расчета времени
        new_count = status_counts.get('new', 0)
        
        # Прогноз времени (среднее время обработки 1.5 минуты на группу)
        avg_time_per_group = 1.5  # минуты
        total_minutes = new_count * avg_time_per_group
        hours = int(total_minutes // 60)
        minutes = int(total_minutes % 60)
        time_forecast = format_time(hours, minutes)
        
        # Выводим красивую таблицу
        print("\n" + "=" * 70)
        print(" " * 25 + "📊 СТАТИСТИКА ПО ГРУППАМ (БАЛИ)")
        print("=" * 70)
        print(f"\n{datetime.now().strftime('Дата: %Y-%m-%d %H:%M:%S')}\n")
        
        # Статистика по статусам
        print("Статус                     | Количество")
        print("-" * 70)
        
        # Active (Ready to post)
        active_count = status_counts.get('active', 0)
        print(f"Active (Ready to post)      | {active_count}")
        if active_count > 0:
            print(f"  └─ Готовы к постингу        | {ready_for_posting}")
        
        # New (Queue)
        print(f"New (Queue)                 | {new_count}")
        
        # Read Only (Filtered)
        read_only_count = status_counts.get('read_only', 0)
        print(f"Read Only (Filtered)         | {read_only_count}")
        
        # Banned/Invalid
        banned_count = status_counts.get('banned', 0)
        inaccessible_count = status_counts.get('inaccessible', 0)
        invalid_total = banned_count + inaccessible_count
        print(f"Banned/Invalid              | {invalid_total}")
        if banned_count > 0:
            print(f"  └─ Banned                   | {banned_count}")
        if inaccessible_count > 0:
            print(f"  └─ Inaccessible             | {inaccessible_count}")
        
        # Pending (Waitlist)
        pending_count = status_counts.get('pending', 0)
        if pending_count > 0:
            print(f"Pending (Waitlist)           | {pending_count}")
        
        # Общее количество
        total = sum(status_counts.values())
        print("-" * 70)
        print(f"ВСЕГО                       | {total}")
        
        # Прогноз
        print("\n" + "=" * 70)
        print(" " * 20 + "⏱️  ПРОГНОЗ ЗАВЕРШЕНИЯ ОЧЕРЕДИ")
        print("=" * 70)
        if new_count > 0:
            print(f"\nОсталось обработать: {new_count} групп")
            print(f"Среднее время на группу: {avg_time_per_group} минут")
            print(f"\n🎯 Примерное время до завершения очереди: {time_forecast}")
        else:
            print("\n✅ Очередь пуста! Все группы обработаны.")
        
        print("\n" + "=" * 70 + "\n")
        
    except Exception as e:
        print(f"\n❌ Ошибка при получении статистики: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    finally:
        db.close()


if __name__ == "__main__":
    main()
