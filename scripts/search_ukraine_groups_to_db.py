#!/usr/bin/env python3
"""
Скрипт поиска групп по ключевым словам для Ukraine проекта
Находит группы и сохраняет их в БД со статусом 'new' для последующего вступления
"""
import sys
import os
import asyncio
import logging
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Устанавливаем переменные для Ukraine БД
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://telegram_user_ukraine:telegram_password_ukraine@localhost:5439/ukraine_db'
os.environ['POSTGRES_HOST'] = 'localhost'
os.environ['POSTGRES_PORT'] = '5439'
os.environ['POSTGRES_USER'] = 'telegram_user_ukraine'
os.environ['POSTGRES_PASSWORD'] = 'telegram_password_ukraine'
os.environ['POSTGRES_DB'] = 'ukraine_db'
os.environ['NICHE'] = 'ukraine_cars'
os.environ['PROJECT_NAME'] = 'ukraine'

from lexus_db.models import Account, Target
from lexus_db.session import AsyncSessionLocal
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.contacts import SearchRequest
from sqlalchemy import select

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Ключевые слова для поиска украинских групп по продаже автомобилей
SEARCH_KEYWORDS = [
    # Украинские варианты
    'україна авто',
    'україна автомобілі',
    'продаж авто україна',
    'купити авто україна',
    'авто україна продаж',
    'автомобілі україна',
    'київ авто продаж',
    'київ купити авто',
    'одеса авто продаж',
    'харків авто продаж',
    'львів авто продаж',
    'дніпро авто продаж',
    'авто б/у україна',
    'авто бу україна',
    'авто з пробігом україна',
    # Русские варианты
    'украина авто',
    'украина автомобили',
    'продажа авто украина',
    'купить авто украина',
    'авто украина продажа',
    'автомобили украина',
    'киев авто продажа',
    'киев купить авто',
    'одесса авто продажа',
    'харьков авто продажа',
    'львов авто продажа',
    'днепр авто продажа',
    'авто б/у украина',
    'авто бу украина',
    'авто с пробегом украина',
    'авто украина объявления',
    'автомобили украина объявления',
    # Английские варианты
    'ukraine cars',
    'ukraine car sale',
    'ukraine auto',
    'ukraine automobile',
    'kyiv cars',
    'kyiv car sale',
    'odessa cars',
    'kharkiv cars',
    # Группы по городам
    'київ купити продати авто',
    'одеса купити продати авто',
    'харків купити продати авто',
    'львів купити продати авто',
    'киев купить продать авто',
    'одесса купить продать авто',
    'харьков купить продать авто',
    'львов купить продать авто',
]


def normalize_group_link(link: str) -> str:
    """Нормализация ссылки на группу"""
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
    
    return link.lower()


async def search_and_save_groups():
    """Поиск групп по ключевым словам и сохранение в БД"""
    logger.info("=" * 80)
    logger.info("🔍 ПОИСК ГРУПП ПО КЛЮЧЕВЫМ СЛОВАМ (UKRAINE)")
    logger.info("=" * 80)
    
    ukraine_accounts = ['promotion_dao_bro', 'promotion_alex_ever', 'promotion_rod_shaihutdinov']
    
    async with AsyncSessionLocal() as session:
        # Получаем аккаунты из БД
        result = await session.execute(
            select(Account).where(Account.session_name.in_(ukraine_accounts))
        )
        accounts = result.scalars().all()
        
        if not accounts:
            logger.error("❌ Ukraine аккаунты не найдены в БД")
            return
        
        logger.info(f"✅ Найдено {len(accounts)} Ukraine аккаунтов")
        
        # Используем первый аккаунт для поиска
        account = accounts[0]
        if not account.string_session:
            logger.error(f"❌ У {account.session_name} нет string_session")
            return
        
        try:
            session_obj = StringSession(account.string_session.strip())
            client = TelegramClient(
                session_obj,
                account.api_id,
                account.api_hash
            )
            await client.connect()
            
            if not await client.is_user_authorized():
                logger.error(f"❌ {account.session_name} не авторизован")
                await client.disconnect()
                return
            
            logger.info(f"✅ Подключен аккаунт для поиска: {account.session_name}")
            
            found_groups = set()  # Для избежания дубликатов
            total_found = 0
            total_added = 0
            total_skipped = 0
            
            # Поиск групп по ключевым словам
            logger.info(f"\n🔍 Начинаю поиск по {len(SEARCH_KEYWORDS)} ключевым словам...")
            
            for keyword in SEARCH_KEYWORDS:
                try:
                    logger.info(f"  Ищу по ключевому слову: '{keyword}'")
                    
                    results = await client(SearchRequest(
                        q=keyword,
                        limit=20
                    ))
                    
                    for chat in results.chats:
                        if hasattr(chat, 'username') and chat.username:
                            username = f"@{chat.username.lower()}"
                            
                            if username not in found_groups:
                                found_groups.add(username)
                                total_found += 1
                                
                                title = getattr(chat, 'title', 'Unknown')
                                
                                # Проверяем, существует ли группа в БД
                                result = await session.execute(
                                    select(Target).where(Target.username == username)
                                )
                                existing = result.scalar_one_or_none()
                                
                                if existing:
                                    # Обновляем нишу, если нужно
                                    if existing.niche != 'ukraine_cars':
                                        existing.niche = 'ukraine_cars'
                                        existing.updated_at = datetime.utcnow()
                                        await session.commit()
                                    total_skipped += 1
                                    logger.debug(f"    ⏭️  Пропущена (уже есть): {title} ({username})")
                                else:
                                    # Создаем новую группу со статусом 'new'
                                    new_group = Target(
                                        username=username,
                                        title=title,
                                        niche='ukraine_cars',
                                        status='new',  # Статус 'new' - для последующего вступления
                                        created_at=datetime.utcnow(),
                                        updated_at=datetime.utcnow()
                                    )
                                    session.add(new_group)
                                    total_added += 1
                                    logger.info(f"    ✅ Добавлена: {title} ({username})")
                    
                    # Небольшая задержка между запросами
                    await asyncio.sleep(2)
                    
                except Exception as e:
                    logger.error(f"  ❌ Ошибка при поиске '{keyword}': {e}")
                    continue
            
            await session.commit()
            
            logger.info("")
            logger.info("=" * 80)
            logger.info(f"✅ ПОИСК ЗАВЕРШЕН")
            logger.info("=" * 80)
            logger.info(f"📊 Найдено уникальных групп: {total_found}")
            logger.info(f"📊 Добавлено новых групп: {total_added}")
            logger.info(f"📊 Пропущено (уже есть): {total_skipped}")
            logger.info("=" * 80)
            logger.info("")
            logger.info("📋 СЛЕДУЮЩИЙ ШАГ:")
            logger.info("   Запустите скрипт для вступления в группы:")
            logger.info("   docker exec telegram-bali-account-manager python3 /app/scripts/monitoring/check_and_join_writeable_groups.py")
            logger.info("=" * 80)
            
            await client.disconnect()
            
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}", exc_info=True)


if __name__ == "__main__":
    try:
        asyncio.run(search_and_save_groups())
    except KeyboardInterrupt:
        logger.info("\n🛑 Прервано пользователем")
    except Exception as e:
        logger.error(f"\n❌ Критическая ошибка: {e}", exc_info=True)
