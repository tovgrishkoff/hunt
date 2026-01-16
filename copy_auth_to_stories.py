#!/usr/bin/env python3
"""
Копирование авторизованных сессий для stories-viewer
Использует string_session из accounts_config.json
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


async def copy_sessions_from_string():
    """Создание stories сессий из string_session"""
    
    # Создаём папку для stories сессий
    Path("sessions_stories").mkdir(exist_ok=True)
    
    # Загружаем конфигурацию
    with open('accounts_config.json', 'r', encoding='utf-8') as f:
        accounts = json.load(f)
    
    logger.info(f"✅ Загружено {len(accounts)} аккаунтов")
    
    for account in accounts:
        session_name = f"stories_{account['session_name']}"
        api_id = int(account['api_id'])
        api_hash = account['api_hash']
        string_session = account.get('string_session', '')
        
        if not string_session:
            logger.warning(f"⚠️ Нет string_session для {account['session_name']}")
            continue
        
        logger.info(f"\n{'='*60}")
        logger.info(f"📱 Создание сессии: {session_name}")
        logger.info(f"{'='*60}")
        
        try:
            # Подключаемся через string session
            client = TelegramClient(
                StringSession(string_session),
                api_id,
                api_hash
            )
            
            await client.connect()
            
            if await client.is_user_authorized():
                me = await client.get_me()
                username = getattr(me, 'username', 'No username')
                logger.info(f"✅ Авторизован как @{username}")
                
                # Создаём новый файл сессии
                file_client = TelegramClient(
                    f"sessions_stories/{session_name}",
                    api_id,
                    api_hash
                )
                
                # Копируем авторизацию
                await file_client.connect()
                await file_client.start(
                    phone=lambda: None,
                    code_callback=lambda: None
                )
                
                # Переносим auth_key
                file_client.session.auth_key = client.session.auth_key
                file_client.session.save()
                
                logger.info(f"✅ Сессия сохранена: sessions_stories/{session_name}.session")
                
                await file_client.disconnect()
            else:
                logger.error(f"❌ String session не авторизован для {account['session_name']}")
            
            await client.disconnect()
            
        except Exception as e:
            logger.error(f"❌ Ошибка для {account['session_name']}: {e}")
            import traceback
            traceback.print_exc()
    
    logger.info("\n✅ Создание сессий завершено!")
    logger.info("Теперь перезапустите контейнер stories-viewer:")
    logger.info("  cd /home/tovgrishkoff/PIAR/telegram_promotion_system")
    logger.info("  docker-compose restart stories-viewer")


if __name__ == '__main__':
    asyncio.run(copy_sessions_from_string())

















