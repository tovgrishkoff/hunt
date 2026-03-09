#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Простой скрипт для форс-постинга Lexus
Исправляет статусы аккаунтов и групп, затем запускает постинг
"""

import asyncio
import sys
import logging
from datetime import datetime

# Добавляем корень проекта в путь
sys.path.insert(0, '/app')

from services.marketer.poster import SmartPoster
from lexus_db.session import AsyncSessionLocal
from sqlalchemy import text

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


async def fix_accounts_status():
    """Исправляет статус аккаунтов: переводит из cooldown в active, если время прошло"""
    logger.info("=" * 80)
    logger.info("🔧 FIXING ACCOUNTS STATUS")
    logger.info("=" * 80)
    
    async with AsyncSessionLocal() as session:
        try:
            # Обновляем аккаунты из cooldown в active, если время прошло
            result = await session.execute(
                text("""
                    UPDATE accounts 
                    SET status = 'active',
                        updated_at = NOW()
                    WHERE status = 'cooldown' 
                      AND (next_allowed_action_time IS NULL OR next_allowed_action_time <= NOW())
                    RETURNING id, session_name, status
                """)
            )
            updated_accounts = result.fetchall()
            
            if updated_accounts:
                logger.info(f"✅ Updated {len(updated_accounts)} accounts from cooldown to active:")
                for acc in updated_accounts:
                    logger.info(f"   - {acc[1]} (id: {acc[0]})")
            else:
                logger.info("ℹ️ No accounts needed status update")
            
            await session.commit()
            
            # Проверяем текущий статус всех аккаунтов
            result = await session.execute(
                text("""
                    SELECT session_name, status, next_allowed_action_time 
                    FROM accounts 
                    ORDER BY session_name
                """)
            )
            all_accounts = result.fetchall()
            
            logger.info(f"\n📊 Current accounts status:")
            for acc in all_accounts:
                logger.info(f"   - {acc[0]}: {acc[1]} (next_action: {acc[2]})")
            
        except Exception as e:
            logger.error(f"❌ Error fixing accounts status: {e}", exc_info=True)
            await session.rollback()


async def fix_groups_status():
    """Активирует группы, которые прошли warm-up период"""
    logger.info("\n" + "=" * 80)
    logger.info("🔧 FIXING GROUPS STATUS")
    logger.info("=" * 80)
    
    async with AsyncSessionLocal() as session:
        try:
            # Активируем группы, которые прошли warm-up
            result = await session.execute(
                text("""
                    UPDATE groups 
                    SET status = 'active',
                        updated_at = NOW()
                    WHERE niche = 'ukraine_cars'
                      AND status != 'active'
                      AND (warm_up_until IS NULL OR warm_up_until <= NOW())
                      AND can_post = true
                    RETURNING id, username, status
                """)
            )
            updated_groups = result.fetchall()
            
            if updated_groups:
                logger.info(f"✅ Activated {len(updated_groups)} groups:")
                for grp in updated_groups[:10]:  # Показываем первые 10
                    logger.info(f"   - {grp[1]} (id: {grp[0]})")
                if len(updated_groups) > 10:
                    logger.info(f"   ... and {len(updated_groups) - 10} more")
            else:
                logger.info("ℹ️ No groups needed activation")
            
            await session.commit()
            
            # Проверяем статистику групп
            result = await session.execute(
                text("""
                    SELECT 
                        COUNT(*) as total,
                        COUNT(CASE WHEN status = 'active' THEN 1 END) as active,
                        COUNT(CASE WHEN warm_up_until <= NOW() THEN 1 END) as warmed_up
                    FROM groups 
                    WHERE niche = 'ukraine_cars'
                """)
            )
            stats = result.fetchone()
            
            logger.info(f"\n📊 Groups statistics:")
            logger.info(f"   Total: {stats[0]}")
            logger.info(f"   Active: {stats[1]}")
            logger.info(f"   Warmed up: {stats[2]}")
            
        except Exception as e:
            logger.error(f"❌ Error fixing groups status: {e}", exc_info=True)
            await session.rollback()


async def force_posting(batch_size: int = 20):
    """Запускает форс-постинг"""
    logger.info("\n" + "=" * 80)
    logger.info("🚀 FORCE POSTING")
    logger.info("=" * 80)
    
    try:
        poster = SmartPoster(niche='ukraine_cars')
        await poster.run_batch(batch_size=batch_size)
        logger.info("✅ Force posting completed")
    except Exception as e:
        logger.error(f"❌ Error during force posting: {e}", exc_info=True)
        raise


async def main():
    """Основная функция"""
    logger.info("=" * 80)
    logger.info("🚀 FORCE LEXUS POSTING - Принудительный запуск постинга")
    logger.info("=" * 80)
    
    # Шаг 1: Исправляем статус аккаунтов
    await fix_accounts_status()
    
    # Шаг 2: Активируем группы
    await fix_groups_status()
    
    # Шаг 3: Запускаем постинг
    batch_size = 20
    if len(sys.argv) > 1:
        try:
            batch_size = int(sys.argv[1])
        except ValueError:
            logger.warning(f"⚠️ Invalid batch_size argument: {sys.argv[1]}, using default: {batch_size}")
    
    await force_posting(batch_size=batch_size)
    
    logger.info("\n" + "=" * 80)
    logger.info("✅ FORCE POSTING COMPLETED")
    logger.info("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
