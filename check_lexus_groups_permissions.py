#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка прав на постинг в группах Lexus
Проверяет, являются ли аккаунты участниками и могут ли постить
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    UsernameNotOccupiedError,
    ChannelPrivateError,
    UserBannedInChannelError,
    ChatWriteForbiddenError,
    FloodWaitError,
    RPCError
)
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.messages import GetFullChatRequest

sys.path.insert(0, '.')

from promotion_system import PromotionSystem

def setup_logging():
    """Настройка логирования"""
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    
    log_file = log_dir / 'check_lexus_permissions.log'
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    return logging.getLogger(__name__)

async def check_group_permissions(client, account_name, group_username, logger):
    """Проверка прав на постинг в группе"""
    try:
        logger.info(f"  Проверяю {group_username} для {account_name}...")
        
        # Получаем entity
        entity = await client.get_entity(group_username)
        
        # Проверяем, участник ли
        is_member = False
        try:
            me = await client.get_me()
            # Пробуем получить участников (если получили - значит участник)
            participants = await client.get_participants(entity, limit=1)
            is_member = True
            logger.info(f"    ✅ {account_name} является участником {group_username}")
        except Exception as e:
            error_str = str(e).lower()
            if 'not a member' in error_str or 'not a participant' in error_str:
                logger.warning(f"    ❌ {account_name} НЕ является участником {group_username}")
                return {
                    'is_member': False,
                    'can_post': False,
                    'error': 'not_member'
                }
            else:
                # Другая ошибка - пробуем другой способ
                logger.debug(f"    ⚠️ Ошибка при проверке участника: {e}")
        
        # Если не участник через get_participants, пробуем через permissions
        if not is_member:
            try:
                me = await client.get_me()
                permissions = await client.get_permissions(entity, me)
                if permissions:
                    is_member = True
                    logger.info(f"    ✅ {account_name} является участником {group_username} (проверено через permissions)")
            except Exception as e:
                error_str = str(e).lower()
                if 'not a member' in error_str or 'not a participant' in error_str:
                    logger.warning(f"    ❌ {account_name} НЕ является участником {group_username}")
                    return {
                        'is_member': False,
                        'can_post': False,
                        'error': 'not_member'
                    }
        
        # Проверяем права на постинг
        try:
            me = await client.get_me()
            permissions = await client.get_permissions(entity, me)
            
            can_send = False
            if permissions:
                if hasattr(permissions, 'send_messages'):
                    can_send = permissions.send_messages
                elif hasattr(permissions, 'banned_rights') and permissions.banned_rights:
                    if hasattr(permissions.banned_rights, 'send_messages'):
                        can_send = not permissions.banned_rights.send_messages
            
            if can_send:
                logger.info(f"    ✅ {account_name} МОЖЕТ постить в {group_username}")
                return {
                    'is_member': True,
                    'can_post': True,
                    'error': None
                }
            else:
                logger.warning(f"    ⚠️ {account_name} НЕ МОЖЕТ постить в {group_username} (нет прав)")
                return {
                    'is_member': True,
                    'can_post': False,
                    'error': 'no_permission'
                }
                
        except UserBannedInChannelError:
            logger.warning(f"    🚫 {account_name} ЗАБАНЕН в {group_username}")
            return {
                'is_member': False,
                'can_post': False,
                'error': 'banned'
            }
        except ChatWriteForbiddenError:
            logger.warning(f"    ⚠️ {account_name} НЕТ ПРАВ на постинг в {group_username}")
            return {
                'is_member': True,
                'can_post': False,
                'error': 'write_forbidden'
            }
        except Exception as e:
            logger.warning(f"    ⚠️ Ошибка при проверке прав в {group_username}: {e}")
            return {
                'is_member': is_member,
                'can_post': False,
                'error': str(e)
            }
            
    except UsernameNotOccupiedError:
        logger.warning(f"    ⚠️ Группа {group_username} не найдена")
        return {
            'is_member': False,
            'can_post': False,
            'error': 'not_found'
        }
    except ChannelPrivateError:
        logger.warning(f"    ⚠️ Группа {group_username} приватная")
        return {
            'is_member': False,
            'can_post': False,
            'error': 'private'
        }
    except Exception as e:
        logger.error(f"    ❌ Ошибка для {group_username}: {e}")
        return {
            'is_member': False,
            'can_post': False,
            'error': str(e)
        }

async def main():
    """Основная функция"""
    logger = setup_logging()

    parser = argparse.ArgumentParser(description="Проверка прав на постинг в Lexus группах")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Ограничить число проверяемых групп (0 = без лимита)",
    )
    parser.add_argument(
        "--targets-only",
        action="store_true",
        help="Проверять только группы, которые есть в targets.txt",
    )
    args = parser.parse_args()
    
    logger.info("=" * 80)
    logger.info("🔍 ПРОВЕРКА ПРАВ НА ПОСТИНГ В ГРУППАХ LEXUS")
    logger.info("=" * 80)
    
    system = PromotionSystem()
    system.load_accounts()
    system.load_lexus_accounts_config()
    
    # Фильтруем аккаунты для Lexus
    if hasattr(system, 'lexus_allowed_accounts') and system.lexus_allowed_accounts:
        system.accounts = [
            acc for acc in system.accounts
            if acc.get('session_name') in system.lexus_allowed_accounts
        ]
        logger.info(f"✅ Загружено {len(system.accounts)} аккаунтов для Lexus")
    else:
        logger.warning("⚠️ Не найден whitelist для Lexus")
    
    system.load_group_niches()
    await system.initialize_clients()
    
    if not system.clients:
        logger.error("❌ Нет доступных клиентов!")
        return
    
    # Получаем группы с нишей ukraine_cars
    ukraine_cars_groups = [
        target for target, niche in system.group_niches.items()
        if niche == 'ukraine_cars'
    ]

    if args.targets_only:
        targets_path = Path("targets.txt")
        if targets_path.exists():
            with targets_path.open("r", encoding="utf-8") as f:
                targets = {line.strip() for line in f if line.strip() and not line.startswith("#")}
            ukraine_cars_groups = [g for g in ukraine_cars_groups if g in targets]
            logger.info(f"📌 Фильтр targets.txt: осталось {len(ukraine_cars_groups)} групп")
        else:
            logger.warning("⚠️ targets.txt не найден, фильтр targets-only пропущен")

    if args.limit and args.limit > 0:
        ukraine_cars_groups = ukraine_cars_groups[:args.limit]
        logger.info(f"📌 Лимит групп: проверяем {len(ukraine_cars_groups)}")
    
    logger.info(f"📋 Найдено {len(ukraine_cars_groups)} групп с нишей 'ukraine_cars'")
    logger.info("")
    
    # Результаты проверки
    results = {}
    
    for group_username in ukraine_cars_groups:
        logger.info(f"\n{'='*80}")
        logger.info(f"📋 Группа: {group_username}")
        logger.info(f"{'='*80}")
        
        group_results = {}
        
        for account_name, client in system.clients.items():
            result = await check_group_permissions(client, account_name, group_username, logger)
            group_results[account_name] = result
            
            # Небольшая задержка между проверками
            await asyncio.sleep(1)
        
        results[group_username] = group_results
        
        # Задержка между группами
        await asyncio.sleep(2)
    
    # Выводим итоговую таблицу
    logger.info("")
    logger.info("=" * 80)
    logger.info("📊 ИТОГОВАЯ ТАБЛИЦА")
    logger.info("=" * 80)
    logger.info(f"{'Группа':<30} {'Аккаунт':<25} {'Участник':<10} {'Может постить':<15} {'Ошибка':<20}")
    logger.info("-" * 100)
    
    for group_username, group_results in results.items():
        for account_name, result in group_results.items():
            is_member = "✅" if result['is_member'] else "❌"
            can_post = "✅" if result['can_post'] else "❌"
            error = result.get('error', '') or '-'
            
            logger.info(f"{group_username:<30} {account_name:<25} {is_member:<10} {can_post:<15} {error:<20}")
    
    # Статистика
    logger.info("")
    logger.info("=" * 80)
    logger.info("📈 СТАТИСТИКА")
    logger.info("=" * 80)
    
    total_groups = len(results)
    groups_with_post_permission = 0
    accounts_with_permission = 0
    
    for group_username, group_results in results.items():
        has_any_permission = any(r['can_post'] for r in group_results.values())
        if has_any_permission:
            groups_with_post_permission += 1
        accounts_with_permission += sum(1 for r in group_results.values() if r['can_post'])
    
    logger.info(f"Всего групп: {total_groups}")
    logger.info(f"Групп, где можно постить (хотя бы одним аккаунтом): {groups_with_post_permission}")
    logger.info(f"Всего комбинаций аккаунт-группа с правами на постинг: {accounts_with_permission}")
    logger.info(f"Групп, где НЕЛЬЗЯ постить: {total_groups - groups_with_post_permission}")
    
    # Сохраняем результаты в JSON
    log_dir = Path('logs')
    results_file = log_dir / 'lexus_groups_permissions_check.json'
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    logger.info(f"\n💾 Результаты сохранены в {results_file}")
    
    logger.info("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
