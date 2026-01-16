#!/usr/bin/env python3
"""
Восстановление файловых сессий из string_session в конфиге
"""

import asyncio
import json
import logging
from pathlib import Path
from telethon import TelegramClient
from telethon.sessions import StringSession

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def restore_session(account):
    """Восстановление сессии из string_session"""
    session_name = account['session_name']
    api_id = int(account['api_id'])
    api_hash = account['api_hash']
    string_session = account.get('string_session', '')
    
    if not string_session:
        logger.warning(f"⚠️ {session_name}: нет string_session, пропускаем")
        return False
    
    logger.info(f"🔄 Восстанавливаем сессию: {session_name}")
    
    try:
        # Создаем клиент с string_session
        client = TelegramClient(StringSession(string_session), api_id, api_hash)
        await client.connect()
        
        if not await client.is_user_authorized():
            logger.error(f"❌ {session_name}: string_session не валиден")
            await client.disconnect()
            return False
        
        me = await client.get_me()
        username = getattr(me, 'username', 'No username')
        logger.info(f"✅ {session_name}: авторизован как @{username}")
        
        # Сохраняем сессию в файл
        session_path = f"sessions/{session_name}"
        logger.info(f"💾 Сохраняем сессию в {session_path}...")
        
        # Используем метод save() для сохранения в файл
        # Сначала отключаемся от string_session
        await client.disconnect()
        
        # Создаем новый клиент с файловой сессией
        file_client = TelegramClient(session_path, api_id, api_hash)
        await file_client.connect()
        
        # Если файловая сессия не авторизована, копируем из string_session
        if not await file_client.is_user_authorized():
            # Используем string_session для авторизации
            string_client = TelegramClient(StringSession(string_session), api_id, api_hash)
            await string_client.connect()
            
            # Получаем auth_key из string_session и сохраняем в файл
            # Проще всего - использовать метод save() напрямую
            await string_client.disconnect()
            
            # Создаем новую файловую сессию и авторизуем через string_session
            # Пересоздаем клиент с файловой сессией
            file_client = TelegramClient(session_path, api_id, api_hash)
            await file_client.connect()
            
            # Если все еще не авторизован, пробуем другой способ
            if not await file_client.is_user_authorized():
                # Используем прямой способ - создаем сессию из string_session
                from telethon.sessions import SQLiteSession
                sqlite_session = SQLiteSession(session_path)
                # Копируем данные из string_session
                string_session_obj = StringSession(string_session)
                # Получаем auth_key
                auth_key = string_session_obj.auth_key
                if auth_key:
                    sqlite_session.auth_key = auth_key
                    sqlite_session.save()
                    logger.info(f"✅ Сессия сохранена через прямой метод")
                else:
                    logger.warning(f"⚠️ Не удалось получить auth_key из string_session")
                    await file_client.disconnect()
                    return False
        
        # Проверяем, что файловая сессия работает
        await file_client.disconnect()
        file_client = TelegramClient(session_path, api_id, api_hash)
        await file_client.connect()
        
        if await file_client.is_user_authorized():
            me = await file_client.get_me()
            username = getattr(me, 'username', 'No username')
            logger.info(f"✅ Файловая сессия восстановлена! Пользователь: @{username}")
            await file_client.disconnect()
            return True
        else:
            logger.error(f"❌ Файловая сессия не авторизована после восстановления")
            await file_client.disconnect()
            return False
            
    except Exception as e:
        logger.error(f"❌ Ошибка восстановления {session_name}: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Главная функция"""
    config_file = Path('accounts_config.json')
    
    if not config_file.exists():
        logger.error(f"❌ Файл {config_file} не найден!")
        return
    
    # Загружаем конфигурацию
    with open(config_file, 'r', encoding='utf-8') as f:
        accounts = json.load(f)
    
    if not accounts:
        logger.error("❌ Нет аккаунтов в конфигурации")
        return
    
    logger.info(f"📋 Найдено {len(accounts)} аккаунтов")
    
    # Восстанавливаем сессии
    success_count = 0
    for i, account in enumerate(accounts, 1):
        logger.info(f"\n[{i}/{len(accounts)}] Обрабатываем: {account['session_name']}")
        
        if await restore_session(account):
            success_count += 1
        
        # Пауза между аккаунтами
        if i < len(accounts):
            await asyncio.sleep(2)
    
    logger.info(f"\n{'='*60}")
    logger.info(f"📊 Результаты: {success_count}/{len(accounts)} сессий восстановлено")
    logger.info(f"{'='*60}")

if __name__ == "__main__":
    asyncio.run(main())
