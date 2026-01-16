#!/usr/bin/env python3
"""
Комплексная проверка и очистка групп
1. Проверяет группы на основе ошибок в БД
2. Проверяет права доступа через Telegram API
3. Обновляет статус в БД
4. Очищает targets.txt от заблокированных групп
5. Создает отчет
"""
import sys
import asyncio
import json
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from sqlalchemy import func, and_, or_

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.database.session import SessionLocal, init_db
from shared.database.models import Account, Group, Post
from shared.telegram.client_manager import TelegramClientManager
from telethon.errors import (
    UsernameNotOccupiedError,
    ChannelPrivateError,
    UserBannedInChannelError,
    ChatWriteForbiddenError,
    FloodWaitError
)

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/comprehensive_group_cleanup.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


async def check_group_permissions(client, group_username, logger):
    """
    Проверяет права на постинг в группе
    
    Returns:
        (can_post: bool, reason: str)
    """
    try:
        entity = await client.get_entity(group_username)
        me = await client.get_me()
        
        # Получаем права
        try:
            permissions = await client.get_permissions(entity, me)
            
            if permissions:
                # Проверяем, может ли постить
                can_post = True
                reason = "OK"
                
                if hasattr(permissions, 'send_messages') and not permissions.send_messages:
                    can_post = False
                    reason = "No send_messages permission"
                elif hasattr(permissions, 'banned_rights') and permissions.banned_rights:
                    if hasattr(permissions.banned_rights, 'send_messages') and permissions.banned_rights.send_messages:
                        can_post = False
                        reason = "Banned rights: send_messages forbidden"
                
                return can_post, reason
            else:
                return False, "Cannot get permissions (not a member?)"
                
        except UserBannedInChannelError:
            return False, "Banned in channel"
        except ChatWriteForbiddenError:
            return False, "Write forbidden"
        except Exception as e:
            return False, f"Permission check error: {str(e)}"
            
    except UsernameNotOccupiedError:
        return False, "Username not occupied"
    except ChannelPrivateError:
        return False, "Channel private"
    except UserBannedInChannelError:
        return False, "Banned in channel"
    except Exception as e:
        return False, f"Error: {str(e)}"


async def comprehensive_cleanup():
    """Комплексная проверка и очистка групп"""
    logger.info("=" * 80)
    logger.info("🔍 КОМПЛЕКСНАЯ ПРОВЕРКА И ОЧИСТКА ГРУПП")
    logger.info("=" * 80)
    
    init_db()
    db = SessionLocal()
    
    try:
        # Инициализация клиентов
        sessions_dir = Path(__file__).parent.parent / "sessions"
        if not sessions_dir.exists():
            sessions_dir = Path("/app/sessions")
        
        client_manager = TelegramClientManager(sessions_dir=str(sessions_dir))
        await client_manager.load_accounts_from_db(db)
        
        logger.info(f"✅ Загружено аккаунтов: {len(client_manager.clients)}")
        
        # ШАГ 1: Анализ ошибок в БД за последние 7 дней
        logger.info("\n" + "=" * 80)
        logger.info("📊 ШАГ 1: Анализ ошибок в БД")
        logger.info("=" * 80)
        
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        
        # Группы с ошибками Write forbidden
        banned_errors = db.query(
            Post.group_id,
            func.count(Post.id).label('error_count')
        ).filter(
            and_(
                Post.sent_at >= seven_days_ago,
                Post.success == False,
                or_(
                    Post.error_message.like('%Write forbidden%'),
                    Post.error_message.like('%banned%'),
                    Post.error_message.like('%Channel private%')
                )
            )
        ).group_by(Post.group_id).all()
        
        groups_with_errors = {}
        for group_id, error_count in banned_errors:
            group = db.query(Group).filter(Group.id == group_id).first()
            if group:
                groups_with_errors[group.username] = error_count
        
        logger.info(f"📋 Найдено групп с ошибками: {len(groups_with_errors)}")
        logger.info("   Топ-10 групп с ошибками:")
        for i, (group_username, count) in enumerate(sorted(groups_with_errors.items(), key=lambda x: x[1], reverse=True)[:10], 1):
            logger.info(f"   {i}. {group_username}: {count} ошибок")
        
        # ШАГ 2: Проверка активных групп через Telegram API
        logger.info("\n" + "=" * 80)
        logger.info("🔍 ШАГ 2: Проверка прав доступа через Telegram API")
        logger.info("=" * 80)
        
        # Получаем активные группы для проверки
        active_groups = db.query(Group).filter(
            Group.status == 'active',
            Group.can_post == True
        ).all()
        
        logger.info(f"📋 Найдено активных групп для проверки: {len(active_groups)}")
        logger.info("🔄 Начинаю проверку...")
        
        checked = 0
        can_post_count = 0
        banned_count = 0
        inaccessible_count = 0
        groups_to_ban = []
        groups_to_mark_inaccessible = []
        
        # Используем первый доступный аккаунт для проверки
        account = db.query(Account).filter(Account.status == 'active').first()
        if not account:
            logger.error("❌ Нет активных аккаунтов")
            return
        
        client = client_manager.clients.get(account.session_name)
        if not client:
            logger.warning(f"⚠️ Клиент {account.session_name} не загружен, загружаю...")
            await client_manager.load_accounts_from_db(db)
            client = client_manager.clients.get(account.session_name)
        
        if not client:
            logger.error(f"❌ Не удалось загрузить клиент {account.session_name}")
            return
        
        if not client.is_connected():
            client = await client_manager.ensure_client_connected(account.session_name)
            if not client:
                logger.error(f"❌ Не удалось подключить клиент {account.session_name}")
                return
        
        logger.info(f"👤 Использую аккаунт: {account.session_name}")
        
        # Проверяем группы (начинаем с тех, у которых есть ошибки)
        groups_to_check = []
        
        # Сначала проверяем группы с ошибками
        for group in active_groups:
            if group.username in groups_with_errors:
                groups_to_check.append((group, True))  # True = has errors
        
        # Затем остальные
        for group in active_groups:
            if group.username not in groups_with_errors:
                groups_to_check.append((group, False))
        
        for group, has_errors in groups_to_check:
            checked += 1
            
            try:
                can_post, reason = await check_group_permissions(client, group.username, logger)
                
                if can_post:
                    can_post_count += 1
                    logger.info(f"  [{checked}/{len(groups_to_check)}] ✅ {group.username}: может постить")
                    
                    # Если группа была помечена как banned, но теперь может постить - восстанавливаем
                    if group.status == 'banned':
                        group.status = 'active'
                        group.can_post = True
                        db.commit()
                        logger.info(f"     🔄 Восстановлен статус группы {group.username}")
                else:
                    if has_errors or 'banned' in reason.lower() or 'forbidden' in reason.lower():
                        banned_count += 1
                        groups_to_ban.append((group, reason))
                        logger.warning(f"  [{checked}/{len(groups_to_check)}] 🚫 {group.username}: {reason}")
                    else:
                        inaccessible_count += 1
                        groups_to_mark_inaccessible.append((group, reason))
                        logger.warning(f"  [{checked}/{len(groups_to_check)}] ⚠️ {group.username}: {reason}")
                
            except Exception as e:
                logger.error(f"  [{checked}/{len(groups_to_check)}] ❌ {group.username}: ошибка проверки - {e}")
                inaccessible_count += 1
                groups_to_mark_inaccessible.append((group, str(e)))
            
            # Пауза между проверками
            if checked % 10 == 0:
                logger.info(f"  ⏸️ Пауза 5 секунд... (проверено {checked}/{len(groups_to_check)})")
                await asyncio.sleep(5)
            else:
                await asyncio.sleep(2)
        
        # ШАГ 3: Обновление статусов в БД
        logger.info("\n" + "=" * 80)
        logger.info("📝 ШАГ 3: Обновление статусов в БД")
        logger.info("=" * 80)
        
        for group, reason in groups_to_ban:
            try:
                group.status = 'banned'
                group.can_post = False
                db.commit()
                logger.info(f"  🚫 Помечена как banned: {group.username} ({reason})")
            except Exception as e:
                logger.error(f"  ❌ Ошибка обновления {group.username}: {e}")
                db.rollback()
        
        for group, reason in groups_to_mark_inaccessible:
            try:
                group.status = 'inaccessible'
                group.can_post = False
                db.commit()
                logger.info(f"  ⚠️ Помечена как inaccessible: {group.username} ({reason})")
            except Exception as e:
                logger.error(f"  ❌ Ошибка обновления {group.username}: {e}")
                db.rollback()
        
        # ШАГ 4: Очистка targets.txt
        logger.info("\n" + "=" * 80)
        logger.info("🧹 ШАГ 4: Очистка targets.txt")
        logger.info("=" * 80)
        
        targets_file = Path(__file__).parent.parent / "targets.txt"
        if targets_file.exists():
            # Создаем backup
            backup_file = targets_file.parent / f"targets.txt.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            shutil.copy2(targets_file, backup_file)
            logger.info(f"💾 Создан backup: {backup_file}")
            
            # Читаем текущий targets.txt
            with open(targets_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Получаем список заблокированных групп
            banned_usernames = {g.username for g, _ in groups_to_ban}
            inaccessible_usernames = {g.username for g, _ in groups_to_mark_inaccessible}
            all_blocked = banned_usernames | inaccessible_usernames
            
            # Фильтруем строки
            valid_lines = []
            removed_count = 0
            
            for line in lines:
                stripped = line.strip()
                if not stripped or stripped.startswith('#'):
                    valid_lines.append(line)
                    continue
                
                # Проверяем, не заблокирована ли группа
                if stripped in all_blocked:
                    removed_count += 1
                    logger.debug(f"  Удалена из targets.txt: {stripped}")
                    continue
                
                valid_lines.append(line)
            
            # Записываем обновленный файл
            with open(targets_file, 'w', encoding='utf-8') as f:
                f.writelines(valid_lines)
            
            logger.info(f"✅ Обновлен targets.txt: удалено {removed_count} групп")
        else:
            logger.warning("⚠️ targets.txt не найден, пропускаю очистку")
        
        # ШАГ 5: Итоговый отчет
        logger.info("\n" + "=" * 80)
        logger.info("📊 ИТОГОВЫЙ ОТЧЕТ")
        logger.info("=" * 80)
        logger.info(f"✅ Проверено групп: {checked}")
        logger.info(f"✅ Могут постить: {can_post_count}")
        logger.info(f"🚫 Помечено как banned: {banned_count}")
        logger.info(f"⚠️ Помечено как inaccessible: {inaccessible_count}")
        logger.info(f"🧹 Удалено из targets.txt: {removed_count if targets_file.exists() else 0}")
        logger.info("=" * 80)
        logger.info("✅ ПРОВЕРКА ЗАВЕРШЕНА")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    try:
        asyncio.run(comprehensive_cleanup())
    except KeyboardInterrupt:
        logger.info("🛑 Прервано пользователем")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)
