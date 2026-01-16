#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Добавление найденных групп по Бали в targets.txt и group_niches.json
Автоматически определяет нишу на основе названия группы
"""

import json
import logging
from pathlib import Path
from datetime import datetime

def setup_logging():
    """Настройка логирования"""
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler()
        ]
    )
    
    return logging.getLogger(__name__)

def detect_niche_from_title(title, username):
    """Определение ниши на основе названия группы"""
    title_lower = title.lower()
    username_lower = username.lower()
    combined = f"{title_lower} {username_lower}"
    
    # Недвижимость
    if any(word in combined for word in ['property', 'real estate', 'rent', 'rental', 'villa', 'apartment', 
                                         'недвижимость', 'аренда', 'вилла', 'квартира', 'риелтор', 'агентство']):
        return 'rental_property'
    
    # Фотограф
    if any(word in combined for word in ['photographer', 'photo', 'фотограф', 'фото', 'съемка', 'фотосессия']):
        return 'photographer'
    
    # Видеограф
    if any(word in combined for word in ['videographer', 'video', 'видеограф', 'видео', 'монтаж']):
        return 'videographer'
    
    # Маникюр
    if any(word in combined for word in ['manicure', 'nail', 'маникюр', 'ногти']):
        return 'manicure'
    
    # Волосы
    if any(word in combined for word in ['hair', 'salon', 'волосы', 'прическа', 'парикмахер']):
        return 'hair'
    
    # Брови
    if any(word in combined for word in ['eyebrow', 'брови', 'бров']):
        return 'eyebrows'
    
    # Ресницы
    if any(word in combined for word in ['eyelash', 'ресницы', 'ресниц']):
        return 'eyelashes'
    
    # Макияж
    if any(word in combined for word in ['makeup', 'макияж', 'визажист']):
        return 'makeup'
    
    # Косметология
    if any(word in combined for word in ['cosmetology', 'beauty', 'косметология', 'красота']):
        return 'cosmetology'
    
    # Аренда авто
    if any(word in combined for word in ['car rental', 'car rent', 'авто', 'машина', 'аренда авто']):
        return 'car_rental'
    
    # Аренда байков
    if any(word in combined for word in ['bike rental', 'scooter', 'motorbike', 'байк', 'скутер', 'мотоцикл']):
        return 'bike_rental'
    
    # Транспорт
    if any(word in combined for word in ['transport', 'taxi', 'transfer', 'транспорт', 'такси', 'трансфер']):
        return 'transport'
    
    # Туризм
    if any(word in combined for word in ['tour', 'guide', 'excursion', 'тур', 'гид', 'экскурсия']):
        return 'tourism'
    
    # Обмен валют
    if any(word in combined for word in ['currency', 'exchange', 'валюта', 'обмен']):
        return 'currency'
    
    # Кальяны
    if any(word in combined for word in ['hookah', 'кальян']):
        return 'hookah'
    
    # Playstation
    if any(word in combined for word in ['playstation', 'ps4', 'ps5', 'игра', 'консоль']):
        return 'playstation'
    
    # Медиа-студия
    if any(word in combined for word in ['media', 'studio', 'студия', 'медиа']):
        return 'media_studio'
    
    # Продажа недвижимости
    if any(word in combined for word in ['sale', 'sell', 'продажа', 'продать']):
        if any(word in combined for word in ['property', 'real estate', 'недвижимость']):
            return 'sale_property'
    
    # Дизайнер
    if any(word in combined for word in ['design', 'designer', 'дизайн', 'дизайнер']):
        return 'designer'
    
    # Общие чаты
    if any(word in combined for word in ['chat', 'group', 'community', 'чат', 'группа', 'сообщество']):
        return 'general'
    
    # По умолчанию - общая ниша
    return 'general'

def add_groups_to_targets():
    """Добавление найденных групп в targets.txt и group_niches.json"""
    logger = setup_logging()
    
    logger.info("=" * 80)
    logger.info("📝 ДОБАВЛЕНИЕ ГРУПП ПО БАЛИ В РАССЫЛКУ")
    logger.info("=" * 80)
    
    found_file = Path('logs/found_bali_groups.json')
    targets_file = Path('targets.txt')
    niches_file = Path('group_niches.json')
    
    if not found_file.exists():
        logger.error(f"❌ Файл {found_file} не найден!")
        return
    
    # Загружаем найденные группы
    try:
        with found_file.open('r', encoding='utf-8') as f:
            found_groups = json.load(f)
    except Exception as e:
        logger.error(f"❌ Ошибка при загрузке {found_file}: {e}")
        return
    
    if not found_groups:
        logger.info("ℹ️ Нет найденных групп для добавления")
        return
    
    # Загружаем существующие targets
    existing_targets = set()
    if targets_file.exists():
        try:
            with targets_file.open('r', encoding='utf-8') as f:
                existing_targets = {line.strip() for line in f if line.strip() and not line.strip().startswith('#')}
        except Exception as e:
            logger.warning(f"⚠️ Ошибка при загрузке {targets_file}: {e}")
    
    # Загружаем существующие ниши
    existing_niches = {}
    if niches_file.exists():
        try:
            with niches_file.open('r', encoding='utf-8') as f:
                existing_niches = json.load(f)
        except Exception as e:
            logger.warning(f"⚠️ Ошибка при загрузке {niches_file}: {e}")
    
    # Создаем backup
    if targets_file.exists():
        backup_file = Path(f'targets.txt.backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}')
        try:
            import shutil
            shutil.copy2(targets_file, backup_file)
            logger.info(f"💾 Создан backup: {backup_file}")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось создать backup: {e}")
    
    if niches_file.exists():
        backup_file = Path(f'group_niches.json.backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}')
        try:
            import shutil
            shutil.copy2(niches_file, backup_file)
            logger.info(f"💾 Создан backup: {backup_file}")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось создать backup: {e}")
    
    # Добавляем новые группы
    added_count = 0
    updated_niches = {}
    
    for group in found_groups:
        username = group.get('username', '')
        if not username or username in existing_targets:
            continue
        
        title = group.get('title', '')
        niche = detect_niche_from_title(title, username)
        
        # Добавляем в targets.txt
        try:
            with targets_file.open('a', encoding='utf-8') as f:
                f.write(f"{username}\n")
            existing_targets.add(username)
            added_count += 1
            logger.info(f"✅ Добавлена группа: {username} (ниша: {niche})")
        except Exception as e:
            logger.error(f"❌ Ошибка при добавлении {username} в targets.txt: {e}")
            continue
        
        # Добавляем нишу
        updated_niches[username] = niche
    
    # Обновляем group_niches.json
    existing_niches.update(updated_niches)
    try:
        with niches_file.open('w', encoding='utf-8') as f:
            json.dump(existing_niches, f, ensure_ascii=False, indent=2)
        logger.info(f"✅ Обновлен {niches_file}")
    except Exception as e:
        logger.error(f"❌ Ошибка при обновлении {niches_file}: {e}")
    
    logger.info("")
    logger.info("=" * 80)
    logger.info(f"✅ Добавлено {added_count} новых групп")
    logger.info("=" * 80)

if __name__ == "__main__":
    add_groups_to_targets()

