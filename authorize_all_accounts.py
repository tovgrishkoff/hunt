#!/usr/bin/env python3
"""
Скрипт для авторизации всех аккаунтов из accounts_config.json
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

async def authorize_account(account):
    """Авторизация одного аккаунта"""
    session_name = account['session_name']
    phone = account['phone']
    api_id = int(account['api_id'])
    api_hash = account['api_hash']
    string_session = account.get('string_session', '')
    
    logger.info(f"\n{'='*60}")
    logger.info(f"📱 Авторизация: {session_name}")
    logger.info(f"   Телефон: {phone}")
    logger.info(f"{'='*60}")
    
    # Пробуем использовать string_session, если есть
    if string_session:
        try:
            logger.info("🔄 Пробуем использовать string_session...")
            client = TelegramClient(StringSession(string_session), api_id, api_hash)
            await client.connect()
            
            if await client.is_user_authorized():
                me = await client.get_me()
                username = getattr(me, 'username', 'No username')
                logger.info(f"✅ Авторизован через string_session как @{username}")
                
                # Сохраняем сессию в файл
                await client.disconnect()
                client = TelegramClient(f"sessions/{session_name}", api_id, api_hash)
                await client.connect()
                if not await client.is_user_authorized():
                    # Копируем сессию из string_session
                    client.session = StringSession(string_session)
                    await client.connect()
                    await client.disconnect()
                    # Переподключаемся с файловой сессией
                    client = TelegramClient(f"sessions/{session_name}", api_id, api_hash)
                    await client.connect()
                
                me = await client.get_me()
                username = getattr(me, 'username', 'No username')
                logger.info(f"✅ Сессия сохранена в файл. Пользователь: @{username}")
                await client.disconnect()
                return True
        except Exception as e:
            logger.warning(f"⚠️ Не удалось использовать string_session: {e}")
            logger.info("📲 Переходим к обычной авторизации...")
    
    # Обычная авторизация через файловую сессию
    client = TelegramClient(f"sessions/{session_name}", api_id, api_hash)
    
    try:
        await client.connect()
        logger.info("✅ Подключение установлено")
        
        if await client.is_user_authorized():
            me = await client.get_me()
            username = getattr(me, 'username', 'No username')
            logger.info(f"✅ Уже авторизован как @{username}")
            await client.disconnect()
            return True
        
        logger.info("📲 Отправляем код авторизации...")
        await client.send_code_request(phone)
        logger.info(f"📨 Код отправлен на {phone}")
        
        # Запрашиваем код
        code = input(f"Введите код для {session_name} ({phone}): ").strip()
        
        try:
            await client.sign_in(phone, code)
            logger.info("✅ Авторизация успешна!")
        except Exception as e:
            error_str = str(e).lower()
            if "password" in error_str or "two-step" in error_str or "2fa" in error_str:
                logger.info("🔐 Требуется пароль 2FA")
                password = input(f"Введите пароль 2FA для {session_name}: ").strip()
                await client.sign_in(password=password)
                logger.info("✅ Авторизация с 2FA успешна!")
            else:
                raise
        
        # Проверяем авторизацию
        me = await client.get_me()
        username = getattr(me, 'username', 'No username')
        first_name = getattr(me, 'first_name', 'No name')
        logger.info(f"✅ Авторизован как {first_name} (@{username})")
        
        # Обновляем string_session в конфиге
        if hasattr(client.session, 'save'):
            try:
                session_string = client.session.save()
                account['string_session'] = session_string
                account['nickname'] = first_name
                logger.info("✅ String session обновлен в конфиге")
            except:
                pass
        
        await client.disconnect()
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка авторизации {session_name}: {e}")
        try:
            await client.disconnect()
        except:
            pass
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
    
    logger.info(f"📋 Найдено {len(accounts)} аккаунтов для авторизации")
    
    # Авторизуем каждый аккаунт
    success_count = 0
    for i, account in enumerate(accounts, 1):
        logger.info(f"\n[{i}/{len(accounts)}] Обрабатываем аккаунт: {account['session_name']}")
        
        if await authorize_account(account):
            success_count += 1
        
        # Небольшая пауза между аккаунтами
        if i < len(accounts):
            logger.info("⏳ Пауза 3 секунды перед следующим аккаунтом...")
            await asyncio.sleep(3)
    
    # Сохраняем обновленную конфигурацию
    with open(config_file, 'w', encoding='utf-8') as f:
        json.dump(accounts, f, indent=2, ensure_ascii=False)
    
    logger.info(f"\n{'='*60}")
    logger.info(f"📊 Результаты: {success_count}/{len(accounts)} аккаунтов авторизовано")
    logger.info(f"{'='*60}")

if __name__ == "__main__":
    asyncio.run(main())
