#!/usr/bin/env python3
"""
Обновить все StringSession в БД из accounts_config.json
Обновляет существующие аккаунты и добавляет новые
"""
import sys
import json
import asyncio
from pathlib import Path
from datetime import datetime

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


def update_all_accounts_from_config():
    """Обновить все StringSession в БД из accounts_config.json"""
    logger.info("=" * 80)
    logger.info("🔄 ОБНОВЛЕНИЕ ВСЕХ АККАУНТОВ ИЗ CONFIG")
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
    
    logger.info(f"📋 Найдено аккаунтов в конфиге: {len(accounts_config)}")
    logger.info("")
    
    db = SessionLocal()
    updated = 0
    added = 0
    skipped = 0
    
    try:
        for config_data in accounts_config:
            session_name = config_data.get('session_name')
            if not session_name:
                logger.warning(f"⚠️ Пропущен аккаунт без session_name")
                skipped += 1
                continue
            
            string_session = config_data.get('string_session')
            has_valid_session = string_session and len(string_session) >= 50
            
            # Находим аккаунт в БД
            account = db.query(Account).filter(Account.session_name == session_name).first()
            
            if account:
                # Обновляем существующий: всегда синхронизируем proxy, api_id, phone и т.д.
                old_session = account.string_session
                if has_valid_session:
                    account.string_session = string_session
                account.api_id = config_data.get('api_id', account.api_id)
                account.api_hash = config_data.get('api_hash', account.api_hash)
                account.phone = config_data.get('phone', account.phone)
                account.nickname = config_data.get('nickname', account.nickname)
                account.proxy = config_data.get('proxy', account.proxy)
                account.status = 'active'  # Активируем
                account.updated_at = datetime.utcnow()
                
                db.commit()
                
                if has_valid_session and old_session != string_session:
                    logger.info(f"✅ ОБНОВЛЕН: {session_name} (StringSession + proxy/поля)")
                    updated += 1
                else:
                    logger.info(f"✅ ОБНОВЛЕН: {session_name} (proxy и поля из конфига)")
                    updated += 1
            elif has_valid_session:
                # Создаем новый только при наличии валидной сессии
                new_account = Account(
                    session_name=session_name,
                    api_id=config_data.get('api_id'),
                    api_hash=config_data.get('api_hash'),
                    phone=config_data.get('phone'),
                    string_session=string_session,
                    nickname=config_data.get('nickname'),
                    proxy=config_data.get('proxy'),
                    status='active'
                )
                db.add(new_account)
                db.commit()
                
                logger.info(f"✅ ДОБАВЛЕН: {session_name}")
                added += 1
            else:
                logger.warning(f"⚠️ Нет валидной StringSession в конфиге для {session_name}, аккаунт в БД не найден — пропуск")
                skipped += 1
        
        logger.info("")
        logger.info("=" * 80)
        logger.info(f"📊 ИТОГО:")
        logger.info(f"   ✅ Обновлено: {updated}")
        logger.info(f"   ✅ Добавлено: {added}")
        logger.info(f"   ⚠️  Пропущено: {skipped}")
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
        update_all_accounts_from_config()
    except KeyboardInterrupt:
        logger.info("\n⚠️ Прервано пользователем")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
