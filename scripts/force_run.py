#!/usr/bin/env python3
"""
Скрипт принудительного запуска сервисов для тестирования
Позволяет запустить логику сервиса прямо сейчас, игнорируя расписание и warm-up периоды
"""
import sys
import asyncio
import argparse
from pathlib import Path
from datetime import datetime

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.database.session import SessionLocal, init_db
from shared.database.models import Account, Group
from shared.config.loader import ConfigLoader
from shared.telegram.client_manager import TelegramClientManager

# Импортируем классы сервисов
from services.marketer.poster import Poster
import importlib.util

# Импорт finder (account-manager использует дефисы в пути)
finder_path = Path(__file__).parent.parent / "services" / "account-manager" / "finder.py"
finder_spec = importlib.util.spec_from_file_location("finder", finder_path)
finder_module = importlib.util.module_from_spec(finder_spec)
finder_spec.loader.exec_module(finder_module)
GroupFinder = finder_module.GroupFinder

# Импорт joiner
joiner_path = Path(__file__).parent.parent / "services" / "account-manager" / "joiner.py"
joiner_spec = importlib.util.spec_from_file_location("joiner", joiner_path)
joiner_module = importlib.util.module_from_spec(joiner_spec)
joiner_spec.loader.exec_module(joiner_module)
GroupJoiner = joiner_module.GroupJoiner

from services.activity.story_viewer import StoryViewer

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_marketer(group_username: str, use_test_config: bool = False):
    """
    Тестирование Marketer: принудительный постинг в указанную группу
    
    Args:
        group_username: Username группы (например, @my_test_group)
        use_test_config: Использовать тестовый конфиг (test_debug)
    """
    logger.info("=" * 80)
    logger.info("🧪 ТЕСТ MARKETER - Принудительный постинг")
    logger.info("=" * 80)
    
    # Загрузка конфигурации
    config_dir = Path(__file__).parent.parent / "config"
    if not config_dir.exists():
        config_dir = Path("/app/config")
    
    config_loader = ConfigLoader(config_dir=str(config_dir))
    if use_test_config:
        niche_config = config_loader.load_niche_config('test_debug')
        logger.info("📋 Используется тестовый конфиг: test_debug")
    else:
        niche_config = config_loader.load_niche_config()
        logger.info(f"📋 Используется активный конфиг: {niche_config['display_name']}")
    
    # Инициализация компонентов
    # Определяем правильный путь к sessions (на хосте или в Docker)
    sessions_dir = Path(__file__).parent.parent / "sessions"
    if not sessions_dir.exists():
        sessions_dir = Path("/app/sessions")  # Fallback для Docker
    
    client_manager = TelegramClientManager(sessions_dir=str(sessions_dir))
    db = SessionLocal()
    try:
        # Загрузка аккаунтов
        await client_manager.load_accounts_from_db(db)
        if not client_manager.clients:
            logger.error("❌ Нет активных аккаунтов")
            return
        
        # Получение группы из БД
        group = db.query(Group).filter(Group.username == group_username).first()
        if not group:
            logger.error(f"❌ Группа {group_username} не найдена в БД")
            logger.info("💡 Добавьте группу в БД командой:")
            logger.info(f"   python scripts/force_run.py --service manager --add-group {group_username}")
            return
        
        logger.info(f"✅ Группа найдена: {group.title or group_username} ({group.username})")
        
        # Получаем назначенный аккаунт или выбираем свободный
        account = None
        if group.assigned_account_id:
            account = db.query(Account).filter(Account.id == group.assigned_account_id).first()
            if account:
                logger.info(f"✅ Используется назначенный аккаунт: {account.session_name}")
            else:
                logger.warning(f"⚠️ Назначенный аккаунт не найден, выбираем другой")
                account = None
        
        # Если аккаунт не назначен или не найден, выбираем из успешно подключенных
        if not account:
            # Выбираем первый аккаунт, у которого есть активный клиент
            for session_name, client in client_manager.clients.items():
                if client and client.is_connected():
                    account = db.query(Account).filter(Account.session_name == session_name).first()
                    if account:
                        logger.info(f"✅ Используется аккаунт: {account.session_name}")
                        # Назначаем аккаунт группе
                        group.assigned_account_id = account.id
                        db.commit()
                        logger.info(f"✅ Аккаунт назначен группе")
                        break
            
            if not account:
                logger.error("❌ Нет доступных аккаунтов с активными клиентами")
                return
        
        # Игнорируем warm-up период для теста
        original_warm_up = group.warm_up_until
        group.warm_up_until = None
        db.commit()
        logger.info("⚠️ Warm-up период отключен для теста")
        
        # Получаем клиент
        client = client_manager.clients.get(account.session_name)
        if not client or not client.is_connected():
            logger.error(f"❌ Клиент {account.session_name} не найден или не подключен")
            # Пробуем найти другой доступный клиент
            for session_name, alt_client in client_manager.clients.items():
                if alt_client and alt_client.is_connected():
                    account = db.query(Account).filter(Account.session_name == session_name).first()
                    if account:
                        client = alt_client
                        group.assigned_account_id = account.id
                        db.commit()
                        logger.info(f"✅ Используется альтернативный аккаунт: {account.session_name}")
                        break
            
            if not client or not client.is_connected():
                logger.error("❌ Нет доступных подключенных клиентов")
                return
        
        # Инициализация Poster
        poster = Poster(client_manager, config_loader, niche_config)
        await poster.initialize()
        
        # Если используется тестовый конфиг, подменяем сообщение
        if use_test_config:
            test_message = niche_config.get('marketer', {}).get('test_message', '🔔 Это тестовое сообщение системы')
            poster.messages = [test_message]
            logger.info(f"📝 Используется тестовое сообщение: {test_message[:50]}...")
        
        # Выполняем постинг с перебором аккаунтов, если первый забанен
        logger.info(f"📤 Попытка постинга в {group_username}...")
        success, error = await poster.post_to_group(db, group, account, client)
        
        # Если постинг не удался из-за бана, пробуем другие аккаунты
        if not success and error and ("banned" in str(error).lower() or "write forbidden" in str(error).lower()):
            logger.warning(f"⚠️ Аккаунт {account.session_name} забанен, пробуем другие аккаунты...")
            tried_accounts = {account.session_name}
            
            for alt_session_name, alt_client in client_manager.clients.items():
                if alt_session_name in tried_accounts:
                    continue
                if not alt_client or not alt_client.is_connected():
                    continue
                
                alt_account = db.query(Account).filter(Account.session_name == alt_session_name).first()
                if not alt_account:
                    continue
                
                logger.info(f"🔄 Пробуем аккаунт: {alt_account.session_name}")
                success, error = await poster.post_to_group(db, group, alt_account, alt_client)
                
                if success:
                    logger.info(f"✅ Постинг успешен в {group_username} с аккаунтом {alt_account.session_name}")
                    # Назначаем рабочий аккаунт группе
                    group.assigned_account_id = alt_account.id
                    db.commit()
                    break
                else:
                    tried_accounts.add(alt_session_name)
                    logger.warning(f"⚠️ Аккаунт {alt_account.session_name} тоже не подошел: {error}")
            
            if not success:
                logger.error(f"❌ Ошибка постинга: {error}")
        elif success:
            logger.info(f"✅ Постинг успешен в {group_username}")
        else:
            logger.error(f"❌ Ошибка постинга: {error}")
        
        # Восстанавливаем warm-up период
        group.warm_up_until = original_warm_up
        db.commit()
        
    except Exception as e:
        logger.error(f"❌ Ошибка при тестировании Marketer: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()


async def test_manager(keyword: str, use_test_config: bool = False):
    """
    Тестирование Manager: принудительный поиск групп по ключевому слову
    
    Args:
        keyword: Ключевое слово для поиска
        use_test_config: Использовать тестовый конфиг (test_debug)
    """
    logger.info("=" * 80)
    logger.info("🧪 ТЕСТ MANAGER - Принудительный поиск групп")
    logger.info("=" * 80)
    
    # Загрузка конфигурации
    config_dir = Path(__file__).parent.parent / "config"
    if not config_dir.exists():
        config_dir = Path("/app/config")
    
    config_loader = ConfigLoader(config_dir=str(config_dir))
    if use_test_config:
        niche_config = config_loader.load_niche_config('test_debug')
        logger.info("📋 Используется тестовый конфиг: test_debug")
    else:
        niche_config = config_loader.load_niche_config()
        logger.info(f"📋 Используется активный конфиг: {niche_config['display_name']}")
    
    # Инициализация компонентов
    # Определяем правильный путь к sessions (на хосте или в Docker)
    sessions_dir = Path(__file__).parent.parent / "sessions"
    if not sessions_dir.exists():
        sessions_dir = Path("/app/sessions")  # Fallback для Docker
    
    client_manager = TelegramClientManager(sessions_dir=str(sessions_dir))
    db = SessionLocal()
    try:
        # Загрузка аккаунтов
        await client_manager.load_accounts_from_db(db)
        if not client_manager.clients:
            logger.error("❌ Нет активных аккаунтов")
            return
        
        # Выбираем первый активный аккаунт
        account = db.query(Account).filter(Account.status == 'active').first()
        if not account:
            logger.error("❌ Нет активных аккаунтов")
            return
        
        logger.info(f"✅ Используется аккаунт: {account.session_name}")
        
        # Получаем клиент
        client = client_manager.clients.get(account.session_name)
        if not client:
            logger.error(f"❌ Клиент {account.session_name} не найден")
            return
        
        # Инициализация Finder
        finder = GroupFinder(client_manager)
        
        # Выполняем поиск
        logger.info(f"🔍 Поиск групп по ключевому слову: {keyword}")
        found_groups = await finder.search_groups(client, [keyword], limit_per_keyword=10)
        
        logger.info(f"✅ Найдено {len(found_groups)} групп")
        for group_info in found_groups:
            logger.info(f"  • {group_info.get('username')} - {group_info.get('title')}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при тестировании Manager: {e}", exc_info=True)
    finally:
        db.close()


async def test_join_group(group_username: str, use_test_config: bool = False):
    """
    Тестирование Manager: принудительное вступление в группу через GroupJoiner
    
    Args:
        group_username: Username группы (например, @lexus_auto_sale)
        use_test_config: Использовать тестовый конфиг (test_debug)
    """
    logger.info("=" * 80)
    logger.info("🧪 ТЕСТ MANAGER - Принудительное вступление в группу")
    logger.info("=" * 80)
    
    # Загрузка конфигурации
    config_dir = Path(__file__).parent.parent / "config"
    if not config_dir.exists():
        config_dir = Path("/app/config")
    
    config_loader = ConfigLoader(config_dir=str(config_dir))
    if use_test_config:
        niche_config = config_loader.load_niche_config('test_debug')
        logger.info("📋 Используется тестовый конфиг: test_debug")
    else:
        niche_config = config_loader.load_niche_config()
        logger.info(f"📋 Используется активный конфиг: {niche_config['display_name']}")
    
    # Инициализация компонентов
    sessions_dir = Path(__file__).parent.parent / "sessions"
    if not sessions_dir.exists():
        sessions_dir = Path("/app/sessions")
    
    client_manager = TelegramClientManager(sessions_dir=str(sessions_dir))
    db = SessionLocal()
    try:
        # Загрузка аккаунтов
        await client_manager.load_accounts_from_db(db)
        if not client_manager.clients:
            logger.error("❌ Нет активных аккаунтов")
            return
        
        # Получаем группу из БД или создаем новую
        group = db.query(Group).filter(Group.username == group_username).first()
        if not group:
            logger.info(f"ℹ️ Группа {group_username} не найдена в БД, создаю...")
            niche = niche_config.get('name', 'cars')
            group = Group(
                username=group_username,
                title=f"Test Group: {group_username}",
                niche=niche,
                status='new',
                can_post=True,
                created_at=datetime.utcnow()
            )
            db.add(group)
            db.commit()
            logger.info(f"✅ Группа {group_username} создана в БД со статусом 'new'")
        else:
            # Сбрасываем статус на 'new' для повторного вступления
            if group.status != 'new':
                logger.info(f"ℹ️ Сбрасываю статус группы {group_username} на 'new'")
                group.status = 'new'
                group.assigned_account_id = None
                group.joined_at = None
                group.warm_up_until = None
                db.commit()
        
        # Инициализация GroupJoiner
        joiner = GroupJoiner(client_manager, niche_config)
        
        # Пробуем вступить с разными аккаунтами, если первый получает FloodWait
        tried_account_ids = []
        success = False
        error = None
        
        for attempt in range(5):  # Максимум 5 попыток
            # Выбираем аккаунт для вступления (исключая уже испробованные)
            account = joiner.get_least_loaded_account(db, exclude_account_ids=tried_account_ids)
            if not account:
                logger.error("❌ Нет доступных аккаунтов для вступления")
                break
            
            # Проверяем, что клиент доступен
            if account.session_name not in client_manager.clients:
                logger.warning(f"⚠️ Клиент {account.session_name} не загружен, пропускаем")
                tried_account_ids.append(account.id)
                continue
            
            client = client_manager.clients[account.session_name]
            
            logger.info(f"🚪 Попытка {attempt + 1}: вступаю в {group_username} через {account.session_name}...")
            success, error = await joiner.join_group(client, account, group)
            
            if success:
                # Перезагружаем группу из БД, так как она была обновлена в другой сессии
                db.refresh(group)
                logger.info(f"✅ Успешно вступил в {group_username}")
                logger.info(f"   Аккаунт: {account.session_name}")
                logger.info(f"   Статус группы: {group.status}")
                logger.info(f"   Можно постить: {group.can_post}")
                break
            else:
                tried_account_ids.append(account.id)
                # Если FloodWait - пробуем другой аккаунт
                if error and ("wait" in error.lower() or "flood" in error.lower()):
                    logger.warning(f"⚠️ Аккаунт {account.session_name} получил FloodWait, пробуем другой...")
                    continue
                else:
                    logger.warning(f"⚠️ Аккаунт {account.session_name} не подошел: {error}, пробуем другой...")
                    continue
        
        if not success:
            logger.error(f"❌ Не удалось вступить в группу после {len(tried_account_ids)} попыток. Последняя ошибка: {error}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при тестировании вступления: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()


async def test_activity(group_username: str, use_test_config: bool = False):
    """
    Тестирование Activity: принудительный просмотр Stories участников группы
    
    Args:
        group_username: Username группы (например, @my_test_group)
        use_test_config: Использовать тестовый конфиг (test_debug)
    """
    logger.info("=" * 80)
    logger.info("🧪 ТЕСТ ACTIVITY - Принудительный просмотр Stories")
    logger.info("=" * 80)
    
    # Загрузка конфигурации
    config_dir = Path(__file__).parent.parent / "config"
    if not config_dir.exists():
        config_dir = Path("/app/config")
    
    config_loader = ConfigLoader(config_dir=str(config_dir))
    if use_test_config:
        niche_config = config_loader.load_niche_config('test_debug')
        logger.info("📋 Используется тестовый конфиг: test_debug")
    else:
        niche_config = config_loader.load_niche_config()
        logger.info(f"📋 Используется активный конфиг: {niche_config['display_name']}")
    
    # Инициализация компонентов
    # Определяем правильный путь к sessions (на хосте или в Docker)
    sessions_dir = Path(__file__).parent.parent / "sessions"
    if not sessions_dir.exists():
        sessions_dir = Path("/app/sessions")  # Fallback для Docker
    
    client_manager = TelegramClientManager(sessions_dir=str(sessions_dir))
    db = SessionLocal()
    try:
        # Загрузка аккаунтов
        await client_manager.load_accounts_from_db(db)
        if not client_manager.clients:
            logger.error("❌ Нет активных аккаунтов")
            return
        
        # Получение группы из БД
        group = db.query(Group).filter(Group.username == group_username).first()
        if not group:
            logger.error(f"❌ Группа {group_username} не найдена в БД")
            logger.info("💡 Добавьте группу в БД командой:")
            logger.info(f"   python scripts/force_run.py --service manager --add-group {group_username}")
            return
        
        logger.info(f"✅ Группа найдена: {group.title or group_username} ({group.username})")
        
        # Получаем назначенный аккаунт или выбираем первый
        if group.assigned_account_id:
            account = db.query(Account).filter(Account.id == group.assigned_account_id).first()
        else:
            account = db.query(Account).filter(Account.status == 'active').first()
        
        if not account:
            logger.error("❌ Нет активных аккаунтов")
            return
        
        logger.info(f"✅ Используется аккаунт: {account.session_name}")
        
        # Получаем клиент
        client = client_manager.clients.get(account.session_name)
        if not client:
            logger.error(f"❌ Клиент {account.session_name} не найден")
            return
        
        # Инициализация StoryViewer
        story_viewer = StoryViewer(client_manager, niche_config)
        
        # Выполняем просмотр Stories
        logger.info(f"👁️ Просмотр Stories участников группы {group_username}...")
        viewed, reactions = await story_viewer.process_account(account)
        
        logger.info(f"✅ Просмотрено {viewed} Stories, поставлено {reactions} реакций")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при тестировании Activity: {e}", exc_info=True)
    finally:
        db.close()


async def test_secretary(use_test_config: bool = False):
    """
    Тестирование Secretary: проверка ответа на тестовое сообщение
    
    Args:
        use_test_config: Использовать тестовый конфиг (test_debug)
    """
    logger.info("=" * 80)
    logger.info("🧪 ТЕСТ SECRETARY - Проверка автоответчика")
    logger.info("=" * 80)
    
    # Загрузка конфигурации
    config_dir = Path(__file__).parent.parent / "config"
    if not config_dir.exists():
        config_dir = Path("/app/config")
    
    config_loader = ConfigLoader(config_dir=str(config_dir))
    if use_test_config:
        niche_config = config_loader.load_niche_config('test_debug')
        logger.info("📋 Используется тестовый конфиг: test_debug")
    else:
        niche_config = config_loader.load_niche_config()
        logger.info(f"📋 Используется активный конфиг: {niche_config['display_name']}")
    
    from services.secretary.gpt_handler import GPTHandler
    import os
    
    # Проверка OpenAI API ключа
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        logger.error("❌ OPENAI_API_KEY не установлен")
        return
    
    # Инициализация GPTHandler
    gpt_handler = GPTHandler(api_key=api_key, niche_config=niche_config)
    
    # Тестовое сообщение
    test_message = "PING"
    logger.info(f"📨 Тестовое сообщение: {test_message}")
    
    # Генерация ответа
    logger.info("🤖 Генерация ответа через GPT-4o-mini...")
    response = await gpt_handler.generate_response(
        incoming_message=test_message,
        conversation_history=[],
        user_info=None
    )
    
    logger.info(f"✅ Ответ получен: {response}")
    
    if use_test_config and "PONG" in response.upper():
        logger.info("✅ Тест Secretary пройден! Ответ содержит PONG")
    elif not use_test_config:
        logger.info("✅ Тест Secretary пройден! GPT ответил на сообщение")
    else:
        logger.warning("⚠️ Тест Secretary: ответ не содержит PONG (возможно, используется обычный конфиг)")


async def add_test_group(group_username: str, niche: str = 'cars'):
    """
    Добавить тестовую группу в БД
    
    Args:
        group_username: Username группы (например, @my_test_group)
        niche: Ниша группы (default: 'cars')
    """
    logger.info("=" * 80)
    logger.info("➕ ДОБАВЛЕНИЕ ТЕСТОВОЙ ГРУППЫ В БД")
    logger.info("=" * 80)
    
    db = SessionLocal()
    try:
        # Проверяем, есть ли уже такая группа
        existing = db.query(Group).filter(Group.username == group_username).first()
        if existing:
            logger.info(f"ℹ️ Группа {group_username} уже есть в БД")
            existing.status = 'active'
            existing.can_post = True
            existing.warm_up_until = None  # Убираем warm-up для тестов
            db.commit()
            logger.info(f"✅ Группа обновлена: status=active, warm_up_until=null")
            return
        
        # Создаем новую группу
        new_group = Group(
            username=group_username,
            title=f"Test Group: {group_username}",
            niche=niche,
            status='active',
            can_post=True,
            warm_up_until=None,  # Без warm-up для тестов
            created_at=datetime.utcnow()
        )
        
        db.add(new_group)
        db.commit()
        
        logger.info(f"✅ Группа {group_username} добавлена в БД (niche={niche})")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при добавлении группы: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()


def main():
    """Основная функция"""
    parser = argparse.ArgumentParser(
        description='Принудительный запуск сервисов для тестирования',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:

  # Тест Marketer: постинг в тестовую группу
  python scripts/force_run.py --service marketer --group @my_test_group --test-config

  # Тест Manager: поиск групп по ключевому слову
  python scripts/force_run.py --service manager --keyword "test_group_verification_123" --test-config

  # Тест Manager: принудительное вступление в группу
  python scripts/force_run.py --service manager --join-group --group @my_test_group --test-config

  # Тест Activity: просмотр Stories участников группы
  python scripts/force_run.py --service activity --group @my_test_group --test-config

  # Тест Secretary: проверка ответа GPT
  python scripts/force_run.py --service secretary --test-config

  # Добавить тестовую группу в БД
  python scripts/force_run.py --service manager --add-group --group @my_test_group
        """
    )
    
    parser.add_argument('--service', required=True, choices=['marketer', 'manager', 'activity', 'secretary'],
                        help='Сервис для тестирования')
    parser.add_argument('--group', help='Username группы (для marketer и activity)')
    parser.add_argument('--keyword', help='Ключевое слово для поиска (для manager)')
    parser.add_argument('--test-config', action='store_true',
                        help='Использовать тестовый конфиг (test_debug)')
    parser.add_argument('--add-group', action='store_true',
                        help='Добавить группу в БД (используется с --group)')
    parser.add_argument('--join-group', action='store_true',
                        help='Принудительно вступить в группу через GroupJoiner (используется с --group для manager)')
    parser.add_argument('--niche', default='cars',
                        help='Ниша для добавления группы (default: cars)')
    
    args = parser.parse_args()
    
    # Инициализация БД
    try:
        init_db()
    except Exception as e:
        logger.warning(f"⚠️ Ошибка инициализации БД (возможно, уже инициализирована): {e}")
    
    if args.add_group:
        # Добавление группы в БД
        if not args.group:
            logger.error("❌ Необходимо указать --group для добавления группы")
            return
        asyncio.run(add_test_group(args.group, args.niche))
        return
    
    # Запуск тестов
    if args.service == 'marketer':
        if not args.group:
            logger.error("❌ Необходимо указать --group для тестирования Marketer")
            return
        asyncio.run(test_marketer(args.group, args.test_config))
    
    elif args.service == 'manager':
        if args.join_group:
            if not args.group:
                logger.error("❌ Необходимо указать --group для вступления в группу")
                return
            asyncio.run(test_join_group(args.group, args.test_config))
        elif args.keyword:
            asyncio.run(test_manager(args.keyword, args.test_config))
        else:
            logger.error("❌ Необходимо указать --keyword или --join-group для тестирования Manager")
            return
    
    elif args.service == 'activity':
        if not args.group:
            logger.error("❌ Необходимо указать --group для тестирования Activity")
            return
        asyncio.run(test_activity(args.group, args.test_config))
    
    elif args.service == 'secretary':
        asyncio.run(test_secretary(args.test_config))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("🛑 Прервано пользователем")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)

