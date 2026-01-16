"""
Менеджер клиентов Telegram для всех микросервисов
"""
import os
import json
import asyncio
from pathlib import Path
from telethon import TelegramClient
from telethon.sessions import StringSession
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class TelegramClientManager:
    """Менеджер для создания и управления Telegram клиентами"""
    
    def __init__(self, sessions_dir: str = "/app/sessions"):
        self.sessions_dir = Path(sessions_dir)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.clients: Dict[str, TelegramClient] = {}
    
    def parse_proxy(self, proxy_string: Optional[str]):
        """Парсинг строки прокси"""
        if not proxy_string:
            return None
        
        try:
            # Формат: http://user:pass@host:port или socks5://user:pass@host:port
            if proxy_string.startswith('http://'):
                parts = proxy_string.replace('http://', '').split('@')
                if len(parts) == 2:
                    auth, addr = parts
                    user, pwd = auth.split(':')
                    host, port = addr.split(':')
                    return {
                        'proxy_type': 'http',
                        'addr': host,
                        'port': int(port),
                        'username': user,
                        'password': pwd
                    }
            elif proxy_string.startswith('socks5://'):
                parts = proxy_string.replace('socks5://', '').split('@')
                if len(parts) == 2:
                    auth, addr = parts
                    user, pwd = auth.split(':')
                    host, port = addr.split(':')
                    return {
                        'proxy_type': 'socks5',
                        'addr': host,
                        'port': int(port),
                        'username': user,
                        'password': pwd
                    }
        except Exception as e:
            logger.warning(f"Failed to parse proxy {proxy_string}: {e}")
        
        return None
    
    async def create_client(
        self,
        session_name: str,
        api_id: int,
        api_hash: str,
        string_session: Optional[str] = None,
        proxy: Optional[str] = None
    ) -> TelegramClient:
        """Создать клиент Telegram"""
        
        if session_name in self.clients:
            return self.clients[session_name]
        
        proxy_config = self.parse_proxy(proxy)
        
        # Приоритет: string_session > файловая сессия
        if string_session and string_session.strip() and string_session not in ['', 'null']:
            try:
                session_obj = StringSession(string_session.strip())
                client = TelegramClient(
                    session_obj,
                    api_id,
                    api_hash,
                    proxy=proxy_config
                )
                logger.info(f"Created client {session_name} with StringSession")
            except Exception as e:
                logger.error(f"Failed to create StringSession for {session_name}: {e}")
                # Fallback на файловую сессию
                session_path = self.sessions_dir / f"{session_name}.session"
                client = TelegramClient(
                    str(session_path),
                    api_id,
                    api_hash,
                    proxy=proxy_config
                )
        else:
            # Используем файловую сессию
            session_path = self.sessions_dir / f"{session_name}.session"
            client = TelegramClient(
                str(session_path),
                api_id,
                api_hash,
                proxy=proxy_config
            )
            logger.info(f"Created client {session_name} with file session: {session_path}")
        
        try:
            await client.connect()
            
            # Проверяем авторизацию
            if not await client.is_user_authorized():
                logger.warning(f"Client {session_name} is not authorized")
                await client.disconnect()
                return None
            
            self.clients[session_name] = client
            logger.info(f"✅ Client {session_name} connected and authorized")
            return client
        except Exception as e:
            logger.error(f"Failed to connect client {session_name}: {e}")
            # Пытаемся правильно закрыть соединение
            try:
                if client.is_connected():
                    await asyncio.wait_for(client.disconnect(), timeout=2.0)
            except Exception:
                pass
            return None
    
    async def get_client(self, session_name: str) -> Optional[TelegramClient]:
        """Получить существующий клиент"""
        return self.clients.get(session_name)
    
    async def ensure_client_connected(self, session_name: str) -> Optional[TelegramClient]:
        """Проверить подключенность клиента и переподключить при необходимости"""
        client = self.clients.get(session_name)
        if not client:
            logger.warning(f"Client {session_name} not found")
            return None
        
        try:
            if not client.is_connected():
                logger.info(f"Client {session_name} disconnected, reconnecting...")
                await client.connect()
                
                # Проверяем авторизацию после переподключения
                if not await client.is_user_authorized():
                    logger.warning(f"Client {session_name} is not authorized after reconnection")
                    return None
                
                logger.info(f"✅ Client {session_name} reconnected")
        except Exception as e:
            logger.error(f"Failed to reconnect client {session_name}: {e}")
            return None
        
        return client
    
    async def disconnect_all(self):
        """Отключить все клиенты"""
        for name, client in list(self.clients.items()):
            try:
                if client.is_connected():
                    await asyncio.wait_for(client.disconnect(), timeout=3.0)
                logger.info(f"Disconnected client {name}")
            except asyncio.TimeoutError:
                logger.warning(f"Timeout disconnecting {name}, forcing close")
                try:
                    client._sender.set_connection(None)
                except:
                    pass
            except Exception as e:
                logger.warning(f"Error disconnecting {name}: {e}")
        self.clients.clear()
    
    async def load_accounts_from_db(self, db_session, exclude_lexus_accounts: bool = True):
        """
        Загрузить аккаунты из БД и создать клиенты
        
        Args:
            db_session: Сессия базы данных
            exclude_lexus_accounts: Если True, исключает аккаунты из lexus_accounts_config.json
                                   (используется в Bali системе для разделения с Lexus)
        """
        from ..database.models import Account
        
        accounts = db_session.query(Account).filter(
            Account.status == 'active'
        ).all()
        
        # Загружаем список аккаунтов для фильтрации
        excluded_accounts = set()
        allowed_accounts = set()
        use_whitelist = False
        
        if exclude_lexus_accounts:
            # Сначала проверяем, есть ли whitelist для Bali
            bali_config_paths = [
                Path('/app/bali_accounts_config.json'),
                Path('bali_accounts_config.json'),
                Path('../bali_accounts_config.json'),
            ]
            
            for path in bali_config_paths:
                if path.exists():
                    try:
                        with open(path, 'r', encoding='utf-8') as f:
                            bali_config = json.load(f)
                            allowed_accounts = set(bali_config.get('allowed_accounts', []))
                            if allowed_accounts:
                                use_whitelist = True
                                logger.info(f"✅ Using Bali whitelist: {sorted(allowed_accounts)}")
                                break
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to load bali_accounts_config.json from {path}: {e}")
            
            # Если нет whitelist, используем blacklist (исключаем Lexus аккаунты)
            if not use_whitelist:
                lexus_config_paths = [
                    Path('/app/lexus_accounts_config.json'),
                    Path('lexus_accounts_config.json'),
                    Path('../lexus_accounts_config.json'),
                ]
                
                for path in lexus_config_paths:
                    if path.exists():
                        try:
                            with open(path, 'r', encoding='utf-8') as f:
                                lexus_config = json.load(f)
                                excluded_accounts = set(lexus_config.get('allowed_accounts', []))
                                if excluded_accounts:
                                    logger.info(f"⚠️ Excluding {len(excluded_accounts)} Lexus accounts from Bali: {sorted(excluded_accounts)}")
                                    break
                        except Exception as e:
                            logger.warning(f"⚠️ Failed to load lexus_accounts_config.json from {path}: {e}")
        
        loaded_count = 0
        failed_count = 0
        excluded_count = 0
        
        for account in accounts:
            # Фильтруем аккаунты: whitelist или blacklist
            if exclude_lexus_accounts:
                if use_whitelist:
                    # Используем whitelist: загружаем только разрешенные аккаунты
                    if account.session_name not in allowed_accounts:
                        excluded_count += 1
                        logger.debug(f"Skipping account (not in Bali whitelist): {account.session_name}")
                        continue
                else:
                    # Используем blacklist: исключаем аккаунты Lexus
                    if account.session_name in excluded_accounts:
                        excluded_count += 1
                        logger.debug(f"Skipping Lexus account: {account.session_name}")
                        continue
            
            try:
                client = await self.create_client(
                    session_name=account.session_name,
                    api_id=account.api_id,
                    api_hash=account.api_hash,
                    string_session=account.string_session,
                    proxy=account.proxy
                )
                if client:
                    loaded_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                logger.error(f"Failed to load account {account.session_name}: {e}")
                failed_count += 1
        
        if exclude_lexus_accounts and excluded_count > 0:
            logger.info(f"✅ Loaded {loaded_count} Bali accounts, {failed_count} failed, {excluded_count} excluded (Lexus)")
        else:
            logger.info(f"✅ Loaded {loaded_count} accounts, {failed_count} failed")

