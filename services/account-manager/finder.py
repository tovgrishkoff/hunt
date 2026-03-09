"""
Модуль поиска новых групп для вступления
"""
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from sqlalchemy import and_

from telethon.tl.functions.contacts import SearchRequest
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.errors import (
    FloodWaitError,
    UsernameNotOccupiedError,
    ChannelPrivateError,
    ChatAdminRequiredError
)

from shared.database.session import SessionLocal
from shared.database.models import Group

logger = logging.getLogger(__name__)


class GroupFinder:
    """Класс для поиска новых групп"""
    
    # Слова для фильтрации мусора
    INAPPROPRIATE_KEYWORDS = [
        'порно', 'porn', 'xxx', '18+', 'взрослые', 'adult',
        'ставки', 'betting', 'казино', 'casino', 'покер', 'poker',
        'гемблинг', 'gambling', 'лотерея', 'lottery',
        'наркотики', 'drugs', 'cannabis', 'weed',
        'мошенничество', 'scam', 'обман',
        'продажа оружия', 'weapons', 'guns'
    ]
    
    def __init__(self, client_manager):
        self.client_manager = client_manager
    
    def is_appropriate_group(self, title: str, username: str = None) -> bool:
        """
        Проверка, подходит ли группа (фильтрация мусора)
        
        Args:
            title: Название группы
            username: Username группы (опционально)
        
        Returns:
            True если группа подходит, False если мусор
        """
        if not title:
            return False
        
        text_to_check = (title + " " + (username or "")).lower()
        
        # Проверяем на неподходящие ключевые слова
        for keyword in self.INAPPROPRIATE_KEYWORDS:
            if keyword in text_to_check:
                logger.debug(f"  ⚠️ Фильтр: найдено '{keyword}' в '{title}'")
                return False
        
        # Дополнительные проверки
        if len(title) < 3:  # Слишком короткое название
            return False

        return True
    
    async def check_can_post_in_group(self, client, entity) -> bool:
        """
        Проверка, можно ли постить в группе до вступления
        
        Args:
            client: Telegram клиент
            entity: Entity группы
        
        Returns:
            True если можно постить, False если нет
        """
        try:
            # Каналы (broadcast=True): только админы могут постить, обычные подписчики — нет
            if getattr(entity, "broadcast", False):
                logger.debug(f"  ⏭️ Пропуск канала (broadcast): постить могут только админы")
                return False

            # Пробуем получить информацию о группе
            try:
                full_info = await client(GetFullChannelRequest(entity))
                if hasattr(full_info, 'full_chat'):
                    # Для супергрупп проверяем default_banned_rights
                    if hasattr(full_info.full_chat, 'default_banned_rights'):
                        banned_rights = full_info.full_chat.default_banned_rights
                        if banned_rights and hasattr(banned_rights, 'send_messages'):
                            can_post = not banned_rights.send_messages
                            if not can_post:
                                logger.debug(f"  ⚠️ Нельзя постить (banned_rights)")
                            return can_post
                    # Если нет ограничений, считаем что можно
                    return True
            except Exception as e:
                logger.debug(f"  ⚠️ Не удалось проверить права через GetFullChannelRequest: {e}")
            
            # Если не можем проверить, считаем что можно (проверим после вступления)
            return True
            
        except Exception as e:
            logger.warning(f"  ⚠️ Ошибка при проверке прав: {e}")
            # Если не можем проверить, считаем что можно (проверим после вступления)
            return True
    
    async def search_groups(self, client, keywords: List[str], limit_per_keyword: int = 20) -> List[Dict]:
        """
        Поиск групп по ключевым словам
        
        Args:
            client: Telegram клиент
            keywords: Список ключевых слов для поиска
            limit_per_keyword: Максимум результатов на ключевое слово
        
        Returns:
            Список найденных групп
        """
        found_groups = []
        
        logger.info(f"🔍 Поиск групп по {len(keywords)} ключевым словам...")
        
        for keyword in keywords:
            try:
                logger.info(f"  Ищу по ключевому слову: '{keyword}'")
                
                # Проверяем подключенность клиента перед использованием
                if not client.is_connected():
                    logger.warning(f"  ⚠️ Client disconnected, attempting to reconnect...")
                    # Пытаемся переподключить
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
                    if not self.is_appropriate_group(title, username):
                        logger.debug(f"  ⚠️ Пропускаем '{username}' - фильтр мусора")
                        continue
                    
                    # Проверяем, нет ли уже такой группы в БД
                    db = SessionLocal()
                    try:
                        existing = db.query(Group).filter(Group.username == username).first()
                        if existing:
                            logger.debug(f"  ℹ️ Группа {username} уже есть в БД")
                            continue
                    finally:
                        db.close()
                    
                    # Проверяем права на постинг
                    try:
                        entity = await client.get_entity(username)
                        can_post = await self.check_can_post_in_group(client, entity)
                        if not can_post:
                            logger.debug(f"  ⚠️ Пропускаем '{username}' - нельзя постить")
                            continue
                    except (UsernameNotOccupiedError, ChannelPrivateError):
                        logger.debug(f"  ⚠️ Группа {username} недоступна")
                        continue
                    except Exception as e:
                        logger.debug(f"  ⚠️ Ошибка при проверке {username}: {e}")
                        # Продолжаем, добавим группу, проверим после вступления
                    
                    # Добавляем группу
                    found_groups.append({
                        'username': username,
                        'title': title,
                        'id': chat.id,
                        'members_count': getattr(chat, 'participants_count', 0),
                        'found_by': keyword
                    })
                    logger.info(f"  ✅ Найдена группа: {username} - {title}")
                
                # Пауза между поисками
                await asyncio.sleep(2)
                
            except FloodWaitError as e:
                # Для небольших FloodWait просто подождём и продолжим с тем же аккаунтом,
                # но слишком большие значения пробрасываем наверх, чтобы планировщик
                # мог поместить аккаунт в cooldown и переключиться на другой.
                wait_seconds = int(getattr(e, "seconds", 0) or 0)
                if wait_seconds <= 0:
                    wait_seconds = 60
                if wait_seconds > 600:
                    # >10 минут — считаем, что аккаунту нужен «отдых», не блокируем весь поток здесь
                    logger.warning(
                        f"  ⏳ FloodWait {wait_seconds} секунд для '{keyword}' "
                        f"(слишком большой, передаём управление планировщику)"
                    )
                    raise
                capped = min(wait_seconds, 3600)  # Максимум 1 час
                logger.warning(f"  ⏳ FloodWait {capped} секунд для '{keyword}'")
                await asyncio.sleep(capped)
                continue
            except Exception as e:
                logger.error(f"  ❌ Ошибка при поиске '{keyword}': {e}")
                continue
        
        logger.info(f"✅ Найдено новых групп: {len(found_groups)}")
        return found_groups
    
    def save_groups_to_db(
        self,
        groups: List[Dict],
        niche: str,
        keyword_to_sub_niche: Optional[Dict[str, str]] = None,
    ) -> int:
        """
        Сохранение найденных групп в БД со статусом 'new' и обновление group_niches.json.

        По ключу found_by из keyword_to_sub_niche задаётся под-ниша (например india_retreat)
        для выбора сообщений при постинге.

        Args:
            groups: Список найденных групп (с полем found_by — ключевое слово поиска)
            niche: Ниша групп (например 'bali')
            keyword_to_sub_niche: Маппинг ключевое слово -> под-ниша (например {"Thailand expat": "india_retreat"})

        Returns:
            Количество сохраненных групп
        """
        if not groups:
            return 0

        if keyword_to_sub_niche is None:
            keyword_to_sub_niche = {}

        db = SessionLocal()
        saved_count = 0
        group_niches_updates = {}  # username -> sub_niche для обновления group_niches.json

        try:
            for group_info in groups:
                username = group_info.get('username')
                if not username:
                    continue

                found_by = group_info.get('found_by', '')
                sub_niche = keyword_to_sub_niche.get(found_by, 'general')
                group_niches_updates[username] = sub_niche

                try:
                    # Проверяем, нет ли уже такой группы
                    existing = db.query(Group).filter(Group.username == username).first()
                    if existing:
                        # Обновляем статус на 'new' если он был другой
                        if existing.status != 'new':
                            existing.status = 'new'
                            existing.niche = niche
                            existing.title = group_info.get('title', existing.title)
                            existing.members_count = group_info.get('members_count', existing.members_count)
                            if hasattr(existing, 'found_by_keyword'):
                                existing.found_by_keyword = group_info.get('found_by', existing.found_by_keyword or '')
                            db.commit()
                            saved_count += 1
                            logger.debug(f"  🔄 Обновлена группа {username} -> статус 'new'")
                        continue

                    # Создаем новую группу
                    new_group = Group(
                        username=username,
                        title=group_info.get('title', ''),
                        niche=niche,
                        found_by_keyword=group_info.get('found_by', ''),
                        status='new',  # Статус 'new' - готова к вступлению
                        can_post=True,
                        members_count=group_info.get('members_count', 0)
                    )
                    db.add(new_group)
                    db.commit()
                    saved_count += 1
                    logger.debug(f"  ✅ Сохранена новая группа {username}")

                except Exception as e:
                    db.rollback()
                    logger.error(f"  ❌ Ошибка при сохранении {username}: {e}")
                    continue

            logger.info(f"💾 Сохранено в БД: {saved_count} групп со статусом 'new'")

            # Обновляем group_niches.json для выбора сообщений по под-нише при постинге
            if group_niches_updates:
                self._update_group_niches_file(group_niches_updates)

        except Exception as e:
            db.rollback()
            logger.error(f"❌ Ошибка при сохранении групп: {e}")
        finally:
            db.close()

        return saved_count

    def _update_group_niches_file(self, updates: Dict[str, str]) -> None:
        """Дописать/обновить group_niches.json по маппингу username -> sub_niche."""
        paths = [
            Path('/app/group_niches.json'),
            Path(__file__).resolve().parent.parent.parent / 'group_niches.json',
            Path('group_niches.json'),
            Path(__file__).resolve().parent.parent.parent.parent / 'group_niches.json',
        ]
        group_niches_path = None
        for p in paths:
            if p.exists() or p.parent.exists():
                group_niches_path = p
                break
        if group_niches_path is None:
            group_niches_path = Path(__file__).resolve().parent.parent.parent / 'group_niches.json'
        try:
            if group_niches_path.exists():
                with open(group_niches_path, 'r', encoding='utf-8') as f:
                    group_niches = json.load(f)
            else:
                group_niches = {}
            for username, sub_niche in updates.items():
                if not username.startswith('@'):
                    username = '@' + username
                group_niches[username] = sub_niche
            with open(group_niches_path, 'w', encoding='utf-8') as f:
                json.dump(group_niches, f, ensure_ascii=False, indent=2)
            logger.info(f"  📝 Обновлён group_niches.json: +{len(updates)} записей (под-ниши для постинга)")
        except Exception as e:
            logger.warning(f"  ⚠️ Не удалось обновить group_niches.json: {e}")