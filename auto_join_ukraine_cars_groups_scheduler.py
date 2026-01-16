#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Планировщик для автоматического поиска и вступления в украинские авто-группы
Работает по джакартскому времени, когда Киев спит
"""

import asyncio
import logging
import sys
import pytz
from pathlib import Path
from datetime import datetime, timedelta, time as dtime

sys.path.insert(0, '.')

from auto_join_ukraine_cars_groups import search_and_join_groups

def setup_logging():
    """Настройка логирования"""
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    
    log_file = log_dir / 'auto_join_ukraine_scheduler.log'
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    return logging.getLogger(__name__)

async def run_scheduler():
    """Планировщик для поиска и вступления в группы по джакартскому времени"""
    logger = setup_logging()
    
    jakarta_tz = pytz.timezone('Asia/Jakarta')
    kiev_tz = pytz.timezone('Europe/Kiev')
    
    # Расписание по джакартскому времени, когда Киев спит
    # Когда в Киеве 00:00-06:00, в Джакарте 05:00-11:00
    # Запускаем в 05:00, 07:00, 09:00, 11:00 по джакартскому времени
    slots = [
        ('early_morning', dtime(hour=5, minute=0)),   # 05:00 Jakarta = 00:00 Kiev
        ('morning_1', dtime(hour=7, minute=0)),       # 07:00 Jakarta = 02:00 Kiev
        ('morning_2', dtime(hour=9, minute=0)),       # 09:00 Jakarta = 04:00 Kiev
        ('late_morning', dtime(hour=11, minute=0)),  # 11:00 Jakarta = 06:00 Kiev
    ]
    
    logger.info("=" * 80)
    logger.info("🔍 ПЛАНИРОВЩИК ПОИСКА УКРАИНСКИХ АВТО-ГРУПП")
    logger.info("=" * 80)
    logger.info("⏰ Расписание: по джакартскому времени (когда Киев спит)")
    logger.info(f"📅 Слотов в день: {len(slots)}")
    for name, t in slots:
        jakarta_time = t.strftime('%H:%M')
        # Вычисляем время в Киеве (разница 5 часов)
        kiev_hour = (t.hour - 5) % 24
        kiev_time = f"{kiev_hour:02d}:{t.minute:02d}"
        logger.info(f"  - {jakarta_time} Jakarta ({name}) = {kiev_time} Kiev")
    logger.info("=" * 80)
    
    posted_slots_today = {name: None for name, _ in slots}
    
    while True:
        now_jakarta = datetime.now(jakarta_tz)
        now_kiev = datetime.now(kiev_tz)
        today = now_jakarta.date()
        
        # Сброс отметок в полночь
        for name in list(posted_slots_today.keys()):
            posted_date = posted_slots_today[name]
            if posted_date is None or posted_date < today:
                posted_slots_today[name] = None
        
        # Найти следующий слот
        next_slot_name = None
        next_slot_dt = None
        for name, t in slots:
            slot_dt = jakarta_tz.localize(datetime.combine(today, t))
            if slot_dt <= now_jakarta:
                # Если время слота прошло, переносим на завтра
                slot_dt = slot_dt + timedelta(days=1)
            if next_slot_dt is None or slot_dt < next_slot_dt:
                next_slot_dt = slot_dt
                next_slot_name = name
        
        # Подождать до следующего слота
        wait_seconds = max(1, int((next_slot_dt - now_jakarta).total_seconds()))
        wait_hours = wait_seconds // 3600
        wait_minutes = (wait_seconds % 3600) // 60
        
        logger.info(f"⏰ Следующий запуск: {next_slot_name} в {next_slot_dt.strftime('%Y-%m-%d %H:%M:%S')} Jakarta")
        logger.info(f"   (через {wait_hours}ч {wait_minutes}м)")
        logger.info(f"   В Киеве будет: {now_kiev.strftime('%H:%M')} (сейчас {now_kiev.strftime('%H:%M')})")
        await asyncio.sleep(wait_seconds)
        
        # Время слота наступило
        slot_name = next_slot_name
        run_day = datetime.now(jakarta_tz).date()
        
        if posted_slots_today.get(slot_name) == run_day:
            # Уже запускали в этом слоте сегодня
            logger.info(f"Slot {slot_name}: already ran today, skipping")
            continue
        
        logger.info("=" * 80)
        logger.info(f"⏰ Время слота {slot_name} - начинаю поиск и вступление в группы")
        logger.info(f"   Jakarta time: {now_jakarta.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"   Kiev time: {now_kiev.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 80)
        
        try:
            # Запускаем поиск и вступление
            await search_and_join_groups()
            
            # Добавляем найденные группы в targets.txt и group_niches.json
            logger.info("📝 Добавляю найденные группы в targets.txt...")
            try:
                import subprocess
                result = subprocess.run(
                    ['python3', 'add_ukraine_cars_groups_to_targets.py'],
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                if result.returncode == 0:
                    logger.info("✅ Группы успешно добавлены в targets.txt")
                    if result.stdout:
                        logger.info(f"Вывод: {result.stdout[-500:]}")  # Последние 500 символов
                else:
                    logger.warning(f"⚠️ Скрипт завершился с кодом {result.returncode}")
                    if result.stderr:
                        logger.warning(f"Ошибки: {result.stderr[-500:]}")
            except Exception as e:
                logger.error(f"❌ Ошибка при добавлении групп в targets.txt: {e}")
            
            # Отмечаем слот как выполненный
            posted_slots_today[slot_name] = run_day
            logger.info(f"✅ Слот {slot_name} выполнен")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при выполнении слота {slot_name}: {e}")
        
        logger.info("")

if __name__ == "__main__":
    asyncio.run(run_scheduler())


