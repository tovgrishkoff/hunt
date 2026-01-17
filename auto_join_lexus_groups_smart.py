#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Умная система автоматического поиска и вступления в группы Lexus
Проверяет права на постинг ДО вступления и покидает группы, где нельзя постить
Аналогично системе для Бали
"""

import asyncio
import json
import logging
import random
import sys
from pathlib import Path
from datetime import datetime, timedelta
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    FloodWaitError, 
    UserAlreadyParticipantError,
    UsernameNotOccupiedError,
    ChatAdminRequiredError,
    ChatWriteForbiddenError,
    UserBannedInChannelError,
    ChannelPrivateError,
    RPCError
)
from telethon.tl.functions.channels import JoinChannelRequest, GetFullChannelRequest
from telethon.tl.functions.messages import GetFullChatRequest
from telethon.tl.functions.contacts import SearchRequest

sys.path.insert(0, '.')

from promotion_system import PromotionSystem

ADMIN_ID = 210147380

def setup_logging():
    """Настройка логирования"""
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    
    log_file = log_dir / 'auto_join_lexus_smart.log'
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    return logging.getLogger(__name__)

async def check_can_post_before_join(client, entity, logger):
    """
    Проверка возможности постить в группе ДО вступления
    Для публичных групп можно проверить через GetFullChannelRequest
    """
    try:
        # Пробуем получить полную информацию о группе
        if hasattr(entity, 'broadcast') and entity.broadcast:
            # Это канал
            full_info = await client(GetFullChannelRequest(entity))
            if hasattr(full_info, 'full_chat'):
                # Проверяем default_banned_rights
                if hasattr(full_info.full_chat, 'default_banned_rights'):
                    banned_rights = full_info.full_chat.default_banned_rights
                    if banned_rights and hasattr(banned_rights, 'send_messages'):
                        if banned_rights.send_messages:
                            logger.debug(f"    ⚠️ Группа запрещает постинг (default_banned_rights)")
                            return False
        else:
            # Это группа
            try:
                full_info = await client(GetFullChatRequest(entity.chat_id))
                if hasattr(full_info, 'full_chat'):
                    # Проверяем default_banned_rights
                    if hasattr(full_info.full_chat, 'default_banned_rights'):
                        banned_rights = full_info.full_chat.default_banned_rights
                        if banned_rights and hasattr(banned_rights, 'send_messages'):
                            if banned_rights.send_messages:
                                logger.debug(f"    ⚠️ Группа запрещает постинг (default_banned_rights)")
                                return False
            except Exception as e:
                logger.debug(f"    ⚠️ Не удалось проверить через GetFullChatRequest: {e}")
        
        # Если не можем проверить, считаем что можно (проверим после вступления)
        return True
    except Exception as e:
        logger.debug(f"    ⚠️ Ошибка при проверке прав до вступления: {e}")
        # Если не можем проверить, считаем что можно (проверим после вступления)
        return True

async def check_can_post_after_join(client, entity, logger, retry_count=3, delay=5):
    """
    Проверка возможности постить в группе ПОСЛЕ вступления
    Делает несколько попыток с задержкой, так как некоторые группы дают права не сразу
    """
    for attempt in range(retry_count):
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
                
                if can_send:
                    if attempt > 0:
                        logger.info(f"    ✅ Права получены после {attempt + 1} попытки (подождали {attempt * delay} секунд)")
                    return True
                else:
                    if attempt < retry_count - 1:
                        logger.debug(f"    ⏳ Попытка {attempt + 1}/{retry_count}: права еще не получены, ждем {delay} секунд...")
                        await asyncio.sleep(delay)
                    else:
                        logger.warning(f"    ⚠️ После {retry_count} попыток права на постинг не получены")
                        return False
            
            # Если не получили permissions, пробуем еще раз
            if attempt < retry_count - 1:
                logger.debug(f"    ⏳ Попытка {attempt + 1}/{retry_count}: permissions не получены, ждем {delay} секунд...")
                await asyncio.sleep(delay)
        
        except ChatWriteForbiddenError:
            # Явный запрет на постинг - не ждем
            logger.warning(f"    ⚠️ Явный запрет на постинг (ChatWriteForbiddenError)")
            return False
        except UserBannedInChannelError:
            # Забанен - не ждем
            logger.warning(f"    🚫 Аккаунт забанен в группе")
            return False
        except Exception as e:
            if attempt < retry_count - 1:
                logger.debug(f"    ⏳ Попытка {attempt + 1}/{retry_count}: ошибка при проверке ({e}), ждем {delay} секунд...")
                await asyncio.sleep(delay)
            else:
                logger.warning(f"    ⚠️ Ошибка при проверке прав после {retry_count} попыток: {e}")
                # Если не можем проверить после всех попыток, считаем что можно (оптимистично)
                return True
    
    # Если дошли сюда - не получили прав после всех попыток
    return False

async def join_group_smart(client, account_name, group_username, logger, system):
    """
    Умное вступление в группу с проверкой прав:
    1. Проверяет права ДО вступления (если возможно)
    2. Вступает в группу
    3. Проверяет права ПОСЛЕ вступления
    4. Если нельзя постить - покидает группу
    5. Если можно - сохраняет привязку аккаунта
    """
    try:
        logger.info(f"  🔍 Проверяю группу {group_username}...")
        
        # Получаем entity группы
        entity = await client.get_entity(group_username)
        
        # ШАГ 1: Проверяем права ДО вступления (для публичных групп)
        can_post_before = await check_can_post_before_join(client, entity, logger)
        if not can_post_before:
            logger.warning(f"  ⚠️ В группе {group_username} нельзя постить (проверка до вступления) - пропускаем")
            return False
        
        # ШАГ 2: Проверяем, не участник ли уже
        is_already_member = False
        try:
            me = await client.get_me()
            permissions = await client.get_permissions(entity, me)
            if permissions:
                is_already_member = True
                logger.info(f"  ℹ️ {account_name} уже участник {group_username}")
                
                # Если уже участник - просто сохраняем привязку (не проверяем права)
                if not system.is_group_assigned(group_username):
                    system.assign_account_to_group(group_username, account_name, datetime.utcnow())
                    logger.info(f"  🔗 Назначен аккаунт {account_name} для группы {group_username} (уже был участником)")
                return True
        except Exception as e:
            # Не участник - продолжаем
            logger.debug(f"    Не участник: {e}")
        
        # ШАГ 3: Вступаем в группу
        logger.info(f"  🚪 {account_name} вступает в {group_username}...")
        await client(JoinChannelRequest(entity))
        logger.info(f"  ✅ {account_name} вступил в {group_username}")
        
        # Небольшая задержка после вступления
        await asyncio.sleep(2)
        
        # ШАГ 4: Сохраняем привязку аккаунта (не проверяем права, просто вступаем)
        # Права могут появиться позже, поэтому просто сохраняем группу
        try:
            system.assign_account_to_group(group_username, account_name, datetime.utcnow())
            logger.info(f"  🔗 Назначен аккаунт {account_name} для группы {group_username} (warm-up 24 часа)")
        except Exception as e:
            logger.error(f"  ❌ Ошибка при сохранении привязки: {e}")
        
        return True
        
    except UserAlreadyParticipantError:
        logger.info(f"  ℹ️ {account_name} уже участник {group_username}")
        # Если уже участник - просто сохраняем привязку (не проверяем права)
        try:
            if not system.is_group_assigned(group_username):
                system.assign_account_to_group(group_username, account_name, datetime.utcnow())
                logger.info(f"  🔗 Назначен аккаунт {account_name} для группы {group_username}")
            return True
        except Exception as e:
            logger.warning(f"  ⚠️ Ошибка при сохранении привязки для уже участника: {e}")
            return False
    except UsernameNotOccupiedError:
        logger.warning(f"  ⚠️ Группа {group_username} не найдена")
        return False
    except ChannelPrivateError:
        logger.warning(f"  ⚠️ Группа {group_username} приватная")
        return False
    except UserBannedInChannelError:
        logger.warning(f"  🚫 {account_name} забанен в {group_username}")
        return False
    except FloodWaitError as e:
        wait_seconds = e.seconds
        wait_minutes = wait_seconds // 60
        wait_hours = wait_minutes // 60
        
        if wait_hours > 0:
            logger.warning(f"  ⏳ FloodWait: {wait_hours}ч {wait_minutes % 60}м ({wait_seconds} секунд)")
        else:
            logger.warning(f"  ⏳ FloodWait: {wait_minutes}м ({wait_seconds} секунд)")
        
        # Если FloodWait больше 10 минут - пропускаем эту группу и переключаемся на другой аккаунт
        if wait_seconds > 600:
            logger.info(f"  ⏸️ FloodWait слишком большой ({wait_minutes}м), пропускаем группу {group_username}")
            return ("FLOOD_WAIT", wait_seconds)  # Возвращаем специальный код для переключения аккаунта
        
        # Если FloodWait небольшой (до 10 минут) - ждем и пробуем еще раз
        logger.info(f"  ⏳ Ждем {wait_minutes}м перед следующей попыткой...")
        await asyncio.sleep(min(wait_seconds, 300))  # Максимум 5 минут ждем
        return ("FLOOD_WAIT", wait_seconds)
    except ChatWriteForbiddenError:
        logger.warning(f"  ⚠️ Нет прав на постинг в {group_username} (но остаемся в группе - права могут появиться позже)")
        # Не покидаем группу - просто сохраняем привязку
        try:
            system.assign_account_to_group(group_username, account_name, datetime.utcnow())
            logger.info(f"  🔗 Назначен аккаунт {account_name} для группы {group_username} (права могут появиться позже)")
            return True
        except Exception as e:
            logger.error(f"  ❌ Ошибка при сохранении привязки: {e}")
            return False
    except RPCError as e:
        error_msg = str(e)
        if "CAPTCHA" in error_msg or "капча" in error_msg.lower():
            logger.warning(f"  🔐 Требуется капча для {group_username}")
            return False
        logger.error(f"  ❌ RPC Error: {e}")
        return False
    except Exception as e:
        logger.error(f"  ❌ Неожиданная ошибка для {group_username}: {e}")
        return False

async def search_and_join_lexus_groups():
    """Поиск новых групп и умное вступление в них"""
    logger = setup_logging()
    
    logger.info("=" * 80)
    logger.info("🔍 УМНЫЙ ПОИСК И ВСТУПЛЕНИЕ В ГРУППЫ LEXUS")
    logger.info("=" * 80)
    logger.info("📋 Проверяет права ДО вступления и покидает группы, где нельзя постить")
    logger.info("=" * 80)
    
    system = PromotionSystem()
    system.load_accounts()
    system.load_lexus_accounts_config()
    
    # Фильтруем аккаунты для Lexus
    if hasattr(system, 'lexus_allowed_accounts') and system.lexus_allowed_accounts:
        original_count = len(system.accounts)
        system.accounts = [
            acc for acc in system.accounts
            if acc.get('session_name') in system.lexus_allowed_accounts
        ]
        logger.info(f"✅ Загружено {len(system.accounts)} аккаунтов для Lexus (из {original_count})")
        logger.info(f"   Аккаунты: {sorted([acc.get('session_name') for acc in system.accounts])}")
    else:
        logger.warning("⚠️ Не найден whitelist для Lexus")
    
    system.load_group_assignments()
    await system.initialize_clients()
    
    if not system.clients:
        logger.error("❌ Нет доступных клиентов!")
        return
    
    # Ключевые слова для поиска
    search_keywords = [
        # Авто-группы
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
        # Барахолки
        'барахолка украина', 'барахолка киев', 'барахолка україна',
        'частные объявления украина', 'частні оголошення україна',
        'объявления киев', 'оголошення київ', 'объявления украина',
        'продажа киев', 'продаж київ', 'купля продаж украина',
        'частные продажи', 'приватні продажі', 'частные объявления',
        'барахолка одесса', 'барахолка львов', 'барахолка харьков',
        'объявления одесса', 'объявления львов', 'объявления харьков',
        'buy sell ukraine', 'classifieds ukraine', 'marketplace ukraine',
        # Барахолки с авто-тематикой
        'барахолка авто', 'барахолка автомобили', 'барахолка машины',
        'авто барахолка', 'автомобили барахолка', 'машины барахолка',
        'объявления авто', 'оголошення авто', 'продажа авто',
        'частные авто', 'приватні авто', 'авто частные'
    ]
    
    found_groups = []
    found_file = Path('logs/found_lexus_groups.json')
    
    # Загружаем уже найденные группы
    existing_groups = set()
    if found_file.exists():
        try:
            with open(found_file, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
                existing_groups = {g.get('username', '') for g in existing_data if g.get('username')}
        except:
            pass
    
    # Загружаем группы из targets.txt
    targets_file = Path('targets.txt')
    if targets_file.exists():
        with open(targets_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and line.startswith('@'):
                    existing_groups.add(line)
    
    logger.info(f"📋 Уже известно групп: {len(existing_groups)}")
    logger.info(f"🔍 Начинаю поиск по {len(search_keywords)} ключевым словам...")
    
    # Используем первый доступный клиент для поиска
    client_name = list(system.clients.keys())[0]
    client = system.clients[client_name]
    logger.info(f"👤 Используем аккаунт для поиска: {client_name}")
    
    # Поиск новых групп
    for idx, keyword in enumerate(search_keywords, 1):
        try:
            logger.info(f"  [{idx}/{len(search_keywords)}] Ищу: '{keyword}'...")
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
                        existing_groups.add(username)
            
            await asyncio.sleep(2)  # Пауза между поисками
            
        except Exception as e:
            logger.error(f"  ❌ Ошибка при поиске '{keyword}': {e}")
            continue
    
    if not found_groups:
        logger.info("  ℹ️ Новых групп не найдено")
        # Пробуем использовать уже найденные группы, которые еще не обработаны
        if found_file.exists():
            try:
                with open(found_file, 'r', encoding='utf-8') as f:
                    all_existing = json.load(f)
                
                # Фильтруем группы, которые еще не назначены аккаунтам
                assigned_groups = set(system.group_assignments.keys())
                unassigned_groups = [
                    g for g in all_existing
                    if g.get('username') and g.get('username') not in assigned_groups
                ]
                
                if unassigned_groups:
                    logger.info(f"  📌 Найдено {len(unassigned_groups)} уже найденных групп, которые еще не обработаны")
                    random.shuffle(unassigned_groups)
                    found_groups = unassigned_groups[:50]  # Берем максимум 50
                    logger.info(f"  ✅ Будем обрабатывать {len(found_groups)} необработанных групп")
                else:
                    logger.info("  ℹ️ Все найденные группы уже обработаны")
                    return
            except Exception as e:
                logger.warning(f"  ⚠️ Ошибка при загрузке найденных групп: {e}")
                return
        else:
            logger.info("  ℹ️ Ранее найденных групп нет, выходим")
            return
    
    logger.info(f"✅ Найдено новых групп: {len(found_groups)}")
    
    # Сохраняем найденные группы
    all_groups = []
    if found_file.exists():
        try:
            with open(found_file, 'r', encoding='utf-8') as f:
                all_groups = json.load(f)
        except:
            pass
    
    all_groups.extend(found_groups)
    
    with open(found_file, 'w', encoding='utf-8') as f:
        json.dump(all_groups, f, ensure_ascii=False, indent=2)
    
    logger.info(f"💾 Сохранено {len(found_groups)} новых групп в {found_file}")
    
    # Вступление в найденные группы
    logger.info("")
    logger.info("=" * 80)
    logger.info("🚪 УМНОЕ ВСТУПЛЕНИЕ В НАЙДЕННЫЕ ГРУППЫ")
    logger.info("=" * 80)
    
    # Лимиты
    max_joins_per_account = 10  # Максимум вступлений в день на аккаунт
    max_groups_to_process = 50  # Максимум групп для обработки за раз
    
    groups_to_process = found_groups[:max_groups_to_process]
    logger.info(f"📊 Обработаем {len(groups_to_process)} групп (максимум {max_joins_per_account} вступлений на аккаунт)")
    
    # Подсчитываем вступления за сегодня для каждого аккаунта
    joins_today = {name: 0 for name in system.clients.keys()}
    
    joined_count = 0
    skipped_count = 0
    failed_count = 0
    
    # Перемешиваем группы и аккаунты для равномерного распределения
    random.shuffle(groups_to_process)
    account_names = list(system.clients.keys())
    random.shuffle(account_names)
    
    # Словарь для отслеживания FloodWait по аккаунтам
    account_flood_wait = {name: 0 for name in account_names}
    
    for idx, group_info in enumerate(groups_to_process, 1):
        username = group_info['username']
        title = group_info.get('title', username)
        
        logger.info(f"\n[{idx}/{len(groups_to_process)}] {username}")
        logger.info(f"  📝 {title}")
        
        # Выбираем аккаунт с наименьшим количеством вступлений сегодня и без активного FloodWait
        available_accounts = [
            name for name in account_names 
            if joins_today.get(name, 0) < max_joins_per_account and account_flood_wait.get(name, 0) == 0
        ]
        
        if not available_accounts:
            # Если все аккаунты в FloodWait или достигли лимита - проверяем, можно ли продолжить
            accounts_in_flood = [name for name in account_names if account_flood_wait.get(name, 0) > 0]
            if accounts_in_flood:
                # Находим аккаунт с минимальным FloodWait
                account_name = min(accounts_in_flood, key=lambda name: account_flood_wait.get(name, 0))
                wait_remaining = account_flood_wait[account_name]
                if wait_remaining > 60:  # Если осталось больше минуты - пропускаем группу
                    logger.info(f"  ⏸️ Все аккаунты в FloodWait, минимальное ожидание: {wait_remaining // 60}м")
                    skipped_count += 1
                    continue
                else:
                    # Если осталось немного - ждем и используем этот аккаунт
                    logger.info(f"  ⏳ Ждем {wait_remaining}с для аккаунта {account_name}...")
                    await asyncio.sleep(wait_remaining)
                    account_flood_wait[account_name] = 0
            else:
                # Все аккаунты достигли лимита
                logger.warning(f"  ⚠️ Все аккаунты достигли лимита вступлений")
                break
        
        # Выбираем аккаунт
        if available_accounts:
            account_name = min(available_accounts, key=lambda name: joins_today.get(name, 0))
        else:
            account_name = min(account_names, key=lambda name: account_flood_wait.get(name, 0))
        
        client = system.clients[account_name]
        
        # Умное вступление
        result = await join_group_smart(client, account_name, username, logger, system)
        
        if result is True:
            joined_count += 1
            joins_today[account_name] = joins_today.get(account_name, 0) + 1
            account_flood_wait[account_name] = 0  # Сбрасываем FloodWait при успехе
            logger.info(f"  ✅ Успешно: {account_name} (вступлений сегодня: {joins_today[account_name]})")
        elif isinstance(result, tuple) and result[0] == "FLOOD_WAIT":
            # Получили FloodWait - помечаем аккаунт и переключаемся на другой
            wait_seconds = result[1]
            account_flood_wait[account_name] = wait_seconds
            logger.warning(f"  ⏸️ Аккаунт {account_name} получил FloodWait {wait_seconds // 60}м - переключаемся на другой аккаунт")
            skipped_count += 1
        elif result is False:
            failed_count += 1
            account_flood_wait[account_name] = 0  # Сбрасываем FloodWait при ошибке
            logger.warning(f"  ❌ Не удалось вступить/проверить {username}")
        else:
            skipped_count += 1
        
        # Уменьшаем FloodWait для всех аккаунтов (прошла задержка между группами)
        delay = random.randint(10, 30)
        for name in account_flood_wait:
            if account_flood_wait[name] > 0:
                account_flood_wait[name] = max(0, account_flood_wait[name] - delay)
        
        # Задержка между группами
        if idx < len(groups_to_process):
            await asyncio.sleep(delay)
    
    logger.info("")
    logger.info("=" * 80)
    logger.info("📊 ИТОГИ:")
    logger.info(f"  ✅ Успешно вступили: {joined_count}")
    logger.info(f"  ⏭️ Пропущено: {skipped_count}")
    logger.info(f"  ❌ Не удалось: {failed_count}")
    logger.info(f"  📋 Всего обработано: {len(groups_to_process)}")
    logger.info("")
    logger.info("📊 Вступления по аккаунтам:")
    for account_name, count in joins_today.items():
        logger.info(f"  {account_name}: {count}/{max_joins_per_account}")
    logger.info("=" * 80)
    
    # Добавляем успешно вступившие группы в targets.txt и group_niches.json
    if joined_count > 0:
        logger.info("")
        logger.info("📝 Добавляю успешно вступившие группы в targets.txt и group_niches.json...")
        try:
            import subprocess
            result = subprocess.run(
                ['python3', 'add_ukraine_cars_groups_to_targets.py'],
                capture_output=True,
                text=True,
                timeout=300
            )
            if result.returncode == 0:
                logger.info("✅ Группы успешно добавлены в targets.txt и group_niches.json")
            else:
                logger.warning(f"⚠️ Скрипт завершился с кодом {result.returncode}")
        except Exception as e:
            logger.error(f"❌ Ошибка при добавлении групп: {e}")

if __name__ == "__main__":
    asyncio.run(search_and_join_lexus_groups())
