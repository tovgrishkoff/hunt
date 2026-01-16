"""
Утилита для конвертации .session файлов в StringSession
"""
import asyncio
from pathlib import Path
from telethon import TelegramClient
from telethon.sessions import StringSession
import logging

logger = logging.getLogger(__name__)


async def convert_session_to_string(
    session_file: Path,
    api_id: int,
    api_hash: str,
    proxy: str = None
) -> str:
    """
    Конвертирует .session файл в StringSession
    
    Args:
        session_file: Путь к .session файлу
        api_id: API ID
        api_hash: API Hash
        proxy: Прокси (опционально)
    
    Returns:
        StringSession в виде строки
    """
    try:
        # Парсим прокси если указан
        proxy_config = None
        if proxy:
            if proxy.startswith('http://'):
                parts = proxy.replace('http://', '').split('@')
                if len(parts) == 2:
                    auth, addr = parts
                    user, pwd = auth.split(':')
                    host, port = addr.split(':')
                    proxy_config = {
                        'proxy_type': 'http',
                        'addr': host,
                        'port': int(port),
                        'username': user,
                        'password': pwd
                    }
        
        # Создаем клиент из файловой сессии
        client = TelegramClient(
            str(session_file),
            api_id,
            api_hash,
            proxy=proxy_config
        )
        
        # Подключаемся
        await client.connect()
        
        # Проверяем авторизацию
        if not await client.is_user_authorized():
            logger.error(f"Session {session_file} is not authorized")
            await client.disconnect()
            return None
        
        # Получаем StringSession
        string_session = client.session.save()
        
        await client.disconnect()
        
        logger.info(f"✅ Converted {session_file.name} to StringSession")
        return string_session
        
    except Exception as e:
        logger.error(f"❌ Failed to convert {session_file}: {e}")
        return None

