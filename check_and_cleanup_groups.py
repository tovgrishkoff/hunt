#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для проверки и очистки мёртвых групп из targets.txt
Проверяет доступность групп и удаляет недоступные
"""

import asyncio
import json
import logging
from pathlib import Path
from datetime import datetime
import shutil
from urllib.parse import urlparse
from telethon import TelegramClient
from telethon.errors import (
    UsernameInvalidError,
    UsernameNotOccupiedError,
    ChannelPrivateError,
    FloodWaitError,
    UserBannedInChannelError,
    ChatAdminRequiredError,
    RPCError,
    AuthKeyDuplicatedError
)

def setup_logging():
    """Настройка логирования"""
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / 'check_and_cleanup_groups.log'
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

async def check_group_access(client, group_username, logger):
    """Проверяет доступность группы"""
    try:
        # Убираем @ если есть
        username = group_username.lstrip('@')
        
        # Пытаемся получить информацию о группе
        entity = await client.get_entity(username)
        
        # Проверяем, что это группа/канал
        if hasattr(entity, 'broadcast') and entity.broadcast:
            # Это канал, проверяем доступ
            try:
                await client.get_messages(entity, limit=1)
                return True, "OK"
            except (ChannelPrivateError, UserBannedInChannelError):
                return False, "Private or banned"
            except Exception as e:
                return False, f"Error: {str(e)}"
        else:
            # Это группа, проверяем доступ
            try:
                await client.get_messages(entity, limit=1)
                return True, "OK"
            except (ChannelPrivateError, UserBannedInChannelError):
                return False, "Private or banned"
            except Exception as e:
                return False, f"Error: {str(e)}"
                
    except UsernameInvalidError:
        return False, "Invalid username"
    except UsernameNotOccupiedError:
        return False, "Not occupied"
    except ChannelPrivateError:
        return False, "Private channel"
    except UserBannedInChannelError:
        return False, "Banned in channel"
    except FloodWaitError as e:
        # Если FloodWait больше 1 часа (3600 секунд), пропускаем группу
        if e.seconds > 3600:
            logger.warning(f"⚠️ FloodWait {e.seconds}s ({e.seconds//3600}ч) для {group_username} - слишком долго, пропускаем")
            return False, f"FloodWait {e.seconds}s (пропущено)"
        else:
            logger.warning(f"⚠️ FloodWait {e.seconds}s для {group_username}, ждём...")
            await asyncio.sleep(e.seconds)
            return None, f"FloodWait {e.seconds}s"
    except Exception as e:
        return False, f"Error: {str(e)}"

async def check_groups(accounts_config_path, targets_path, group_niches_path, logger):
    """Проверяет все группы из targets.txt"""
    
    # Загружаем конфигурацию (это список словарей)
    with open(accounts_config_path, 'r', encoding='utf-8') as f:
        accounts_config = json.load(f)
    
    # Загружаем targets
    with open(targets_path, 'r', encoding='utf-8') as f:
        targets = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
    
    # Загружаем group_niches
    group_niches = {}
    if Path(group_niches_path).exists():
        with open(group_niches_path, 'r', encoding='utf-8') as f:
            group_niches = json.load(f)
    
    logger.info(f"📋 Загружено {len(targets)} групп для проверки")
    
    # Пробуем найти рабочий аккаунт (пропускаем проблемные)
    account_config = None
    account_name = None
    
    for acc_config in accounts_config:
        # Проверяем, что аккаунт не отключен (если есть поле enabled)
        if not acc_config.get('enabled', True):
            continue
        
        acc_name = acc_config.get('session_name')
        if not acc_name:
            continue
        
        # Пропускаем известные проблемные аккаунты
        if acc_name in ['promotion_dao_bro', 'promotion_oleg_petrov']:
            logger.info(f"⏭️ Пропускаем проблемный аккаунт: {acc_name}")
            continue
        
        account_config = acc_config
        account_name = acc_name
        break
    
    if not account_config or not account_name:
        logger.error("❌ Нет доступных аккаунтов")
        return
    
    logger.info(f"👤 Используем аккаунт: {account_name}")
    
    api_id = account_config.get('api_id')
    api_hash = account_config.get('api_hash')
    proxy_config = account_config.get('proxy')
    string_session = account_config.get('string_session')
    
    if not api_id or not api_hash:
        logger.error(f"❌ Нет API credentials для {account_name}")
        return
    
    # Парсим прокси
    proxy = None
    if proxy_config:
        try:
            # Формат: http://user:pass@host:port
            if '://' in proxy_config:
                parsed = urlparse(proxy_config)
                proxy = {
                    'proxy_type': 'http',
                    'addr': parsed.hostname,
                    'port': parsed.port,
                    'username': parsed.username,
                    'password': parsed.password
                }
                logger.info(f"  Используем прокси: {proxy['addr']}:{proxy['port']}")
        except Exception as e:
            logger.warning(f"  Не удалось распарсить прокси: {e}")
    
    # Создаём клиент (используем StringSession если есть, иначе файловую сессию)
    client = None
    if string_session and string_session not in ['', 'TO_BE_CREATED', 'null', None]:
        if isinstance(string_session, str) and string_session.strip():
            from telethon.sessions import StringSession
            try:
                logger.info(f"  Используем StringSession (length: {len(string_session.strip())})")
                client = TelegramClient(
                    StringSession(string_session.strip()),
                    api_id,
                    api_hash,
                    proxy=proxy
                )
            except Exception as e:
                logger.error(f"  Ошибка создания StringSession: {e}")
                client = None
    
    if not client:
        # Fallback: используем файловую сессию
        session_file = Path('sessions') / f"{account_name}.session"
        if not session_file.exists():
            logger.error(f"❌ Сессия не найдена: {session_file}")
            return
        logger.info(f"  Используем файловую сессию: {session_file}")
        client = TelegramClient(
            str(session_file),
            api_id,
            api_hash,
            proxy=proxy
        )
    
    # Сохраняем имя первого аккаунта для пропуска
    first_account_name = account_name
    
    try:
        await client.start()
        logger.info(f"✅ Подключен {account_name}")
    except AuthKeyDuplicatedError as e:
        logger.error(f"❌ Ошибка авторизации для {account_name}: {e}")
        logger.info("🔄 Пробуем следующий аккаунт...")
        
        # Закрываем старый клиент
        try:
            await client.disconnect()
        except:
            pass
        
        # Пробуем следующий аккаунт
        account_config = None
        account_name = None
        
        for acc_config in accounts_config:
            if not acc_config.get('enabled', True):
                continue
            
            acc_name = acc_config.get('session_name')
            if not acc_name:
                continue
            
            # Пропускаем уже попробованный и проблемные
            if acc_name in ['promotion_dao_bro', 'promotion_oleg_petrov'] or acc_name == first_account_name:
                continue
            
            account_config = acc_config
            account_name = acc_name
            break
        
        if not account_config or not account_name:
            logger.error("❌ Нет других доступных аккаунтов")
            return
        
        logger.info(f"👤 Переключаемся на аккаунт: {account_name}")
        
        # Создаём новый клиент
        api_id = account_config.get('api_id')
        api_hash = account_config.get('api_hash')
        proxy_config = account_config.get('proxy')
        string_session = account_config.get('string_session')
        
        # Парсим прокси
        proxy = None
        if proxy_config:
            try:
                if '://' in proxy_config:
                    parsed = urlparse(proxy_config)
                    proxy = {
                        'proxy_type': 'http',
                        'addr': parsed.hostname,
                        'port': parsed.port,
                        'username': parsed.username,
                        'password': parsed.password
                    }
                    logger.info(f"  Используем прокси: {proxy['addr']}:{proxy['port']}")
            except Exception as e:
                logger.warning(f"  Не удалось распарсить прокси: {e}")
        
        # Создаём клиент
        client = None
        if string_session and string_session not in ['', 'TO_BE_CREATED', 'null', None]:
            if isinstance(string_session, str) and string_session.strip():
                from telethon.sessions import StringSession
                try:
                    logger.info(f"  Используем StringSession (length: {len(string_session.strip())})")
                    client = TelegramClient(
                        StringSession(string_session.strip()),
                        api_id,
                        api_hash,
                        proxy=proxy
                    )
                except Exception as e:
                    logger.error(f"  Ошибка создания StringSession: {e}")
                    client = None
        
        if not client:
            session_file = Path('sessions') / f"{account_name}.session"
            if not session_file.exists():
                logger.error(f"❌ Сессия не найдена: {session_file}")
                return
            logger.info(f"  Используем файловую сессию: {session_file}")
            client = TelegramClient(
                str(session_file),
                api_id,
                api_hash,
                proxy=proxy
            )
        
        # Пробуем подключиться снова
        try:
            await client.start()
            logger.info(f"✅ Подключен {account_name}")
        except Exception as e:
            logger.error(f"❌ Не удалось подключиться к {account_name}: {e}")
            return
    
    # Проверяем группы (выполняется после успешного подключения)
    valid_groups = []
    invalid_groups = []
    ukraine_cars_groups = []
    bali_groups = []
    
    # Счётчик последовательных FloodWait для ротации аккаунтов
    consecutive_floodwaits = 0
    max_consecutive_floodwaits = 3  # После 3 подряд - переключаем аккаунт
    used_accounts = [account_name]  # Список использованных аккаунтов
    
    for i, group in enumerate(targets, 1):
        logger.info(f"[{i}/{len(targets)}] Проверяю {group}...")
        
        try:
            result, reason = await check_group_access(client, group, logger)
            
            if result is None:  # FloodWait (короткий, уже обработан)
                logger.warning(f"⏸️ Пропускаю {group} из-за FloodWait (короткий)")
                valid_groups.append(group)  # Оставляем на потом
                consecutive_floodwaits += 1
                continue
            
            # Проверяем, есть ли FloodWait в причине
            if "FloodWait" in reason:
                consecutive_floodwaits += 1
                logger.warning(f"⚠️ FloodWait обнаружен: {reason} (подряд: {consecutive_floodwaits})")
            else:
                # Сбрасываем счётчик при успешной проверке
                consecutive_floodwaits = 0
            
            # Если много последовательных FloodWait - переключаем аккаунт
            if consecutive_floodwaits >= max_consecutive_floodwaits:
                logger.warning(f"⚠️ Получено {consecutive_floodwaits} FloodWait подряд - переключаем аккаунт")
                
                # Закрываем текущий клиент
                try:
                    await client.disconnect()
                except:
                    pass
                
                # Ищем следующий аккаунт
                next_account_config = None
                next_account_name = None
                
                for acc_config in accounts_config:
                    if not acc_config.get('enabled', True):
                        continue
                    
                    acc_name = acc_config.get('session_name')
                    if not acc_name:
                        continue
                    
                    # Пропускаем уже использованные и проблемные
                    if acc_name in ['promotion_dao_bro', 'promotion_oleg_petrov'] or acc_name in used_accounts:
                        continue
                    
                    next_account_config = acc_config
                    next_account_name = acc_name
                    break
                
                if next_account_config and next_account_name:
                    logger.info(f"🔄 Переключаемся на аккаунт: {next_account_name}")
                    account_config = next_account_config
                    account_name = next_account_name
                    used_accounts.append(account_name)
                    consecutive_floodwaits = 0
                    
                    # Создаём новый клиент
                    api_id = account_config.get('api_id')
                    api_hash = account_config.get('api_hash')
                    proxy_config = account_config.get('proxy')
                    string_session = account_config.get('string_session')
                    
                    # Парсим прокси
                    proxy = None
                    if proxy_config:
                        try:
                            if '://' in proxy_config:
                                parsed = urlparse(proxy_config)
                                proxy = {
                                    'proxy_type': 'http',
                                    'addr': parsed.hostname,
                                    'port': parsed.port,
                                    'username': parsed.username,
                                    'password': parsed.password
                                }
                        except:
                            pass
                    
                    # Создаём клиент
                    client = None
                    if string_session and string_session not in ['', 'TO_BE_CREATED', 'null', None]:
                        if isinstance(string_session, str) and string_session.strip():
                            from telethon.sessions import StringSession
                            try:
                                client = TelegramClient(
                                    StringSession(string_session.strip()),
                                    api_id,
                                    api_hash,
                                    proxy=proxy
                                )
                            except:
                                client = None
                    
                    if not client:
                        session_file = Path('sessions') / f"{account_name}.session"
                        if session_file.exists():
                            client = TelegramClient(
                                str(session_file),
                                api_id,
                                api_hash,
                                proxy=proxy
                            )
                    
                    if client:
                        try:
                            await client.start()
                            logger.info(f"✅ Подключен {account_name}")
                            # Делаем паузу перед продолжением
                            logger.info("⏸️ Пауза 30 секунд перед продолжением...")
                            await asyncio.sleep(30)
                        except Exception as e:
                            logger.error(f"❌ Не удалось подключиться к {account_name}: {e}")
                            # Если не удалось - продолжаем со старым клиентом
                    else:
                        logger.error(f"❌ Не удалось создать клиент для {account_name}")
                else:
                    logger.warning("⚠️ Нет других аккаунтов для переключения, делаем большую паузу...")
                    logger.info("⏸️ Пауза 10 минут перед продолжением...")
                    await asyncio.sleep(600)  # 10 минут пауза
                    consecutive_floodwaits = 0
                    used_accounts = [account_name]  # Сбрасываем список использованных
            
            if result:
                valid_groups.append(group)
                niche = group_niches.get(group, 'unknown')
                if niche == 'ukraine_cars':
                    ukraine_cars_groups.append(group)
                elif niche and niche != 'disabled_kammora':
                    bali_groups.append(group)
                logger.info(f"  ✅ {group} - доступна ({reason})")
            else:
                invalid_groups.append(group)
                logger.warning(f"  ❌ {group} - недоступна ({reason})")
        
        except Exception as e:
            logger.error(f"  ❌ Ошибка при проверке {group}: {e}")
            invalid_groups.append(group)
        
        # Пауза между проверками (увеличена для безопасности)
        await asyncio.sleep(5)
    
    logger.info("=" * 80)
    logger.info("📊 РЕЗУЛЬТАТЫ ПРОВЕРКИ")
    logger.info("=" * 80)
    logger.info(f"✅ Валидных групп: {len(valid_groups)}")
    logger.info(f"❌ Невалидных групп: {len(invalid_groups)}")
    logger.info(f"🚗 Ukraine cars групп: {len(ukraine_cars_groups)}")
    logger.info(f"🏖️ Bali групп: {len(bali_groups)}")
    
    if invalid_groups:
        logger.info("\n❌ Невалидные группы для удаления:")
        for group in invalid_groups:
            logger.info(f"  - {group}")
    
    # Создаём backup
    backup_file = Path(f'{targets_path}.backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}')
    shutil.copy2(targets_path, backup_file)
    logger.info(f"\n💾 Создан backup: {backup_file}")
    
    # Обновляем targets.txt
    with open(targets_path, 'w', encoding='utf-8') as f:
        for group in valid_groups:
            f.write(f"{group}\n")
    
    logger.info(f"✅ Обновлён {targets_path}: {len(valid_groups)} групп")
    
    # Удаляем невалидные группы из group_niches.json
    if invalid_groups and Path(group_niches_path).exists():
        backup_niches = Path(f'{group_niches_path}.backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}')
        shutil.copy2(group_niches_path, backup_niches)
        
        for group in invalid_groups:
            if group in group_niches:
                del group_niches[group]
        
        with open(group_niches_path, 'w', encoding='utf-8') as f:
            json.dump(group_niches, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ Обновлён {group_niches_path}: удалено {len(invalid_groups)} групп")
    
    logger.info("=" * 80)
    logger.info("✅ ПРОВЕРКА ЗАВЕРШЕНА")
    logger.info("=" * 80)
    
    # Отключаемся от клиента
    try:
        await client.disconnect()
    except:
        pass

async def main():
    logger = setup_logging()
    logger.info("=" * 80)
    logger.info("🔍 ПРОВЕРКА И ОЧИСТКА ГРУПП")
    logger.info("=" * 80)
    
    accounts_config_path = Path('accounts_config.json')
    targets_path = Path('targets.txt')
    group_niches_path = Path('group_niches.json')
    
    if not accounts_config_path.exists():
        logger.error(f"❌ Файл не найден: {accounts_config_path}")
        return
    
    if not targets_path.exists():
        logger.error(f"❌ Файл не найден: {targets_path}")
        return
    
    await check_groups(accounts_config_path, targets_path, group_niches_path, logger)

if __name__ == "__main__":
    asyncio.run(main())

