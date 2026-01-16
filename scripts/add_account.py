#!/usr/bin/env python3
"""
Утилита для добавления нового аккаунта
Просто указываем имя session файла
"""
import sys
import os
from pathlib import Path

# Добавляем путь к shared модулям
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.database.session import SessionLocal, init_db
from shared.database.models import Account
import json


def load_account_from_config(session_name: str):
    """Загрузить конфигурацию аккаунта из accounts_config.json"""
    config_file = Path(__file__).parent.parent / "accounts_config.json"
    
    if not config_file.exists():
        print(f"❌ Config file not found: {config_file}")
        return None
    
    with open(config_file, 'r', encoding='utf-8') as f:
        accounts = json.load(f)
    
    for acc in accounts:
        if acc.get('session_name') == session_name:
            return acc
    
    return None


def add_account_to_db(session_name: str, config_data: dict = None):
    """Добавить аккаунт в БД"""
    init_db()
    db = SessionLocal()
    
    try:
        # Проверяем, есть ли уже такой аккаунт
        existing = db.query(Account).filter(Account.session_name == session_name).first()
        if existing:
            print(f"⚠️ Account {session_name} already exists in DB")
            return False
        
        if config_data:
            account = Account(
                session_name=session_name,
                phone=config_data.get('phone'),
                api_id=config_data.get('api_id'),
                api_hash=config_data.get('api_hash'),
                string_session=config_data.get('string_session'),
                proxy=config_data.get('proxy'),
                nickname=config_data.get('nickname'),
                bio=config_data.get('bio'),
                status='active'
            )
        else:
            # Минимальная информация
            account = Account(
                session_name=session_name,
                status='active'
            )
        
        db.add(account)
        db.commit()
        print(f"✅ Account {session_name} added to database")
        return True
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error adding account: {e}")
        return False
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python add_account.py <session_name> [--from-config]")
        print("Example: python add_account.py promotion_new_account")
        print("         python add_account.py promotion_new_account --from-config")
        sys.exit(1)
    
    session_name = sys.argv[1]
    from_config = '--from-config' in sys.argv
    
    # Проверяем наличие session файла
    sessions_dir = Path(__file__).parent.parent / "sessions"
    session_file = sessions_dir / f"{session_name}.session"
    
    if not session_file.exists():
        print(f"⚠️ Session file not found: {session_file}")
        print(f"   Please copy your session file to: {session_file}")
        response = input("Continue anyway? (y/n): ")
        if response.lower() != 'y':
            sys.exit(1)
    else:
        print(f"✅ Found session file: {session_file}")
    
    # Загружаем конфигурацию, если нужно
    config_data = None
    if from_config:
        config_data = load_account_from_config(session_name)
        if config_data:
            print(f"✅ Loaded config from accounts_config.json")
        else:
            print(f"⚠️ Config not found in accounts_config.json, using minimal info")
    
    # Добавляем в БД
    success = add_account_to_db(session_name, config_data)
    
    if success:
        print("\n✅ Account successfully added!")
        print("   The account will be automatically loaded by services on next restart")
    else:
        sys.exit(1)

