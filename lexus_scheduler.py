#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Планировщик рассылки Lexus по киевскому времени
Работает отдельно от основного планировщика для украинских групп
"""

import asyncio
import random
import json
import logging
import argparse
import sys
import pytz
from pathlib import Path
from datetime import datetime, timedelta, time as dtime

sys.path.insert(0, '.')

from promotion_system import PromotionSystem


def setup_lexus_logging() -> logging.Logger:
    """Единая настройка логирования для Lexus."""
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / 'lexus_scheduler.log'

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)


async def setup_lexus_system(logger: logging.Logger) -> PromotionSystem:
    """Инициализация PromotionSystem и загрузка конфигов Lexus."""
    system = PromotionSystem()
    system.load_accounts()
    logger.info(f"📋 Loaded {len(system.accounts)} accounts from config")

    # Загружаем конфиг Lexus ДО инициализации клиентов, чтобы отфильтровать аккаунты
    system.load_lexus_accounts_config()  # Загружаем whitelist для Lexus

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

    return system


def get_lexus_slots():
    """Слоты по киевскому времени для планировщика Lexus."""
    return [
        ('morning', dtime(hour=8, minute=0)),    # 08:00 - утро
        ('noon', dtime(hour=12, minute=0)),      # 12:00 - обед
        ('afternoon', dtime(hour=15, minute=0)), # 15:00 - день
        ('evening', dtime(hour=18, minute=0)),   # 18:00 - вечер
        ('night', dtime(hour=20, minute=0)),     # 20:00 - поздний вечер
    ]


async def run_lexus_slot_once(
    system: PromotionSystem,
    logger: logging.Logger,
    slot_name: str,
    slots: list,
) -> None:
    """Один проход Lexus-постинга (используется и планировщиком, и форс-режимом)."""
    # Постинг только для групп с нишей ukraine_cars
    dry_run = False  # по месту вызова решаем, dry_run или нет через do_post

    logger.info(f"🚀 Starting Lexus posting for slot {slot_name}, dry_run={dry_run}")
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
            # Группа не закреплена — пропускаем (постим только в подтвержденных, как в Bali)
            logger.debug(f"  {group}: not assigned yet - skip")

    if not available_groups:
        logger.warning(
            f"⚠️ No groups available for slot {slot_name} "
            f"(all groups reached daily limit of 2 posts or in warm-up)"
        )
        return

    logger.info(
        f"✅ Selected {len(available_groups)} groups for slot {slot_name} "
        f"(from {len(ukraine_cars_groups)} total)"
    )

    # Рандомизируем порядок групп для ротации
    random.shuffle(available_groups)

    # Временно используем только доступные группы для этого слота
    original_targets = system.targets.copy()
    system.targets = available_groups

    # Постим только в доступные украинские группы
    # Ограничиваем количество постов на слот, чтобы распределить между слотами
    max_posts_per_slot = min(
        len(available_groups),
        len(available_groups) // max(len(slots), 1) + 1,
    )
    logger.info(
        f"📊 Max posts for this slot: {max_posts_per_slot} "
        f"(from {len(available_groups)} available groups)"
    )

    await system.post_to_targets(
        dry_run=False,
        interval_seconds=60,
        max_posts=max_posts_per_slot,
        niche='ukraine_cars',  # Принудительно используем нишу ukraine_cars
    )

    # Восстанавливаем оригинальный список
    system.targets = original_targets
    logger.info(f"✅ Completed slot {slot_name}")


async def run_lexus_scheduler(do_post: bool = False):
    """Планировщик для Lexus по киевскому времени."""
    logger = setup_lexus_logging()
    system = await setup_lexus_system(logger)

    kiev_tz = pytz.timezone('Europe/Kiev')
    slots = get_lexus_slots()

    logger.info("=" * 80)
    logger.info("🚗 LEXUS SCHEDULER - Киевское время")
    logger.info("=" * 80)
    logger.info(f"Расписание: {len(slots)} слотов в день")
    for name, t in slots:
        logger.info(f"  - {t.strftime('%H:%M')} ({name})")
    logger.info("=" * 80)

    posted_slots_today = {name: None for name, _ in slots}

    while True:
        now = datetime.now(kiev_tz)
        today = now.date()

        # Сброс отметок в полночь
        for name in list(posted_slots_today.keys()):
            posted_date = posted_slots_today[name]
            if posted_date is None or posted_date < today:
                posted_slots_today[name] = None
                if posted_date and posted_date < today:
                    logger.info(
                        f"Reset slot {name}: old date {posted_date} -> None "
                        f"(today is {today})"
                    )

        # Сброс счетчиков дневных постов в полночь
        if not hasattr(system, '_last_reset_date') or system._last_reset_date < today:
            for account_name in system.daily_posts.keys():
                system.daily_posts[account_name] = 0
            system._last_reset_date = today
            logger.info(
                f"✅ Reset daily post counters for all accounts (new day: {today})"
            )

        # Найти следующий слот
        next_slot_name = None
        next_slot_dt = None
        for name, t in slots:
            slot_dt = kiev_tz.localize(datetime.combine(today, t))
            if slot_dt <= now:
                # Если время слота прошло, переносим на завтра
                slot_dt = slot_dt + timedelta(days=1)
            if next_slot_dt is None or slot_dt < next_slot_dt:
                next_slot_dt = slot_dt
                next_slot_name = name

        # Подождать до следующего слота
        wait_seconds = max(1, int((next_slot_dt - now).total_seconds()))
        wait_hours = wait_seconds // 3600
        wait_minutes = (wait_seconds % 3600) // 60
        logger.info(
            f"⏰ Next slot: {next_slot_name} at "
            f"{next_slot_dt.strftime('%Y-%m-%d %H:%M:%S')} Kiev time "
            f"(in {wait_hours}h {wait_minutes}m)"
        )
        await asyncio.sleep(wait_seconds)

        # Время слота наступило
        slot_name = next_slot_name
        run_day = datetime.now(kiev_tz).date()
        logger.info(f"⏰ Woke up for slot: {slot_name}, date: {run_day}")

        if posted_slots_today.get(slot_name) == run_day:
            # Уже постили в этом слоте сегодня (на случай перезапуска)
            logger.info(f"Slot {slot_name}: already posted today, skipping")
            continue

        # dry_run управляется флагом do_post
        if not do_post:
            logger.info("Running in DRY-RUN mode (no actual posts will be sent)")

        await run_lexus_slot_once(system, logger, slot_name, slots)
        posted_slots_today[slot_name] = run_day


async def run_lexus_force(do_post: bool = False):
    """Форс‑режим: единоразовый запуск Lexus‑постинга без ожидания слота.

    Учитывает все те же лимиты/warm-up/assignments, что и обычный планировщик.
    """
    logger = setup_lexus_logging()
    logger.info("=" * 80)
    logger.info("🚗 LEXUS FORCE RUN - ОДНОРАЗОВЫЙ ЗАПУСК БЕЗ ОЖИДАНИЯ СЛОТА")
    logger.info("=" * 80)

    system = await setup_lexus_system(logger)
    slots = get_lexus_slots()

    # dry_run управляется флагом do_post
    if not do_post:
        logger.info("Running in DRY-RUN mode (no actual posts will be sent)")

    # Используем специальное имя слота, чтобы в логах было видно, что это форс
    await run_lexus_slot_once(system, logger, slot_name="force", slots=slots)

async def main():
    parser = argparse.ArgumentParser(description='Lexus scheduler - Киевское время')
    parser.add_argument(
        '--post',
        action='store_true',
        help='Отправлять сообщения (иначе dry-run)',
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Единоразовый запуск без ожидания ближайшего слота (форс-пост)',
    )
    args = parser.parse_args()
    
    if args.force:
        await run_lexus_force(do_post=args.post)
    else:
        await run_lexus_scheduler(do_post=args.post)

if __name__ == "__main__":
    asyncio.run(main())

