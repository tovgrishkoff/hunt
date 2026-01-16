#!/usr/bin/env python3
"""
Простой скрипт для добавления аккаунтов и групп Ukraine в БД
Использует psycopg2 для прямого подключения к БД
"""
import json
import sys
from pathlib import Path
from datetime import datetime
import re

try:
    import psycopg2
    from psycopg2.extras import execute_values
except ImportError:
    print("❌ psycopg2 не установлен. Установите: pip install psycopg2-binary")
    sys.exit(1)


DB_CONFIG = {
    'host': 'localhost',
    'port': 5439,
    'database': 'ukraine_db',
    'user': 'telegram_user_ukraine',
    'password': 'telegram_password_ukraine'
}


def normalize_group_link(link):
    """Нормализация ссылки на группу"""
    link = link.strip()
    if not link:
        return None
    
    link = re.sub(r'\s+', '', link)
    
    if link.startswith('@'):
        return link.lower()
    
    if 't.me/' in link:
        match = re.search(r't\.me/([^/?\s]+)', link)
        if match:
            username = match.group(1)
            return f"@{username}" if not username.startswith('@') else f"@{username.lstrip('@')}"
    
    if link.startswith('http'):
        match = re.search(r't\.me/([^/?\s]+)', link)
        if match:
            username = match.group(1)
            return f"@{username}" if not username.startswith('@') else f"@{username.lstrip('@')}"
    
    return link


def migrate_accounts(conn):
    """Миграция аккаунтов"""
    print("=" * 80)
    print("👤 МИГРАЦИЯ АККАУНТОВ")
    print("=" * 80)
    
    base_dir = Path(__file__).parent.parent.parent
    
    accounts_config_file = base_dir / "accounts_config.json"
    lexus_config_file = base_dir / "lexus_accounts_config.json"
    
    if not accounts_config_file.exists():
        print(f"❌ Файл {accounts_config_file} не найден!")
        return
    
    if not lexus_config_file.exists():
        print(f"❌ Файл {lexus_config_file} не найден!")
        return
    
    with open(accounts_config_file, 'r') as f:
        accounts_config = json.load(f)
    
    with open(lexus_config_file, 'r') as f:
        lexus_config = json.load(f)
    
    lexus_allowed = set(lexus_config.get('allowed_accounts', []))
    
    cur = conn.cursor()
    
    added = 0
    skipped = 0
    
    for acc_config in accounts_config:
        session_name = acc_config.get('session_name', '')
        
        if session_name not in lexus_allowed:
            continue
        
        # Проверяем, существует ли уже
        cur.execute("SELECT id FROM accounts WHERE session_name = %s", (session_name,))
        if cur.fetchone():
            print(f"⏭️  Пропущен (уже есть): {session_name}")
            skipped += 1
            continue
        
        # Создаем аккаунт (используем string_session из config, но в БД может быть session_string)
        # Проверяем какое поле есть в БД
        cur.execute("""
            INSERT INTO accounts (session_name, phone, api_id, api_hash, status, 
                                 daily_posts_count, last_stats_reset, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            session_name,
            acc_config.get('phone'),
            acc_config.get('api_id'),
            acc_config.get('api_hash'),
            'active',
            0,
            datetime.utcnow(),
            datetime.utcnow(),
            datetime.utcnow()
        ))
        print(f"✅ Добавлен: {session_name}")
        added += 1
    
    conn.commit()
    print(f"\n📊 Итого: добавлено {added}, пропущено {skipped}")


def migrate_groups(conn):
    """Миграция групп из group_niches.json"""
    print("\n" + "=" * 80)
    print("📋 МИГРАЦИЯ ГРУПП")
    print("=" * 80)
    
    base_dir = Path(__file__).parent.parent.parent
    group_niches_file = base_dir / "group_niches.json"
    
    if not group_niches_file.exists():
        print(f"❌ Файл {group_niches_file} не найден!")
        return
    
    with open(group_niches_file, 'r') as f:
        group_niches = json.load(f)
    
    # Фильтруем только ukraine_cars
    ukraine_cars_groups = {
        group: niche for group, niche in group_niches.items()
        if niche == 'ukraine_cars'
    }
    
    print(f"📋 Найдено {len(ukraine_cars_groups)} групп с нишей 'ukraine_cars'")
    
    cur = conn.cursor()
    
    added = 0
    skipped = 0
    
    for group_link, niche in ukraine_cars_groups.items():
        normalized_link = normalize_group_link(group_link)
        if not normalized_link:
            print(f"⚠️  Пропущена невалидная ссылка: {group_link}")
            skipped += 1
            continue
        
        # Проверяем, существует ли уже
        cur.execute("SELECT id FROM targets WHERE link = %s", (normalized_link,))
        if cur.fetchone():
            skipped += 1
            continue
        
        # Создаем группу
        cur.execute("""
            INSERT INTO targets (link, niche, status, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            normalized_link,
            niche,
            'new',
            datetime.utcnow(),
            datetime.utcnow()
        ))
        added += 1
    
    conn.commit()
    print(f"\n📊 Итого: добавлено {added}, пропущено {skipped}")


def main():
    """Основная функция"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        print("✅ Подключение к БД установлено\n")
    except Exception as e:
        print(f"❌ Ошибка подключения к БД: {e}")
        sys.exit(1)
    
    try:
        migrate_accounts(conn)
        migrate_groups(conn)
        
        print("\n" + "=" * 80)
        print("✅ МИГРАЦИЯ ЗАВЕРШЕНА")
        print("=" * 80)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
