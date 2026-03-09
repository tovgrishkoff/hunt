"""
Модуль вступления в найденные группы
"""
import asyncio
import random
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple, List, Iterable, Set
from sqlalchemy import func, and_, desc, nullslast, desc, nullslast

from telethon.tl.functions.channels import JoinChannelRequest, GetFullChannelRequest
from telethon.errors import (
    FloodWaitError,
    UserAlreadyParticipantError,
    UsernameNotOccupiedError,
    ChannelPrivateError,
    ChatAdminRequiredError,
    ChatWriteForbiddenError,
    UserBannedInChannelError,
    InviteRequestSentError,
    RPCError
)

from shared.database.session import SessionLocal
from shared.database.models import Account, Group

logger = logging.getLogger(__name__)


class GroupJoiner:
    """Класс для вступления в группы"""
    
    def __init__(
        self,
        client_manager,
        niche_config,
        allowed_sessions: Optional[Iterable[str]] = None,
    ):
        """
        Args:
            client_manager: TelegramClientManager
            niche_config: конфиг ниши (limits, schedule и т.п.)
            allowed_sessions: опциональный список session_name аккаунтов,
                которые разрешено использовать для вступления в группы
                (например, Bali love-аккаунты).
        """
        self.client_manager = client_manager
        self.niche_config = niche_config
        limits = niche_config.get('limits', {})
        # Количество часов прогрева группы после вступления
        self.warm_up_hours = limits.get('warm_up_hours', 24)
        # Максимум вступлений в день на аккаунт (можно переопределить в конфиге ниши)
        self.max_joins_per_day = limits.get('max_joins_per_day', 10)
        # Задержки между вступлениями (в секундах)
        self.min_delay_between_joins = limits.get('min_delay_between_joins', 30)
        self.max_delay_between_joins = limits.get('max_delay_between_joins', 90)
        # Ограничение по аккаунтам для вступления (например, только Bali love-аккаунты)
        self.allowed_sessions: Set[str] = set(allowed_sessions or [])
    
    def get_least_loaded_account(self, db, exclude_account_ids: list = None, loaded_clients: set = None) -> Optional[Account]:
        """
        Получить наименее загруженный аккаунт для вступления
        
        Критерии:
        - Аккаунт активен
        - Аккаунт загружен в client_manager (если указан loaded_clients)
        - У него меньше всего присвоенных групп
        - Не превышен лимит вступлений за сегодня
        
        Args:
            db: Сессия БД
            exclude_account_ids: Список ID аккаунтов для исключения
            loaded_clients: Множество session_name загруженных клиентов
        
        Returns:
            Account или None
        """
        now = datetime.utcnow()
        today = now.date()
        
        # Запрос аккаунтов с количеством групп и вступлений сегодня
        query = db.query(
            Account.id,
            Account.session_name,
            func.count(Group.id).label('groups_count')
        ).outerjoin(
            Group,
            Group.assigned_account_id == Account.id
        ).filter(
            Account.status == 'active'
        )
        
        # Если заданы allowed_sessions (например, для ниши Bali) —
        # используем ТОЛЬКО эти аккаунты для вступления.
        if self.allowed_sessions:
            query = query.filter(Account.session_name.in_(self.allowed_sessions))
        
        if exclude_account_ids:
            query = query.filter(~Account.id.in_(exclude_account_ids))
        
        query = query.group_by(Account.id, Account.session_name)
        query = query.order_by('groups_count')
        
        # Фильтруем аккаунты, где не превышен лимит вступлений и клиент загружен
        available_accounts = []
        for result in query.all():
            account_id = result.id
            session_name = result.session_name
            
            # Пропускаем аккаунты, которые не загружены в client_manager
            if loaded_clients and session_name not in loaded_clients:
                continue
            
            # Подсчитываем вступления за сегодня
            joins_today = db.query(func.count(Group.id)).filter(
                and_(
                    Group.assigned_account_id == account_id,
                    Group.joined_at >= datetime.combine(today, datetime.min.time()),
                    Group.joined_at < datetime.combine(today + timedelta(days=1), datetime.min.time())
                )
            ).scalar() or 0
            
            if joins_today < self.max_joins_per_day:
                available_accounts.append((account_id, session_name, result.groups_count, joins_today))
        
        if not available_accounts:
            logger.warning("⚠️ Нет доступных аккаунтов для вступления (лимит достигнут или клиенты не загружены)")
            return None
        
        # Сортируем по количеству вступлений сегодня, затем по количеству групп
        available_accounts.sort(key=lambda x: (x[3], x[2]))  # joins_today, groups_count
        
        # БЕЗОПАСНОСТЬ: Выбираем случайно из аккаунтов с минимальной нагрузкой
        # Это предотвращает использование одного аккаунта для всех групп подряд
        min_joins = available_accounts[0][3]  # Минимальное количество вступлений сегодня
        
        # Находим все аккаунты с минимальным количеством вступлений сегодня
        # (это более справедливое распределение - учитываем только вступления, не общее количество групп)
        accounts_with_min_joins = [
            acc for acc in available_accounts
            if acc[3] == min_joins
        ]
        
        # Если есть несколько аккаунтов с одинаковым минимальным количеством вступлений - выбираем случайный
        if len(accounts_with_min_joins) > 1:
            selected = random.choice(accounts_with_min_joins)
            logger.info(f"  🎲 Случайный выбор из {len(accounts_with_min_joins)} аккаунтов с {min_joins} вступлениями сегодня")
        else:
            # Если только один аккаунт с минимальным количеством вступлений - берем его
            selected = available_accounts[0]
        
        account_id, session_name, groups_count, joins_today = selected
        logger.info(f"  ✅ Выбран аккаунт {session_name} (групп: {groups_count}, вступлений сегодня: {joins_today})")
        
        # Логируем доступные аккаунты для отладки
        if len(available_accounts) > 1:
            logger.debug(f"  📋 Доступные аккаунты: {', '.join([f'{name}({joins} joins, {groups} groups)' for _, name, groups, joins in available_accounts[:5]])}")
        
        return db.query(Account).filter(Account.id == account_id).first()
    
    async def check_can_post_after_join(self, client, entity) -> Tuple[bool, bool]:
        """
        Проверка членства и прав на постинг после вступления.

        Сначала верифицирует, что мы действительно участники (get_permissions успешен).
        Если Telegram отвечает "not a member" — возвращает (False, False), чтобы не писать
        в БД статус joined/active.

        Args:
            client: Telegram клиент
            entity: Entity группы

        Returns:
            (can_post: bool, is_member: bool).
            is_member=False → не писать в БД joined/active; статус откатить в pending/failed.
        """
        try:
            if not client.is_connected():
                logger.warning("  ⚠️ Client disconnected, cannot check permissions")
                return False, False

            me = await client.get_me()
            try:
                permissions = await client.get_permissions(entity, me)

                if permissions:
                    # Мы участники (get_permissions успешен). Проверяем право на постинг.
                    if hasattr(permissions, 'send_messages'):
                        can_send = permissions.send_messages
                        logger.debug(f"  🔍 Permission check: send_messages = {can_send}")
                        return can_send, True
                    if hasattr(permissions, 'banned_rights') and permissions.banned_rights:
                        if hasattr(permissions.banned_rights, 'send_messages'):
                            can_send = not permissions.banned_rights.send_messages
                            logger.debug(f"  🔍 Banned rights check: can_send = {can_send}")
                            return can_send, True
                    if hasattr(entity, 'broadcast') and entity.broadcast:
                        logger.info(f"  ℹ️ Это канал (broadcast=True), обычные участники не могут писать")
                        return False, True
                    try:
                        full_info = await client(GetFullChannelRequest(entity))
                        if hasattr(full_info, 'full_chat') and hasattr(full_info.full_chat, 'default_banned_rights'):
                            banned_rights = full_info.full_chat.default_banned_rights
                            if banned_rights and hasattr(banned_rights, 'send_messages'):
                                if banned_rights.send_messages:
                                    logger.info(f"  ⚠️ default_banned_rights.send_messages = True - писать могут только админы")
                                    return False, True
                                return True, True
                    except Exception as e:
                        logger.debug(f"  ℹ️ Не удалось проверить default_banned_rights: {e}")
                    logger.debug(f"  ℹ️ Permissions получены, send_messages не найден - разрешаем по умолчанию")
                    return True, True

                # permissions = None
                try:
                    full_info = await client(GetFullChannelRequest(entity))
                    if hasattr(full_info, 'full_chat') and hasattr(full_info.full_chat, 'default_banned_rights'):
                        banned_rights = full_info.full_chat.default_banned_rights
                        if banned_rights and hasattr(banned_rights, 'send_messages') and banned_rights.send_messages:
                            logger.info(f"  ⚠️ default_banned_rights.send_messages = True (permissions=None)")
                            return False, True
                except Exception as e:
                    logger.debug(f"  ℹ️ Не удалось проверить default_banned_rights при permissions=None: {e}")
                return True, True

            except (RPCError, Exception) as e:
                error_str = str(e)
                if "GetParticipantRequest" in error_str or "not a member" in error_str.lower():
                    logger.warning(f"  ⚠️ Верификация участника не прошла (get_permissions): {e}")
                    # Критично: мы НЕ участники — не помечаем как joined/active.
                    return False, False
                logger.warning(f"  ⚠️ Ошибка при проверке прав: {e}")
                return False, True

        except Exception as e:
            logger.warning(f"  ⚠️ Критическая ошибка при проверке прав: {e}")
            return False, False
    
    async def join_group(
        self,
        client,
        account: Account,
        group_id: int,
        username: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Вступление в группу с проверкой прав
        
        Args:
            client: Telegram клиент
            account: Аккаунт для вступления
            group_id: ID группы в БД
            username: Username группы (@username)
        
        Returns:
            (success: bool, error_message: Optional[str])
        """
        
        try:
            # Проверяем подключенность клиента
            if not client.is_connected():
                logger.warning(f"  ⚠️ Client {account.session_name} disconnected, cannot join {username}")
                return False, "Client disconnected"
            
            logger.info(f"  🚪 Вступаю в {username} через {account.session_name}...")
            
            # Нормализуем username (должен быть с @ для get_entity)
            if username and not username.startswith('@'):
                username = '@' + username
            
            # Получаем entity группы
            try:
                entity = await client.get_entity(username)
            except FloodWaitError as e:
                wait_seconds = getattr(e, "seconds", 0) or 0
                error_msg = f"FloodWait: {wait_seconds} seconds"
                logger.warning(f"  ⏳ {error_msg} (аккаунт временно в лимите, переключимся на другого)")
                return False, error_msg
            except UsernameNotOccupiedError:
                error_msg = f"Группа {username} не найдена"
                logger.warning(f"  ⚠️ {error_msg}")
                return False, error_msg
            except ChannelPrivateError:
                error_msg = f"Группа {username} приватная"
                logger.warning(f"  ⚠️ {error_msg}")
                return False, error_msg
            except ValueError as e:
                # Telethon: "No user has X as username" — группа переименована/удалена или это invite hash
                error_msg = f"Группа не найдена ({e})"
                logger.warning(f"  ⚠️ {error_msg}")
                return False, error_msg
            
            # Проверяем, не участник ли уже
            try:
                await client.get_participants(entity, limit=1)
                logger.info(f"  ℹ️ Уже участник {username}")
                is_already_member = True
            except Exception:
                is_already_member = False

            # Вступаем в группу (если еще не участник)
            if not is_already_member:
                try:
                    updates = await client(JoinChannelRequest(entity))
                    # Проверяем ответ: если в updates есть чат с left=True — мы не вступили, только заявка
                    if updates and getattr(updates, 'chats', None):
                        for c in updates.chats:
                            if getattr(c, 'left', False):
                                logger.info(f"  📤 JoinChannelRequest: чат с left=True — заявка отправлена, ждём одобрения")
                                return False, "Waiting for approval"
                    # Проверяем, действительно ли мы стали участниками
                    try:
                        await client.get_participants(entity, limit=1)
                        chat_id = entity.id if hasattr(entity, 'id') else 'unknown'
                        logger.info(f"  ✅ Successfully joined {username} (chat_id: {chat_id})")
                        is_already_member = True
                    except Exception:
                        chat_id = entity.id if hasattr(entity, 'id') else 'unknown'
                        logger.info(f"  📤 Sent join request to {username} (chat_id: {chat_id}) - Waiting for approval")
                        return False, "Waiting for approval"
                except InviteRequestSentError:
                    logger.info(f"  📤 InviteRequestSentError: заявка на вступление отправлена в {username}")
                    return False, "Waiting for approval"
                except UserAlreadyParticipantError:
                    logger.info(f"  ℹ️ Уже участник {username}")
                    is_already_member = True
                except FloodWaitError as e:
                    wait_seconds = e.seconds
                    # Ограничиваем максимальное ожидание до 10 минут (600 секунд)
                    # Если FloodWait больше - просто пропускаем группу без ожидания
                    max_wait = 600
                    error_msg = f"FloodWait: {wait_seconds} секунд"
                    
                    if wait_seconds > max_wait:
                        logger.warning(f"  ⏳ {error_msg} - СЛИШКОМ БОЛЬШОЙ, пропускаем группу (аккаунт требует отдыха)")
                        return False, f"FloodWait: {wait_seconds} seconds (too large, skipping)"
                    else:
                        logger.warning(f"  ⏳ {error_msg} - ждем...")
                        await asyncio.sleep(wait_seconds)
                        # После ожидания пробуем снова не будем - пропускаем эту группу
                        return False, error_msg
                except ChatAdminRequiredError:
                    error_msg = "Требуются права администратора"
                    logger.warning(f"  ⚠️ {error_msg}")
                    return False, error_msg
                except RPCError as e:
                    error_msg = str(e)
                    if "CAPTCHA" in error_msg or "капча" in error_msg.lower():
                        error_msg = "Требуется капча"
                    logger.warning(f"  ⚠️ Ошибка RPC: {error_msg}")
                    return False, error_msg
            
            # Проверяем, что мы действительно участники перед проверкой прав
            if not is_already_member:
                # Дополнительная проверка на случай, если предыдущая проверка не сработала
                try:
                    await client.get_participants(entity, limit=1)
                    is_already_member = True
                except Exception as e:
                    chat_id = entity.id if hasattr(entity, 'id') else 'unknown'
                    logger.warning(f"  ⚠️ Not a member of {username} (chat_id: {chat_id}) after join request: {e}")
                    return False, "Not a member after join request"
            
            # Верификация участника и прав: если мы не участники — не пишем в БД joined/active
            can_post, is_member = await self.check_can_post_after_join(client, entity)
            if not is_member:
                logger.warning(f"  ⚠️ Верификация не прошла: аккаунт не является участником {username}, в БД joined не пишем")
                return False, "Not a member (verification failed)"

            chat_id = entity.id if hasattr(entity, 'id') else 'unknown'

            # Обновляем группу в БД только при подтверждённом членстве
            db = SessionLocal()
            try:
                locked_group = db.query(Group).filter(Group.id == group_id).with_for_update().first()
                if not locked_group:
                    return False, "Группа не найдена в БД"

                now = datetime.utcnow()
                locked_group.assigned_account_id = account.id
                locked_group.joined_at = now
                locked_group.warm_up_until = now + timedelta(hours=self.warm_up_hours)
                locked_group.can_post = can_post

                if not can_post:
                    error_msg = "Нельзя постить в группе (read-only или канал)"
                    logger.warning(f"  ⚠️ {error_msg} (chat_id: {chat_id}) - помечаю как read-only")
                    locked_group.status = 'read_only'  # Меняем статус на read_only
                    db.commit()
                    logger.info(f"  📝 Группа {username} (group_id: {locked_group.id}, chat_id: {chat_id}) сохранена со статусом 'read_only', can_post=False")
                    # Не покидаем группу - может быть полезно для активности
                    return False, error_msg
                
                # Если can_post = True - устанавливаем статус active
                locked_group.status = 'active'
                
                # Обновляем title и members_count если нужно
                try:
                    full_info = await client(GetFullChannelRequest(entity))
                    if hasattr(full_info, 'full_chat'):
                        if hasattr(full_info.full_chat, 'title'):
                            locked_group.title = full_info.full_chat.title
                        if hasattr(full_info.full_chat, 'participants_count'):
                            locked_group.members_count = full_info.full_chat.participants_count
                except Exception as e:
                    logger.debug(f"  ℹ️ Не удалось обновить title/members_count: {e}")
                
                db.commit()
                logger.info(f"  🔗 Назначен аккаунт {account.session_name} для {username} (group_id: {locked_group.id}, chat_id: {chat_id}, can_post={can_post}, warm-up {self.warm_up_hours}ч)")
                
                if can_post:
                    logger.info(f"  ✅ Подтверждено: можно постить в {username} (chat_id: {chat_id})")
                    return True, None
                else:
                    # Это не должно произойти, т.к. мы уже обработали can_post=False выше
                    return False, "can_post=False after DB update"
                
            except Exception as e:
                db.rollback()
                error_msg = f"Ошибка при обновлении БД: {e}"
                logger.error(f"  ❌ {error_msg}")
                return False, error_msg
            finally:
                db.close()
            
        except Exception as e:
            error_msg = f"Неожиданная ошибка: {e}"
            logger.error(f"  ❌ {error_msg}", exc_info=True)
            return False, error_msg
    
    def get_new_groups(self, db, niche: str, limit: int = None) -> List[Group]:
        """
        Получить группы со статусом 'new' для вступления
        
        Args:
            db: Сессия БД
            niche: Ниша групп
            limit: Максимум групп (если None - все)
        
        Returns:
            Список групп
        """
        query = db.query(Group).filter(
            and_(
                Group.status == 'new',
                Group.niche == niche
            )
        ).order_by(nullslast(desc(Group.members_count)), Group.created_at)
        
        if limit:
            query = query.limit(limit)
        
        return query.all()
    
    async def process_new_groups(self, niche: str) -> Tuple[int, int]:
        """
        Обработка новых групп: вступление и назначение аккаунтов
        
        Использует DTO-подход: загружает группы в простые структуры данных,
        закрывает сессию БД, работает с данными в памяти, открывает короткие
        сессии только для обновления статусов.
        
        Args:
            niche: Ниша групп
        
        Returns:
            (joined_count: int, failed_count: int)
        """
        joined_count = 0
        failed_count = 0
        
        # ШАГ 1: Eager Loading - загружаем все группы в простые структуры данных
        db = SessionLocal()
        try:
            # Получаем группы со статусом 'new'
            new_groups_orm = self.get_new_groups(db, niche, limit=80)  # Выборка для батча (реальный лимит — join_batch_size из конфига)
            
            if not new_groups_orm:
                logger.info("ℹ️ Нет новых групп для вступления")
                return 0, 0
            
            # Преобразуем объекты ORM в простые словари (DTO) - загружаем все данные в память
            # ВАЖНО: Загружаем все атрибуты ДО закрытия сессии, чтобы избежать DetachedInstanceError
            groups_dto = []
            for group in new_groups_orm:
                # Явно загружаем все нужные атрибуты в переменные (eager loading)
                group_id = group.id
                group_username = group.username
                group_status = group.status
                group_title = group.title if group.title else None
                group_link = getattr(group, 'link', None) or group_username
                
                # Сохраняем в словарь (простые типы Python, не объекты ORM)
                groups_dto.append({
                    'id': group_id,
                    'username': group_username,
                    'link': group_link,
                    'status': group_status,
                    'title': group_title
                })
            
            logger.info(f"📋 Найдено {len(groups_dto)} новых групп для вступления")
            
            # Ограничиваем количество групп за слот (читаем из конфига или используем 20 по умолчанию)
            limits_config = self.niche_config.get('limits', {})
            max_groups_per_slot = limits_config.get('join_batch_size', 20)
            groups_to_process = groups_dto[:max_groups_per_slot]
            
            logger.info(f"📋 Обработаем {len(groups_to_process)} групп из {len(groups_dto)} (лимит: {max_groups_per_slot} за слот)")
        finally:
            # Закрываем сессию БД - больше не нужна, все данные в памяти
            db.close()
        
        # ШАГ 2: Работаем с данными в памяти (без открытой сессии БД)
        # Аккаунты с FloodWait исключаем из выбора на этот батч, чтобы переключиться на других
        exclude_account_ids: List[int] = []
        for idx, group_data in enumerate(groups_to_process, 1):
            group_id = group_data['id']
            group_username = group_data['username']
            
            try:
                # Выбираем аккаунт для вступления (исключаем тех, кто в FloodWait в этом батче)
                db = SessionLocal()
                try:
                    loaded_clients = set(self.client_manager.clients.keys()) if self.client_manager.clients else set()
                    account = self.get_least_loaded_account(db, exclude_account_ids=exclude_account_ids, loaded_clients=loaded_clients)
                finally:
                    db.close()
                
                if not account:
                    logger.warning("⚠️ Нет доступных аккаунтов (лимит достигнут или клиенты не загружены), останавливаем обработку")
                    break
                
                # Проверяем и переподключаем клиент при необходимости
                client = await self.client_manager.ensure_client_connected(account.session_name)
                if not client:
                    logger.warning(f"⚠️ Не удалось подключить клиент {account.session_name}, пропускаем")
                    failed_count += 1
                    continue
                
                logger.info(f"\n[{idx}/{len(groups_to_process)}] {group_username}")
                
                # Вступаем в группу (join_group сам откроет короткую сессию для обновления БД)
                success, error = await self.join_group(client, account, group_id, group_username)
                
                if success:
                    joined_count += 1
                    
                    # Пауза между вступлениями только если это не последняя группа
                    if idx < len(groups_to_process):
                        delay = random.randint(self.min_delay_between_joins, self.max_delay_between_joins)
                        delay_seconds = delay
                        if delay >= 60:
                            delay_minutes = delay // 60
                            logger.info(f"  ⏸ Пауза {delay_minutes} минут ({delay_seconds} сек) перед следующим вступлением...")
                        else:
                            logger.info(f"  ⏸ Пауза {delay_seconds} секунд перед следующим вступлением...")
                        await asyncio.sleep(delay)
                    else:
                        logger.info(f"  ✅ Последняя группа обработана, пауза не требуется")
                else:
                    failed_count += 1
                    
                    # ОБРАБОТКА JOIN REQUEST и неуспешной верификации участника
                    if error and (
                        "waiting for approval" in error.lower()
                        or "not a member after join request" in error.lower()
                        or "not a member (verification failed)" in error.lower()
                    ):
                        db = SessionLocal()
                        try:
                            group = db.query(Group).filter(Group.id == group_id).first()
                            if group:
                                group.status = 'pending'
                                group.updated_at = datetime.utcnow()
                                db.commit()
                                logger.info(f"  📤 Группа {group_username} помечена как 'pending' (заявка или верификация не прошла)")
                        except Exception as e:
                            db.rollback()
                            logger.error(f"  ❌ Ошибка при обновлении статуса на pending: {e}")
                        finally:
                            db.close()
                        await asyncio.sleep(30)
                    # Если группа недоступна (не найдена, приватная, username не существует), помечаем её
                    elif error and (
                        "не найдена" in error.lower()
                        or "приватная" in error.lower()
                        or "inaccessible" in error.lower()
                        or "no user has" in error.lower()
                    ):
                        db = SessionLocal()
                        try:
                            group = db.query(Group).filter(Group.id == group_id).first()
                            if group:
                                group.status = 'inaccessible'
                                db.commit()
                                logger.info(f"  📛 Группа {group_username} помечена как 'inaccessible' (больше не будем пытаться)")
                        except Exception as e:
                            db.rollback()
                            logger.error(f"  ❌ Ошибка при обновлении статуса на inaccessible: {e}")
                        finally:
                            db.close()
                        await asyncio.sleep(5)
                    # Обработка FloodWait — исключаем этот аккаунт на остаток батча, следующий цикл возьмёт другого
                    elif error and ("wait" in error.lower() or "flood" in error.lower()):
                        if account and account.id not in exclude_account_ids:
                            exclude_account_ids.append(account.id)
                            logger.warning(f"  ⏳ FloodWait для {group_username}, аккаунт {account.session_name} исключён до конца батча")
                        await asyncio.sleep(5)
                    else:
                        # Короткая пауза при ошибке
                        await asyncio.sleep(60)
            
            except FloodWaitError as e:
                wait_seconds = getattr(e, "seconds", 0) or 0
                if account and account.id not in exclude_account_ids:
                    exclude_account_ids.append(account.id)
                    logger.warning(f"  ⏳ FloodWait {wait_seconds} сек у {account.session_name}, исключаем до конца батча")
                failed_count += 1
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"❌ Ошибка при обработке группы {group_username} (ID: {group_id}): {e}", exc_info=True)
                failed_count += 1
                await asyncio.sleep(30)
        
        logger.info(f"\n✅ Обработано: {joined_count} вступлений, {failed_count} неудач")
        
        return joined_count, failed_count
