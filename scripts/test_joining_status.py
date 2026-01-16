#!/usr/bin/env python3
"""
Тестовый скрипт для проверки статуса вступления в группы и отслеживания
"""
import sys
from pathlib import Path
from datetime import datetime

# Добавляем корень проекта
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from shared.database.session import SessionLocal
    from shared.database.models import Group, Account
    from sqlalchemy import func, and_, or_
except ImportError:
    print("⚠️ Не удалось импортировать модули БД. Используем прямой SQL.")
    import subprocess

def check_joining_status_sql():
    """Проверка статуса через SQL"""
    print("\n" + "="*80)
    print("📊 СТАТУС ВСТУПЛЕНИЯ В ГРУППЫ (Bali)")
    print("="*80)
    
    commands = [
        ("Общая статистика по статусам", 
         "SELECT status, COUNT(*) as count FROM groups WHERE niche = 'bali' GROUP BY status ORDER BY count DESC;"),
        
        ("Группы готовые к вступлению (status='new')", 
         "SELECT COUNT(*) as count FROM groups WHERE niche = 'bali' AND status = 'new';"),
        
        ("Активные группы с warm-up", 
         "SELECT COUNT(*) as total, COUNT(CASE WHEN warm_up_until <= NOW() THEN 1 END) as warmup_done, COUNT(CASE WHEN warm_up_until > NOW() THEN 1 END) as warmup_in_progress FROM groups WHERE niche = 'bali' AND status = 'active';"),
        
        ("Последние вступившие группы", 
         "SELECT username, status, joined_at, warm_up_until, CASE WHEN warm_up_until <= NOW() THEN '✅ done' ELSE '⏳ in progress' END as warmup_status FROM groups WHERE niche = 'bali' AND status = 'active' ORDER BY joined_at DESC LIMIT 10;"),
    ]
    
    for title, query in commands:
        print(f"\n📋 {title}:")
        try:
            result = subprocess.run(
                ['docker', 'exec', 'telegram-bali-postgres', 
                 'psql', '-U', 'telegram_user_bali', '-d', 'telegram_promotion_bali', 
                 '-c', query],
                capture_output=True,
                text=True,
                check=True
            )
            print(result.stdout)
        except subprocess.CalledProcessError as e:
            print(f"❌ Ошибка: {e.stderr}")

def check_joining_status():
    """Проверка статуса через ORM"""
    print("\n" + "="*80)
    print("📊 СТАТУС ВСТУПЛЕНИЯ В ГРУППЫ (Bali)")
    print("="*80)
    
    db = SessionLocal()
    try:
        # Общая статистика
        stats = db.query(
            Group.status,
            func.count(Group.id).label('count')
        ).filter(
            Group.niche == 'bali'
        ).group_by(Group.status).all()
        
        print("\n📋 Общая статистика по статусам:")
        total = 0
        for status, count in stats:
            print(f"  {status:15} → {count:4} групп")
            total += count
        print(f"  {'TOTAL':15} → {total:4} групп")
        
        # Группы готовые к вступлению
        new_groups = db.query(Group).filter(
            Group.niche == 'bali',
            Group.status == 'new'
        ).count()
        
        print(f"\n📋 Группы готовые к вступлению (status='new'): {new_groups}")
        
        # Активные группы
        active_groups = db.query(Group).filter(
            Group.niche == 'bali',
            Group.status == 'active'
        ).all()
        
        now = datetime.utcnow()
        warmup_done = sum(1 for g in active_groups if g.warm_up_until and g.warm_up_until <= now)
        warmup_in_progress = len(active_groups) - warmup_done
        
        print(f"\n📋 Активные группы:")
        print(f"  Всего активных: {len(active_groups)}")
        print(f"  Warm-up завершен: {warmup_done}")
        print(f"  Warm-up в процессе: {warmup_in_progress}")
        
        # Последние вступившие группы
        recent_groups = db.query(Group).filter(
            Group.niche == 'bali',
            Group.status == 'active'
        ).order_by(Group.joined_at.desc()).limit(10).all()
        
        print(f"\n📋 Последние вступившие группы (топ 10):")
        for group in recent_groups:
            warmup_status = "✅ done" if (group.warm_up_until and group.warm_up_until <= now) else "⏳ in progress"
            joined_str = group.joined_at.strftime("%Y-%m-%d %H:%M") if group.joined_at else "N/A"
            print(f"  {group.username:30} → {warmup_status:15} (joined: {joined_str})")
        
        # Группы с привязкой к аккаунтам
        groups_with_accounts = db.query(Group).filter(
            Group.niche == 'bali',
            Group.assigned_account_id.isnot(None)
        ).count()
        
        print(f"\n📋 Группы с привязкой к аккаунтам: {groups_with_accounts}")
        
    except Exception as e:
        print(f"❌ Ошибка при проверке статуса: {e}")
        import traceback
        traceback.print_exc()
        # Fallback на SQL
        check_joining_status_sql()
    finally:
        db.close()

def check_account_manager_logs():
    """Проверка логов Account Manager"""
    print("\n" + "="*80)
    print("📋 ЛОГИ ACCOUNT MANAGER (последние записи о вступлении)")
    print("="*80)
    
    try:
        result = subprocess.run(
            ['docker', 'logs', 'telegram-bali-account-manager', '--tail', '200'],
            capture_output=True,
            text=True,
            check=True
        )
        
        lines = result.stdout.split('\n')
        relevant_lines = [
            line for line in lines 
            if any(keyword in line.lower() for keyword in ['joining', 'joined', 'вступл', 'warm-up', 'step 2', 'new groups', 'saved'])
        ]
        
        if relevant_lines:
            print("\n".join(relevant_lines[-20:]))
        else:
            print("⚠️ Нет записей о вступлении в последних 200 строках логов")
            
    except subprocess.CalledProcessError as e:
        print(f"❌ Ошибка при чтении логов: {e}")

def main():
    """Главная функция"""
    print("="*80)
    print("🧪 ТЕСТИРОВАНИЕ СТАТУСА ВСТУПЛЕНИЯ В ГРУППЫ")
    print("="*80)
    
    try:
        check_joining_status()
    except Exception as e:
        print(f"⚠️ Ошибка при проверке через ORM: {e}")
        check_joining_status_sql()
    
    check_account_manager_logs()
    
    print("\n" + "="*80)
    print("✅ ПРОВЕРКА ЗАВЕРШЕНА")
    print("="*80)

if __name__ == "__main__":
    main()
