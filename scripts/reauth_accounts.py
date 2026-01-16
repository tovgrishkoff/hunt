#!/usr/bin/env python3
"""
Скрипт для переавторизации аккаунтов
Создает новые StringSession для аккаунтов, у которых сессии были сброшены
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


async def reauth_account(session_name: str, api_id: int, api_hash: str, proxy: str = None, password: str = None):
    """
    Переавторизовать аккаунт и получить новую StringSession
    
    Args:
        session_name: Имя сессии
        api_id: API ID
        api_hash: API Hash
        proxy: Прокси (опционально)
        password: 2FA пароль (если требуется)
    
    Returns:
        StringSession или None
    """
    logger.info(f"🔄 Переавторизация аккаунта: {session_name}")
    
    # Определяем путь к session файлу
    sessions_dir = Path(__file__).parent.parent / "sessions"
    session_file = sessions_dir / f"{session_name}.session"
    
    if not session_file.exists():
        logger.error(f"❌ Session файл не найден: {session_file}")
        return None
    
    # Используем существующую утилиту для конвертации
    try:
        logger.info(f"🔄 Конвертация {session_name}.session в StringSession...")
        string_session = await convert_session_to_string(
            session_file=session_file,
            api_id=api_id,
            api_hash=api_hash,
            proxy=proxy
        )
        
        if string_session:
            # Проверяем, что это валидная StringSession (обычно начинается с "1" и имеет длину > 100)
            if len(string_session) > 50 and string_session.startswith('1'):
                logger.info(f"✅ StringSession создана для {session_name} (длина: {len(string_session)})")
                return string_session
            else:
                logger.warning(f"⚠️ Получена невалидная StringSession для {session_name} (длина: {len(string_session) if string_session else 0})")
                logger.info("💡 Возможно, сессия не авторизована. Для переавторизации нужно:")
                logger.info(f"   1. Удалить старый .session файл: rm sessions/{session_name}.session")
                logger.info("   2. Создать новую сессию через Telethon с кодом из Telegram")
                return None
        else:
            logger.warning(f"⚠️ Аккаунт {session_name} не авторизован или сессия невалидна")
            logger.info("💡 Для переавторизации нужно:")
            logger.info(f"   1. Удалить старый .session файл: rm sessions/{session_name}.session")
            logger.info("   2. Создать новую сессию через Telethon с кодом из Telegram")
            return None
        
    except Exception as e:
        logger.error(f"❌ Ошибка при переавторизации {session_name}: {e}", exc_info=True)
        return None


async def update_account_string_session(session_name: str, string_session: str):
    """Обновить StringSession в БД"""
    db = SessionLocal()
    try:
        account = db.query(Account).filter(Account.session_name == session_name).first()
        if not account:
            logger.error(f"❌ Аккаунт {session_name} не найден в БД")
            return False
        
        account.string_session = string_session
        db.commit()
        
        logger.info(f"✅ StringSession обновлен в БД для {session_name}")
        return True
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Ошибка при обновлении БД: {e}")
        return False
    finally:
        db.close()


async def main():
    """Основная функция"""
    logger.info("=" * 80)
    logger.info("🔄 ПЕРЕАВТОРИЗАЦИЯ АККАУНТОВ")
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
    
    # Создаем маппинг session_name -> config
    config_map = {acc.get('session_name'): acc for acc in accounts_config if acc.get('session_name')}
    
    # Аккаунты для переавторизации
    accounts_to_reauth = ['promotion_dao_bro', 'promotion_oleg_petrov']
    
    logger.info(f"📋 Аккаунты для переавторизации: {', '.join(accounts_to_reauth)}")
    logger.info("")
    
    for session_name in accounts_to_reauth:
        if session_name not in config_map:
            logger.warning(f"⚠️ Аккаунт {session_name} не найден в accounts_config.json, пропускаем")
            continue
        
        config_data = config_map[session_name]
        api_id = config_data.get('api_id')
        api_hash = config_data.get('api_hash')
        proxy = config_data.get('proxy')
        phone = config_data.get('phone')
        password = config_data.get('password')  # 2FA пароль если есть
        
        if not api_id or not api_hash:
            logger.error(f"❌ Нет API credentials для {session_name}, пропускаем")
            continue
        
        logger.info(f"")
        logger.info(f"🔄 Обработка аккаунта: {session_name}")
        logger.info(f"📱 Телефон: {phone if phone else 'не указан'}")
        logger.info(f"=" * 80)
        
        # Переавторизация
        string_session = await reauth_account(
            session_name=session_name,
            api_id=api_id,
            api_hash=api_hash,
            proxy=proxy,
            password=password
        )
        
        if string_session and len(string_session) > 10:  # Проверяем, что сессия валидная
            # Обновляем в БД
            success = await update_account_string_session(session_name, string_session)
            if success:
                logger.info(f"✅ Аккаунт {session_name} успешно переавторизован и обновлен в БД")
            else:
                logger.error(f"❌ Не удалось обновить БД для {session_name}")
        else:
            logger.warning(f"⚠️ Не удалось получить новую сессию для {session_name}")
            logger.info(f"💡 Попробуйте удалить файл sessions/{session_name}.session и создать новый")
            logger.info(f"   Или используйте интерактивную авторизацию через Telethon")
        
        logger.info("")
    
    logger.info("=" * 80)
    logger.info("✅ ПЕРЕАВТОРИЗАЦИЯ ЗАВЕРШЕНА")
    logger.info("=" * 80)
    logger.info("")
    logger.info("🔄 Перезапустите контейнеры для применения изменений:")
    logger.info("   docker-compose restart account-manager marketer activity secretary")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Прервано пользователем")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)

