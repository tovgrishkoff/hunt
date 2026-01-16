#!/usr/bin/env python3
"""
Скрипт для обновления string_session в БД Ukraine из accounts_config.json
"""
import sys
import json
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lexus_db.models import Account
import logging
import os

# Устанавливаем переменные окружения для Ukraine БД
os.environ['DATABASE_URL'] = 'postgresql://telegram_user_ukraine:telegram_password_ukraine@localhost:5439/ukraine_db'
os.environ['POSTGRES_HOST'] = 'localhost'
os.environ['POSTGRES_PORT'] = '5439'
os.environ['POSTGRES_USER'] = 'telegram_user_ukraine'
os.environ['POSTGRES_PASSWORD'] = 'telegram_password_ukraine'
os.environ['POSTGRES_DB'] = 'ukraine_db'

# Импортируем после установки переменных окружения
from shared.database.session import SessionLocal

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Обновить string_session для Ukraine аккаунтов"""
    logger.info("=" * 80)
    logger.info("🔄 ОБНОВЛЕНИЕ UKRAINE АККАУНТОВ ИЗ CONFIG")
    logger.info("=" * 80)
    
    # Загружаем конфиг
    config_path = Path(__file__).parent.parent / "accounts_config.json"
    
    if not config_path.exists():
        logger.error(f"❌ Файл accounts_config.json не найден: {config_path}")
        return
    
    with open(config_path, 'r', encoding='utf-8') as f:
        accounts_config = json.load(f)
    
    # Ukraine аккаунты
    accounts_to_update = ['promotion_dao_bro', 'promotion_alex_ever', 'promotion_rod_shaihutdinov']
    
    db = SessionLocal()
    updated = 0
    skipped = 0
    
    try:
        for config_data in accounts_config:
            session_name = config_data.get('session_name')
            if session_name not in accounts_to_update:
                continue
            
            string_session = config_data.get('string_session')
            if not string_session or len(string_session) < 50:
                logger.warning(f"⚠️ Нет валидной StringSession в конфиге для {session_name}")
                skipped += 1
                continue
            
            # Находим аккаунт в БД
            account = db.query(Account).filter(Account.session_name == session_name).first()
            if not account:
                logger.warning(f"⚠️ Аккаунт {session_name} не найден в БД")
                skipped += 1
                continue
            
            # Обновляем StringSession
            old_session = account.string_session
            account.string_session = string_session
            account.status = 'active'  # Активируем аккаунт
            db.commit()
            
            if old_session != string_session:
                logger.info(f"✅ ОБНОВЛЕН: {session_name} (StringSession изменен, длина: {len(string_session)})")
                updated += 1
            else:
                logger.info(f"ℹ️  БЕЗ ИЗМЕНЕНИЙ: {session_name} (StringSession уже актуален)")
        
        logger.info("")
        logger.info("=" * 80)
        logger.info(f"✅ ОБНОВЛЕНО: {updated} аккаунтов")
        if skipped > 0:
            logger.info(f"⚠️  ПРОПУЩЕНО: {skipped} аккаунтов")
        logger.info("=" * 80)
        logger.info("")
        logger.info("🔄 Перезапустите контейнер ukraine-marketer для применения изменений:")
        logger.info("   docker-compose -f docker-compose.ukraine.yml restart marketer")
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Ошибка при обновлении: {e}", exc_info=True)
    finally:
        db.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("\n🛑 Прервано пользователем")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n❌ Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)
