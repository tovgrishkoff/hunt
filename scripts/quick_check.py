#!/usr/bin/env python3
"""
⚡ БЫСТРАЯ ПРОВЕРКА СИСТЕМЫ (30 секунд)
Проверяет только критичные компоненты перед рассылкой
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.database.session import SessionLocal, init_db
from shared.database.models import Account, Group
from shared.config.loader import ConfigLoader

print("=" * 60)
print("⚡ БЫСТРАЯ ПРОВЕРКА СИСТЕМЫ")
print("=" * 60)
print()

errors = []
warnings = []

# 1. БД
try:
    init_db()
    db = SessionLocal()
    accounts_count = db.query(Account).filter(Account.status == 'active').count()
    groups_count = db.query(Group).filter(Group.status == 'active').count()
    print(f"✅ БД: {accounts_count} аккаунтов, {groups_count} активных групп")
    db.close()
except Exception as e:
    print(f"❌ БД: {e}")
    errors.append(f"БД: {e}")

# 2. Конфиг
try:
    loader = ConfigLoader(config_dir="config")
    niche_config = loader.load_niche_config()
    messages = loader.load_messages()
    print(f"✅ Конфиг: {niche_config.get('display_name')}, {len(messages)} сообщений")
    if len(messages) == 0:
        warnings.append("Нет сообщений для постинга")
except Exception as e:
    print(f"❌ Конфиг: {e}")
    errors.append(f"Конфиг: {e}")

# 3. Аккаунты
try:
    from shared.telegram.client_manager import TelegramClientManager
    import asyncio
    
    async def check_accounts():
        sessions_dir = Path(__file__).parent.parent / "sessions"
        if not sessions_dir.exists():
            sessions_dir = Path("/app/sessions")
        
        client_manager = TelegramClientManager(sessions_dir=str(sessions_dir))
        await client_manager.load_accounts_from_db(db)
        return len(client_manager.clients)
    
    db = SessionLocal()
    accounts_count = asyncio.run(check_accounts())
    print(f"✅ Аккаунты: {accounts_count} загружено")
    db.close()
except Exception as e:
    print(f"❌ Аккаунты: {e}")
    errors.append(f"Аккаунты: {e}")

# 4. OpenAI API
if os.getenv('OPENAI_API_KEY'):
    print(f"✅ OpenAI API: ключ установлен")
else:
    print(f"⚠️  OpenAI API: ключ не найден")
    warnings.append("Secretary не будет работать без API ключа")

# Итоги
print()
print("=" * 60)
if errors:
    print(f"❌ ОШИБКИ: {len(errors)}")
    for e in errors:
        print(f"   • {e}")
    print()
    print("⚠️  СИСТЕМА НЕ ГОТОВА К РАБОТЕ!")
    sys.exit(1)
elif warnings:
    print(f"⚠️  ПРЕДУПРЕЖДЕНИЯ: {len(warnings)}")
    for w in warnings:
        print(f"   • {w}")
    print()
    print("✅ Система готова, но есть предупреждения")
else:
    print("✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ!")
    print("✅ Система готова к работе")
print("=" * 60)
