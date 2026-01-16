#!/usr/bin/env python3
"""
Scout (Парсер/Разведчик) - Поиск новых групп и добавление в БД
Работает с PostgreSQL через Async SQLAlchemy
"""
import asyncio
import logging
import sys
import os
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path

# Добавляем корень проекта в путь
sys.path.insert(0, '/app')

from lexus_db.session import AsyncSessionLocal, init_db
from lexus_db.models import Target, Base
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
    
    async def search_groups(self) -> List[Dict[str, str]]:
        """
        Поиск новых групп (заглушка/шаблон)
        
        В реальной реализации здесь должен быть код для:
        - Поиска групп через Telegram API
        - Парсинга результатов поиска
        - Фильтрации по критериям
        
        Returns:
            Список словарей с информацией о группах:
            [
                {'link': '@groupname', 'title': 'Group Title'},
                ...
            ]
        """
        logger.info(f"🔍 Поиск групп для ниши: {self.niche}")
        
        # TODO: Здесь должна быть реальная логика поиска
        # Пример заглушки:
        found_groups = [
            # {'link': '@example_group_1', 'title': 'Example Group 1'},
            # {'link': '@example_group_2', 'title': 'Example Group 2'},
        ]
        
        logger.info(f"📋 Найдено групп: {len(found_groups)}")
        return found_groups
    
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
            groups: Список групп для сохранения
        
        Returns:
            Количество добавленных групп
        """
        if not groups:
            logger.info("📭 Нет групп для сохранения")
            return 0
        
        added_count = 0
        skipped_count = 0
        
        for group_info in groups:
            link = group_info.get('link')
            title = group_info.get('title')
            
            if not link:
                logger.warning(f"⚠️ Пропускаем группу без link: {group_info}")
                skipped_count += 1
                continue
            
            normalized_link = self.normalize_group_link(link)
            
            # Проверяем, существует ли группа в БД
            stmt = select(Target).where(Target.link == normalized_link)
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            
            if existing:
                logger.debug(f"  ⏭️  Группа {normalized_link} уже существует в БД")
                skipped_count += 1
                continue
            
            # Создаем новую группу
            new_target = Target(
                link=normalized_link,
                title=title,
                niche=self.niche,
                status='new',  # Статус 'new' - Smart Joiner подхватит
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            
            session.add(new_target)
            added_count += 1
            logger.info(f"  ✅ Добавлена группа: {normalized_link} ({title})")
        
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
        
        async with AsyncSessionLocal() as session:
            try:
                # Шаг 1: Поиск групп
                found_groups = await self.search_groups()
                
                if not found_groups:
                    logger.info("📭 Новых групп не найдено")
                    return
                
                # Шаг 2: Сохранение в БД
                saved_count = await self.save_groups_to_db(session, found_groups)
                
                logger.info("=" * 80)
                logger.info(f"✅ SCOUT ЗАВЕРШЕН: Добавлено {saved_count} новых групп")
                logger.info("=" * 80)
                
            except Exception as e:
                await session.rollback()
                logger.error(f"❌ Ошибка при выполнении scout: {e}", exc_info=True)
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
