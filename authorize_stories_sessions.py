#!/usr/bin/env python3
"""
Авторизация сессий для просмотра Stories
"""

import asyncio
import json
import logging
from pathlib import Path
from telethon import TelegramClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def authorize_story_sessions():
    """Авторизация сессий stories"""
    
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
        phone = account['phone']
        
        logger.info(f"\n{'='*60}")
        logger.info(f"📱 Авторизация: {session_name}")
        logger.info(f"   Телефон: {phone}")
        logger.info(f"{'='*60}")
        
        client = TelegramClient(
            f"sessions_stories/{session_name}",
            api_id,
            api_hash
        )
        
        await client.connect()
        
        if not await client.is_user_authorized():
            logger.info("❌ Требуется авторизация")
            
            try:
                await client.send_code_request(phone)
                logger.info(f"📨 Код отправлен на {phone}")
                
                code = input(f"Введите код для {phone}: ").strip()
                
                try:
                    await client.sign_in(phone, code)
                    logger.info("✅ Авторизация успешна!")
                except Exception as e:
                    if "Two-steps" in str(e) or "password" in str(e).lower():
                        password = input("Введите 2FA пароль: ").strip()
                        await client.sign_in(password=password)
                        logger.info("✅ Авторизация с 2FA успешна!")
                    else:
                        raise
                
                # Проверка
                me = await client.get_me()
                username = getattr(me, 'username', 'No username')
                logger.info(f"✅ Авторизован как @{username}")
                
            except Exception as e:
                logger.error(f"❌ Ошибка авторизации: {e}")
        else:
            me = await client.get_me()
            username = getattr(me, 'username', 'No username')
            logger.info(f"✅ Уже авторизован как @{username}")
        
        await client.disconnect()
    
    logger.info("\n✅ Авторизация завершена!")
    logger.info("Теперь перезапустите контейнер stories-viewer:")
    logger.info("  cd /home/tovgrishkoff/PIAR/telegram_promotion_system")
    logger.info("  docker-compose restart stories-viewer")


if __name__ == '__main__':
    asyncio.run(authorize_story_sessions())

















