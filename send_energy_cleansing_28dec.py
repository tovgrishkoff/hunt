#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для рассылки объявлений об энергетической чистке перед Новым годом
Запуск на 28 декабря
"""

import asyncio
import json
import logging
import random
import sys
from pathlib import Path
from datetime import datetime

from telethon.errors import FloodWaitError, ChatWriteForbiddenError, UserBannedInChannelError

sys.path.insert(0, '.')
from promotion_system import PromotionSystem


async def send_energy_cleansing_messages(dry_run=False):
    """Рассылка сообщений об энергетической чистке"""
    
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('logs/energy_cleansing_28dec.log', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 80)
    logger.info("✨ РАССЫЛКА: Энергетическая чистка перед Новым годом (28 декабря)")
    logger.info("=" * 80)
    
    # Инициализируем систему
    system = PromotionSystem()
    system.load_accounts()
    await system.initialize_clients()
    
    if not system.clients:
        logger.error("❌ Нет доступных клиентов!")
        return
    
    logger.info(f"✅ Загружено {len(system.clients)} аккаунтов")
    
    # Загружаем сообщение
    messages_file = Path('messages_energy_cleansing.txt')
    if not messages_file.exists():
        logger.error(f"❌ Файл {messages_file} не найден!")
        return
    
    with messages_file.open('r', encoding='utf-8') as f:
        message_text = f.read().strip()
    
    logger.info(f"✅ Загружено сообщение ({len(message_text)} символов)")
    
    # Загружаем все группы про Бали
    targets_file = Path('targets.txt')
    if not targets_file.exists():
        logger.error("❌ Файл targets.txt не найден!")
        return
    
    with targets_file.open('r', encoding='utf-8') as f:
        all_groups = [line.strip() for line in f if line.strip() and line.strip().startswith('@')]
    
    logger.info(f"✅ Загружено {len(all_groups)} групп")
    
    # Статистика
    stats = {
        'total_groups': len(all_groups),
        'attempted': 0,
        'successful': 0,
        'failed': 0,
        'by_account': {}
    }
    
    # Перемешиваем группы
    random.shuffle(all_groups)
    
    logger.info(f"\n{'🔍 DRY-RUN: только просмотр' if dry_run else '📨 РЕАЛЬНАЯ РАССЫЛКА'}")
    logger.info(f"⏰ Начало: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 80)
    
    # Рассылаем во все группы
    for group_idx, group in enumerate(all_groups, 1):
        stats['attempted'] += 1
        
        # Выбираем аккаунт (ротация)
        account_names = list(system.clients.keys())
        account_name = random.choice(account_names)
        client = system.clients[account_name]
        
        if account_name not in stats['by_account']:
            stats['by_account'][account_name] = {'attempted': 0, 'successful': 0, 'failed': 0}
        
        stats['by_account'][account_name]['attempted'] += 1
        
        logger.info(f"\n[{group_idx}/{len(all_groups)}] 📬 Группа: {group}")
        logger.info(f"   👤 Аккаунт: {account_name}")
        logger.info(f"   💬 Сообщение: {message_text[:80]}...")
        
        if dry_run:
            logger.info(f"   [DRY-RUN] Будет отправлено сообщение")
            stats['successful'] += 1
            stats['by_account'][account_name]['successful'] += 1
            await asyncio.sleep(0.5)
            continue
        
        # Реальная отправка
        try:
            # Разрешаем entity
            entity = await system.resolve_target(client, group)
            if entity is None:
                logger.warning(f"   ⚠️ Не удалось разрешить {group}")
                stats['failed'] += 1
                stats['by_account'][account_name]['failed'] += 1
                continue
            
            # Отправляем сообщение
            await client.send_message(entity, message_text)
            
            logger.info(f"   ✅ Успешно отправлено!")
            stats['successful'] += 1
            stats['by_account'][account_name]['successful'] += 1
            
            # Обновляем историю
            system.mark_group_posted(group, account_name)
            
        except FloodWaitError as e:
            logger.warning(f"   ⏳ FloodWait: нужно подождать {e.seconds} секунд")
            await asyncio.sleep(min(e.seconds, 300))  # Максимум 5 минут
            stats['failed'] += 1
            stats['by_account'][account_name]['failed'] += 1
            
        except (ChatWriteForbiddenError, UserBannedInChannelError) as e:
            logger.warning(f"   🔒 Нет доступа к группе: {e}")
            stats['failed'] += 1
            stats['by_account'][account_name]['failed'] += 1
            
        except Exception as e:
            logger.error(f"   ❌ Ошибка: {e}")
            stats['failed'] += 1
            stats['by_account'][account_name]['failed'] += 1
        
        # Задержка между постами (30-90 секунд)
        if group_idx < len(all_groups):
            delay = random.randint(30, 90)
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
    stats_file = Path('logs/energy_cleansing_28dec_stats.json')
    with stats_file.open('w', encoding='utf-8') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'stats': stats
        }, f, ensure_ascii=False, indent=2)
    
    logger.info(f"💾 Статистика сохранена в {stats_file}")


if __name__ == "__main__":
    # Проверяем дату - скрипт должен запускаться 28 декабря
    today = datetime.now()
    if today.day != 28:
        print(f"⚠️  ВНИМАНИЕ: Сегодня {today.day} число, а скрипт предназначен для 28 декабря")
        print("Для запуска в другую дату используйте --force")
        if '--force' not in sys.argv:
            sys.exit(1)
    
    dry_run = '--dry-run' in sys.argv or '-d' in sys.argv
    
    if dry_run:
        print("🔍 DRY-RUN режим: сообщения не будут отправлены, только просмотр")
        print("Для реальной рассылки запустите без --dry-run")
        print()
    
    asyncio.run(send_energy_cleansing_messages(dry_run=dry_run))


