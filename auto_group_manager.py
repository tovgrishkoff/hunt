#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Автоматический менеджер групп: поиск → вступление → отлежка → добавление в рассылку

Процесс:
1. Поиск новых групп (search_rental_groups.py)
2. Вступление в найденные группы (join_found_groups.py)
3. Отлежка после вступления (5 дней по умолчанию)
4. Добавление групп в рассылку после отлежки (targets.txt)
"""

import asyncio
import json
import logging
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Настройки
COOLDOWN_DAYS = 5  # Количество дней отлежки после вступления
TARGETS_FILE = Path('targets.txt')
FOUND_GROUPS_FILE = Path('logs/found_rental_groups.json')
NEW_GROUPS_FILE = Path('logs/new_groups_to_join.json')
COOLDOWN_FILE = Path('logs/groups_cooldown.json')
JOIN_PROGRESS_FILE = Path('logs/join_found_groups_progress.json')

def setup_logging():
    """Настройка логирования"""
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    
    log_file = log_dir / 'auto_group_manager.log'
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    return logging.getLogger(__name__)

def load_cooldown_data():
    """Загрузка данных об отлежке групп"""
    if COOLDOWN_FILE.exists():
        try:
            with COOLDOWN_FILE.open('r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logging.warning(f"⚠️ Ошибка загрузки cooldown данных: {e}")
    return {}

def save_cooldown_data(cooldown_data):
    """Сохранение данных об отлежке"""
    COOLDOWN_FILE.parent.mkdir(exist_ok=True)
    try:
        with COOLDOWN_FILE.open('w', encoding='utf-8') as f:
            json.dump(cooldown_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"❌ Ошибка сохранения cooldown данных: {e}")

def filter_new_groups():
    """
    Фильтрует найденные группы и создает список новых для вступления.
    Исключает группы, которые уже есть в targets.txt
    """
    logger = logging.getLogger(__name__)
    
    if not FOUND_GROUPS_FILE.exists():
        logger.warning(f"⚠️ Файл {FOUND_GROUPS_FILE} не найден. Пропускаем фильтрацию.")
        return []
    
    # Загружаем найденные группы
    try:
        with FOUND_GROUPS_FILE.open('r', encoding='utf-8') as f:
            found_groups = json.load(f)
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки найденных групп: {e}")
        return []
    
    # Загружаем текущие группы из targets.txt
    existing_groups = set()
    if TARGETS_FILE.exists():
        try:
            with TARGETS_FILE.open('r', encoding='utf-8') as f:
                existing_groups = {line.strip() for line in f if line.strip() and not line.strip().startswith('#')}
        except Exception as e:
            logger.warning(f"⚠️ Ошибка чтения targets.txt: {e}")
    
    # Загружаем данные cooldown для фильтрации
    cooldown_data = load_cooldown_data()
    
    # Фильтруем новые группы
    new_groups = []
    for group in found_groups:
        username = group.get('username', '')
        if username and username not in existing_groups:
            # Проверяем, не в отлежке ли уже
            if username not in cooldown_data:
                # Формируем link из username
                username_clean = username.lstrip('@')
                new_groups.append({
                    'username': username,
                    'link': f'https://t.me/{username_clean}',
                    'title': group.get('title', ''),
                    'members_count': group.get('members_count', 0)
                })
    
    logger.info(f"📊 Найдено {len(found_groups)} групп, из них новых: {len(new_groups)}")
    
    # Сохраняем новые группы для вступления
    if new_groups:
        try:
            NEW_GROUPS_FILE.parent.mkdir(exist_ok=True)
            with NEW_GROUPS_FILE.open('w', encoding='utf-8') as f:
                json.dump(new_groups, f, ensure_ascii=False, indent=2)
            logger.info(f"✅ Сохранено {len(new_groups)} новых групп в {NEW_GROUPS_FILE}")
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения новых групп: {e}")
    
    return new_groups

def update_cooldown_from_join_progress():
    """
    Обновляет cooldown данные на основе прогресса вступления.
    Если группа успешно вступила, добавляет её в отлежку с текущей датой.
    """
    logger = logging.getLogger(__name__)
    
    if not JOIN_PROGRESS_FILE.exists():
        logger.info("📊 Файл прогресса вступления не найден, пропускаем обновление cooldown")
        return
    
    try:
        with JOIN_PROGRESS_FILE.open('r', encoding='utf-8') as f:
            join_progress = json.load(f)
    except Exception as e:
        logger.warning(f"⚠️ Ошибка загрузки прогресса вступления: {e}")
        return
    
    cooldown_data = load_cooldown_data()
    updated = False
    current_date = datetime.now().isoformat()
    
    # Проходим по всем аккаунтам и их вступившим группам
    for account_name, account_data in join_progress.items():
        joined_groups = account_data.get('joined', [])
        
        for group_link in joined_groups:
            # Извлекаем username из link
            username = None
            # Формат может быть: https://t.me/username, @username, или просто username
            link_clean = group_link.strip()
            
            if link_clean.startswith('http://t.me/') or link_clean.startswith('https://t.me/'):
                # Извлекаем username из URL
                username_part = link_clean.split('/')[-1].strip()
                if username_part:
                    username = f'@{username_part}' if not username_part.startswith('@') else username_part
            elif link_clean.startswith('@'):
                username = link_clean
            elif link_clean:
                username = f'@{link_clean}' if not link_clean.startswith('@') else link_clean
            
            if username and username not in cooldown_data:
                cooldown_data[username] = {
                    'joined_date': current_date,
                    'cooldown_until': (datetime.now() + timedelta(days=COOLDOWN_DAYS)).isoformat(),
                    'status': 'cooldown'
                }
                updated = True
                logger.info(f"✅ Добавлена группа {username} в отлежку до {cooldown_data[username]['cooldown_until']}")
    
    if updated:
        save_cooldown_data(cooldown_data)
        logger.info(f"💾 Обновлены данные отлежки: {len(cooldown_data)} групп")

def add_groups_after_cooldown():
    """
    Добавляет группы в targets.txt после окончания отлежки
    """
    logger = logging.getLogger(__name__)
    
    cooldown_data = load_cooldown_data()
    if not cooldown_data:
        logger.info("📊 Нет групп в отлежке")
        return
    
    current_time = datetime.now()
    groups_to_add = []
    
    # Проверяем, какие группы прошли отлежку
    for username, group_data in list(cooldown_data.items()):
        if group_data.get('status') == 'cooldown':
            cooldown_until_str = group_data.get('cooldown_until')
            if cooldown_until_str:
                try:
                    cooldown_until = datetime.fromisoformat(cooldown_until_str)
                    if current_time >= cooldown_until:
                        groups_to_add.append(username)
                        group_data['status'] = 'ready'
                        group_data['added_to_targets'] = current_time.isoformat()
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка парсинга даты для {username}: {e}")
    
    if not groups_to_add:
        logger.info("📊 Нет групп, готовых для добавления в рассылку")
        return
    
    logger.info(f"✅ Найдено {len(groups_to_add)} групп, готовых для добавления в рассылку")
    
    # Загружаем текущие группы из targets.txt
    existing_groups = set()
    if TARGETS_FILE.exists():
        try:
            with TARGETS_FILE.open('r', encoding='utf-8') as f:
                existing_groups = {line.strip() for line in f if line.strip() and not line.strip().startswith('#')}
        except Exception as e:
            logger.warning(f"⚠️ Ошибка чтения targets.txt: {e}")
    
    # Фильтруем, чтобы не добавлять дубликаты
    groups_to_add_filtered = [g for g in groups_to_add if g not in existing_groups]
    
    if not groups_to_add_filtered:
        logger.info("📊 Все группы уже есть в targets.txt")
        save_cooldown_data(cooldown_data)  # Сохраняем обновленный статус
        return
    
    # Добавляем группы в targets.txt
    try:
        # Создаем backup
        if TARGETS_FILE.exists():
            backup_file = Path(f'{TARGETS_FILE}.backup.{datetime.now().strftime("%Y%m%d_%H%M%S")}')
            import shutil
            shutil.copy(TARGETS_FILE, backup_file)
            logger.info(f"💾 Создан backup: {backup_file}")
        
        # Добавляем новые группы
        with TARGETS_FILE.open('a', encoding='utf-8') as f:
            f.write('\n')
            f.write('# Группы, добавленные автоматически после отлежки\n')
            for group in sorted(groups_to_add_filtered):
                f.write(f'{group}\n')
        
        logger.info(f"✅ Добавлено {len(groups_to_add_filtered)} групп в {TARGETS_FILE}")
        logger.info(f"   Примеры: {', '.join(groups_to_add_filtered[:5])}")
        
        # Сохраняем обновленные данные cooldown
        save_cooldown_data(cooldown_data)
        
    except Exception as e:
        logger.error(f"❌ Ошибка добавления групп в targets.txt: {e}")

async def run_search_groups():
    """Запускает поиск групп"""
    logger = logging.getLogger(__name__)
    logger.info("🔍 Запуск поиска новых групп...")
    
    try:
        result = await asyncio.create_subprocess_exec(
            sys.executable, 'search_rental_groups.py',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=Path.cwd()
        )
        stdout, stderr = await result.communicate()
        
        if result.returncode == 0:
            logger.info("✅ Поиск групп завершен успешно")
            if stdout:
                logger.debug(f"Вывод: {stdout.decode('utf-8', errors='ignore')[:500]}")
        else:
            logger.error(f"❌ Ошибка поиска групп (код {result.returncode})")
            if stderr:
                logger.error(f"Ошибка: {stderr.decode('utf-8', errors='ignore')[:500]}")
            return False
    except Exception as e:
        logger.error(f"❌ Исключение при запуске поиска групп: {e}")
        return False
    
    return True

async def run_join_groups():
    """Запускает вступление в группы"""
    logger = logging.getLogger(__name__)
    logger.info("🚀 Запуск вступления в найденные группы...")
    
    try:
        result = await asyncio.create_subprocess_exec(
            sys.executable, 'join_found_groups.py',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=Path.cwd()
        )
        stdout, stderr = await result.communicate()
        
        if result.returncode == 0:
            logger.info("✅ Вступление в группы завершено")
            if stdout:
                logger.debug(f"Вывод: {stdout.decode('utf-8', errors='ignore')[:500]}")
        else:
            logger.warning(f"⚠️ Вступление в группы завершено с кодом {result.returncode}")
            if stderr:
                logger.warning(f"Предупреждение: {stderr.decode('utf-8', errors='ignore')[:500]}")
    except Exception as e:
        logger.error(f"❌ Исключение при запуске вступления в группы: {e}")

async def main():
    """Основная функция"""
    logger = setup_logging()
    
    logger.info("\n" + "="*80)
    logger.info("🤖 АВТОМАТИЧЕСКИЙ МЕНЕДЖЕР ГРУПП")
    logger.info("="*80)
    logger.info(f"📅 Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"⏱️  Отлежка: {COOLDOWN_DAYS} дней")
    logger.info("="*80)
    
    # Шаг 1: Поиск новых групп
    logger.info("\n📋 ШАГ 1: Поиск новых групп")
    search_success = await run_search_groups()
    
    if not search_success:
        logger.warning("⚠️ Поиск групп завершился с ошибкой, продолжаем...")
    
    # Шаг 2: Фильтрация новых групп
    logger.info("\n📋 ШАГ 2: Фильтрация новых групп")
    new_groups = filter_new_groups()
    
    if not new_groups:
        logger.info("✅ Новых групп для вступления не найдено")
    else:
        # Шаг 3: Вступление в группы
        logger.info(f"\n📋 ШАГ 3: Вступление в {len(new_groups)} новых групп")
        await run_join_groups()
        
        # Шаг 4: Обновление cooldown данных
        logger.info("\n📋 ШАГ 4: Обновление данных об отлежке")
        update_cooldown_from_join_progress()
    
    # Шаг 5: Добавление групп после отлежки
    logger.info("\n📋 ШАГ 5: Проверка групп, готовых для добавления в рассылку")
    add_groups_after_cooldown()
    
    logger.info("\n" + "="*80)
    logger.info("✅ АВТОМАТИЧЕСКИЙ МЕНЕДЖЕР ЗАВЕРШИЛ РАБОТУ")
    logger.info("="*80)

if __name__ == "__main__":
    asyncio.run(main())

