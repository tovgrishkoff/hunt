#!/usr/bin/env python3
"""
🔍 РЕВИЗОР ГРУПП - Проверка реального статуса групп в БД
Проверяет, действительно ли аккаунты являются участниками групп
и могут ли они постить
"""
import sys
import asyncio
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.database.session import SessionLocal, init_db
from shared.database.models import Account, Group
from shared.telegram.client_manager import TelegramClientManager

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def review_groups():
    """Проверить реальный статус групп"""
    logger.info("=" * 80)
    logger.info("🔍 РЕВИЗОР ГРУПП - Проверка реального статуса")
    logger.info("=" * 80)
    
    init_db()
    db = SessionLocal()
    
    try:
        # Инициализация клиентов
        sessions_dir = Path(__file__).parent.parent / "sessions"
        if not sessions_dir.exists():
            sessions_dir = Path("/app/sessions")
        
        client_manager = TelegramClientManager(sessions_dir=str(sessions_dir))
        await client_manager.load_accounts_from_db(db)
        
        logger.info(f"✅ Загружено аккаунтов: {len(client_manager.clients)}")
        
        # Получаем активные группы
        active_groups = db.query(Group).filter(
            Group.niche == 'bali',
            Group.status == 'active',
            Group.can_post == True
        ).all()
        
        logger.info(f"\n📊 Найдено активных групп: {len(active_groups)}")
        logger.info(f"🔄 Проверяю реальный статус...")
        logger.info("")
        
        checked = 0
        actually_joined = 0
        can_post_really = 0
        marked_banned = 0
        marked_inaccessible = 0
        
        for group in active_groups:
            checked += 1
            
            # Получаем назначенный аккаунт
            account = None
            if group.assigned_account_id:
                account = db.query(Account).filter(Account.id == group.assigned_account_id).first()
            
            if not account:
                # Пробуем найти любой активный аккаунт
                account = db.query(Account).filter(Account.status == 'active').first()
            
            if not account:
                logger.warning(f"  ⚠️  {group.username}: нет доступных аккаунтов")
                continue
            
            # Получаем клиент
            client = client_manager.clients.get(account.session_name)
            if not client:
                logger.warning(f"  ⚠️  {group.username}: клиент {account.session_name} не загружен")
                continue
            
            # Убеждаемся, что клиент подключен
            if not client.is_connected():
                client = await client_manager.ensure_client_connected(account.session_name)
                if not client:
                    logger.warning(f"  ⚠️  {group.username}: клиент не подключен")
                    continue
            
            try:
                # Проверяем, является ли аккаунт участником группы
                entity = await client.get_entity(group.username)
                
                # Пробуем получить права
                try:
                    me = await client.get_me()
                    permissions = await client.get_permissions(entity, me)
                    
                    if permissions:
                        # Проверяем, может ли постить
                        can_post = True
                        if hasattr(permissions, 'send_messages') and not permissions.send_messages:
                            can_post = False
                        elif hasattr(permissions, 'banned_rights') and permissions.banned_rights:
                            if hasattr(permissions.banned_rights, 'send_messages') and permissions.banned_rights.send_messages:
                                can_post = False
                        
                        if can_post:
                            can_post_really += 1
                            actually_joined += 1
                            logger.info(f"  ✅ {group.username}: участник, может постить")
                        else:
                            actually_joined += 1
                            marked_banned += 1
                            logger.warning(f"  🚫 {group.username}: участник, но НЕ может постить")
                            
                            # Помечаем как banned
                            try:
                                group.status = 'banned'
                                group.can_post = False
                                db.commit()
                            except:
                                db.rollback()
                    else:
                        # Не можем получить права - возможно не участник
                        logger.warning(f"  ⚠️  {group.username}: не удалось получить права (возможно не участник)")
                        marked_inaccessible += 1
                        
                        # Помечаем как inaccessible
                        try:
                            group.status = 'inaccessible'
                            group.can_post = False
                            db.commit()
                        except:
                            db.rollback()
                
                except Exception as perm_error:
                    # Ошибка при получении прав - возможно не участник
                    logger.warning(f"  ⚠️  {group.username}: ошибка проверки прав - {perm_error}")
                    marked_inaccessible += 1
                    
                    # Помечаем как inaccessible
                    try:
                        group.status = 'inaccessible'
                        group.can_post = False
                        db.commit()
                    except:
                        db.rollback()
                
            except Exception as e:
                logger.warning(f"  ❌ {group.username}: ошибка проверки - {e}")
                marked_inaccessible += 1
                
                # Помечаем как inaccessible
                try:
                    group.status = 'inaccessible'
                    group.can_post = False
                    db.commit()
                except:
                    db.rollback()
            
            # Небольшая пауза между проверками
            await asyncio.sleep(2)
        
        logger.info("")
        logger.info("=" * 80)
        logger.info("📊 ИТОГИ РЕВИЗИИ:")
        logger.info(f"   Проверено групп: {checked}")
        logger.info(f"   ✅ Реально участники: {actually_joined}")
        logger.info(f"   ✅ Могут постить: {can_post_really}")
        logger.info(f"   🚫 Помечено как banned: {marked_banned}")
        logger.info(f"   ⚠️  Помечено как inaccessible: {marked_inaccessible}")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    try:
        asyncio.run(review_groups())
    except KeyboardInterrupt:
        logger.info("🛑 Прервано пользователем")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)
