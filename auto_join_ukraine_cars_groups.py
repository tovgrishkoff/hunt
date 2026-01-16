#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Автоматический поиск и вступление в украинские группы по продаже авто
Проверяет, можно ли постить в группе перед вступлением
"""

import asyncio
import json
import logging
import random
import sys
from pathlib import Path
from datetime import datetime
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    FloodWaitError, 
    UserAlreadyParticipantError,
    InviteHashExpiredError,
    UsernameNotOccupiedError,
    ChatAdminRequiredError,
    RPCError
)
from telethon.tl.functions.messages import CheckChatInviteRequest, ImportChatInviteRequest
from telethon.tl.functions.channels import JoinChannelRequest, GetFullChannelRequest
from telethon.tl.functions.contacts import SearchRequest
from telethon.tl.types import ChatInvite

sys.path.insert(0, '.')

from promotion_system import PromotionSystem

ADMIN_ID = 210147380

def setup_logging():
    """Настройка логирования"""
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    
    log_file = log_dir / 'auto_join_ukraine_cars.log'
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    return logging.getLogger(__name__)

async def check_can_post_in_group(client, entity):
    """Проверка, можно ли постить в группе"""
    try:
        # Пробуем получить права текущего пользователя
        me = await client.get_me()
        try:
            permissions = await client.get_permissions(entity, me)
            if permissions:
                # Проверяем право на отправку сообщений
                if hasattr(permissions, 'send_messages'):
                    return permissions.send_messages
                # Если нет атрибута, проверяем через banned_rights
                if hasattr(permissions, 'banned_rights') and permissions.banned_rights:
                    if hasattr(permissions.banned_rights, 'send_messages'):
                        return not permissions.banned_rights.send_messages
        except:
            pass
        
        # Если не можем проверить права до вступления, проверяем через full_chat
        try:
            if hasattr(entity, 'id'):
                full_info = await client(GetFullChannelRequest(entity))
                if hasattr(full_info, 'full_chat'):
                    # Для супергрупп проверяем default_banned_rights
                    if hasattr(full_info.full_chat, 'default_banned_rights'):
                        banned_rights = full_info.full_chat.default_banned_rights
                        if banned_rights and hasattr(banned_rights, 'send_messages'):
                            return not banned_rights.send_messages
                    # Если нет ограничений, считаем что можно
                    return True
        except:
            pass
        
        # Если не можем проверить, считаем что можно (проверим после вступления)
        return True
    except Exception as e:
        # Если не можем проверить, считаем что можно (проверим после вступления)
        return True

async def join_group_with_check(client, account_name, group_info, logger):
    """Вступление в группу с проверкой возможности постить"""
    group_link = group_info.get('username', '')
    if not group_link:
        return False
    
    # Формируем username
    if not group_link.startswith('@'):
        username = f"@{group_link}"
    else:
        username = group_link
    
    logger.info(f"  Проверяю группу {username}...")
    
    try:
        # Пробуем получить информацию о группе
        entity = await client.get_entity(username)
        
        # Проверяем, можно ли постить
        can_post = await check_can_post_in_group(client, entity)
        
        if not can_post:
            logger.warning(f"  ⚠️ В группе {username} нельзя постить - пропускаем")
            return False
        
        # Проверяем, не участник ли уже
        is_already_member = False
        try:
            await client.get_participants(entity, limit=1)
            logger.info(f"  ℹ️ Уже участник {username}")
            is_already_member = True
            # Проверяем права постинга для уже участника
            can_post = await check_can_post_in_group(client, entity)
            if not can_post:
                logger.warning(f"  ⚠️ Уже участник, но нельзя постить в {username}")
                return False
            # Если уже участник и можно постить - сохраняем привязку и возвращаемся
            try:
                from promotion_system import PromotionSystem
                from datetime import datetime
                system = PromotionSystem()
                system.load_group_assignments()
                # Если группы еще нет в assignments - добавляем
                if not system.is_group_assigned(username):
                    system.assign_account_to_group(username, account_name, datetime.utcnow())
                    logger.info(f"  🔗 Назначен аккаунт {account_name} для группы {username} (уже был участником)")
            except Exception as e:
                logger.warning(f"  ⚠️ Ошибка при сохранении привязки для уже участника: {e}")
            return True
        except:
            pass
        
        # Вступаем в группу
        await client(JoinChannelRequest(username))
        logger.info(f"  ✅ Вступил в группу {username}")
        
        # Дополнительная проверка после вступления
        can_send = False  # Инициализируем переменную
        try:
            me = await client.get_me()
            permissions = await client.get_permissions(entity, me)
            if permissions:
                can_send = False
                if hasattr(permissions, 'send_messages'):
                    can_send = permissions.send_messages
                elif hasattr(permissions, 'banned_rights') and permissions.banned_rights:
                    if hasattr(permissions.banned_rights, 'send_messages'):
                        can_send = not permissions.banned_rights.send_messages
                
                if not can_send:
                    logger.warning(f"  ⚠️ После вступления: нельзя постить в {username} - покидаем группу")
                    try:
                        await client.delete_dialog(entity)
                    except:
                        pass
                    return False
                else:
                    logger.info(f"  ✅ Подтверждено: можно постить в {username}")
                    can_send = True  # Группа доступна для постинга
        except Exception as e:
            logger.warning(f"  ⚠️ Не удалось проверить права после вступления: {e}")
            # Если не можем проверить, оставляем группу (может быть можно постить)
            can_send = True  # Оптимистично предполагаем, что можно постить
        
        # Если можно постить - сохраняем привязку аккаунта к группе
        if can_send:
            try:
                from promotion_system import PromotionSystem
                from datetime import datetime
                system = PromotionSystem()
                system.load_group_assignments()
                # Назначаем аккаунт группе с текущим временем (warm-up 24 часа)
                system.assign_account_to_group(username, account_name, datetime.utcnow())
                logger.info(f"  🔗 Назначен аккаунт {account_name} для группы {username} (warm-up 24 часа)")
            except Exception as e:
                logger.error(f"  ❌ Ошибка при сохранении привязки аккаунта: {e}")
                # Не прерываем процесс, продолжаем работу
        
        return True
        
    except UserAlreadyParticipantError:
        logger.info(f"  ℹ️ Уже участник {username}")
        return True
    except UsernameNotOccupiedError:
        logger.warning(f"  ⚠️ Группа {username} не найдена")
        return False
    except FloodWaitError as e:
        wait_seconds = e.seconds
        wait_minutes = wait_seconds // 60
        logger.warning(f"  ⚠️ FloodWait: {wait_seconds} секунд ({wait_minutes} минут)")
        return ("FLOOD_WAIT", wait_seconds)
    except ChatAdminRequiredError:
        logger.warning(f"  ⚠️ Нет доступа к группе {username}")
        return False
    except RPCError as e:
        error_msg = str(e)
        if "CAPTCHA" in error_msg or "капча" in error_msg.lower():
            logger.warning(f"  🔐 Требуется капча для {username}")
            return False
        logger.error(f"  ❌ Ошибка RPC: {e}")
        return False
    except Exception as e:
        logger.error(f"  ❌ Неожиданная ошибка для {username}: {e}")
        return False

async def search_and_join_groups():
    """Поиск новых групп и вступление в них"""
    logger = setup_logging()
    
    logger.info("=" * 80)
    logger.info("🔍 АВТОМАТИЧЕСКИЙ ПОИСК И ВСТУПЛЕНИЕ В УКРАИНСКИЕ ГРУППЫ ПО АВТО")
    logger.info("=" * 80)
    
    system = PromotionSystem()
    system.load_accounts()
    
    # Загружаем конфиг Lexus ДО инициализации клиентов, чтобы отфильтровать аккаунты
    system.load_lexus_accounts_config()
    
    # Фильтруем аккаунты: оставляем только те, что в whitelist Lexus
    if hasattr(system, 'lexus_allowed_accounts') and system.lexus_allowed_accounts:
        original_count = len(system.accounts)
        original_names = [acc.get('session_name') for acc in system.accounts]
        system.accounts = [
            acc for acc in system.accounts
            if acc.get('session_name') in system.lexus_allowed_accounts
        ]
        filtered_names = [acc.get('session_name') for acc in system.accounts]
        logger.info(f"✅ Filtered accounts for Lexus: {len(system.accounts)}/{original_count} accounts")
        logger.info(f"   Whitelist: {sorted(system.lexus_allowed_accounts)}")
        logger.info(f"   Before: {sorted(original_names)}")
        logger.info(f"   After: {sorted(filtered_names)}")
    else:
        logger.warning(f"⚠️ No Lexus whitelist found, using all {len(system.accounts)} accounts")
    
    # Загружаем group_assignments для подсчета вступлений за день
    system.load_group_assignments()
    
    await system.initialize_clients()
    
    if not system.clients:
        logger.error("❌ Нет доступных клиентов!")
        return
    
    # Используем первый доступный клиент для поиска
    client_name = list(system.clients.keys())[0]
    client = system.clients[client_name]
    
    logger.info(f"👤 Используем аккаунт для поиска: {client_name}")
    
    # Ключевые слова для поиска
    search_keywords = [
        # Авто-группы (расширенный список)
        'україна авто', 'авто продажа україна', 'купить авто україна',
        'авторынок украина', 'автобазар украина', 'автомобили украина',
        'авто киев', 'авто продажа киев', 'авторынок киев',
        'авто львов', 'авто одесса', 'авто харьков',
        'авто днепр', 'авто запорожье', 'авто николаев',
        'авто продажа', 'продам авто', 'куплю авто',
        'автомобили киев', 'автомобили украина', 'машины украина',
        'авто б у', 'авто бу украина', 'б у авто',
        'автосалон украина', 'автодилер украина', 'автосалон киев',
        'ukraine cars', 'ukraine auto', 'kyiv cars',
        'cars ukraine', 'auto ukraine', 'car sale ukraine',
        # Барахолки и частные объявления
        'барахолка украина', 'барахолка киев', 'барахолка україна',
        'частные объявления украина', 'частні оголошення україна',
        'объявления киев', 'оголошення київ', 'объявления украина',
        'продажа киев', 'продаж київ', 'купля продаж украина',
        'частные продажи', 'приватні продажі', 'частные объявления',
        'барахолка одесса', 'барахолка львов', 'барахолка харьков',
        'объявления одесса', 'объявления львов', 'объявления харьков',
        'buy sell ukraine', 'classifieds ukraine', 'marketplace ukraine',
        'частный продавец', 'приватний продавець', 'доски объявлений',
        # Барахолки с авто-тематикой
        'барахолка авто', 'барахолка автомобили', 'барахолка машины',
        'авто барахолка', 'автомобили барахолка', 'машины барахолка',
        'объявления авто', 'оголошення авто', 'продажа авто',
        'частные авто', 'приватні авто', 'авто частные'
    ]
    
    found_groups = []
    found_file = Path('logs/found_ukraine_cars_groups.json')
    
    # Загружаем уже найденные группы
    existing_groups = set()
    if found_file.exists():
        try:
            with found_file.open('r') as f:
                existing_data = json.load(f)
                existing_groups = {g.get('username', '') for g in existing_data if g.get('username')}
        except:
            pass
    
    logger.info(f"📋 Уже найдено групп: {len(existing_groups)}")
    
    # Поиск новых групп
    logger.info("🔍 Начинаю поиск новых групп...")
    for keyword in search_keywords:  # Проверяем все ключевые слова
        try:
            logger.info(f"  Ищу по ключевому слову: {keyword}")
            results = await client(SearchRequest(
                q=keyword,
                limit=20
            ))
            
            for chat in results.chats:
                if hasattr(chat, 'username') and chat.username:
                    username = f"@{chat.username}"
                    if username not in existing_groups:
                        found_groups.append({
                            'username': username,
                            'title': getattr(chat, 'title', 'Unknown'),
                            'id': chat.id,
                            'members_count': getattr(chat, 'participants_count', 0),
                            'found_by': keyword
                        })
            
            await asyncio.sleep(2)  # Пауза между поисками
            
        except Exception as e:
            logger.error(f"  ❌ Ошибка при поиске '{keyword}': {e}")
            continue
    
    # Если новых групп нет – пробуем пройтись по уже найденным
    if not found_groups:
        logger.info("  ℹ️ Новых групп не найдено, пробуем пройтись по уже найденным группам")
        if found_file.exists():
            try:
                with found_file.open('r') as f:
                    all_existing = json.load(f)
                # Берем случайную выборку уже найденных групп, чтобы повступать ещё
                random.shuffle(all_existing)
                found_groups = all_existing[:50]  # максимум 50 групп за запуск
                logger.info(f"  📌 Используем {len(found_groups)} уже найденных групп для попытки вступления")
            except:
                logger.info("  ℹ️ Не удалось загрузить найденные группы, выходим")
                return
        else:
            logger.info("  ℹ️ Ранее найденных групп нет, выходим")
            return
    else:
        logger.info(f"✅ Найдено новых групп: {len(found_groups)}")
        
        # Сохраняем найденные группы
        all_groups = []
        if found_file.exists():
            try:
                with found_file.open('r') as f:
                    all_groups = json.load(f)
            except:
                pass
        
        all_groups.extend(found_groups)
        
        with found_file.open('w', encoding='utf-8') as f:
            json.dump(all_groups, f, ensure_ascii=False, indent=2)
        
        logger.info(f"💾 Сохранено {len(found_groups)} новых групп в {found_file}")
    
    # Вступление в найденные группы
    logger.info("")
    logger.info("=" * 80)
    logger.info("🚪 ВСТУПЛЕНИЕ В НАЙДЕННЫЕ ГРУППЫ")
    logger.info("=" * 80)
    
    # Используем все доступные аккаунты
    accounts = system.accounts
    random.shuffle(accounts)
    
    # Максимум вступлений в день на аккаунт
    MAX_JOINS_PER_DAY = 10
    
    # Подсчитываем вступления за сегодня для каждого аккаунта
    today = datetime.utcnow().date()
    account_joins_today = {}
    
    for account_name in [acc.get('session_name') for acc in accounts]:
        account_joins_today[account_name] = 0
        # Подсчитываем вступления за сегодня из group_assignments
        for group, assignment in system.group_assignments.items():
            if assignment.get('account') == account_name:
                joined_at_str = assignment.get('joined_at')
                if joined_at_str:
                    try:
                        joined_at = datetime.fromisoformat(joined_at_str.replace('Z', '+00:00'))
                        if joined_at.date() == today:
                            account_joins_today[account_name] += 1
                    except:
                        pass
    
    logger.info(f"📊 Вступлений сегодня по аккаунтам:")
    for account_name, joins_count in account_joins_today.items():
        logger.info(f"   {account_name}: {joins_count}/{MAX_JOINS_PER_DAY}")
    
    joined_count = 0
    failed_count = 0
    skipped_limit_count = 0
    
    for group_info in found_groups:
        username = group_info.get('username', '')
        if not username:
            continue
        
        # Проверяем, не назначена ли уже группа аккаунту
        if username in system.group_assignments:
            assigned_account = system.group_assignments[username].get('account')
            if assigned_account:
                logger.debug(f"  {username}: уже назначена аккаунту {assigned_account}, пропускаем")
                continue
        
        # Выбираем аккаунт с наименьшим количеством вступлений сегодня
        available_accounts = [
            acc for acc in accounts
            if acc.get('session_name') in system.clients and 
            account_joins_today.get(acc.get('session_name'), 0) < MAX_JOINS_PER_DAY
        ]
        
        if not available_accounts:
            logger.warning(f"  ⚠️ Все аккаунты достигли лимита {MAX_JOINS_PER_DAY} вступлений сегодня, пропускаем оставшиеся группы")
            skipped_limit_count = len(found_groups) - found_groups.index(group_info)
            break
        
        # Выбираем аккаунт с наименьшим количеством вступлений
        account = min(available_accounts, key=lambda acc: account_joins_today.get(acc.get('session_name'), 0))
        account_name = account['session_name']
        
        client = system.clients[account_name]
        
        logger.info(f"\n[{found_groups.index(group_info) + 1}/{len(found_groups)}] {username}")
        logger.info(f"  Используем аккаунт: {account_name} (вступлений сегодня: {account_joins_today[account_name]}/{MAX_JOINS_PER_DAY})")
        
        result = await join_group_with_check(client, account_name, group_info, logger)
        
        if result is True:
            joined_count += 1
            # Увеличиваем счетчик вступлений для аккаунта
            account_joins_today[account_name] = account_joins_today.get(account_name, 0) + 1
            logger.info(f"  ✅ Успешно вступили (вступлений сегодня: {account_joins_today[account_name]}/{MAX_JOINS_PER_DAY})")
        elif result is False:
            failed_count += 1
        elif isinstance(result, tuple) and result[0] == "FLOOD_WAIT":
            wait_seconds = result[1]
            logger.warning(f"  ⏳ FloodWait {wait_seconds} секунд - пропускаем эту группу")
            failed_count += 1
        
        # Пауза между вступлениями
        await asyncio.sleep(random.randint(30, 60))
    
    logger.info("")
    logger.info("=" * 80)
    logger.info(f"✅ ЗАВЕРШЕНО: Вступили в {joined_count} групп, неудачно: {failed_count}")
    if skipped_limit_count > 0:
        logger.info(f"   Пропущено из-за лимита: {skipped_limit_count} групп")
    logger.info("=" * 80)
    
    logger.info(f"📊 Итоговое количество вступлений сегодня по аккаунтам:")
    for account_name, joins_count in account_joins_today.items():
        logger.info(f"   {account_name}: {joins_count}/{MAX_JOINS_PER_DAY}")
    
    # Автоматически добавляем найденные группы в рассылку
    logger.info("")
    logger.info("📝 Добавляю найденные группы в targets.txt и group_niches.json...")
    try:
        import subprocess
        result = subprocess.run(
            ['python3', 'add_ukraine_cars_groups_to_targets.py'],
            capture_output=True,
            text=True,
            timeout=300
        )
        if result.returncode == 0:
            logger.info("✅ Группы успешно добавлены в рассылку")
        else:
            logger.warning(f"⚠️ Ошибка при добавлении групп: {result.stderr}")
    except Exception as e:
        logger.error(f"❌ Ошибка при запуске add_ukraine_cars_groups_to_targets.py: {e}")

if __name__ == "__main__":
    asyncio.run(search_and_join_groups())

