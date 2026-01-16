#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для рассылки объявлений о сдаче апартаментов (Kammora) в группы аренды/недвижимости
"""

import asyncio
import json
import logging
import random
import sys
from pathlib import Path
from datetime import datetime

from telethon import TelegramClient
from telethon.errors import FloodWaitError, ChatWriteForbiddenError, UserBannedInChannelError, RPCError

sys.path.insert(0, '.')
from promotion_system import PromotionSystem


async def send_kammora_to_groups(dry_run=False):
    """Рассылка Kammora в группы аренды/недвижимости"""
    
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('logs/kammora_today.log', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 80)
    logger.info("🏖️ РАССЫЛКА KAMMORA (Сдача апартаментов в Чангу)")
    logger.info("=" * 80)
    
    # Инициализируем систему
    system = PromotionSystem()
    system.load_accounts()
    await system.initialize_clients()
    
    if not system.clients:
        logger.error("❌ Нет доступных клиентов!")
        return
    
    logger.info(f"✅ Загружено {len(system.clients)} аккаунтов")
    
    # Загружаем сообщения Kammora
    system.load_kammora_messages()
    if not system.kammora_messages:
        logger.error("❌ Сообщения Kammora не загружены!")
        return
    
    logger.info(f"✅ Загружены сообщения Kammora")
    
    # Загружаем группы с нишей kammora
    system.load_group_niches()
    
    # Фильтруем группы с нишей kammora
    kammora_groups = [group for group, niche in system.group_niches.items() if niche == 'kammora']
    
    logger.info(f"✅ Найдено {len(kammora_groups)} групп для рассылки Kammora")
    
    # Статистика
    stats = {
        'total_groups': len(kammora_groups),
        'attempted': 0,
        'successful': 0,
        'failed': 0,
        'by_account': {}
    }
    
    # Перемешиваем группы
    random.shuffle(kammora_groups)
    
    # Список всех доступных аккаунтов для ротации
    all_account_names = list(system.clients.keys())
    account_index = 0  # Индекс для round-robin ротации
    
    logger.info(f"\n{'🔍 DRY-RUN: только просмотр' if dry_run else '📨 РЕАЛЬНАЯ РАССЫЛКА'}")
    logger.info(f"⏰ Начало: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"👥 Доступно аккаунтов: {len(all_account_names)}")
    logger.info("=" * 80)
    
    # Рассылаем в группы
    for group_idx, group in enumerate(kammora_groups, 1):
        stats['attempted'] += 1
        
        # Выбираем случайное сообщение (русское или английское)
        lang = random.choice(['ru', 'en'])
        if lang not in system.kammora_messages or not system.kammora_messages[lang]:
            logger.warning(f"   ⚠️ Нет сообщений для языка {lang}, пропускаем")
            continue
        
        message_data = random.choice(system.kammora_messages[lang])
        photo_path = message_data.get('photo', '')
        caption = message_data.get('text', '')
        
        # Проверяем наличие фото
        photo_file = Path(photo_path)
        if not photo_file.exists():
            logger.warning(f"   ⚠️ Фото не найдено: {photo_path}, пропускаем")
            continue
        
        # Пробуем отправить через разные аккаунты (максимум попыток = количество аккаунтов)
        success = False
        tried_accounts = []
        
        for attempt in range(len(all_account_names)):
            # Выбираем аккаунт (round-robin ротация)
            account_name = all_account_names[account_index % len(all_account_names)]
            account_index += 1
            client = system.clients[account_name]
            
            if account_name not in stats['by_account']:
                stats['by_account'][account_name] = {'attempted': 0, 'successful': 0, 'failed': 0}
            
            if attempt == 0:
                stats['by_account'][account_name]['attempted'] += 1
            
            tried_accounts.append(account_name)
            
            logger.info(f"\n[{group_idx}/{len(kammora_groups)}] 📬 Группа: {group}")
            logger.info(f"   👤 Аккаунт: {account_name} (попытка {attempt + 1}/{len(all_account_names)})")
            logger.info(f"   🌐 Язык: {lang}")
            logger.info(f"   📷 Фото: {photo_file.name}")
            logger.info(f"   💬 Текст: {caption[:80]}...")
            
            if dry_run:
                logger.info(f"   [DRY-RUN] Будет отправлено фото с текстом")
                stats['successful'] += 1
                stats['by_account'][account_name]['successful'] += 1
                success = True
                await asyncio.sleep(0.5)
                break
            
            # Реальная отправка
            entity = None
            try:
                # Разрешаем entity с обработкой FloodWait
                try:
                    entity = await system.resolve_target(client, group)
                except FloodWaitError as e:
                    logger.warning(f"   ⏳ FloodWait при разрешении ({account_name}): нужно подождать {e.seconds} секунд")
                    # Пробуем следующий аккаунт
                    await asyncio.sleep(2)
                    continue
                
                if entity is None:
                    logger.warning(f"   ⚠️ Не удалось разрешить {group} через {account_name}")
                    # Пробуем следующий аккаунт
                    await asyncio.sleep(1)
                    continue
                
                # Используем оригинальный текст (GPT переформулировка опциональна, но не обязательна)
                final_caption = caption
                
                # Отправляем фото с текстом
                await client.send_file(
                    entity,
                    str(photo_file),
                    caption=final_caption
                )
                
                logger.info(f"   ✅ Успешно отправлено через {account_name}!")
                stats['successful'] += 1
                stats['by_account'][account_name]['successful'] += 1
                
                # Обновляем историю
                system.mark_group_posted(group, account_name)
                success = True
                break  # Успешно отправлено, выходим из цикла попыток
                
            except FloodWaitError as e:
                wait_time = min(e.seconds, 300)  # Максимум 5 минут
                logger.warning(f"   ⏳ FloodWait при отправке ({account_name}): нужно подождать {e.seconds} секунд")
                # Пробуем следующий аккаунт
                await asyncio.sleep(2)
                continue
                
            except (ChatWriteForbiddenError, UserBannedInChannelError) as e:
                logger.warning(f"   🔒 Нет доступа к группе через {account_name}: {e}")
                # Пробуем следующий аккаунт
                await asyncio.sleep(1)
                continue
                
            except Exception as e:
                logger.error(f"   ❌ Ошибка ({account_name}): {e}")
                # Пробуем следующий аккаунт
                await asyncio.sleep(1)
                continue
        
        # Если не удалось отправить ни через один аккаунт
        if not success:
            logger.error(f"   ❌ Не удалось отправить в {group} ни через один аккаунт (пробовали: {', '.join(tried_accounts)})")
            stats['failed'] += 1
            # Увеличиваем failed для всех попробованных аккаунтов
            for account_name in tried_accounts:
                if account_name not in stats['by_account']:
                    stats['by_account'][account_name] = {'attempted': 0, 'successful': 0, 'failed': 0}
                stats['by_account'][account_name]['failed'] += 1
        
        # Задержка между постами (60-120 секунд)
        if group_idx < len(kammora_groups):
            delay = random.randint(60, 120)
            logger.info(f"   ⏳ Задержка {delay} секунд перед следующим постом...")
            await asyncio.sleep(delay)
    
    # Финальная статистика
    logger.info("\n" + "=" * 80)
    logger.info("📊 ФИНАЛЬНАЯ СТАТИСТИКА")
    logger.info("=" * 80)
    logger.info(f"📬 Всего групп: {stats['total_groups']}")
    logger.info(f"🔄 Попыток отправки: {stats['attempted']}")
    logger.info(f"✅ Успешно: {stats['successful']}")
    logger.info(f"❌ Неудачно: {stats['failed']}")
    if stats['attempted'] > 0:
        success_rate = round(stats['successful']/stats['attempted']*100, 1)
        logger.info(f"📈 Процент успеха: {success_rate}%")
    
    logger.info(f"\n👥 СТАТИСТИКА ПО АККАУНТАМ:")
    for account, account_stats in stats['by_account'].items():
        if account_stats['attempted'] > 0:
            rate = round(account_stats['successful']/account_stats['attempted']*100, 1)
            logger.info(f"   {account}:")
            logger.info(f"      Попыток: {account_stats['attempted']}")
            logger.info(f"      Успешно: {account_stats['successful']}")
            logger.info(f"      Неудачно: {account_stats['failed']}")
            logger.info(f"      Успешность: {rate}%")
    
    logger.info(f"\n⏰ Завершено: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Сохраняем статистику
    stats_file = Path('logs/kammora_today_stats.json')
    with stats_file.open('w', encoding='utf-8') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'stats': stats
        }, f, ensure_ascii=False, indent=2)
    
    logger.info(f"💾 Статистика сохранена в {stats_file}")


if __name__ == "__main__":
    dry_run = '--dry-run' in sys.argv or '-d' in sys.argv
    
    if dry_run:
        print("🔍 DRY-RUN режим: сообщения не будут отправлены, только просмотр")
        print("Для реальной рассылки запустите без --dry-run")
        print()
    
    asyncio.run(send_kammora_to_groups(dry_run=dry_run))

