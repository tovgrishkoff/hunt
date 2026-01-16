#!/usr/bin/env python3
"""
Обновить StringSession в БД из accounts_config.json
Используется когда сессии в конфиге актуальны, но в БД устарели
"""
import sys
import json
import asyncio
from pathlib import Path

# Добавляем путь к shared модулям
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.database.session import SessionLocal, init_db
from shared.database.models import Account
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def update_accounts_from_config():
    """Обновить StringSession в БД из accounts_config.json"""
    logger.info("=" * 80)
    logger.info("🔄 ОБНОВЛЕНИЕ АККАУНТОВ ИЗ CONFIG")
    logger.info("=" * 80)
    
    # Инициализация БД
    try:
        init_db()
    except Exception as e:
        logger.warning(f"⚠️ БД уже инициализирована: {e}")
    
    # Загружаем конфиг
    base_dir = Path(__file__).parent.parent
    config_file = base_dir / "accounts_config.json"
    
    if not config_file.exists():
        logger.error(f"❌ Файл accounts_config.json не найден: {config_file}")
        return
    
    with open(config_file, 'r', encoding='utf-8') as f:
        accounts_config = json.load(f)
    
    # Аккаунты для обновления
    accounts_to_update = ['promotion_dao_bro', 'promotion_oleg_petrov']
    
    logger.info(f"📋 Аккаунты для обновления: {', '.join(accounts_to_update)}")
    logger.info("")
    
    db = SessionLocal()
    updated = 0
    
    try:
        for config_data in accounts_config:
            session_name = config_data.get('session_name')
            if session_name not in accounts_to_update:
                continue
            
            string_session = config_data.get('string_session')
            if not string_session or len(string_session) < 50:
                logger.warning(f"⚠️ Нет валидной StringSession в конфиге для {session_name}")
                continue
            
            # Находим аккаунт в БД
            account = db.query(Account).filter(Account.session_name == session_name).first()
            if not account:
                logger.warning(f"⚠️ Аккаунт {session_name} не найден в БД")
                continue
            
            # Обновляем StringSession
            account.string_session = string_session
            db.commit()
            
            logger.info(f"✅ StringSession обновлен в БД для {session_name} (длина: {len(string_session)})")
            updated += 1
        
        logger.info("")
        logger.info("=" * 80)
        logger.info(f"✅ ОБНОВЛЕНО: {updated} аккаунтов")
        logger.info("=" * 80)
        logger.info("")
        logger.info("🔄 Перезапустите контейнеры для применения изменений:")
        logger.info("   docker-compose restart account-manager marketer activity secretary")
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Ошибка при обновлении: {e}", exc_info=True)
    finally:
        db.close()


if __name__ == "__main__":
    try:
        asyncio.run(update_accounts_from_config())
    except KeyboardInterrupt:
        logger.info("🛑 Прервано пользователем")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)

