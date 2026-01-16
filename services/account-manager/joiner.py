"""
Модуль вступления в найденные группы
"""
import asyncio
import random
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple, List
from sqlalchemy import func, and_

from telethon.tl.functions.channels import JoinChannelRequest, GetFullChannelRequest
from telethon.errors import (
    FloodWaitError,
    UserAlreadyParticipantError,
    UsernameNotOccupiedError,
    ChannelPrivateError,
    ChatAdminRequiredError,
    ChatWriteForbiddenError,
    UserBannedInChannelError,
    RPCError
)

from shared.database.session import SessionLocal
from shared.database.models import Account, Group

logger = logging.getLogger(__name__)


class GroupJoiner:
    """Класс для вступления в группы"""
    
    def __init__(self, client_manager, niche_config):
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
    
    async def check_can_post_after_join(self, client, entity) -> bool:
        """
        Проверка, можно ли постить в группе после вступления
        
        Проверяет права через get_permissions и banned_rights.
        Для каналов и групп с ограниченными правами возвращает False.
        
        Args:
            client: Telegram клиент
            entity: Entity группы
        
        Returns:
            True если можно постить, False если нет
        """
        try:
            # Проверяем подключенность клиента
            if not client.is_connected():
                logger.warning("  ⚠️ Client disconnected, cannot check permissions")
                return False  # Не можем проверить - считаем что нельзя постить
            
            me = await client.get_me()
            try:
                permissions = await client.get_permissions(entity, me)
                
                if permissions:
                    # Проверяем право на отправку сообщений напрямую
                    if hasattr(permissions, 'send_messages'):
                        can_send = permissions.send_messages
                        logger.debug(f"  🔍 Permission check: send_messages = {can_send}")
                        return can_send
                    
                    # Проверяем через banned_rights (если send_messages заблокирован)
                    if hasattr(permissions, 'banned_rights') and permissions.banned_rights:
                        if hasattr(permissions.banned_rights, 'send_messages'):
                            is_banned = permissions.banned_rights.send_messages
                            can_send = not is_banned
                            logger.debug(f"  🔍 Banned rights check: send_messages banned = {is_banned}, can_send = {can_send}")
                            return can_send
                    
                    # Если есть permissions, но нет явного send_messages - проверяем другие признаки
                    # Для супергрупп и каналов без явных прав считаем что нельзя постить
                    if hasattr(entity, 'broadcast') and entity.broadcast:
                        # Это канал - обычные участники не могут писать
                        logger.info(f"  ℹ️ Это канал (broadcast=True), обычные участники не могут писать")
                        return False
                    
                    # Если permissions есть, но нет send_messages - проверяем default_banned_rights
                    # Это важно для групп, где писать могут только админы
                    try:
                        full_info = await client(GetFullChannelRequest(entity))
                        if hasattr(full_info, 'full_chat') and hasattr(full_info.full_chat, 'default_banned_rights'):
                            banned_rights = full_info.full_chat.default_banned_rights
                            if banned_rights and hasattr(banned_rights, 'send_messages'):
                                if banned_rights.send_messages:
                                    logger.info(f"  ⚠️ default_banned_rights.send_messages = True - писать могут только админы")
                                    return False
                                else:
                                    logger.debug(f"  ✅ default_banned_rights.send_messages = False - можно писать")
                                    return True
                    except Exception as e:
                        logger.debug(f"  ℹ️ Не удалось проверить default_banned_rights: {e}")
                    
                    # Если permissions есть, но нет send_messages и default_banned_rights - по умолчанию разрешаем
                    # (для обычных групп это обычно работает)
                    logger.debug(f"  ℹ️ Permissions получены, но send_messages не найден - разрешаем по умолчанию")
                    return True
                
                # Если permissions = None - проверяем default_banned_rights
                try:
                    full_info = await client(GetFullChannelRequest(entity))
                    if hasattr(full_info, 'full_chat') and hasattr(full_info.full_chat, 'default_banned_rights'):
                        banned_rights = full_info.full_chat.default_banned_rights
                        if banned_rights and hasattr(banned_rights, 'send_messages'):
                            if banned_rights.send_messages:
                                logger.info(f"  ⚠️ default_banned_rights.send_messages = True (permissions=None) - писать могут только админы")
                                return False
                except Exception as e:
                    logger.debug(f"  ℹ️ Не удалось проверить default_banned_rights при permissions=None: {e}")
                
                # Если permissions = None и не удалось проверить default_banned_rights - разрешаем по умолчанию
                logger.debug(f"  ℹ️ Permissions = None, разрешаем по умолчанию (обычная группа)")
                return True
                
            except (RPCError, Exception) as e:
                error_str = str(e)
                # Если GetParticipantRequest не работает - это может быть канал или группа с ограничениями
                if "GetParticipantRequest" in error_str or "not a member" in error_str.lower():
                    logger.warning(f"  ⚠️ Не удалось проверить права через get_permissions: {e}")
                    # Для каналов и групп с ограничениями - считаем что нельзя постить
                    if hasattr(entity, 'broadcast') and entity.broadcast:
                        logger.info(f"  ℹ️ Это канал, нельзя постить без прав админа")
                        return False
                    # Для обычных групп - разрешаем (может быть временная ошибка API)
                    logger.debug(f"  ℹ️ Обычная группа, разрешаем по умолчанию")
                    return True
                else:
                    logger.warning(f"  ⚠️ Ошибка при проверке прав: {e}")
                    # При неизвестной ошибке - не разрешаем (безопаснее)
                    return False
            
        except Exception as e:
            logger.warning(f"  ⚠️ Критическая ошибка при проверке прав: {e}")
            # При критической ошибке - не разрешаем (безопаснее)
            return False
    
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
            
            # Получаем entity группы
            try:
                entity = await client.get_entity(username)
            except UsernameNotOccupiedError:
                error_msg = f"Группа {username} не найдена"
                logger.warning(f"  ⚠️ {error_msg}")
                return False, error_msg
            except ChannelPrivateError:
                error_msg = f"Группа {username} приватная"
                logger.warning(f"  ⚠️ {error_msg}")
                return False, error_msg
            
            # Проверяем, не участник ли уже
            try:
                await client.get_participants(entity, limit=1)
                logger.info(f"  ℹ️ Уже участник {username}")
                is_already_member = True
            except:
                is_already_member = False
            
            # Вступаем в группу (если еще не участник)
            join_request_sent = False
            if not is_already_member:
                try:
                    await client(JoinChannelRequest(entity))
                    join_request_sent = True
                    # Проверяем, действительно ли мы стали участниками
                    # (JoinChannelRequest может не выбросить ошибку, но заявка может требовать одобрения)
                    try:
                        await client.get_participants(entity, limit=1)
                        # Если get_participants не выбросил ошибку - мы участники
                        chat_id = entity.id if hasattr(entity, 'id') else 'unknown'
                        logger.info(f"  ✅ Successfully joined {username} (chat_id: {chat_id})")
                        is_already_member = True
                    except Exception as participants_error:
                        # Если get_participants выбросил ошибку - мы НЕ участники (заявка отправлена)
                        chat_id = entity.id if hasattr(entity, 'id') else 'unknown'
                        logger.info(f"  📤 Sent join request to {username} (chat_id: {chat_id}) - Waiting for approval")
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
            
            # Проверяем права на постинг после вступления
            can_post = await self.check_can_post_after_join(client, entity)
            
            chat_id = entity.id if hasattr(entity, 'id') else 'unknown'
            
            # Обновляем группу в БД (независимо от can_post, чтобы сохранить информацию)
            db = SessionLocal()
            try:
                # Блокируем группу для обновления
                locked_group = db.query(Group).filter(Group.id == group_id).with_for_update().first()
                
                if not locked_group:
                    return False, "Группа не найдена в БД"
                
                # Обновляем информацию о группе
                now = datetime.utcnow()
                locked_group.assigned_account_id = account.id
                locked_group.joined_at = now
                locked_group.warm_up_until = now + timedelta(hours=self.warm_up_hours)
                # ВАЖНО: Записываем результат проверки прав в БД ПЕРЕД установкой статуса
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
                except:
                    pass
                
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
        ).order_by(Group.created_at)
        
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
            new_groups_orm = self.get_new_groups(db, niche, limit=50)  # Максимум 50 за раз
            
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
        for idx, group_data in enumerate(groups_to_process, 1):
            group_id = group_data['id']
            group_username = group_data['username']
            
            try:
                # Выбираем аккаунт для вступления (открываем короткую сессию только для этого)
                db = SessionLocal()
                try:
                    loaded_clients = set(self.client_manager.clients.keys()) if self.client_manager.clients else set()
                    account = self.get_least_loaded_account(db, loaded_clients=loaded_clients)
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
                    
                    # ОБРАБОТКА JOIN REQUEST (заявка на вступление)
                    # Если отправлена заявка, НЕ проверяем права и НЕ помечаем как read_only
                    if error and ("waiting for approval" in error.lower() or "not a member after join request" in error.lower()):
                        # Открываем короткую сессию только для обновления статуса
                        db = SessionLocal()
                        try:
                            group = db.query(Group).filter(Group.id == group_id).first()
                            if group:
                                group.status = 'pending'
                                group.updated_at = datetime.utcnow()
                                db.commit()
                                logger.info(f"  📤 Группа {group_username} помечена как 'pending' - заявка отправлена, ждем одобрения")
                        except Exception as e:
                            db.rollback()
                            logger.error(f"  ❌ Ошибка при обновлении статуса на pending: {e}")
                        finally:
                            db.close()
                        # Небольшая пауза и продолжаем
                        await asyncio.sleep(30)
                    # Если группа недоступна, помечаем её
                    elif error and ("не найдена" in error.lower() or "приватная" in error.lower() or "inaccessible" in error.lower()):
                        # Открываем короткую сессию только для обновления статуса
                        db = SessionLocal()
                        try:
                            group = db.query(Group).filter(Group.id == group_id).first()
                            if group:
                                group.status = 'inaccessible'
                                db.commit()
                        except:
                            db.rollback()
                        finally:
                            db.close()
                        await asyncio.sleep(30)
                    # Обработка FloodWait - пропускаем группу, но продолжаем
                    elif error and ("wait" in error.lower() or "flood" in error.lower()):
                        logger.warning(f"  ⏳ FloodWait для {group_username}, пропускаем эту группу")
                        # Небольшая пауза и продолжаем
                        await asyncio.sleep(30)
                    else:
                        # Короткая пауза при ошибке
                        await asyncio.sleep(60)
            
            except Exception as e:
                logger.error(f"❌ Ошибка при обработке группы {group_username} (ID: {group_id}): {e}", exc_info=True)
                failed_count += 1
                await asyncio.sleep(30)
        
        logger.info(f"\n✅ Обработано: {joined_count} вступлений, {failed_count} неудач")
        
        return joined_count, failed_count
