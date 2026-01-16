#!/usr/bin/env python3
"""
Запуск постинга прямо сейчас для всех доступных групп
"""
import sys
import asyncio
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.database.session import SessionLocal, init_db
from shared.database.models import Account, Group
from shared.config.loader import ConfigLoader
from shared.telegram.client_manager import TelegramClientManager
from services.marketer.poster import Poster

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def start_posting():
    """Запустить постинг для всех доступных групп"""
    logger.info("=" * 80)
    logger.info("🚀 ЗАПУСК ПОСТИНГА ПРЯМО СЕЙЧАС")
    logger.info("=" * 80)
    
    # Инициализация
    init_db()
    db = SessionLocal()
    
    try:
        # Загрузка конфигурации
        config_dir = Path(__file__).parent.parent / "config"
        if not config_dir.exists():
            config_dir = Path("/app/config")
        config_loader = ConfigLoader(config_dir=str(config_dir))
        niche_config = config_loader.load_niche_config()
        niche_name = niche_config.get('name', 'bali')
        
        logger.info(f"📋 Ниша: {niche_config.get('display_name')} ({niche_name})")
        
        # Инициализация клиентов
        sessions_dir = Path(__file__).parent.parent / "sessions"
        if not sessions_dir.exists():
            sessions_dir = Path("/app/sessions")
        
        client_manager = TelegramClientManager(sessions_dir=str(sessions_dir))
        await client_manager.load_accounts_from_db(db)
        
        logger.info(f"✅ Загружено аккаунтов: {len(client_manager.clients)}")
        
        # Инициализация Poster
        poster = Poster(client_manager, config_loader, niche_config)
        await poster.initialize()
        
        logger.info(f"✅ Загружено сообщений: {len(poster.messages)}")
        
        # Получаем доступные группы
        available_groups = poster.get_available_groups(db, niche_name, limit=None)
        
        logger.info(f"\n📊 Доступных групп для постинга: {len(available_groups)}")
        
        if len(available_groups) == 0:
            logger.warning("⚠️  Нет доступных групп для постинга")
            logger.info("\n💡 Возможные причины:")
            logger.info("   - Группы не вступили (joined_at = NULL)")
            logger.info("   - Warm-up период не закончился")
            logger.info("   - Группы помечены как banned")
            logger.info("   - Достигнут лимит постов за день")
            return
        
        # Показываем первые 10 групп
        logger.info("\n📋 Группы для постинга (первые 10):")
        for i, group in enumerate(available_groups[:10], 1):
            account_name = "не назначен"
            if group.assigned_account_id:
                account = db.query(Account).filter(Account.id == group.assigned_account_id).first()
                if account:
                    account_name = account.session_name
            logger.info(f"   {i}. {group.username} (аккаунт: {account_name})")
        
        if len(available_groups) > 10:
            logger.info(f"   ... и ещё {len(available_groups) - 10} групп")
        
        # Запускаем постинг
        logger.info(f"\n🚀 Начинаю постинг в {len(available_groups)} групп...")
        logger.info("=" * 80)
        
        successful = 0
        failed = 0
        
        for i, group in enumerate(available_groups, 1):
            try:
                # Получаем аккаунт для группы
                account = None
                if group.assigned_account_id:
                    account = db.query(Account).filter(Account.id == group.assigned_account_id).first()
                
                if not account:
                    # Выбираем случайный аккаунт
                    accounts = db.query(Account).filter(Account.status == 'active').all()
                    if accounts:
                        import random
                        account = random.choice(accounts)
                        # Назначаем аккаунт группе
                        group.assigned_account_id = account.id
                        db.commit()
                
                if not account:
                    logger.warning(f"  ⚠️  {i}/{len(available_groups)} {group.username}: нет доступных аккаунтов")
                    failed += 1
                    continue
                
                # Получаем клиент
                client = client_manager.clients.get(account.session_name)
                if not client or not client.is_connected():
                    logger.warning(f"  ⚠️  {i}/{len(available_groups)} {group.username}: клиент {account.session_name} не подключен")
                    failed += 1
                    continue
                
                logger.info(f"  📤 {i}/{len(available_groups)} Постинг в {group.username} через {account.session_name}...")
                
                # Постим
                success, error = await poster.post_to_group(db, group, account, client)
                
                if success:
                    successful += 1
                    logger.info(f"     ✅ Успешно!")
                else:
                    failed += 1
                    logger.warning(f"     ❌ Ошибка: {error}")
                
                # Небольшая пауза между постами
                await asyncio.sleep(2)
                
            except Exception as e:
                failed += 1
                logger.error(f"  ❌ {i}/{len(available_groups)} {group.username}: {e}", exc_info=True)
                await asyncio.sleep(1)
        
        logger.info("")
        logger.info("=" * 80)
        logger.info("📊 ИТОГИ ПОСТИНГА:")
        logger.info(f"   ✅ Успешно: {successful}")
        logger.info(f"   ❌ Неудачно: {failed}")
        logger.info(f"   📊 Всего: {len(available_groups)}")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    try:
        asyncio.run(start_posting())
    except KeyboardInterrupt:
        logger.info("🛑 Прервано пользователем")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)
