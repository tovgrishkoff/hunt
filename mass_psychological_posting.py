#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для массовой рассылки психологических сообщений во все группы про Бали
Максимальный охват со всех аккаунтов
"""

import asyncio
import random
import json
import logging
import sys
from pathlib import Path
from datetime import datetime
from telethon import TelegramClient
from telethon.errors import FloodWaitError, ChatWriteForbiddenError, UserBannedInChannelError

sys.path.insert(0, '.')
from promotion_system import PromotionSystem

async def mass_psychological_posting(dry_run=False):
    """Массовая рассылка психологических сообщений"""
    
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('logs/mass_psychological_posting.log', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 80)
    logger.info("🚀 МАССОВАЯ РАССЫЛКА ПСИХОЛОГИЧЕСКИХ СООБЩЕНИЙ")
    logger.info("=" * 80)
    
    # Инициализируем систему
    system = PromotionSystem()
    system.load_accounts()
    await system.initialize_clients()
    
    if not system.clients:
        logger.error("❌ Нет доступных клиентов!")
        return
    
    logger.info(f"✅ Загружено {len(system.clients)} аккаунтов")
    
    # Загружаем сообщения
    messages_file = Path('messages_psychological.txt')
    if not messages_file.exists():
        logger.error(f"❌ Файл {messages_file} не найден!")
        return
    
    with messages_file.open('r', encoding='utf-8') as f:
        content = f.read()
    
    # Разбиваем сообщения по разделителю ---
    messages = [msg.strip() for msg in content.split('---') if msg.strip()]
    logger.info(f"✅ Загружено {len(messages)} сообщений")
    
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
    
    # Перемешиваем группы для разнообразия
    random.shuffle(all_groups)
    
    logger.info(f"\n{'🔍 DRY-RUN: только просмотр' if dry_run else '📨 РЕАЛЬНАЯ РАССЫЛКА'}")
    logger.info(f"⏰ Начало: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 80)
    
    # Рассылаем во все группы
    for group_idx, group in enumerate(all_groups, 1):
        stats['attempted'] += 1
        
        # Выбираем случайное сообщение
        message = random.choice(messages)
        
        # Выбираем аккаунт (ротация)
        account_names = list(system.clients.keys())
        account_name = random.choice(account_names)
        client = system.clients[account_name]
        
        # Инициализируем счетчик для аккаунта
        if account_name not in stats['by_account']:
            stats['by_account'][account_name] = {'attempted': 0, 'successful': 0, 'failed': 0}
        
        stats['by_account'][account_name]['attempted'] += 1
        
        logger.info(f"\n[{group_idx}/{len(all_groups)}] 📬 Группа: {group}")
        logger.info(f"   👤 Аккаунт: {account_name}")
        logger.info(f"   💬 Сообщение #{messages.index(message) + 1} ({len(message)} символов)")
        
        if dry_run:
            logger.info(f"   [DRY-RUN] Будет отправлено: {message[:100]}...")
            stats['successful'] += 1
            stats['by_account'][account_name]['successful'] += 1
            await asyncio.sleep(0.5)  # Небольшая задержка даже в dry-run
            continue
        
        # Реальная отправка
        try:
            # Разрешаем entity
            entity = await client.get_entity(group)
            
            # Отправляем сообщение
            await client.send_message(entity, message)
            
            logger.info(f"   ✅ Успешно отправлено!")
            stats['successful'] += 1
            stats['by_account'][account_name]['successful'] += 1
            
        except FloodWaitError as e:
            logger.warning(f"   ⏳ FloodWait: нужно подождать {e.seconds} секунд")
            await asyncio.sleep(e.seconds)
            # Пробуем еще раз
            try:
                entity = await client.get_entity(group)
                await client.send_message(entity, message)
                logger.info(f"   ✅ Отправлено после ожидания!")
                stats['successful'] += 1
                stats['by_account'][account_name]['successful'] += 1
            except Exception as retry_e:
                logger.error(f"   ❌ Ошибка при повторной попытке: {retry_e}")
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
        
        # Задержка между постами (30-90 секунд для безопасности)
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
    logger.info(f"📈 Процент успеха: {round(stats['successful']/stats['attempted']*100, 1) if stats['attempted'] > 0 else 0}%")
    
    logger.info(f"\n👥 СТАТИСТИКА ПО АККАУНТАМ:")
    for account, account_stats in stats['by_account'].items():
        success_rate = round(account_stats['successful']/account_stats['attempted']*100, 1) if account_stats['attempted'] > 0 else 0
        logger.info(f"   {account}:")
        logger.info(f"      Попыток: {account_stats['attempted']}")
        logger.info(f"      Успешно: {account_stats['successful']}")
        logger.info(f"      Неудачно: {account_stats['failed']}")
        logger.info(f"      Успешность: {success_rate}%")
    
    logger.info(f"\n⏰ Завершено: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Сохраняем статистику в файл
    stats_file = Path('logs/mass_psychological_stats.json')
    with stats_file.open('w', encoding='utf-8') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'stats': stats
        }, f, ensure_ascii=False, indent=2)
    
    logger.info(f"💾 Статистика сохранена в {stats_file}")

if __name__ == "__main__":
    import sys
    
    dry_run = '--dry-run' in sys.argv or '-d' in sys.argv
    
    if dry_run:
        print("🔍 DRY-RUN режим: сообщения не будут отправлены, только просмотр")
        print("Для реальной рассылки запустите без --dry-run")
        print()
    
    asyncio.run(mass_psychological_posting(dry_run=dry_run))

