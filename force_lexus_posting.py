#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Форс-постинг для Lexus - запуск постинга немедленно без ожидания расписания
"""

import asyncio
import random
import json
import logging
import sys
import argparse
import pytz
from pathlib import Path
from datetime import datetime

sys.path.insert(0, '.')

from promotion_system import PromotionSystem

def setup_logging():
    """Настройка логирования"""
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    
    log_file = log_dir / 'force_lexus_posting.log'
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    return logging.getLogger(__name__)

async def force_lexus_posting(do_post: bool = False, max_posts: int = None):
    """Форс-постинг для Lexus - запуск немедленно"""
    
    logger = setup_logging()
    
    logger.info("=" * 80)
    logger.info("🚀 FORCE LEXUS POSTING - Принудительный запуск постинга")
    logger.info("=" * 80)
    
    system = PromotionSystem()
    # Инициализируем систему вручную
    system.load_accounts()
    logger.info(f"📋 Loaded {len(system.accounts)} accounts from config")
    
    # Загружаем конфиг Lexus ДО инициализации клиентов, чтобы отфильтровать аккаунты
    system.load_lexus_accounts_config()
    
    # Фильтруем аккаунты: оставляем только те, что в whitelist Lexus
    if hasattr(system, 'lexus_allowed_accounts') and system.lexus_allowed_accounts:
        original_count = len(system.accounts)
        original_names = [acc.get('session_name') for acc in system.accounts]
        system.accounts = [
            acc for acc in system.accounts
            if acc.get('session_name') in system.lexus_allowed_accounts
        ]
        filtered_names = [acc.get('session_name') for acc in system.accounts]
        logger.info(f"✅ Filtered accounts for Lexus: {len(system.accounts)}/{original_count} accounts")
        logger.info(f"   Whitelist: {sorted(system.lexus_allowed_accounts)}")
        logger.info(f"   Before: {sorted(original_names)}")
        logger.info(f"   After: {sorted(filtered_names)}")
    else:
        logger.warning(f"⚠️ No Lexus whitelist found, using all {len(system.accounts)} accounts")
    
    system.load_targets()
    system.load_messages()
    system.load_niche_messages()
    system.load_group_niches()
    system.load_group_accounts()
    system.load_group_assignments()  # Загружаем строгие привязки с warm-up
    system.load_kammora_messages()
    system.load_lexus_messages()
    system.load_ukraine_cars_accounts_config()  # Загружаем для обратной совместимости
    await system.initialize_clients()
    
    # Постинг только для групп с нишей ukraine_cars
    dry_run = not do_post
    
    logger.info(f"🚀 Starting FORCE Lexus posting, dry_run={dry_run}")
    logger.info(f"Account usage stats: {dict(system.account_usage)}")
    
    # Фильтруем группы с нишей ukraine_cars
    ukraine_cars_groups = [
        target for target in system.targets 
        if system.group_niches.get(target) == 'ukraine_cars'
    ]
    
    if not ukraine_cars_groups:
        logger.warning("⚠️ No groups with niche 'ukraine_cars' found")
        return
    
    logger.info(f"📋 Found {len(ukraine_cars_groups)} groups with niche 'ukraine_cars'")
    
    # Фильтруем группы с учетом строгой эксклюзивности и warm-up периода
    available_groups = []
    now_utc = datetime.utcnow()
    
    for group in ukraine_cars_groups:
        # Проверяем, закреплена ли группа за аккаунтом
        assigned_account = system.get_assigned_account(group)
        
        if assigned_account:
            # Группа закреплена - проверяем доступность
            # 1. Проверка warm-up периода
            if not system.can_post_after_warmup(group, now=now_utc):
                warm_up_until_str = system.group_assignments[group].get('warm_up_until', 'N/A')
                logger.debug(f"  {group}: warm-up until {warm_up_until_str} - skip")
                continue
            
            # 2. Проверка лимита постов
            posts_today = system.get_group_daily_posts_count(group, now=now_utc)
            if posts_today >= 2:
                logger.debug(f"  {group}: {posts_today}/2 posts today - skip (limit reached)")
                continue
            
            # 3. Проверка доступности закрепленного аккаунта
            if assigned_account not in system.clients:
                logger.debug(f"  {group}: assigned account {assigned_account} not available - skip")
                continue
            
            # 4. Проверка дневного лимита закрепленного аккаунта
            if system.daily_posts.get(assigned_account, 0) >= system.max_daily_posts:
                logger.debug(
                    f"  {group}: assigned account {assigned_account} "
                    f"reached daily limit - skip"
                )
                continue
            
            available_groups.append(group)
            logger.debug(
                f"  {group}: assigned to {assigned_account}, "
                f"posts {posts_today}/2 - available"
            )
        else:
            # Группа не закреплена - будет назначена при первом посте
            available_groups.append(group)
            logger.debug(f"  {group}: not assigned yet - will assign on first post")
    
    if not available_groups:
        logger.warning(f"⚠️ No groups available for posting (all groups reached daily limit of 2 posts or warm-up)")
        return
    
    logger.info(f"✅ Selected {len(available_groups)} groups for posting (from {len(ukraine_cars_groups)} total)")
    
    # Рандомизируем порядок групп для ротации
    random.shuffle(available_groups)
    
    # Временно используем только доступные группы
    original_targets = system.targets.copy()
    system.targets = available_groups
    
    # Определяем максимальное количество постов
    if max_posts is None:
        # По умолчанию - все доступные группы, но не больше 20 (дневной лимит аккаунта)
        max_posts = min(len(available_groups), 20)
    
    logger.info(f"📊 Max posts for this force run: {max_posts} (from {len(available_groups)} available groups)")
    
    # Постим
    await system.post_to_targets(
        dry_run=dry_run, 
        interval_seconds=60, 
        max_posts=max_posts, 
        niche='ukraine_cars'  # Принудительно используем нишу ukraine_cars
    )
    
    # Восстанавливаем оригинальный список
    system.targets = original_targets
    
    logger.info("=" * 80)
    logger.info("✅ FORCE POSTING COMPLETED")
    logger.info("=" * 80)

async def main():
    parser = argparse.ArgumentParser(description='Force Lexus posting - немедленный запуск постинга')
    parser.add_argument('--post', action='store_true', help='Отправлять сообщения (иначе dry-run)')
    parser.add_argument('--max-posts', type=int, help='Максимальное количество постов (по умолчанию: все доступные, но не больше 20)')
    args = parser.parse_args()
    
    await force_lexus_posting(do_post=args.post, max_posts=args.max_posts)

if __name__ == "__main__":
    asyncio.run(main())
