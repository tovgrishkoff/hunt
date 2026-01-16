#!/bin/bash
# Скрипт для добавления аккаунтов Ukraine/Lexus в БД

PROJECT="ukraine"
DB_NAME="ukraine_db"
DB_USER="telegram_user_ukraine"

echo "=" | head -c 80
echo ""
echo "👤 ДОБАВЛЕНИЕ АККАУНТОВ В БД UKRAINE"
echo "=" | head -c 80
echo ""

# Проверяем наличие accounts_config.json
if [ ! -f "accounts_config.json" ]; then
    echo "❌ Файл accounts_config.json не найден!"
    exit 1
fi

# Проверяем наличие lexus_accounts_config.json
if [ ! -f "lexus_accounts_config.json" ]; then
    echo "❌ Файл lexus_accounts_config.json не найден!"
    exit 1
fi

echo ""
echo "📋 Чтение конфигурации..."

# Читаем список аккаунтов Lexus
LEXUS_ACCOUNTS=$(python3 << 'PYEOF'
import json
try:
    with open('lexus_accounts_config.json', 'r') as f:
        config = json.load(f)
    accounts = config.get('allowed_accounts', [])
    print(' '.join(accounts))
except Exception as e:
    print('')
PYEOF
)

if [ -z "$LEXUS_ACCOUNTS" ]; then
    echo "❌ Не найдены аккаунты в lexus_accounts_config.json"
    exit 1
fi

echo "✅ Найдены аккаунты: $LEXUS_ACCOUNTS"
echo ""

# Добавляем аккаунты через Python скрипт
docker exec ukraine-account-manager python3 << PYEOF 2>&1
import asyncio
import json
import sys
import os

# Добавляем путь к модулям
sys.path.insert(0, '/app')

from lexus_db.session import AsyncSessionLocal, init_db
from lexus_db.models import Account
from datetime import datetime

async def add_accounts():
    # Загружаем конфигурацию
    with open('/app/accounts_config.json', 'r') as f:
        accounts_config = json.load(f)
    
    with open('/app/lexus_accounts_config.json', 'r') as f:
        lexus_config = json.load(f)
    
    lexus_allowed = set(lexus_config.get('allowed_accounts', []))
    
    async with AsyncSessionLocal() as session:
        added = 0
        skipped = 0
        
        for acc_config in accounts_config:
            session_name = acc_config.get('session_name', '')
            
            # Добавляем только аккаунты из Lexus
            if session_name not in lexus_allowed:
                continue
            
            # Проверяем, существует ли уже
            from sqlalchemy import select
            result = await session.execute(
                select(Account).where(Account.session_name == session_name)
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                print(f"⏭️  Пропущен (уже есть): {session_name}")
                skipped += 1
                continue
            
            # Создаем аккаунт
            account = Account(
                session_name=session_name,
                phone=acc_config.get('phone'),
                session_string=acc_config.get('string_session'),
                api_id=acc_config.get('api_id'),
                api_hash=acc_config.get('api_hash'),
                status='active',
                daily_posts_count=0,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            
            session.add(account)
            print(f"✅ Добавлен: {session_name}")
            added += 1
        
        await session.commit()
        print(f"\n📊 Итого: добавлено {added}, пропущено {skipped}")

asyncio.run(add_accounts())
PYEOF

echo ""
echo "✅ Готово!"
echo ""
echo "Проверка:"
docker exec ${PROJECT}-postgres psql -U ${DB_USER} -d ${DB_NAME} -c "
SELECT session_name, status, daily_posts_count 
FROM accounts 
ORDER BY session_name;
" 2>&1
