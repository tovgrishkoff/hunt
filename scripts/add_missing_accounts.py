#!/usr/bin/env python3
"""
Добавить недостающие аккаунты в БД из accounts_config.json
"""
import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.database.session import SessionLocal, init_db
from shared.database.models import Account

def add_missing_accounts():
    """Добавить недостающие аккаунты"""
    init_db()
    db = SessionLocal()
    
    # Загружаем конфиг
    config_file = Path(__file__).parent.parent / "accounts_config.json"
    with open(config_file, 'r', encoding='utf-8') as f:
        accounts_config = json.load(f)
    
    # Аккаунты для добавления
    accounts_to_add = ['promotion_lisa_soak', 'promotion_new_account_2']
    
    added = 0
    for config_data in accounts_config:
        session_name = config_data.get('session_name')
        if session_name not in accounts_to_add:
            continue
        
        # Проверяем, есть ли уже
        existing = db.query(Account).filter(Account.session_name == session_name).first()
        if existing:
            print(f"ℹ️  {session_name} уже есть в БД")
            continue
        
        # Создаем новый
        new_account = Account(
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
        db.add(new_account)
        print(f"✅ Добавлен: {session_name}")
        added += 1
    
    db.commit()
    db.close()
    
    print(f"\n✅ Добавлено аккаунтов: {added}")

if __name__ == "__main__":
    add_missing_accounts()
