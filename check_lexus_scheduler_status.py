#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для проверки статуса Lexus планировщика
Проверяет логи и статистику постов
"""

import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
import pytz

def setup_logging():
    """Настройка логирования"""
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / 'check_lexus_scheduler_status.log'
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

def check_lexus_scheduler_status():
    """Проверяет статус Lexus планировщика"""
    logger = setup_logging()
    
    logger.info("=" * 80)
    logger.info("🚗 ПРОВЕРКА СТАТУСА LEXUS SCHEDULER")
    logger.info("=" * 80)
    
    # Проверяем логи
    log_file = Path('logs/lexus_scheduler.log')
    if not log_file.exists():
        logger.warning("⚠️ Лог файл не найден: logs/lexus_scheduler.log")
        logger.info("   Проверьте, что контейнер lexus-scheduler запущен")
        return
    
    # Читаем последние строки лога
    with open(log_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    if not lines:
        logger.warning("⚠️ Лог файл пуст")
        return
    
    logger.info(f"📋 Всего строк в логе: {len(lines)}")
    
    # Ищем записи о слотах
    kiev_tz = pytz.timezone('Europe/Kiev')
    today = datetime.now(kiev_tz).date()
    yesterday = today - timedelta(days=1)
    
    slots = ['morning', 'noon', 'afternoon', 'evening', 'night']
    slot_times = {
        'morning': '08:00',
        'noon': '12:00',
        'afternoon': '15:00',
        'evening': '18:00',
        'night': '20:00'
    }
    
    # Анализируем последние 500 строк
    recent_lines = lines[-500:] if len(lines) > 500 else lines
    
    logger.info("\n📊 АНАЛИЗ ПОСЛЕДНИХ ЗАПИСЕЙ:")
    logger.info("-" * 80)
    
    slot_executions = {slot: [] for slot in slots}
    posting_attempts = []
    errors = []
    
    for line in recent_lines:
        if 'Woke up for slot:' in line or 'Starting Lexus posting for slot' in line:
            for slot in slots:
                if slot in line.lower():
                    slot_executions[slot].append(line.strip())
        elif '📤' in line or 'Posting to' in line or 'Отправляю' in line:
            posting_attempts.append(line.strip())
        elif 'ERROR' in line or '❌' in line:
            errors.append(line.strip())
    
    # Статистика по слотам
    logger.info("\n⏰ ВЫПОЛНЕНИЕ СЛОТОВ:")
    for slot in slots:
        count = len(slot_executions[slot])
        if count > 0:
            logger.info(f"  ✅ {slot} ({slot_times[slot]}): {count} выполнений")
            if slot_executions[slot]:
                logger.info(f"     Последнее: {slot_executions[slot][-1][:80]}...")
        else:
            logger.warning(f"  ❌ {slot} ({slot_times[slot]}): нет выполнений")
    
    # Статистика по постам
    logger.info(f"\n📤 ПОПЫТКИ ПОСТИНГА: {len(posting_attempts)}")
    if posting_attempts:
        logger.info("   Последние 5:")
        for attempt in posting_attempts[-5:]:
            logger.info(f"     {attempt[:100]}...")
    else:
        logger.warning("   ⚠️ Нет записей о попытках постинга")
    
    # Ошибки
    if errors:
        logger.warning(f"\n❌ ОШИБКИ: {len(errors)}")
        logger.info("   Последние 5:")
        for error in errors[-5:]:
            logger.info(f"     {error[:100]}...")
    
    # Проверяем group_post_history.json
    history_file = Path('logs/group_post_history.json')
    if history_file.exists():
        with open(history_file, 'r', encoding='utf-8') as f:
            history = json.load(f)
        
        # Подсчитываем посты за сегодня
        today_posts = 0
        ukraine_cars_posts = 0
        
        for group, accounts_data in history.items():
            if isinstance(accounts_data, dict):
                for account, timestamps in accounts_data.items():
                    if isinstance(timestamps, list):
                        for ts in timestamps:
                            try:
                                post_time = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                                if post_time.date() == today:
                                    today_posts += 1
                                    # Проверяем, является ли группа ukraine_cars
                                    niches_file = Path('group_niches.json')
                                    if niches_file.exists():
                                        with open(niches_file, 'r', encoding='utf-8') as nf:
                                            niches = json.load(nf)
                                        if niches.get(group) == 'ukraine_cars':
                                            ukraine_cars_posts += 1
                            except:
                                pass
        
        logger.info(f"\n📊 ПОСТЫ ЗА СЕГОДНЯ:")
        logger.info(f"   Всего: {today_posts}")
        logger.info(f"   Ukraine cars: {ukraine_cars_posts}")
    
    # Проверяем количество ukraine_cars групп
    niches_file = Path('group_niches.json')
    if niches_file.exists():
        with open(niches_file, 'r', encoding='utf-8') as f:
            niches = json.load(f)
        
        ukraine_cars_count = sum(1 for niche in niches.values() if niche == 'ukraine_cars')
        logger.info(f"\n🚗 UKRAINE CARS ГРУПП: {ukraine_cars_count}")
    
    logger.info("=" * 80)
    logger.info("✅ ПРОВЕРКА ЗАВЕРШЕНА")
    logger.info("=" * 80)

if __name__ == "__main__":
    check_lexus_scheduler_status()

