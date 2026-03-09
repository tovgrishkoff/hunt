#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Улучшенный форс-постинг для Lexus
- Проверяет и исправляет статусы аккаунтов
- Активирует группы
- Проверяет членство в группах
- Запускает постинг с детальной статистикой
"""

import asyncio
import sys
import logging
import argparse
from datetime import datetime
from pathlib import Path

# Добавляем корень проекта в путь
sys.path.insert(0, '/app')

from services.marketer.poster import SmartPoster
from lexus_db.session import AsyncSessionLocal
from lexus_db.models import Account, Target
from sqlalchemy import text, select, and_, or_, func

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/logs/force_lexus_posting.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


async def check_and_fix_accounts():
    """Проверяет и исправляет статус аккаунтов"""
    logger.info("=" * 80)
    logger.info("🔧 ПРОВЕРКА И ИСПРАВЛЕНИЕ АККАУНТОВ")
    logger.info("=" * 80)
    
    async with AsyncSessionLocal() as session:
        try:
            # Получаем все аккаунты
            result = await session.execute(
                select(Account).order_by(Account.session_name)
            )
            all_accounts = result.scalars().all()
            
            logger.info(f"📊 Всего аккаунтов в БД: {len(all_accounts)}")
            
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
                logger.info(f"✅ Обновлено {len(updated_accounts)} аккаунтов из cooldown в active:")
                for acc in updated_accounts:
                    logger.info(f"   - {acc[1]} (id: {acc[0]})")
            else:
                logger.info("ℹ️ Нет аккаунтов, требующих обновления статуса")
            
            await session.commit()
            
            # Проверяем активные аккаунты
            result = await session.execute(
                select(Account).where(Account.status == 'active')
            )
            active_accounts = result.scalars().all()
            
            logger.info(f"\n📊 Активные аккаунты ({len(active_accounts)}):")
            for acc in active_accounts:
                logger.info(f"   - {acc.session_name} (id: {acc.id}, status: {acc.status})")
            
            if len(active_accounts) == 0:
                logger.warning("⚠️ НЕТ АКТИВНЫХ АККАУНТОВ! Постинг невозможен.")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка при проверке аккаунтов: {e}", exc_info=True)
            await session.rollback()
            return False


async def check_and_activate_groups():
    """Проверяет и активирует группы"""
    logger.info("\n" + "=" * 80)
    logger.info("🔧 ПРОВЕРКА И АКТИВАЦИЯ ГРУПП")
    logger.info("=" * 80)
    
    async with AsyncSessionLocal() as session:
        try:
            # Статистика групп
            result = await session.execute(
                text("""
                    SELECT 
                        COUNT(*) as total,
                        COUNT(CASE WHEN status = 'active' THEN 1 END) as active,
                        COUNT(CASE WHEN status = 'joined' THEN 1 END) as joined,
                        COUNT(CASE WHEN status = 'new' THEN 1 END) as new,
                        COUNT(CASE WHEN status = 'no_accounts_left' THEN 1 END) as no_accounts,
                        COUNT(CASE WHEN status = 'inaccessible' THEN 1 END) as inaccessible,
                        COUNT(CASE WHEN warm_up_until <= NOW() THEN 1 END) as warmed_up
                    FROM groups 
                    WHERE niche = 'ukraine_cars'
                """)
            )
            stats = result.fetchone()
            
            logger.info(f"📊 Статистика групп:")
            logger.info(f"   Всего: {stats[0]}")
            logger.info(f"   Active: {stats[1]}")
            logger.info(f"   Joined: {stats[2]}")
            logger.info(f"   New: {stats[3]}")
            logger.info(f"   No accounts left: {stats[4]}")
            logger.info(f"   Inaccessible: {stats[5]}")
            logger.info(f"   Warmed up: {stats[6]}")
            
            # Активируем группы, которые прошли warm-up
            result = await session.execute(
                text("""
                    UPDATE groups 
                    SET status = CASE 
                        WHEN status = 'joined' THEN 'joined'
                        ELSE 'active'
                    END,
                        updated_at = NOW()
                    WHERE niche = 'ukraine_cars'
                      AND status NOT IN ('joined', 'active')
                      AND (warm_up_until IS NULL OR warm_up_until <= NOW())
                      AND can_post = true
                    RETURNING id, username, status
                """)
            )
            updated_groups = result.fetchall()
            
            if updated_groups:
                logger.info(f"\n✅ Активировано {len(updated_groups)} групп:")
                for grp in updated_groups[:10]:  # Показываем первые 10
                    logger.info(f"   - {grp[1]} (id: {grp[0]}, status: {grp[2]})")
                if len(updated_groups) > 10:
                    logger.info(f"   ... и {len(updated_groups) - 10} еще")
            else:
                logger.info("ℹ️ Нет групп, требующих активации")
            
            await session.commit()
            
            # Проверяем готовые к постингу группы
            now = datetime.utcnow()
            result = await session.execute(
                select(func.count(Target.id))
                .where(
                    and_(
                        Target.niche == 'ukraine_cars',
                        or_(Target.status == 'joined', Target.status == 'active'),
                        or_(Target.warm_up_until.is_(None), Target.warm_up_until <= now),
                        or_(Target.can_post.is_(None), Target.can_post.is_(True)),
                        or_(Target.daily_posts_count.is_(None), Target.daily_posts_count < 2),
                    )
                )
            )
            ready_count = result.scalar_one() or 0
            
            logger.info(f"\n📊 Групп готовых к постингу: {ready_count}")
            
            if ready_count == 0:
                logger.warning("⚠️ НЕТ ГРУПП, ГОТОВЫХ К ПОСТИНГУ!")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка при проверке групп: {e}", exc_info=True)
            await session.rollback()
            return False


async def check_membership_stats():
    """Проверяет статистику членства в группах"""
    logger.info("\n" + "=" * 80)
    logger.info("👥 ПРОВЕРКА ЧЛЕНСТВА В ГРУППАХ")
    logger.info("=" * 80)
    
    async with AsyncSessionLocal() as session:
        try:
            # Группы с назначенными аккаунтами
            result = await session.execute(
                text("""
                    SELECT 
                        COUNT(*) as total_with_account,
                        COUNT(CASE WHEN status = 'joined' THEN 1 END) as joined_with_account,
                        COUNT(CASE WHEN status = 'active' THEN 1 END) as active_with_account
                    FROM groups 
                    WHERE niche = 'ukraine_cars' 
                      AND assigned_account_id IS NOT NULL
                """)
            )
            stats = result.fetchone()
            
            logger.info(f"📊 Группы с назначенными аккаунтами:")
            logger.info(f"   Всего: {stats[0]}")
            logger.info(f"   Со статусом 'joined': {stats[1]}")
            logger.info(f"   Со статусом 'active': {stats[2]}")
            
            # Группы без назначенных аккаунтов, но готовые к постингу
            now = datetime.utcnow()
            result = await session.execute(
                select(func.count(Target.id))
                .where(
                    and_(
                        Target.niche == 'ukraine_cars',
                        or_(Target.status == 'joined', Target.status == 'active'),
                        or_(Target.warm_up_until.is_(None), Target.warm_up_until <= now),
                        or_(Target.can_post.is_(None), Target.can_post.is_(True)),
                        Target.assigned_account_id.is_(None),
                    )
                )
            )
            ready_without_account = result.scalar_one() or 0
            
            logger.info(f"\n📊 Групп готовых к постингу БЕЗ назначенного аккаунта: {ready_without_account}")
            logger.info("   (Аккаунт будет назначен автоматически при первом посте)")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при проверке членства: {e}", exc_info=True)


async def run_posting(batch_size: int = 20, dry_run: bool = False):
    """Запускает постинг"""
    logger.info("\n" + "=" * 80)
    logger.info("🚀 ЗАПУСК ПОСТИНГА")
    logger.info("=" * 80)
    logger.info(f"📊 Размер батча: {batch_size}")
    logger.info(f"🔍 Режим: {'DRY-RUN (тестовый)' if dry_run else 'РЕАЛЬНЫЙ ПОСТИНГ'}")
    logger.info("=" * 80)
    
    if dry_run:
        logger.warning("⚠️ DRY-RUN режим: посты НЕ будут отправлены!")
        return
    
    try:
        poster = SmartPoster(niche='ukraine_cars')
        await poster.run_batch(batch_size=batch_size)
        logger.info("✅ Постинг завершен")
    except Exception as e:
        logger.error(f"❌ Ошибка во время постинга: {e}", exc_info=True)
        raise


async def show_final_stats():
    """Показывает финальную статистику"""
    logger.info("\n" + "=" * 80)
    logger.info("📊 ФИНАЛЬНАЯ СТАТИСТИКА")
    logger.info("=" * 80)
    
    async with AsyncSessionLocal() as session:
        try:
            # Статистика постов за последние 24 часа
            result = await session.execute(
                text("""
                    SELECT 
                        COUNT(*) as total,
                        COUNT(CASE WHEN success = true THEN 1 END) as successful,
                        COUNT(CASE WHEN success = false THEN 1 END) as failed
                    FROM posts 
                    WHERE sent_at > NOW() - INTERVAL '24 hours'
                """)
            )
            post_stats = result.fetchone()
            
            logger.info(f"📝 Посты за последние 24 часа:")
            logger.info(f"   Всего: {post_stats[0]}")
            logger.info(f"   Успешных: {post_stats[1]}")
            logger.info(f"   Неудачных: {post_stats[2]}")
            
            # Статистика групп
            result = await session.execute(
                text("""
                    SELECT 
                        COUNT(*) as total,
                        COUNT(CASE WHEN status = 'joined' THEN 1 END) as joined,
                        COUNT(CASE WHEN status = 'active' THEN 1 END) as active,
                        COUNT(CASE WHEN assigned_account_id IS NOT NULL THEN 1 END) as with_account
                    FROM groups 
                    WHERE niche = 'ukraine_cars'
                """)
            )
            group_stats = result.fetchone()
            
            logger.info(f"\n👥 Группы:")
            logger.info(f"   Всего: {group_stats[0]}")
            logger.info(f"   Со статусом 'joined': {group_stats[1]}")
            logger.info(f"   Со статусом 'active': {group_stats[2]}")
            logger.info(f"   С назначенным аккаунтом: {group_stats[3]}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при получении статистики: {e}", exc_info=True)


async def main():
    """Основная функция"""
    parser = argparse.ArgumentParser(
        description='Улучшенный форс-постинг для Lexus',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  # Тестовый запуск (dry-run)
  python3 force_lexus_posting.py --dry-run
  
  # Реальный постинг, 20 постов
  python3 force_lexus_posting.py --batch-size 20
  
  # Реальный постинг, 50 постов
  python3 force_lexus_posting.py --batch-size 50
        """
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=20,
        help='Размер батча постинга (по умолчанию: 20)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Тестовый режим (посты не будут отправлены)'
    )
    parser.add_argument(
        '--skip-checks',
        action='store_true',
        help='Пропустить проверки и сразу запустить постинг'
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 80)
    logger.info("🚀 FORCE LEXUS POSTING - Улучшенный форс-постинг")
    logger.info("=" * 80)
    logger.info(f"📋 Параметры:")
    logger.info(f"   Размер батча: {args.batch_size}")
    logger.info(f"   Dry-run: {args.dry_run}")
    logger.info(f"   Пропустить проверки: {args.skip_checks}")
    logger.info("=" * 80)
    
    if not args.skip_checks:
        # Шаг 1: Проверка и исправление аккаунтов
        accounts_ok = await check_and_fix_accounts()
        if not accounts_ok:
            logger.error("❌ Проблемы с аккаунтами. Прерываем выполнение.")
            return
        
        # Шаг 2: Проверка и активация групп
        groups_ok = await check_and_activate_groups()
        if not groups_ok:
            logger.error("❌ Проблемы с группами. Прерываем выполнение.")
            return
        
        # Шаг 3: Проверка членства
        await check_membership_stats()
    
    # Шаг 4: Запуск постинга
    try:
        await run_posting(batch_size=args.batch_size, dry_run=args.dry_run)
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при постинге: {e}", exc_info=True)
        return
    
    # Шаг 5: Финальная статистика
    await show_final_stats()
    
    logger.info("\n" + "=" * 80)
    logger.info("✅ FORCE POSTING COMPLETED")
    logger.info("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
