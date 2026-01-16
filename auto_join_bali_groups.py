#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Автоматический поиск и вступление в группы по Бали
Проверяет, можно ли постить в группе перед вступлением
Ищет группы релевантные для наших ниш
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
    
    log_file = log_dir / 'auto_join_bali_groups.log'
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    return logging.getLogger(__name__)

async def check_group_permissions(client, entity, logger):
    """Проверяет, можно ли постить в группу."""
    try:
        permissions = await client.get_permissions(entity)
        can_send_messages = permissions.send_messages if permissions else False
        # Дополнительная проверка на тип группы (чтобы не постить в каналы без обсуждений)
        is_channel = getattr(entity, 'broadcast', False)
        has_discussion = getattr(entity, 'linked_chat_id', None) is not None
        
        if is_channel and not has_discussion:
            logger.info(f"  ⚠️ Группа {getattr(entity, 'title', 'Unknown')} является каналом без обсуждений, постинг невозможен.")
            return False
        
        return can_send_messages
    except Exception as e:
        logger.warning(f"  ⚠️ Не удалось получить права для {getattr(entity, 'title', 'Unknown')}: {e}")
        return False

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
        except:
            pass
        
        # Если не можем проверить, предполагаем что можно (проверим после вступления)
        return True
    except Exception as e:
        return True  # Если ошибка, предполагаем что можно

async def join_group(client, group_link, logger):
    """Вступление в группу с проверкой возможности постить"""
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
        try:
            await client.get_participants(entity, limit=1)
            logger.info(f"  ℹ️ Уже участник {username}")
            return True
        except:
            pass
        
        # Вступаем в группу
        await client(JoinChannelRequest(username))
        logger.info(f"  ✅ Вступил в группу {username}")
        
        # Дополнительная проверка после вступления
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
        except Exception as e:
            logger.warning(f"  ⚠️ Не удалось проверить права после вступления: {e}")
            # Если не можем проверить, оставляем группу (может быть можно постить)
        
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
    """Поиск новых групп по Бали и вступление в них"""
    logger = setup_logging()
    
    logger.info("=" * 80)
    logger.info("🔍 АВТОМАТИЧЕСКИЙ ПОИСК И ВСТУПЛЕНИЕ В ГРУППЫ ПО БАЛИ")
    logger.info("=" * 80)
    
    system = PromotionSystem()
    system.load_accounts()
    await system.initialize_clients()
    
    if not system.clients:
        logger.error("❌ Нет доступных клиентов!")
        return
    
    # Используем первый доступный клиент для поиска
    client_name = list(system.clients.keys())[0]
    client = system.clients[client_name]
    
    logger.info(f"👤 Используем аккаунт для поиска: {client_name}")
    
    # Ключевые слова для поиска групп по Бали (релевантные для наших ниш)
    search_keywords = [
        # Общие по Бали
        'bali chat', 'bali group', 'bali community', 'bali expat', 'bali expats',
        'bali объявления', 'bali обьявления', 'bali чат', 'bali группа',
        'бали чат', 'бали группа', 'бали объявления', 'бали обьявления',
        
        # Недвижимость
        'bali property', 'bali real estate', 'bali rent', 'bali rental',
        'bali villa', 'bali apartment', 'bali housing',
        'бали недвижимость', 'бали аренда', 'бали вилла', 'бали квартира',
        'bali риелтор', 'bali агентство',
        
        # Фото/Видео
        'bali photographer', 'bali videographer', 'bali photo', 'bali video',
        'bali съемка', 'bali фотосессия', 'bali свадьба',
        'бали фотограф', 'бали видеограф', 'бали съемка',
        
        # Красота
        'bali beauty', 'bali manicure', 'bali nail', 'bali hair', 'bali makeup',
        'bali eyebrows', 'bali eyelashes', 'bali cosmetology',
        'бали маникюр', 'бали макияж', 'бали брови', 'бали ресницы',
        'бали волосы', 'бали косметология',
        
        # Транспорт
        'bali transport', 'bali taxi', 'bali car rental', 'bali bike rental',
        'bali scooter', 'bali motorbike', 'bali transfer',
        'бали транспорт', 'бали такси', 'бали аренда авто', 'бали аренда байка',
        
        # Туризм
        'bali tour', 'bali guide', 'bali excursion', 'bali travel',
        'бали тур', 'бали гид', 'бали экскурсия',
        
        # Разное
        'bali services', 'bali business', 'bali freelance', 'bali work',
        'bali обмен', 'bali валюта', 'bali currency',
        'canggu chat', 'ubud chat', 'seminyak chat',
        'чангу чат', 'убуд чат', 'семиняк чат',
        
        # Английские варианты
        'bali buy sell', 'bali marketplace', 'bali classifieds',
        'bali jobs', 'bali services', 'bali help',
    ]
    
    found_groups = []
    found_file = Path('logs/found_bali_groups.json')
    
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
    for keyword in search_keywords:
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
    
    if not found_groups:
        logger.info("  ℹ️ Новых групп не найдено")
        return
    
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
    
    joined_count = 0
    failed_count = 0
    
    for group_info in found_groups:
        username = group_info.get('username', '')
        if not username:
            continue
        
        # Выбираем аккаунт для вступления
        account = random.choice(accounts)
        account_name = account['session_name']
        
        if account_name not in system.clients:
            logger.warning(f"  ⚠️ Аккаунт {account_name} не инициализирован, пропускаем")
            continue
        
        client = system.clients[account_name]
        logger.info(f"  Используем аккаунт: {account_name}")
        
        result = await join_group(client, username, logger)
        
        if result == True:
            joined_count += 1
        elif isinstance(result, tuple) and result[0] == "FLOOD_WAIT":
            wait_seconds = result[1]
            logger.warning(f"  ⏳ FloodWait {wait_seconds} секунд, пропускаем группу")
            failed_count += 1
        else:
            failed_count += 1
        
        # Пауза между вступлениями
        await asyncio.sleep(random.randint(30, 60))
    
    logger.info("")
    logger.info("=" * 80)
    logger.info(f"✅ Вступили в {joined_count} групп")
    logger.info(f"❌ Не удалось вступить в {failed_count} групп")
    logger.info("=" * 80)

if __name__ == "__main__":
    asyncio.run(search_and_join_groups())

