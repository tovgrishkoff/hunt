#!/usr/bin/env python3
"""
Scout (Парсер/Разведчик) - Поиск новых групп и добавление в БД
Работает с PostgreSQL через Async SQLAlchemy
"""
import asyncio
import logging
import sys
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from pathlib import Path

# Добавляем корень проекта в путь
sys.path.insert(0, '/app')

from lexus_db.session import AsyncSessionLocal, init_db
from lexus_db.models import Account, Target, Base
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/logs/scout.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class Scout:
    """Класс для поиска и добавления новых групп в БД"""
    
    def __init__(self, niche: str):
        """
        Args:
            niche: Ниша для поиска групп (например, 'ukraine_cars', 'bali_rent')
        """
        self.niche = niche
        self.project_name = os.getenv('PROJECT_NAME', 'default')
    
    async def search_groups(self, client, keywords: List[str], limit_per_keyword: int = 20) -> List[Dict[str, str]]:
        """
        Поиск новых групп через Telegram API
        
        Args:
            client: Telegram клиент для поиска
            keywords: Список ключевых слов для поиска
            limit_per_keyword: Максимум результатов на ключевое слово
        
        Returns:
            Список словарей с информацией о группах:
            [
                {'link': '@groupname', 'title': 'Group Title'},
                ...
            ]
        """
        from telethon.tl.functions.contacts import SearchRequest
        from telethon.errors import FloodWaitError, UsernameNotOccupiedError, ChannelPrivateError
        
        logger.info(f"🔍 Поиск групп для ниши: {self.niche}")
        found_groups = []
        
        # Слова для фильтрации мусора
        INAPPROPRIATE_KEYWORDS = [
            'порно', 'porn', 'xxx', '18+', 'взрослые', 'adult',
            'ставки', 'betting', 'казино', 'casino', 'покер', 'poker',
            'гемблинг', 'gambling', 'лотерея', 'lottery',
            'наркотики', 'drugs', 'cannabis', 'weed',
            'мошенничество', 'scam', 'обман',
            'продажа оружия', 'weapons', 'guns'
        ]
        
        def is_appropriate_group(title: str, username: str = None) -> bool:
            """Проверка, подходит ли группа (фильтр мусора)"""
            title_lower = (title or '').lower()
            username_lower = (username or '').lower()
            
            for keyword in INAPPROPRIATE_KEYWORDS:
                if keyword.lower() in title_lower or keyword.lower() in username_lower:
                    return False
            return True
        
        logger.info(f"🔍 Поиск групп по {len(keywords)} ключевым словам...")
        
        for keyword in keywords:
            try:
                logger.info(f"  Ищу по ключевому слову: '{keyword}'")
                
                if not client.is_connected():
                    logger.warning(f"  ⚠️ Client disconnected, attempting to reconnect...")
                    try:
                        await client.connect()
                        if not await client.is_user_authorized():
                            logger.error(f"  ❌ Client not authorized, skipping '{keyword}'")
                            continue
                    except Exception as reconnect_error:
                        logger.error(f"  ❌ Failed to reconnect: {reconnect_error}, skipping '{keyword}'")
                        continue
                
                results = await client(SearchRequest(
                    q=keyword,
                    limit=limit_per_keyword
                ))
                
                for chat in results.chats:
                    if not hasattr(chat, 'username') or not chat.username:
                        continue
                    # Каналы (broadcast): постить могут только админы — пропускаем
                    if getattr(chat, 'broadcast', False):
                        logger.debug(f"  ⏭️ Пропуск канала @{chat.username} (broadcast)")
                        continue

                    username = f"@{chat.username}"
                    title = getattr(chat, 'title', 'Unknown')
                    
                    # Проверяем фильтр мусора
                    if not is_appropriate_group(title, username):
                        logger.debug(f"  ⚠️ Пропускаем '{username}' - фильтр мусора")
                        continue
                    
                    # Проверяем, нет ли уже такой группы в БД
                    async with AsyncSessionLocal() as session:
                        stmt = select(Target).where(Target.username == username)
                        result = await session.execute(stmt)
                        existing = result.scalar_one_or_none()
                        
                        if existing:
                            logger.debug(f"  ℹ️ Группа {username} уже есть в БД")
                            continue
                    
                    # Добавляем группу (используем username, так как Target использует username)
                    found_groups.append({
                        'username': username,  # Target использует username
                        'title': title,
                    })
                    logger.info(f"  ✅ Найдена группа: {username} - {title}")
                
                # Пауза между поисками
                await asyncio.sleep(2)
                
            except FloodWaitError as e:
                wait_seconds = min(e.seconds, 3600)  # Максимум 1 час
                logger.warning(f"  ⏳ FloodWait {wait_seconds} секунд для '{keyword}'")
                await asyncio.sleep(wait_seconds)
                continue
            except Exception as e:
                logger.error(f"  ❌ Ошибка при поиске '{keyword}': {e}")
                continue
        
        logger.info(f"✅ Найдено новых групп: {len(found_groups)}")
        return found_groups
    
    async def search_and_save_groups(
        self,
        keywords: List[str],
        niche: str,
        allowed_sessions: Optional[List[str]] = None,
        client_manager = None
    ) -> int:
        """
        Поиск и сохранение групп в БД
        
        Args:
            keywords: Список ключевых слов для поиска
            niche: Ниша групп
            allowed_sessions: Список разрешенных session_name для поиска
            client_manager: TelegramClientManager для получения клиента
        
        Returns:
            Количество сохраненных групп
        """
        if not keywords:
            logger.warning("⚠️ No keywords provided for search")
            return 0
        
        # Получаем клиент для поиска
        # Если есть client_manager - используем его
        if client_manager and client_manager.clients:
            client_name = list(client_manager.clients.keys())[0]
            client = await client_manager.ensure_client_connected(client_name)
            if not client:
                logger.error(f"❌ Failed to connect client {client_name} for search")
                return 0
        else:
            # Создаем клиент напрямую из БД
            from lexus_db.models import Account
            async with AsyncSessionLocal() as session:
                if allowed_sessions:
                    stmt = select(Account).where(
                        Account.status == 'active',
                        Account.session_name.in_(allowed_sessions)
                    )
                else:
                    stmt = select(Account).where(Account.status == 'active')
                
                result = await session.execute(stmt)
                accounts = result.scalars().all()
                
                if not accounts:
                    logger.error("❌ No active accounts found for search")
                    return 0
                
                account = accounts[0]  # Берем первый доступный
                
                # Создаем клиент
                from telethon import TelegramClient
                from telethon.sessions import StringSession
                
                session_obj = StringSession(account.string_session.strip())
                client = TelegramClient(
                    session_obj,
                    int(account.api_id),
                    account.api_hash
                )
                await client.connect()
                
                if not await client.is_user_authorized():
                    logger.error(f"❌ Client {account.session_name} is not authorized")
                    await client.disconnect()
                    return 0
        
        try:
            # Поиск групп
            found_groups = await self.search_groups(client, keywords, limit_per_keyword=20)
            
            if not found_groups:
                logger.info("📭 Новых групп не найдено")
                return 0
            
            # Сохранение в БД
            async with AsyncSessionLocal() as session:
                saved_count = await self.save_groups_to_db(session, found_groups)
                return saved_count
        finally:
            if not client_manager or client_name not in client_manager.clients:
                # Закрываем клиент, если создавали его напрямую
                try:
                    if client.is_connected():
                        await client.disconnect()
                except:
                    pass
    
    def normalize_group_link(self, link: str) -> str:
        """
        Нормализация ссылки на группу
        
        Преобразует:
        - t.me/groupname -> @groupname
        - https://t.me/groupname -> @groupname
        - groupname -> @groupname
        - @groupname -> @groupname (без изменений)
        """
        link = link.strip()
        
        # Убираем протокол
        if link.startswith('https://'):
            link = link[8:]
        elif link.startswith('http://'):
            link = link[7:]
        
        # Убираем t.me/
        if link.startswith('t.me/'):
            link = link[5:]
        elif link.startswith('telegram.me/'):
            link = link[12:]
        
        # Добавляем @ если нужно
        if not link.startswith('@'):
            link = '@' + link
        
        return link
    
    async def save_groups_to_db(self, session: AsyncSession, groups: List[Dict[str, str]]) -> int:
        """
        Сохранение найденных групп в БД
        
        Группы добавляются со статусом 'new', чтобы Smart Joiner их подхватил
        
        Args:
            session: AsyncSession БД
            groups: Список групп для сохранения (должен содержать 'username' или 'link')
        
        Returns:
            Количество добавленных групп
        """
        if not groups:
            logger.info("📭 Нет групп для сохранения")
            return 0
        
        added_count = 0
        skipped_count = 0
        
        for group_info in groups:
            # Поддерживаем оба формата: 'username' или 'link'
            username = group_info.get('username') or group_info.get('link')
            title = group_info.get('title', '')
            
            if not username:
                logger.warning(f"⚠️ Пропускаем группу без username/link: {group_info}")
                skipped_count += 1
                continue
            
            # Нормализуем username (должен быть @username)
            if not username.startswith('@'):
                username = f"@{username.lstrip('@')}"
            
            # Проверяем, существует ли группа в БД
            stmt = select(Target).where(Target.username == username)
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            
            if existing:
                logger.debug(f"  ⏭️  Группа {username} уже существует в БД")
                skipped_count += 1
                continue
            
            # Создаем новую группу
            new_target = Target(
                username=username,  # Target использует username
                title=title,
                niche=self.niche,
                status='new',  # Статус 'new' - Smart Joiner подхватит
                can_post=True,
                warm_up_until=datetime.utcnow() - timedelta(hours=1)  # Warm-up уже прошел
            )
            
            session.add(new_target)
            added_count += 1
            logger.info(f"  ✅ Добавлена группа: {username} ({title})")
        
        await session.commit()
        
        logger.info(f"📊 Сохранено в БД: {added_count} новых групп, {skipped_count} уже существовали")
        return added_count
    
    async def run(self):
        """Запуск процесса поиска и сохранения групп"""
        logger.info("=" * 80)
        logger.info(f"🚀 SCOUT - ПОИСК ГРУПП")
        logger.info("=" * 80)
        logger.info(f"📋 Проект: {self.project_name}")
        logger.info(f"📋 Ниша: {self.niche}")
        logger.info("=" * 80)
        
        # Инициализация БД
        try:
            await init_db()
            logger.info("✅ База данных инициализирована")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка инициализации БД (возможно, уже инициализирована): {e}")
        
        try:
            # Импортируем здесь, чтобы избежать циклических зависимостей
            from shared.config.loader import ConfigLoader
            from shared.telegram.client_manager import TelegramClientManager
        except ImportError:
            ConfigLoader = None  # type: ignore[assignment]
            TelegramClientManager = None  # type: ignore[assignment]
        
        # Загружаем ключевые слова из конфига ниши (если возможно)
        keywords: List[str] = []
        if ConfigLoader is not None:
            try:
                config_loader = ConfigLoader()
                niche_config = config_loader.load_niche_config(self.niche)
                manager_cfg = niche_config.get("manager", {})
                cfg_keywords = manager_cfg.get("search_keywords", []) or []
                for kw in cfg_keywords:
                    kw = (kw or "").strip()
                    if kw and kw not in keywords:
                        keywords.append(kw)
            except Exception as e:  # noqa: BLE001
                logger.warning("⚠️ Failed to load niche config for scout: %s", e)
        
        if not keywords:
            logger.warning("⚠️ Нет ключевых слов для поиска — scout ничего не сделает")
            return
        
        # Загружаем клиентов (опционально) для повторного использования
        client_manager = None
        if TelegramClientManager is not None:
            try:
                client_manager = TelegramClientManager()
                # Используем sync SessionLocal здесь только для загрузки аккаунтов в клиент-менеджер
                from shared.database.session import SessionLocal as SyncSessionLocal
                sync_db = SyncSessionLocal()
                try:
                    # Для Lexus-проекта нам нужны только Lexus-аккаунты; в client_manager уже есть логика whitelist
                    asyncio.get_running_loop()
                    await client_manager.load_accounts_from_db(sync_db, exclude_lexus_accounts=False)
                finally:
                    sync_db.close()
            except Exception as e:  # noqa: BLE001
                logger.warning("⚠️ Не удалось инициализировать TelegramClientManager: %s", e)
                client_manager = None
        
        try:
            # Шаг 1: Поиск и сохранение групп через универсальный метод
            saved_count = await self.search_and_save_groups(
                keywords=keywords,
                niche=self.niche,
                allowed_sessions=None,
                client_manager=client_manager,
            )
            
            if saved_count == 0:
                logger.info("📭 Новых групп не сохранено (0)")
                return
            
            logger.info("=" * 80)
            logger.info("✅ SCOUT ЗАВЕРШЕН: Добавлено %d новых групп", saved_count)
            logger.info("=" * 80)
        
        except Exception as e:  # noqa: BLE001
            logger.error("❌ Ошибка при выполнении scout: %s", e, exc_info=True)
            raise


async def main():
    """Точка входа"""
    # Получаем нишу из аргументов или переменной окружения
    if len(sys.argv) > 1:
        niche = sys.argv[1]
    else:
        niche = os.getenv('NICHE', 'ukraine_cars')
        logger.info(f"Ниша не указана в аргументах, используем из ENV: {niche}")
    
    scout = Scout(niche=niche)
    await scout.run()


if __name__ == "__main__":
    asyncio.run(main())
