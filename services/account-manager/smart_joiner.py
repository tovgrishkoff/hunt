"""
Smart Joiner - Безопасное вступление в группы с обработкой FloodWait
Работает с PostgreSQL через Async SQLAlchemy
"""
import asyncio
import random
import logging
import re
from datetime import datetime, timedelta
from typing import Optional, List, Tuple
from pathlib import Path

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import CheckChatInviteRequest, ImportChatInviteRequest
from telethon.tl.types import ChatInvite
from telethon.errors import (
    FloodWaitError,
    UserAlreadyParticipantError,
    UsernameNotOccupiedError,
    ChannelPrivateError,
    ChatAdminRequiredError,
    InviteHashExpiredError,
    InviteRequestSentError,
    ChatWriteForbiddenError,
    UserBannedInChannelError,
    RPCError
)

from lexus_db.session import AsyncSessionLocal
from lexus_db.models import Account, Target
from lexus_db.db_manager import DbManager
from sqlalchemy import select, and_, or_, func, case

logger = logging.getLogger(__name__)


class FloodWaitDetected(Exception):
    """Исключение для обнаруженного FloodWait в тексте ошибки"""
    def __init__(self, seconds: int):
        self.seconds = seconds
        super().__init__(f"FloodWait detected: {seconds} seconds")


class SmartJoiner:
    """Класс для безопасного вступления в группы с обработкой FloodWait"""
    
    def __init__(self, accounts_config_path: str = 'accounts_config.json', allowed_sessions: Optional[List[str]] = None):
        """
        Args:
            accounts_config_path: Путь к файлу конфигурации аккаунтов (JSON)
            allowed_sessions: Список разрешенных session_name для вступления (например, для Lexus)
        """
        self.accounts_config_path = Path(accounts_config_path)
        self.accounts_config = self._load_accounts_config()
        self.allowed_sessions = set(allowed_sessions or [])
    
    def _load_accounts_config(self) -> dict:
        """Загрузка конфигурации аккаунтов из JSON"""
        import json
        try:
            if self.accounts_config_path.exists():
                with open(self.accounts_config_path, 'r', encoding='utf-8') as f:
                    accounts_list = json.load(f)
                # Преобразуем список в словарь {session_name: account_config}
                return {acc['session_name']: acc for acc in accounts_list}
            else:
                logger.warning(f"⚠️ Accounts config file not found: {self.accounts_config_path}")
                return {}
        except Exception as e:
            logger.error(f"❌ Failed to load accounts config: {e}")
            return {}
    
    async def get_available_account(self, session, exclude_account_ids: List[int] = None) -> Optional[Account]:
        """
        Получить доступный аккаунт из БД
        
        Условия:
        - status == 'active'
        - next_allowed_action_time < NOW() или NULL
        - session_name в allowed_sessions (если задано)
        
        Args:
            session: AsyncSession БД
            exclude_account_ids: Список ID аккаунтов для исключения
        
        Returns:
            Account или None
        """
        now = datetime.utcnow()
        
        stmt = select(Account).where(
            and_(
                Account.status == 'active',
                or_(
                    Account.next_allowed_action_time.is_(None),
                    Account.next_allowed_action_time < now
                )
            )
        )
        
        # Фильтруем по allowed_sessions, если задано
        if self.allowed_sessions:
            logger.debug(f"🔍 Filtering by allowed_sessions: {sorted(self.allowed_sessions)}")
            stmt = stmt.where(Account.session_name.in_(self.allowed_sessions))
        
        if exclude_account_ids:
            logger.debug(f"🔍 Excluding account IDs: {exclude_account_ids}")
            stmt = stmt.where(~Account.id.in_(exclude_account_ids))
        
        # Ротация: выбираем среди доступных случайно (равномерное распределение по аккаунтам)
        stmt = stmt.order_by(func.random())
        
        result = await session.execute(stmt)
        accounts = result.scalars().all()
        
        if not accounts:
            # Логируем причину отсутствия аккаунтов
            all_accounts_stmt = select(Account).where(Account.status == 'active')
            all_result = await session.execute(all_accounts_stmt)
            all_accounts = all_result.scalars().all()
            logger.warning(
                f"⚠️ No available accounts found. "
                f"Total active accounts: {len(all_accounts)}, "
                f"Allowed sessions: {sorted(self.allowed_sessions) if self.allowed_sessions else 'all'}, "
                f"Excluded IDs: {exclude_account_ids or []}"
            )
            return None
        
        logger.debug(f"✅ Found {len(accounts)} available account(s), using: {accounts[0].session_name}")
        # Возвращаем первый доступный (можно добавить логику балансировки)
        return accounts[0]
    
    async def create_client(self, account: Account) -> Optional[TelegramClient]:
        """
        Создать TelegramClient для аккаунта
        
        Args:
            account: Account из БД
        
        Returns:
            TelegramClient или None
        """
        session_name = account.session_name
        
        # Получаем конфигурацию аккаунта (из JSON или из БД)
        account_config = self.accounts_config.get(session_name, {})
        
        # Используем данные из БД, если они есть, иначе из конфига
        api_id = account.api_id or account_config.get('api_id')
        api_hash = account.api_hash or account_config.get('api_hash')
        string_session = account.string_session or account_config.get('string_session')
        proxy = account.proxy or account_config.get('proxy')
        
        if not all([api_id, api_hash, string_session]):
            logger.error(f"❌ Missing required fields for {session_name} (api_id={bool(api_id)}, api_hash={bool(api_hash)}, string_session={bool(string_session)})")
            return None
        
        # Парсим прокси
        proxy_config = None
        if proxy:
            proxy_config = self._parse_proxy(proxy)
        
        try:
            # Создаем клиент
            session_obj = StringSession(string_session.strip())
            client = TelegramClient(
                session_obj,
                int(api_id),
                api_hash,
                proxy=proxy_config
            )
            
            await client.connect()
            
            if not await client.is_user_authorized():
                logger.warning(f"⚠️ Client {session_name} is not authorized")
                await client.disconnect()
                return None
            
            logger.debug(f"✅ Client {session_name} connected")
            return client
            
        except Exception as e:
            logger.error(f"❌ Failed to create client for {session_name}: {e}")
            return None
    
    def _parse_proxy(self, proxy_string: str) -> Optional[dict]:
        """
        Парсинг строки прокси
        
        Форматы:
        - socks5://user:pass@host:port
        - http://user:pass@host:port
        
        Returns:
            Словарь с настройками прокси или None
        """
        try:
            from urllib.parse import urlparse
            
            parsed = urlparse(proxy_string)
            
            proxy_type = parsed.scheme
            if proxy_type == 'socks5':
                return {
                    'proxy_type': 'socks5',
                    'addr': parsed.hostname,
                    'port': parsed.port,
                    'username': parsed.username,
                    'password': parsed.password
                }
            elif proxy_type in ['http', 'https']:
                return {
                    'proxy_type': 'http',
                    'addr': parsed.hostname,
                    'port': parsed.port,
                    'username': parsed.username,
                    'password': parsed.password
                }
        except Exception as e:
            logger.warning(f"⚠️ Failed to parse proxy {proxy_string}: {e}")
        
        return None
    
    async def check_can_post(self, client: TelegramClient, entity) -> Tuple[bool, Optional[str]]:
        """
        Проверка прав на отправку сообщений в группе
        
        Args:
            client: TelegramClient
            entity: Entity группы/канала
        
        Returns:
            (can_post: bool, error_message: Optional[str])
        """
        try:
            me = await client.get_me()
            permissions = await client.get_permissions(entity, me)
            
            if permissions:
                # Проверяем право на отправку сообщений
                if hasattr(permissions, 'send_messages'):
                    if not permissions.send_messages:
                        return False, "Запрещено отправлять сообщения"
                # Проверяем через banned_rights
                elif hasattr(permissions, 'banned_rights') and permissions.banned_rights:
                    if hasattr(permissions.banned_rights, 'send_messages'):
                        if permissions.banned_rights.send_messages:
                            return False, "Запрещено отправлять сообщения (banned_rights)"
            
            return True, None
        except (ChatWriteForbiddenError, UserBannedInChannelError):
            return False, "Запрещено отправлять сообщения"
        except Exception as e:
            err = str(e).lower()
            if "not a member" in err or "getparticipant" in err:
                logger.warning(f"  ⚠️ Пользователь не участник чата (get_permissions): {e}")
                return False, "Not a member (verification failed)"
            logger.warning(f"  ⚠️ Не удалось проверить права: {e}")
            return False, str(e)
    
    async def join_group(
        self,
        client: TelegramClient,
        account: Account,
        target: Target
    ) -> Tuple[bool, Optional[str]]:
        """
        Вступление в группу с проверкой прав на отправку сообщений
        
        Args:
            client: TelegramClient
            account: Account из БД
            target: Target (группа) из БД
        
        Returns:
            (success: bool, error_message: Optional[str])
        """
        group_link = target.link
        
        try:
            logger.info(f"  🚪 Вступаю в {group_link} через {account.session_name}...")
            
            # Проверяем, это приватная группа (invite link) или публичная
            if '+' in group_link or 'joinchat' in group_link.lower():
                # Приватная группа через invite link
                # Форматы: t.me/+AbCdE..., t.me/joinchat/AbCdE...
                invite_hash = None
                if '+' in group_link:
                    invite_hash = group_link.split('+')[-1].split('/')[-1]
                elif 'joinchat' in group_link.lower():
                    parts = group_link.split('/')
                    if 'joinchat' in parts:
                        idx = parts.index('joinchat')
                        if idx + 1 < len(parts):
                            invite_hash = parts[idx + 1]
                
                if not invite_hash:
                    error_msg = f"Не удалось извлечь invite hash из ссылки {group_link}"
                    logger.warning(f"  ⚠️ {error_msg}")
                    return False, error_msg
                
                logger.info(f"  🔗 Используем invite link (hash: {invite_hash[:20]}...)")
                
                try:
                    # Проверяем invite
                    invite = await client(CheckChatInviteRequest(invite_hash))
                    
                    if isinstance(invite, ChatInvite):
                        # Нужно принять приглашение
                        await client(ImportChatInviteRequest(invite_hash))
                        logger.info(f"  ✅ Вступил в группу через invite link")
                        return True, None
                    else:
                        # Уже участник
                        logger.info(f"  ℹ️ Уже участник группы (через invite)")
                        return True, None
                        
                except InviteHashExpiredError:
                    error_msg = f"Invite hash истек для {group_link}"
                    logger.warning(f"  ⚠️ {error_msg}")
                    return False, error_msg
                except UserAlreadyParticipantError:
                    logger.info(f"  ℹ️ Уже участник группы")
                    return True, None
                except FloodWaitError as e:
                    # FloodWait обрабатывается на уровне выше
                    raise e
                except RPCError as e:
                    error_msg = str(e)
                    logger.warning(f"  ⚠️ Ошибка RPC при вступлении через invite: {error_msg}")
                    return False, error_msg
            
            else:
                # Публичная группа через username
                username = group_link.lstrip('@')
                
                # Получаем entity группы
                try:
                    entity = await client.get_entity(group_link)
                except UsernameNotOccupiedError:
                    error_msg = f"Группа {group_link} не найдена"
                    logger.warning(f"  ⚠️ {error_msg}")
                    return False, error_msg
                except ChannelPrivateError:
                    error_msg = f"Группа {group_link} приватная (нужен invite link)"
                    logger.warning(f"  ⚠️ {error_msg}")
                    return False, error_msg
                
                # Вступаем в группу (как в Bali joiner: проверка заявки и верификация участника)
                try:
                    updates = await client(JoinChannelRequest(entity))
                    # Если в ответе чат с left=True — мы не вступили, только заявка отправлена
                    if updates and getattr(updates, "chats", None):
                        for c in updates.chats:
                            if getattr(c, "left", False):
                                logger.info(f"  📤 JoinChannelRequest: чат с left=True — заявка отправлена, ждём одобрения")
                                return False, "Waiting for approval"
                    # Проверяем, действительно ли мы участники (не попали в заявки)
                    can_post, post_error = await self.check_can_post(client, entity)
                    if not can_post:
                        logger.warning(f"  ⚠️ НЕЛЬЗЯ ПОСТИТЬ / не участник в {group_link}: {post_error}")
                        return False, post_error
                    logger.info(f"  ✅ Вступил в {group_link}, можно постить")
                    return True, None
                except InviteRequestSentError:
                    logger.info(f"  📤 InviteRequestSentError: заявка на вступление отправлена в {group_link}")
                    return False, "Waiting for approval"
                except UserAlreadyParticipantError:
                    logger.info(f"  ℹ️ Уже участник {group_link}")
                    
                    # Проверяем права на отправку сообщений (и что мы реально участники)
                    can_post, post_error = await self.check_can_post(client, entity)
                    if not can_post:
                        logger.warning(f"  ⚠️ НЕЛЬЗЯ ПОСТИТЬ в {group_link}: {post_error}")
                        return False, post_error
                    
                    logger.info(f"  ✅ МОЖНО ПОСТИТЬ в {group_link}")
                    return True, None
                except FloodWaitError as e:
                    # FloodWait обрабатывается на уровне выше
                    raise e
                except ChatAdminRequiredError:
                    error_msg = "Требуются права администратора"
                    logger.warning(f"  ⚠️ {error_msg}")
                    return False, error_msg
                except RPCError as e:
                    error_msg = str(e)
                    logger.warning(f"  ⚠️ Ошибка RPC: {error_msg}")
                    return False, error_msg
            
        except Exception as e:
            error_msg = str(e)
            error_lower = error_msg.lower()
            
            # Проверяем на FloodWait в тексте ошибки (может быть обернуто в Exception)
            if 'wait' in error_lower and ('required' in error_lower or 'seconds' in error_lower):
                # Извлекаем количество секунд из сообщения
                wait_match = re.search(r'wait of (\d+) seconds', error_msg, re.IGNORECASE)
                if wait_match:
                    wait_seconds = int(wait_match.group(1))
                    # Выбрасываем специальное исключение, которое обработается на уровне выше
                    raise FloodWaitDetected(wait_seconds)
            
            error_msg = f"Unexpected error: {error_msg}"
            logger.error(f"  ❌ {error_msg}")
            return False, error_msg
    
    async def run_batch(self, niche: str = 'ukraine_cars', batch_size: int = 5):
        """
        Запуск батча вступлений
        
        Алгоритм:
        1. Выбрать 5 групп со status='new' и niche=niche
        2. Для каждой группы:
           - Выбрать доступный аккаунт
           - Попытка вступления
           - Обработка FloodWait (<=600 сек vs >600 сек)
           - При успехе: привязка группы к аккаунту, warm-up 24 часа
           - Пауза 5-10 минут между успешными вступлениями
        
        Args:
            niche: Ниша групп (по умолчанию 'ukraine_cars')
            batch_size: Размер батча (по умолчанию 5)
        """
        logger.info("=" * 80)
        logger.info("🚀 SMART JOINER - БАТЧ ВСТУПЛЕНИЙ")
        logger.info("=" * 80)
        logger.info(f"📋 Ниша: {niche}")
        logger.info(f"📊 Размер батча: {batch_size}")
        logger.info("=" * 80)
        
        async with AsyncSessionLocal() as session:
            db_manager = DbManager(session)
            
            # ШАГ 1: Получаем группы для вступления
            # Берём: status='new' ИЛИ status='error' (повтор не раньше чем через 24 ч)
            retry_after = datetime.utcnow() - timedelta(hours=24)
            stmt = (
                select(Target)
                .where(
                    and_(
                        Target.niche == niche,
                        or_(
                            Target.status == 'new',
                            and_(
                                Target.status == 'error',
                                Target.updated_at < retry_after
                            )
                        )
                    )
                )
                .order_by(case((Target.status == 'new', 0), else_=1), Target.updated_at.asc())
                .limit(batch_size)
            )
            
            result = await session.execute(stmt)
            targets = result.scalars().all()
            
            if not targets:
                logger.info("✅ Нет групп для вступления (status='new' или 'error' для повтора)")
                return
            
            new_count = sum(1 for t in targets if t.status == 'new')
            error_retry_count = len(targets) - new_count
            logger.info(
                f"📋 Найдено {len(targets)} групп для вступления "
                f"(new: {new_count}, повтор error: {error_retry_count})"
            )
            
            # ШАГ 2: Цикл обработки групп
            # Очищаем excluded_account_ids в начале каждого батча
            excluded_account_ids = []
            
            for idx, target in enumerate(targets, 1):
                logger.info(f"\n{'='*60}")
                logger.info(
                    f"📋 [{idx}/{len(targets)}] Группа: {target.link}"
                    + (f" (повтор, был status=error)" if target.status == 'error' else "")
                )
                logger.info(f"{'='*60}")
                
                # Получаем доступный аккаунт
                account = await self.get_available_account(session, exclude_account_ids=excluded_account_ids)
                
                if not account:
                    logger.warning(f"  ⚠️ Нет доступных аккаунтов, пропускаем группу {target.link}")
                    continue
                
                logger.info(f"  👤 Используем аккаунт: {account.session_name} (id={account.id})")
                
                # Создаем клиент
                client = await self.create_client(account)
                if not client:
                    logger.error(f"  ❌ Не удалось создать клиент для {account.session_name}")
                    excluded_account_ids.append(account.id)
                    continue
                
                try:
                    # Попытка вступления
                    success, error_message = await self.join_group(client, account, target)
                    
                    if success:
                        # УСПЕШНОЕ ВСТУПЛЕНИЕ
                        now = datetime.utcnow()
                        
                        # Привязываем группу к аккаунту
                        await db_manager.assign_group(
                            group_link=target.link,
                            account_id=account.id,
                            joined_at=now
                        )
                        
                        logger.info(f"  ✅ Группа {target.link} привязана к аккаунту {account.session_name}")
                        logger.info(f"  ⏰ Warm-up период: 24 часа (до {now + timedelta(hours=24)})")
                        
                        # PAUSE: 5-10 минут перед следующей группой
                        pause_seconds = random.randint(300, 600)
                        logger.info(f"  ⏸️  Пауза {pause_seconds} сек ({pause_seconds // 60} мин) перед следующей группой...")
                        await asyncio.sleep(pause_seconds)
                        
                    else:
                        # ОШИБКА ВСТУПЛЕНИЯ
                        # Обновляем статус группы
                        target.status = 'error'
                        target.error_message = error_message
                        target.updated_at = datetime.utcnow()
                        await session.commit()
                        
                        logger.warning(f"  ⚠️ Ошибка вступления: {error_message}")
                        
                        # PAUSE: короткая пауза 60 секунд
                        logger.info(f"  ⏸️  Короткая пауза 60 сек...")
                        await asyncio.sleep(60)
                
                except (FloodWaitError, FloodWaitDetected) as e:
                    # ОБРАБОТКА FLOOD_WAIT (как из FloodWaitError, так и из текста ошибки)
                    wait_seconds = e.seconds
                    wait_until = datetime.utcnow() + timedelta(seconds=wait_seconds)
                    
                    # Обновляем FloodWait в БД для любого FloodWait
                    await db_manager.set_account_flood_wait(account.id, wait_until)
                    
                    if wait_seconds <= 600:  # <= 10 минут
                        # Короткий FloodWait - исключаем из текущего батча, переключаемся на другой аккаунт
                        excluded_account_ids.append(account.id)
                        
                        logger.warning(f"  ⏳ FloodWait {wait_seconds} сек ({wait_seconds // 60} мин)")
                        logger.warning(f"  🔄 Исключаем аккаунт {account.session_name} из текущего батча")
                        logger.info(f"  ⏭️  Пропускаем группу {target.link}, пробуем другой аккаунт для следующей группы")
                        
                        # НЕ ждем - сразу переходим к следующей группе с другим аккаунтом
                        
                    else:  # > 600 секунд (10 минут)
                        # Долгий FloodWait - помечаем аккаунт как cooldown и пропускаем группу
                        from sqlalchemy import update
                        stmt = (
                            update(Account)
                            .where(Account.id == account.id)
                            .values(status='cooldown')
                        )
                        await session.execute(stmt)
                        await session.commit()
                        
                        excluded_account_ids.append(account.id)
                        
                        logger.warning(f"  ⚠️ ДОЛГИЙ FloodWait {wait_seconds} сек ({wait_seconds // 60} мин)!")
                        logger.warning(f"  🔒 Аккаунт {account.session_name} переведен в cooldown до {wait_until}")
                        logger.info(f"  ⏭️  Пропускаем группу {target.link}, пробуем другой аккаунт для следующей")
                
                except Exception as e:
                    logger.error(f"  ❌ Неожиданная ошибка при вступлении: {e}", exc_info=True)
                    
                    # Помечаем группу как ошибка
                    target.status = 'error'
                    target.error_message = f"Unexpected error: {str(e)}"
                    target.updated_at = datetime.utcnow()
                    await session.commit()
                    
                    await asyncio.sleep(60)
                
                finally:
                    # Закрываем клиент
                    try:
                        if client and client.is_connected():
                            await client.disconnect()
                    except:
                        pass
            
            logger.info("\n" + "=" * 80)
            logger.info("✅ БАТЧ ВСТУПЛЕНИЙ ЗАВЕРШЕН")
            logger.info("=" * 80)


async def main():
    """Точка входа для запуска скрипта"""
    import sys
    
    # Настройка логирования
    log_dir = Path('logs')
    try:
        log_dir.mkdir(exist_ok=True)
        log_file = log_dir / 'smart_joiner.log'
        handlers = [
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    except (OSError, PermissionError):
        # Если не можем создать директорию или файл, используем только консоль
        handlers = [logging.StreamHandler()]
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=handlers
    )
    
    # Парсинг аргументов
    niche = 'ukraine_cars'
    batch_size = 5
    
    if len(sys.argv) > 1:
        niche = sys.argv[1]
    if len(sys.argv) > 2:
        batch_size = int(sys.argv[2])
    
    # Запуск
    joiner = SmartJoiner()
    await joiner.run_batch(niche=niche, batch_size=batch_size)


if __name__ == "__main__":
    asyncio.run(main())
