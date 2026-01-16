#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка всех групп Lexus, фильтрация по количеству участников и вступление в самые популярные
"""

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from telethon import TelegramClient
from telethon.errors import (
    UsernameNotOccupiedError,
    ChannelPrivateError,
    UserBannedInChannelError,
    ChatWriteForbiddenError,
    FloodWaitError,
    RPCError,
    ChatAdminRequiredError
)
from telethon.tl.functions.channels import JoinChannelRequest, GetFullChannelRequest
from telethon.tl.functions.messages import GetFullChatRequest

from promotion_system import PromotionSystem

# Настройка логирования
log_dir = Path('logs')
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / 'lexus_top_groups_join.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class LexusTopGroupsJoiner:
    """Класс для проверки и вступления в топ группы Lexus"""
    
    def __init__(self, min_members: int = 1000):
        """
        Args:
            min_members: Минимальное количество участников для включения в топ
        """
        self.min_members = min_members
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
        self.results: Dict[str, Dict] = {}  # {username: {members_count, status, accounts_status}}
        self.groups_to_join: List[Dict] = []  # Список групп для вступления
    
    async def initialize_clients(self):
        """Инициализация клиентов Telegram"""
        logger.info("🔄 Инициализация клиентов...")
        await self.system.initialize_clients()
        self.clients = self.system.clients
        logger.info(f"✅ Инициализировано {len(self.clients)} клиентов")
    
    async def get_group_info(self, client: TelegramClient, username: str) -> Optional[Dict]:
        """
        Получение информации о группе (название, количество участников)
        
        Returns:
            Dict с полями: title, members_count, или None если ошибка
        """
        try:
            entity = await client.get_entity(username)
            
            # Пытаемся получить полную информацию
            try:
                if hasattr(entity, 'broadcast') and entity.broadcast:
                    # Это канал
                    full_info = await client(GetFullChannelRequest(entity))
                    members_count = getattr(full_info.full_chat, 'participants_count', 0)
                else:
                    # Это группа
                    full_info = await client(GetFullChatRequest(entity.chat_id))
                    members_count = getattr(full_info.full_chat, 'participants_count', 0)
            except Exception:
                # Fallback: пытаемся получить из entity
                members_count = getattr(entity, 'participants_count', 0)
            
            title = getattr(entity, 'title', username)
            
            return {
                'title': title,
                'members_count': members_count or 0,
                'entity': entity
            }
        except UsernameNotOccupiedError:
            return {'title': username, 'members_count': 0, 'error': 'not_found'}
        except ChannelPrivateError:
            return {'title': username, 'members_count': 0, 'error': 'private'}
        except Exception as e:
            logger.warning(f"  ⚠️ Ошибка при получении информации о {username}: {e}")
            return {'title': username, 'members_count': 0, 'error': str(e)}
    
    async def check_membership_and_permissions(self, client: TelegramClient, account_name: str, username: str, entity) -> Tuple[str, Optional[str]]:
        """
        Проверка участия и прав на постинг
        
        Returns:
            (status, error_message)
        """
        try:
            me = await client.get_me()
            permissions = await client.get_permissions(entity, me)
            
            # Проверяем права на постинг
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
            error_str = str(e).lower()
            if 'not a member' in error_str or 'participant' in error_str:
                return ('not_member', 'Аккаунт не является участником группы')
            else:
                return ('error', f'Ошибка при проверке: {e}')
    
    async def check_all_groups_info(self, limit: Optional[int] = None):
        """Проверка информации о всех группах Lexus"""
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
        logger.info(f"🎯 Минимальное количество участников для включения в топ: {self.min_members}")
        logger.info("🔍 Проверяю информацию о группах...")
        
        # Используем первый доступный клиент для получения информации
        if not self.clients:
            logger.error("❌ Нет доступных клиентов!")
            return
        
        first_client = next(iter(self.clients.values()))
        
        total = len(ukraine_cars_groups)
        checked = 0
        
        for idx, username in enumerate(ukraine_cars_groups, 1):
            if idx % 50 == 0:
                logger.info(f"  Прогресс: {idx}/{total} групп проверено...")
            
            group_info = await self.get_group_info(first_client, username)
            
            if group_info:
                if 'error' in group_info:
                    self.results[username] = {
                        'title': group_info.get('title', username),
                        'members_count': 0,
                        'error': group_info['error'],
                        'accounts_status': {}
                    }
                else:
                    members_count = group_info.get('members_count', 0)
                    entity = group_info.get('entity')
                    
                    # Проверяем участие всех аккаунтов
                    accounts_status = {}
                    for account_name, client in self.clients.items():
                        if entity:
                            status, error = await self.check_membership_and_permissions(client, account_name, username, entity)
                            accounts_status[account_name] = {'status': status, 'error': error}
                        else:
                            accounts_status[account_name] = {'status': 'error', 'error': 'Не удалось получить entity'}
                    
                    self.results[username] = {
                        'title': group_info.get('title', username),
                        'members_count': members_count,
                        'entity': entity,
                        'accounts_status': accounts_status
                    }
            
            checked += 1
            
            # Небольшая задержка между запросами
            if idx % 10 == 0:
                await asyncio.sleep(1)
            else:
                await asyncio.sleep(0.3)
        
        logger.info(f"✅ Проверено {checked}/{total} групп")
    
    def filter_top_groups(self):
        """Фильтрация топ групп по количеству участников"""
        logger.info("🎯 Фильтрую топ группы...")
        
        # Фильтруем группы с достаточным количеством участников
        top_groups = []
        for username, info in self.results.items():
            members_count = info.get('members_count', 0)
            error = info.get('error')
            
            # Пропускаем группы с ошибками
            if error in ['not_found', 'private']:
                continue
            
            # Пропускаем группы с малым количеством участников
            if members_count < self.min_members:
                continue
            
            # Проверяем, есть ли хотя бы один аккаунт, который не является участником
            accounts_status = info.get('accounts_status', {})
            needs_join = False
            for account_name, status_info in accounts_status.items():
                if status_info.get('status') == 'not_member':
                    needs_join = True
                    break
            
            if needs_join:
                top_groups.append({
                    'username': username,
                    'title': info.get('title', username),
                    'members_count': members_count,
                    'entity': info.get('entity'),
                    'accounts_status': accounts_status
                })
        
        # Сортируем по количеству участников (от большего к меньшему)
        top_groups.sort(key=lambda x: x['members_count'], reverse=True)
        
        self.groups_to_join = top_groups
        
        logger.info(f"✅ Найдено {len(top_groups)} топ групп для вступления (≥{self.min_members} участников)")
        
        if top_groups:
            logger.info("Топ-10 групп по количеству участников:")
            for i, group in enumerate(top_groups[:10], 1):
                logger.info(f"  {i:2}. {group['username']:30} - {group['members_count']:>6} участников - {group['title'][:40]}")
    
    async def join_group(self, client: TelegramClient, account_name: str, username: str, entity) -> Tuple[bool, Optional[str]]:
        """Вступление в группу"""
        try:
            # Проверяем, не участник ли уже
            try:
                me = await client.get_me()
                permissions = await client.get_permissions(entity, me)
                # Если получили permissions - значит уже участник
                logger.info(f"    ℹ️ {account_name} уже участник {username}")
                return True, None
            except Exception:
                # Не участник - вступаем
                pass
            
            logger.info(f"    🚪 {account_name} вступает в {username}...")
            await client(JoinChannelRequest(entity))
            logger.info(f"    ✅ {account_name} вступил в {username}")
            
            # Проверяем права после вступления
            await asyncio.sleep(2)  # Небольшая задержка после вступления
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
                return True, None
            else:
                return False, "Нет прав на постинг"
                
        except UserAlreadyParticipantError:
            logger.info(f"    ℹ️ {account_name} уже участник {username}")
            return True, None
        except FloodWaitError as e:
            wait_seconds = e.seconds
            max_wait = 600  # 10 минут
            if wait_seconds > max_wait:
                return False, f"FloodWait: {wait_seconds} секунд (слишком большой, пропускаем)"
            else:
                logger.warning(f"    ⏳ FloodWait {wait_seconds} секунд, ждем...")
                await asyncio.sleep(wait_seconds)
                return False, f"FloodWait: {wait_seconds} секунд"
        except UserBannedInChannelError:
            return False, "Аккаунт забанен в группе"
        except ChatAdminRequiredError:
            return False, "Требуются права администратора"
        except ChannelPrivateError:
            return False, "Группа приватная"
        except RPCError as e:
            error_msg = str(e)
            if "CAPTCHA" in error_msg:
                return False, "Требуется капча"
            return False, f"RPC Error: {error_msg}"
        except Exception as e:
            return False, f"Ошибка: {e}"
    
    async def join_top_groups(self, max_groups: Optional[int] = None):
        """Вступление в топ группы"""
        if not self.groups_to_join:
            logger.warning("⚠️ Нет групп для вступления!")
            return
        
        groups_to_process = self.groups_to_join[:max_groups] if max_groups else self.groups_to_join
        
        logger.info(f"🚀 Начинаю вступление в {len(groups_to_process)} групп...")
        logger.info("=" * 80)
        
        joined_count = 0
        already_member_count = 0
        failed_count = 0
        
        for idx, group in enumerate(groups_to_process, 1):
            username = group['username']
            title = group['title']
            members_count = group['members_count']
            entity = group.get('entity')
            
            if not entity:
                logger.warning(f"[{idx}/{len(groups_to_process)}] {username}: нет entity, пропускаю")
                continue
            
            logger.info(f"\n[{idx}/{len(groups_to_process)}] {username} ({members_count} участников)")
            logger.info(f"  📝 {title}")
            
            # Пробуем вступить через каждый аккаунт, который не является участником
            group_success = False
            for account_name, status_info in group['accounts_status'].items():
                if status_info.get('status') == 'not_member':
                    client = self.clients.get(account_name)
                    if not client:
                        logger.warning(f"    ⚠️ Клиент {account_name} не найден")
                        continue
                    
                    success, error = await self.join_group(client, account_name, username, entity)
                    
                    if success:
                        group_success = True
                        joined_count += 1
                        logger.info(f"    ✅ Успешно: {account_name}")
                        break  # Достаточно одного успешного вступления
                    elif error:
                        logger.warning(f"    ❌ {account_name}: {error}")
                    
                    # Задержка между попытками разных аккаунтов
                    await asyncio.sleep(2)
                elif status_info.get('status') == 'member_can_post':
                    logger.info(f"    ✅ {account_name} уже участник с правом постинга")
                    group_success = True
                    already_member_count += 1
                    break
            
            if not group_success:
                failed_count += 1
            
            # Задержка между группами (важно для избежания FloodWait)
            if idx < len(groups_to_process):
                delay = 10 if idx % 5 == 0 else 5  # Каждые 5 групп - большая задержка
                logger.debug(f"  ⏳ Пауза {delay} секунд перед следующей группой...")
                await asyncio.sleep(delay)
        
        logger.info("\n" + "=" * 80)
        logger.info("📊 ИТОГИ:")
        logger.info(f"  ✅ Успешно вступили: {joined_count}")
        logger.info(f"  ✅ Уже были участниками: {already_member_count}")
        logger.info(f"  ❌ Не удалось вступить: {failed_count}")
        logger.info(f"  📋 Всего обработано: {len(groups_to_process)}")
        logger.info("=" * 80)
    
    def generate_report(self) -> str:
        """Генерация отчета"""
        report_lines = [
            "=" * 80,
            "📊 ОТЧЕТ О ПРОВЕРКЕ И ВСТУПЛЕНИИ В ТОП ГРУППЫ LEXUS",
            f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Минимальное количество участников: {self.min_members}",
            "=" * 80,
            "",
            f"📈 Всего групп проверено: {len(self.results)}",
            f"🎯 Топ групп для вступления (≥{self.min_members} участников): {len(self.groups_to_join)}",
            "",
        ]
        
        if self.groups_to_join:
            report_lines.extend([
                "ТОП-20 ГРУПП ПО КОЛИЧЕСТВУ УЧАСТНИКОВ:",
                "",
            ])
            
            for i, group in enumerate(self.groups_to_join[:20], 1):
                report_lines.append(f"{i:2}. {group['username']:30} - {group['members_count']:>6} участников")
                report_lines.append(f"    {group['title'][:60]}")
                
                # Статус аккаунтов
                for account_name, status_info in group['accounts_status'].items():
                    status = status_info.get('status', 'unknown')
                    error = status_info.get('error')
                    emoji = {
                        'member_can_post': '✅',
                        'member_cannot_post': '⚠️',
                        'not_member': '❌',
                        'banned': '🚫',
                        'error': '❓'
                    }.get(status, '❓')
                    report_lines.append(f"      {emoji} {account_name}: {status}" + (f" ({error})" if error else ""))
                report_lines.append("")
        
        report_lines.append("=" * 80)
        
        return "\n".join(report_lines)


async def main():
    """Основная функция"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Проверка и вступление в топ группы Lexus')
    parser.add_argument('--min-members', type=int, default=1000, help='Минимальное количество участников (по умолчанию: 1000)')
    parser.add_argument('--check-only', action='store_true', help='Только проверить группы, не вступать')
    parser.add_argument('--max-join', type=int, help='Максимальное количество групп для вступления')
    parser.add_argument('--limit-check', type=int, help='Ограничить количество проверяемых групп (для теста)')
    args = parser.parse_args()
    
    joiner = LexusTopGroupsJoiner(min_members=args.min_members)
    
    try:
        await joiner.initialize_clients()
        
        # Проверяем все группы (или ограниченное количество для теста)
        await joiner.check_all_groups_info(limit=args.limit_check)
        
        # Фильтруем топ группы
        joiner.filter_top_groups()
        
        # Генерируем и сохраняем отчет
        report = joiner.generate_report()
        print("\n" + report)
        
        report_file = log_dir / f'lexus_top_groups_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.md'
        report_file.write_text(report, encoding='utf-8')
        logger.info(f"📄 Отчет сохранен в {report_file}")
        
        # Если не только проверка - вступаем в группы
        if not args.check_only:
            max_groups = args.max_join if args.max_join else None
            await joiner.join_top_groups(max_groups=max_groups)
        
    except KeyboardInterrupt:
        logger.info("⚠️ Прервано пользователем")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}", exc_info=True)
    finally:
        # Закрываем клиенты
        for client in joiner.clients.values():
            if client.is_connected():
                await client.disconnect()


if __name__ == '__main__':
    asyncio.run(main())
