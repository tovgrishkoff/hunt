#!/usr/bin/env python3
"""
Массовый импорт аккаунтов из accounts_config.json в PostgreSQL БД
Конвертирует .session файлы в StringSession для хранения в БД
"""
import sys
import json
import asyncio
from pathlib import Path

# Добавляем путь к shared модулям
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.database.session import SessionLocal, init_db
from shared.database.models import Account
from shared.utils.session_converter import convert_session_to_string
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def import_account_from_config(config_data: dict, sessions_dir: Path, skip_conversion: bool = False):
    """
    Импортирует один аккаунт из конфигурации
    
    Args:
        config_data: Данные аккаунта из accounts_config.json
        sessions_dir: Директория с session файлами
        skip_conversion: Пропустить конвертацию (использовать string_session из config если есть)
    """
    session_name = config_data.get('session_name')
    if not session_name:
        logger.warning("⚠️ Skipping account without session_name")
        return False
    
    db = SessionLocal()
    try:
        # Проверяем, есть ли уже такой аккаунт
        existing = db.query(Account).filter(Account.session_name == session_name).first()
        if existing:
            logger.info(f"ℹ️ Account {session_name} already exists, skipping")
            return False
        
        # Проверяем наличие string_session в конфиге
        string_session = config_data.get('string_session')
        
        # Если нет string_session и не пропускаем конвертацию - конвертируем из файла
        if not string_session and not skip_conversion:
            session_file = sessions_dir / f"{session_name}.session"
            if session_file.exists():
                api_id = config_data.get('api_id')
                api_hash = config_data.get('api_hash')
                proxy = config_data.get('proxy')
                
                if api_id and api_hash:
                    logger.info(f"🔄 Converting {session_name}.session to StringSession...")
                    string_session = await convert_session_to_string(
                        session_file,
                        api_id,
                        api_hash,
                        proxy
                    )
                    if not string_session:
                        logger.error(f"❌ Failed to convert {session_name}, skipping")
                        return False
                else:
                    logger.warning(f"⚠️ No API credentials for {session_name}, skipping conversion")
            else:
                logger.warning(f"⚠️ Session file not found: {session_file}")
        
        # Создаем запись в БД
        account = Account(
            session_name=session_name,
            phone=config_data.get('phone'),
            api_id=config_data.get('api_id'),
            api_hash=config_data.get('api_hash'),
            string_session=string_session,
            proxy=config_data.get('proxy'),
            nickname=config_data.get('nickname'),
            bio=config_data.get('bio'),
            status='active'
        )
        
        db.add(account)
        db.commit()
        
        logger.info(f"✅ Imported account: {session_name} (string_session: {'yes' if string_session else 'no'})")
        return True
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Error importing {session_name}: {e}")
        return False
    finally:
        db.close()


async def import_from_session_files(sessions_dir: Path):
    """
    Импортирует аккаунты из session файлов (если нет accounts_config.json)
    """
    logger.info("📁 Scanning session files...")
    
    session_files = list(sessions_dir.glob("*.session"))
    logger.info(f"Found {len(session_files)} session files")
    
    # Нужен accounts_config.json для получения API credentials
    config_file = Path(__file__).parent.parent / "accounts_config.json"
    if not config_file.exists():
        logger.error("❌ accounts_config.json not found. Cannot import without API credentials.")
        return
    
    with open(config_file, 'r', encoding='utf-8') as f:
        accounts_config = json.load(f)
    
    # Создаем маппинг session_name -> config
    config_map = {acc.get('session_name'): acc for acc in accounts_config if acc.get('session_name')}
    
    imported = 0
    for session_file in session_files:
        session_name = session_file.stem
        
        if session_name in config_map:
            config_data = config_map[session_name]
            success = await import_account_from_config(config_data, sessions_dir, skip_conversion=False)
            if success:
                imported += 1
        else:
            logger.warning(f"⚠️ No config found for {session_name}, skipping")
    
    logger.info(f"✅ Imported {imported} accounts from session files")


async def main():
    """Основная функция"""
    logger.info("=" * 80)
    logger.info("📥 MASS ACCOUNT IMPORT")
    logger.info("=" * 80)
    
    # Инициализация БД
    try:
        init_db()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize database: {e}")
        return
    
    base_dir = Path(__file__).parent.parent
    config_file = base_dir / "accounts_config.json"
    sessions_dir = base_dir / "sessions"
    
    # Создаем директорию sessions если нет
    sessions_dir.mkdir(exist_ok=True)
    
    if config_file.exists():
        logger.info(f"📄 Reading accounts from {config_file}")
        with open(config_file, 'r', encoding='utf-8') as f:
            accounts_config = json.load(f)
        
        logger.info(f"Found {len(accounts_config)} accounts in config")
        
        imported = 0
        skipped = 0
        
        for config_data in accounts_config:
            # Проверяем, есть ли уже string_session в конфиге
            has_string_session = bool(config_data.get('string_session'))
            
            if has_string_session:
                # Используем готовый string_session
                success = await import_account_from_config(config_data, sessions_dir, skip_conversion=True)
            else:
                # Конвертируем из файла
                success = await import_account_from_config(config_data, sessions_dir, skip_conversion=False)
            
            if success:
                imported += 1
            else:
                skipped += 1
        
        logger.info("=" * 80)
        logger.info(f"✅ Import completed: {imported} imported, {skipped} skipped")
    else:
        logger.info(f"⚠️ Config file not found: {config_file}")
        logger.info("Trying to import from session files...")
        await import_from_session_files(sessions_dir)


if __name__ == "__main__":
    asyncio.run(main())

