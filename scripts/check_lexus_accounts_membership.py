#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка участия аккаунтов Lexus в группах
Проверяет, являются ли аккаунты promotion_dao_bro и promotion_rod_shaihutdinov участниками групп ukraine_cars
"""

import asyncio
import sys
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime

# Добавляем корневую директорию в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

from telethon import TelegramClient
from telethon.errors import (
    UsernameNotOccupiedError,
    ChannelPrivateError,
    UserBannedInChannelError,
    ChatWriteForbiddenError,
    FloodWaitError,
    RPCError
)
from shared.database.session import get_db
from promotion_system import PromotionSystem


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/check_lexus_membership.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class LexusMembershipChecker:
    """Класс для проверки участия аккаунтов в группах Lexus"""
    
    def __init__(self):
        self.system = PromotionSystem()
        self.system.load_accounts()
        self.system.load_lexus_accounts_config()
        
        # Фильтруем аккаунты для Lexus
        if hasattr(self.system, 'lexus_allowed_accounts') and self.system.lexus_allowed_accounts:
            self.system.accounts = [
                acc for acc in self.system.accounts
                if acc.get('session_name') in self.system.lexus_allowed_accounts
            ]
            logger.info(f"✅ Загружено {len(self.system.accounts)} аккаунтов для Lexus: {[acc.get('session_name') for acc in self.system.accounts]}")
        else:
            logger.warning("⚠️ Не найден whitelist для Lexus, используем все аккаунты")
        
        self.clients: Dict[str, TelegramClient] = {}
        self.results: Dict[str, Dict[str, Dict[str, str]]] = {}  # {group_username: {account_name: {status: ..., error: ...}}}
    
    async def initialize_clients(self):
        """Инициализация клиентов Telegram"""
        logger.info("🔄 Инициализация клиентов...")
        await self.system.initialize_clients()
        self.clients = self.system.clients
        logger.info(f"✅ Инициализировано {len(self.clients)} клиентов")
    
    async def check_membership(self, client: TelegramClient, account_name: str, group_username: str) -> Tuple[str, Optional[str]]:
        """
        Проверка участия аккаунта в группе
        
        Returns:
            (status, error_message): статус ('member', 'not_member', 'banned', 'not_found', 'error') и сообщение об ошибке
        """
        try:
            # Шаг 1: Проверяем, можем ли разрешить entity (группа существует и видна)
            try:
                entity = await client.get_entity(group_username)
            except UsernameNotOccupiedError:
                return ('not_found', f'Группа {group_username} не найдена')
            except ChannelPrivateError:
                return ('private', f'Группа {group_username} приватная')
            except Exception as e:
                return ('error', f'Не удалось разрешить entity: {e}')
            
            # Шаг 2: Проверяем участие через get_permissions (более надежный метод)
            # Если get_permissions работает - значит мы участники группы
            try:
                me = await client.get_me()
                permissions = await client.get_permissions(entity, me)
                
                # Если получили permissions - значит мы участники
                logger.debug(f"  ✅ {account_name} является участником {group_username}")
                
                # Шаг 3: Проверяем права на постинг
                can_send = False
                if permissions:
                    if hasattr(permissions, 'send_messages'):
                        can_send = permissions.send_messages
                    elif hasattr(permissions, 'banned_rights') and permissions.banned_rights:
                        if hasattr(permissions.banned_rights, 'send_messages'):
                            can_send = not permissions.banned_rights.send_messages
                
                if can_send:
                    return ('member_can_post', None)
                else:
                    return ('member_cannot_post', 'Нет прав на постинг')
                    
            except UserBannedInChannelError:
                return ('banned', 'Аккаунт забанен в группе')
            except ChatWriteForbiddenError:
                return ('member_cannot_post', 'Запрещено писать в группе')
            except Exception as e:
                # Если ошибка при получении permissions - возможно, не участник
                error_str = str(e).lower()
                if 'not a member' in error_str or 'user not found' in error_str or 'participant' in error_str or 'chat not found' in error_str:
                    return ('not_member', 'Аккаунт не является участником группы')
                elif 'channel private' in error_str or 'private' in error_str:
                    return ('private', 'Группа приватная')
                else:
                    # Неизвестная ошибка - логируем, но считаем, что не участник
                    logger.warning(f"  ⚠️ Неожиданная ошибка при проверке permissions для {account_name} в {group_username}: {e}")
                    return ('error', f'Ошибка при проверке: {e}')
        
        except FloodWaitError as e:
            logger.warning(f"  ⚠️ FloodWait {e.seconds} секунд для {account_name} в {group_username}")
            return ('flood_wait', f'FloodWait {e.seconds} секунд')
        except Exception as e:
            logger.error(f"  ❌ Неожиданная ошибка для {account_name} в {group_username}: {e}")
            return ('error', str(e))
    
    async def check_all_groups(self, limit: Optional[int] = None):
        """Проверка всех групп Lexus"""
        # Загружаем группы из group_niches.json (как это делает lexus_scheduler)
        import json
        group_niches_path = Path('group_niches.json')
        
        if not group_niches_path.exists():
            logger.error("❌ Файл group_niches.json не найден!")
            return
        
        with open(group_niches_path, 'r', encoding='utf-8') as f:
            group_niches = json.load(f)
        
        # Фильтруем группы с niche='ukraine_cars'
        ukraine_cars_groups = [
            target for target, niche in group_niches.items()
            if niche == 'ukraine_cars'
        ]
        
        if limit:
            ukraine_cars_groups = ukraine_cars_groups[:limit]
        
        logger.info(f"📋 Найдено {len(ukraine_cars_groups)} групп с niche='ukraine_cars'")
        
        total = len(ukraine_cars_groups)
        for idx, username in enumerate(ukraine_cars_groups, 1):
            logger.info(f"  [{idx}/{total}] Проверяю группу {username}...")
            
            self.results[username] = {}
            
            # Проверяем для каждого аккаунта
            for account_name, client in self.clients.items():
                logger.info(f"    📱 Аккаунт: {account_name}")
                status, error = await self.check_membership(client, account_name, username)
                self.results[username][account_name] = {
                    'status': status,
                    'error': error
                }
                
                # Краткий статус
                status_emoji = {
                    'member_can_post': '✅',
                    'member': '✅',
                    'member_cannot_post': '⚠️',
                    'not_member': '❌',
                    'banned': '🚫',
                    'not_found': '🔍',
                    'private': '🔒',
                    'error': '❓',
                    'flood_wait': '⏳'
                }.get(status, '❓')
                
                logger.info(f"      {status_emoji} {status}" + (f": {error}" if error else ""))
                
                # Небольшая задержка между проверками
                await asyncio.sleep(0.5)
            
            await asyncio.sleep(1)  # Задержка между группами
    
    def generate_report(self) -> str:
        """Генерация отчета о проверке"""
        report_lines = [
            "=" * 80,
            "📊 ОТЧЕТ О ПРОВЕРКЕ УЧАСТИЯ АККАУНТОВ LEXUS В ГРУППАХ",
            f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 80,
            ""
        ]
        
        # Статистика
        total_groups = len(self.results)
        stats = {
            'member_can_post': 0,
            'member': 0,
            'member_cannot_post': 0,
            'not_member': 0,
            'banned': 0,
            'not_found': 0,
            'private': 0,
            'error': 0,
            'flood_wait': 0
        }
        
        for group_username, accounts in self.results.items():
            for account_name, result in accounts.items():
                status = result['status']
                stats[status] = stats.get(status, 0) + 1
        
        report_lines.extend([
            "📈 СТАТИСТИКА:",
            f"  Всего групп проверено: {total_groups}",
            f"  Всего проверок (группы × аккаунты): {sum(stats.values())}",
            "",
            "По статусам:",
            f"  ✅ Участник с правом постинга: {stats['member_can_post']}",
            f"  ✅ Участник (права не проверены): {stats['member']}",
            f"  ⚠️ Участник, но нет прав на постинг: {stats['member_cannot_post']}",
            f"  ❌ НЕ участник: {stats['not_member']}",
            f"  🚫 Забанен: {stats['banned']}",
            f"  🔍 Группа не найдена: {stats['not_found']}",
            f"  🔒 Группа приватная: {stats['private']}",
            f"  ❓ Ошибка: {stats['error']}",
            f"  ⏳ FloodWait: {stats['flood_wait']}",
            "",
            "=" * 80,
            "",
        ])
        
        # Группы, где аккаунты НЕ участники
        not_members = {}
        for group_username, accounts in self.results.items():
            for account_name, result in accounts.items():
                if result['status'] in ['not_member', 'banned']:
                    if group_username not in not_members:
                        not_members[group_username] = []
                    not_members[group_username].append((account_name, result))
        
        if not_members:
            report_lines.extend([
                "🚨 ГРУППЫ, ГДЕ АККАУНТЫ НЕ ЯВЛЯЮТСЯ УЧАСТНИКАМИ ИЛИ ЗАБАНЕНЫ:",
                "",
            ])
            
            for group_username, accounts_list in sorted(not_members.items()):
                report_lines.append(f"  {group_username}:")
                for account_name, result in accounts_list:
                    report_lines.append(f"    - {account_name}: {result['status']}" + (f" ({result['error']})" if result['error'] else ""))
                report_lines.append("")
        
        # Группы, где есть проблемы с правами
        permission_issues = {}
        for group_username, accounts in self.results.items():
            for account_name, result in accounts.items():
                if result['status'] == 'member_cannot_post':
                    if group_username not in permission_issues:
                        permission_issues[group_username] = []
                    permission_issues[group_username].append((account_name, result))
        
        if permission_issues:
            report_lines.extend([
                "⚠️ ГРУППЫ, ГДЕ НЕТ ПРАВ НА ПОСТИНГ:",
                "",
            ])
            
            for group_username, accounts_list in sorted(permission_issues.items()):
                report_lines.append(f"  {group_username}:")
                for account_name, result in accounts_list:
                    report_lines.append(f"    - {account_name}: {result['error'] or 'Нет прав на постинг'}")
                report_lines.append("")
        
        # Группы, где все ОК
        all_ok = []
        for group_username, accounts in self.results.items():
            if all(result['status'] in ['member_can_post', 'member'] for result in accounts.values()):
                all_ok.append(group_username)
        
        if all_ok:
            report_lines.extend([
                f"✅ ГРУППЫ, ГДЕ ВСЕ АККАУНТЫ УЧАСТНИКИ ({len(all_ok)}):",
                "",
            ])
            
            # Показываем первые 20
            for group_username in sorted(all_ok)[:20]:
                report_lines.append(f"  ✅ {group_username}")
            
            if len(all_ok) > 20:
                report_lines.append(f"  ... и еще {len(all_ok) - 20} групп")
            report_lines.append("")
        
        report_lines.append("=" * 80)
        
        return "\n".join(report_lines)


async def main():
    """Основная функция"""
    checker = LexusMembershipChecker()
    
    try:
        await checker.initialize_clients()
        
        # Проверяем первые 30 групп (можно увеличить или убрать лимит)
        logger.info("🔍 Начинаю проверку групп...")
        await checker.check_all_groups(limit=30)  # Удалите limit=None для проверки всех групп
        
        # Генерируем отчет
        report = checker.generate_report()
        print("\n" + report)
        
        # Сохраняем отчет в файл
        report_file = Path('logs') / f'lexus_membership_check_{datetime.now().strftime("%Y%m%d_%H%M%S")}.md'
        report_file.parent.mkdir(exist_ok=True)
        report_file.write_text(report, encoding='utf-8')
        logger.info(f"📄 Отчет сохранен в {report_file}")
        
    except KeyboardInterrupt:
        logger.info("⚠️ Прервано пользователем")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}", exc_info=True)
    finally:
        # Закрываем клиенты
        for client in checker.clients.values():
            if client.is_connected():
                await client.disconnect()


if __name__ == '__main__':
    asyncio.run(main())
