#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ежедневная постепенная проверка групп Lexus (10-20 групп в день)
Избегает FloodWait, сохраняет прогресс, позволяет продолжить позже
"""

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime

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
        logging.FileHandler(log_dir / 'daily_lexus_check.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Файлы для сохранения прогресса
PROGRESS_FILE = log_dir / 'lexus_groups_check_progress.json'
RESULTS_FILE = log_dir / 'lexus_groups_check_results.json'


class DailyLexusGroupsChecker:
    """Класс для ежедневной проверки групп Lexus"""
    
    def __init__(self, groups_per_day: int = 15, min_members: int = 500):
        """
        Args:
            groups_per_day: Количество групп для проверки за один запуск
            min_members: Минимальное количество участников для включения в топ
        """
        self.groups_per_day = groups_per_day
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
        
        self.clients: Dict[str, TelegramClient] = {}
        
        # Загружаем прогресс
        self.progress = self.load_progress()
        self.results = self.load_results()
        
        # Все группы для проверки
        self.all_groups = self.load_all_groups()
    
    def load_all_groups(self) -> List[str]:
        """Загрузка всех групп Lexus из group_niches.json"""
        group_niches_path = Path('group_niches.json')
        
        if not group_niches_path.exists():
            logger.error("❌ Файл group_niches.json не найден!")
            return []
        
        with open(group_niches_path, 'r', encoding='utf-8') as f:
            group_niches = json.load(f)
        
        # Фильтруем группы с niche='ukraine_cars'
        ukraine_cars_groups = [
            target for target, niche in group_niches.items()
            if niche == 'ukraine_cars'
        ]
        
        logger.info(f"📋 Загружено {len(ukraine_cars_groups)} групп с niche='ukraine_cars'")
        return ukraine_cars_groups
    
    def load_progress(self) -> Dict:
        """Загрузка прогресса проверки"""
        if PROGRESS_FILE.exists():
            try:
                with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                    progress = json.load(f)
                logger.info(f"📂 Загружен прогресс: проверено {progress.get('checked_count', 0)}/{progress.get('total_count', 0)} групп")
                return progress
            except Exception as e:
                logger.warning(f"⚠️ Не удалось загрузить прогресс: {e}")
        
        return {
            'checked_groups': [],
            'checked_count': 0,
            'total_count': 0,
            'last_check_date': None,
            'flood_wait_groups': []  # Группы с FloodWait
        }
    
    def save_progress(self):
        """Сохранение прогресса"""
        self.progress['checked_count'] = len(self.progress['checked_groups'])
        self.progress['total_count'] = len(self.all_groups)
        self.progress['last_check_date'] = datetime.now().isoformat()
        
        try:
            with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.progress, f, indent=2, ensure_ascii=False)
            logger.debug(f"💾 Прогресс сохранен: {self.progress['checked_count']}/{self.progress['total_count']} групп")
        except Exception as e:
            logger.error(f"❌ Не удалось сохранить прогресс: {e}")
    
    def load_results(self) -> Dict:
        """Загрузка результатов проверки"""
        if RESULTS_FILE.exists():
            try:
                with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
                    results = json.load(f)
                logger.info(f"📂 Загружены результаты: {len(results)} групп")
                return results
            except Exception as e:
                logger.warning(f"⚠️ Не удалось загрузить результаты: {e}")
        
        return {}
    
    def save_results(self):
        """Сохранение результатов"""
        try:
            with open(RESULTS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.results, f, indent=2, ensure_ascii=False)
            logger.debug(f"💾 Результаты сохранены: {len(self.results)} групп")
        except Exception as e:
            logger.error(f"❌ Не удалось сохранить результаты: {e}")
    
    def get_groups_to_check(self) -> List[str]:
        """Получение групп для проверки (еще не проверенные)"""
        checked = set(self.progress.get('checked_groups', []))
        flood_wait = set(self.progress.get('flood_wait_groups', []))
        
        # Берем только непроверенные группы и не находящиеся в FloodWait
        to_check = [
            group for group in self.all_groups
            if group not in checked and group not in flood_wait
        ]
        
        # Ограничиваем количеством групп на день
        groups_to_check = to_check[:self.groups_per_day]
        
        logger.info(f"📋 Групп для проверки: {len(groups_to_check)}/{len(to_check)} (всего: {len(self.all_groups)})")
        logger.info(f"   ✅ Уже проверено: {len(checked)}")
        logger.info(f"   ⏳ В FloodWait: {len(flood_wait)}")
        logger.info(f"   📝 Осталось проверить: {len(to_check)}")
        
        return groups_to_check
    
    async def initialize_clients(self):
        """Инициализация клиентов Telegram"""
        logger.info("🔄 Инициализация клиентов...")
        await self.system.initialize_clients()
        self.clients = self.system.clients
        logger.info(f"✅ Инициализировано {len(self.clients)} клиентов")
    
    async def get_group_info(self, client: TelegramClient, username: str) -> Optional[Dict]:
        """Получение информации о группе"""
        try:
            # Проверяем подключение клиента перед запросами
            if not client.is_connected():
                logger.warning(f"⚠️ Client is disconnected, cannot get info for {username}")
                return {'title': username, 'members_count': 0, 'found': False, 'error': 'disconnected'}
            
            entity = await client.get_entity(username)
            
            # Получаем полную информацию
            try:
                if hasattr(entity, 'broadcast') and entity.broadcast:
                    full_info = await client(GetFullChannelRequest(entity))
                    members_count = getattr(full_info.full_chat, 'participants_count', 0)
                else:
                    if hasattr(entity, 'chat_id'):
                        full_info = await client(GetFullChatRequest(entity.chat_id))
                        members_count = getattr(full_info.full_chat, 'participants_count', 0)
                    else:
                        members_count = getattr(entity, 'participants_count', 0)
            except Exception:
                members_count = getattr(entity, 'participants_count', 0)
            
            title = getattr(entity, 'title', username)
            
            return {
                'title': title,
                'members_count': members_count or 0,
                'entity': None,  # Не сохраняем entity в JSON
                'found': True
            }
        except UsernameNotOccupiedError:
            return {'title': username, 'members_count': 0, 'found': False, 'error': 'not_found'}
        except ChannelPrivateError:
            return {'title': username, 'members_count': 0, 'found': False, 'error': 'private'}
        except FloodWaitError as e:
            # Добавляем группу в FloodWait список
            if username not in self.progress.get('flood_wait_groups', []):
                self.progress.setdefault('flood_wait_groups', []).append(username)
            return {'title': username, 'members_count': 0, 'found': False, 'error': f'flood_wait_{e.seconds}'}
        except Exception as e:
            error_str = str(e).lower()
            if 'wait' in error_str and 'required' in error_str:
                # FloodWait в другом формате
                if username not in self.progress.get('flood_wait_groups', []):
                    self.progress.setdefault('flood_wait_groups', []).append(username)
                return {'title': username, 'members_count': 0, 'found': False, 'error': 'flood_wait'}
            return {'title': username, 'members_count': 0, 'found': False, 'error': str(e)[:100]}
    
    async def check_membership_and_permissions(self, client: TelegramClient, account_name: str, username: str, entity) -> Tuple[str, Optional[str]]:
        """Проверка участия и прав на постинг"""
        try:
            # Проверяем подключение клиента перед запросами
            if not client.is_connected():
                logger.warning(f"    ⚠️ Client {account_name} is disconnected, cannot check {username}")
                return ('error', 'Client disconnected')
            
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
                return ('member_can_post', None)
            else:
                return ('member_cannot_post', 'Нет прав на постинг')
                
        except UserBannedInChannelError:
            return ('banned', 'Аккаунт забанен в группе')
        except ChatWriteForbiddenError:
            return ('member_cannot_post', 'Запрещено писать в группе')
        except FloodWaitError as e:
            wait_seconds = e.seconds
            wait_minutes = wait_seconds // 60
            return ('flood_wait', f'FloodWait {wait_minutes}м')
        except RPCError as e:
            error_msg = str(e)
            if "disconnected" in error_msg.lower() or "not connected" in error_msg.lower() or "Cannot send requests" in error_msg:
                return ('error', 'Client disconnected')
            error_str = error_msg.lower()
            if 'not a member' in error_str or 'participant' in error_str:
                return ('not_member', 'Аккаунт не является участником группы')
            elif 'private' in error_str:
                return ('private', 'Группа приватная')
            else:
                return ('error', f'RPC Error: {error_msg[:100]}')
        except Exception as e:
            error_msg = str(e)
            if "disconnected" in error_msg.lower() or "not connected" in error_msg.lower() or "Cannot send requests" in error_msg:
                return ('error', 'Client disconnected')
            error_str = error_msg.lower()
            if 'not a member' in error_str or 'participant' in error_str:
                return ('not_member', 'Аккаунт не является участником группы')
            elif 'private' in error_str:
                return ('private', 'Группа приватная')
            else:
                return ('error', f'Ошибка: {error_msg[:100]}')
    
    async def check_groups(self):
        """Проверка групп"""
        groups_to_check = self.get_groups_to_check()
        
        if not groups_to_check:
            logger.info("✅ Все группы уже проверены!")
            return
        
        logger.info(f"🔍 Начинаю проверку {len(groups_to_check)} групп...")
        logger.info(f"🎯 Минимальное количество участников: {self.min_members}")
        logger.info("=" * 80)
        
        # Используем первый доступный клиент для получения информации
        if not self.clients:
            logger.error("❌ Нет доступных клиентов!")
            return
        
        first_client = next(iter(self.clients.values()))
        
        checked_count = 0
        top_groups_count = 0
        
        for idx, username in enumerate(groups_to_check, 1):
            logger.info(f"\n[{idx}/{len(groups_to_check)}] Проверяю {username}...")
            
            # Получаем информацию о группе
            group_info = await self.get_group_info(first_client, username)
            
            if not group_info:
                logger.warning(f"  ⚠️ Не удалось получить информацию о {username}")
                self.progress['checked_groups'].append(username)
                checked_count += 1
                await asyncio.sleep(2)  # Задержка между запросами
                continue
            
            error = group_info.get('error')
            if error:
                if error.startswith('flood_wait'):
                    logger.warning(f"  ⏳ FloodWait для {username}, пропускаю")
                    # Уже добавлено в flood_wait_groups в get_group_info
                elif error == 'not_found':
                    logger.warning(f"  🔍 Группа {username} не найдена")
                elif error == 'private':
                    logger.warning(f"  🔒 Группа {username} приватная")
                else:
                    logger.warning(f"  ⚠️ Ошибка для {username}: {error}")
                
                self.results[username] = group_info
                self.progress['checked_groups'].append(username)
                checked_count += 1
                await asyncio.sleep(3)  # Задержка при ошибках
                continue
            
            # Группа найдена - проверяем участие аккаунтов
            members_count = group_info.get('members_count', 0)
            title = group_info.get('title', username)
            
            logger.info(f"  📊 {title} - {members_count} участников")
            
            # Получаем entity для проверки участия
            try:
                entity = await first_client.get_entity(username)
            except Exception as e:
                logger.warning(f"  ⚠️ Не удалось получить entity для {username}: {e}")
                self.results[username] = group_info
                self.progress['checked_groups'].append(username)
                checked_count += 1
                await asyncio.sleep(2)
                continue
            
            # Проверяем участие всех аккаунтов
            accounts_status = {}
            for account_name, client in self.clients.items():
                try:
                    status, error = await self.check_membership_and_permissions(client, account_name, username, entity)
                    accounts_status[account_name] = {'status': status, 'error': error}
                    
                    status_emoji = {
                        'member_can_post': '✅',
                        'member_cannot_post': '⚠️',
                        'not_member': '❌',
                        'banned': '🚫',
                        'private': '🔒',
                        'error': '❓'
                    }.get(status, '❓')
                    
                    logger.info(f"    {status_emoji} {account_name}: {status}" + (f" ({error})" if error else ""))
                    
                    await asyncio.sleep(0.5)  # Задержка между аккаунтами
                except Exception as e:
                    logger.warning(f"    ⚠️ Ошибка при проверке {account_name} в {username}: {e}")
                    accounts_status[account_name] = {'status': 'error', 'error': str(e)[:100]}
            
            # Сохраняем результат
            group_info['accounts_status'] = accounts_status
            self.results[username] = group_info
            
            # Проверяем, попадает ли группа в топ
            if members_count >= self.min_members:
                top_groups_count += 1
                logger.info(f"  🎯 ТОП ГРУППА! (≥{self.min_members} участников)")
            
            # Отмечаем группу как проверенную
            self.progress['checked_groups'].append(username)
            checked_count += 1
            
            # Периодически сохраняем прогресс (каждые 5 групп)
            if checked_count % 5 == 0:
                self.save_progress()
                self.save_results()
                logger.debug(f"  💾 Промежуточное сохранение: {checked_count} групп проверено")
            
            # Задержка между группами (важно для избежания FloodWait)
            delay = 8 if idx % 3 == 0 else 5  # Каждые 3 группы - большая задержка
            if idx < len(groups_to_check):
                await asyncio.sleep(delay)
        
        # Финальное сохранение
        self.save_progress()
        self.save_results()
        
        logger.info("\n" + "=" * 80)
        logger.info("📊 ИТОГИ ПРОВЕРКИ:")
        logger.info(f"  ✅ Проверено групп: {checked_count}")
        logger.info(f"  🎯 Топ групп (≥{self.min_members} участников): {top_groups_count}")
        logger.info(f"  📋 Всего проверено: {len(self.progress['checked_groups'])}/{len(self.all_groups)}")
        logger.info(f"  ⏳ В FloodWait: {len(self.progress.get('flood_wait_groups', []))}")
        logger.info("=" * 80)
    
    def generate_daily_report(self) -> str:
        """Генерация ежедневного отчета"""
        report_lines = [
            "=" * 80,
            f"📊 ЕЖЕДНЕВНЫЙ ОТЧЕТ О ПРОВЕРКЕ ГРУПП LEXUS",
            f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Минимальное количество участников: {self.min_members}",
            "=" * 80,
            "",
            f"📈 Прогресс: {len(self.progress['checked_groups'])}/{len(self.all_groups)} групп проверено",
            f"⏳ В FloodWait: {len(self.progress.get('flood_wait_groups', []))} групп",
            "",
        ]
        
        # Топ группы из последних результатов
        top_groups = []
        for username, info in self.results.items():
            members_count = info.get('members_count', 0)
            if members_count >= self.min_members and info.get('found', False):
                accounts_status = info.get('accounts_status', {})
                top_groups.append({
                    'username': username,
                    'title': info.get('title', username),
                    'members_count': members_count,
                    'accounts_status': accounts_status
                })
        
        if top_groups:
            top_groups.sort(key=lambda x: x['members_count'], reverse=True)
            report_lines.extend([
                f"🏆 ТОП ГРУППЫ (≥{self.min_members} участников) из проверенных сегодня:",
                "",
            ])
            
            for i, group in enumerate(top_groups[:10], 1):
                report_lines.append(f"{i:2}. {group['username']:30} - {group['members_count']:>6} участников")
                report_lines.append(f"    {group['title'][:60]}")
                
                for account_name, status_info in group['accounts_status'].items():
                    status = status_info.get('status', 'unknown')
                    error = status_info.get('error')
                    emoji = {
                        'member_can_post': '✅',
                        'member_cannot_post': '⚠️',
                        'not_member': '❌',
                        'banned': '🚫',
                        'private': '🔒',
                        'error': '❓'
                    }.get(status, '❓')
                    report_lines.append(f"      {emoji} {account_name}: {status}" + (f" ({error})" if error else ""))
                report_lines.append("")
        
        report_lines.append("=" * 80)
        
        return "\n".join(report_lines)


async def main():
    """Основная функция"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Ежедневная проверка групп Lexus')
    parser.add_argument('--groups-per-day', type=int, default=15, help='Количество групп для проверки за один запуск (по умолчанию: 15)')
    parser.add_argument('--min-members', type=int, default=500, help='Минимальное количество участников для включения в топ (по умолчанию: 500)')
    parser.add_argument('--check-only', action='store_true', help='Только проверить группы, не вступать')
    args = parser.parse_args()
    
    checker = DailyLexusGroupsChecker(
        groups_per_day=args.groups_per_day,
        min_members=args.min_members
    )
    
    try:
        await checker.initialize_clients()
        
        # Проверяем группы
        await checker.check_groups()
        
        # Генерируем и сохраняем отчет
        report = checker.generate_daily_report()
        print("\n" + report)
        
        report_file = log_dir / f'daily_lexus_report_{datetime.now().strftime("%Y%m%d")}.md'
        report_file.write_text(report, encoding='utf-8')
        logger.info(f"📄 Отчет сохранен в {report_file}")
        
        logger.info(f"\n💡 Для продолжения проверки запустите скрипт снова завтра (или позже)")
        logger.info(f"   Прогресс сохранен в: {PROGRESS_FILE}")
        logger.info(f"   Результаты сохранены в: {RESULTS_FILE}")
        
    except KeyboardInterrupt:
        logger.info("⚠️ Прервано пользователем")
        checker.save_progress()
        checker.save_results()
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}", exc_info=True)
        checker.save_progress()
        checker.save_results()
    finally:
        # Закрываем клиенты
        for client in checker.clients.values():
            if client.is_connected():
                await client.disconnect()


if __name__ == '__main__':
    asyncio.run(main())
