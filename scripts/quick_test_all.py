#!/usr/bin/env python3
"""
🚀 БЫСТРЫЙ ТЕСТ ВСЕХ УЗЛОВ СИСТЕМЫ
Тестирует все компоненты перед рассылкой
"""
import sys
import asyncio
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.database.session import SessionLocal, init_db
from shared.database.models import Account, Group, Post
from shared.config.loader import ConfigLoader
from shared.telegram.client_manager import TelegramClientManager

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Импорт компонентов
from services.marketer.poster import Poster
import importlib.util

finder_path = Path(__file__).parent.parent / "services" / "account-manager" / "finder.py"
finder_spec = importlib.util.spec_from_file_location("finder", finder_path)
finder_module = importlib.util.module_from_spec(finder_spec)
finder_spec.loader.exec_module(finder_module)
GroupFinder = finder_module.GroupFinder

joiner_path = Path(__file__).parent.parent / "services" / "account-manager" / "joiner.py"
joiner_spec = importlib.util.spec_from_file_location("joiner", joiner_path)
joiner_module = importlib.util.module_from_spec(joiner_spec)
joiner_spec.loader.exec_module(joiner_module)
GroupJoiner = joiner_module.GroupJoiner

from services.activity.story_viewer import StoryViewer
from services.secretary.gpt_handler import GPTHandler
import os


class QuickTestSystem:
    """Быстрое тестирование всех узлов системы"""
    
    def __init__(self, test_group_username: str):
        self.test_group_username = test_group_username
        self.results = {
            'database': False,
            'config': False,
            'accounts': False,
            'test_group': False,
            'account_manager': False,
            'marketer': False,
            'secretary': False,
            'activity': False
        }
        self.errors = []
        
        # Определяем пути
        self.config_dir = Path(__file__).parent.parent / "config"
        if not self.config_dir.exists():
            self.config_dir = Path("/app/config")
        
        self.sessions_dir = Path(__file__).parent.parent / "sessions"
        if not self.sessions_dir.exists():
            self.sessions_dir = Path("/app/sessions")
        
        self.config_loader = None
        self.niche_config = None
        self.client_manager = None
        self.db = None
    
    async def run_all_tests(self):
        """Запустить все тесты"""
        logger.info("=" * 80)
        logger.info("🚀 БЫСТРЫЙ ТЕСТ ВСЕХ УЗЛОВ СИСТЕМЫ")
        logger.info("=" * 80)
        logger.info(f"Тестовая группа: {self.test_group_username}")
        logger.info("=" * 80)
        logger.info("")
        
        try:
            # 1. Тест БД
            await self.test_database()
            
            # 2. Тест конфигурации
            await self.test_config()
            
            # 3. Тест аккаунтов
            await self.test_accounts()
            
            # 4. Тест тестовой группы
            await self.test_group_setup()
            
            # 5. Тест Account Manager (поиск и вступление)
            await self.test_account_manager()
            
            # 6. Тест Marketer (постинг)
            await self.test_marketer()
            
            # 7. Тест Secretary (GPT ответы)
            await self.test_secretary()
            
            # 8. Тест Activity (stories - опционально)
            # await self.test_activity()
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка при тестировании: {e}", exc_info=True)
            self.errors.append(f"Критическая ошибка: {e}")
        
        finally:
            if self.db:
                self.db.close()
        
        # Выводим итоги
        self.print_summary()
    
    async def test_database(self):
        """Тест подключения к БД"""
        logger.info("1️⃣  ТЕСТ БД")
        logger.info("-" * 80)
        
        try:
            init_db()
            self.db = SessionLocal()
            
            # Проверяем таблицы
            accounts_count = self.db.query(Account).count()
            groups_count = self.db.query(Group).count()
            posts_count = self.db.query(Post).count()
            
            logger.info(f"   ✅ БД подключена")
            logger.info(f"   📊 Аккаунтов: {accounts_count}, Групп: {groups_count}, Постов: {posts_count}")
            
            self.results['database'] = True
        except Exception as e:
            logger.error(f"   ❌ Ошибка БД: {e}")
            self.errors.append(f"БД: {e}")
            self.results['database'] = False
    
    async def test_config(self):
        """Тест загрузки конфигурации"""
        logger.info("")
        logger.info("2️⃣  ТЕСТ КОНФИГУРАЦИИ")
        logger.info("-" * 80)
        
        try:
            self.config_loader = ConfigLoader(config_dir=str(self.config_dir))
            self.niche_config = self.config_loader.load_niche_config()
            
            niche_name = self.niche_config.get('name', 'unknown')
            display_name = self.niche_config.get('display_name', 'Unknown')
            
            logger.info(f"   ✅ Конфиг загружен: {display_name} ({niche_name})")
            
            # Проверяем сообщения
            messages = self.config_loader.load_messages()
            logger.info(f"   ✅ Загружено сообщений: {len(messages)}")
            
            if len(messages) == 0:
                logger.warning(f"   ⚠️  Нет сообщений для постинга!")
                self.errors.append("Нет сообщений для постинга")
            
            self.results['config'] = True
        except Exception as e:
            logger.error(f"   ❌ Ошибка конфига: {e}")
            self.errors.append(f"Конфиг: {e}")
            self.results['config'] = False
    
    async def test_accounts(self):
        """Тест аккаунтов"""
        logger.info("")
        logger.info("3️⃣  ТЕСТ АККАУНТОВ")
        logger.info("-" * 80)
        
        try:
            self.client_manager = TelegramClientManager(sessions_dir=str(self.sessions_dir))
            await self.client_manager.load_accounts_from_db(self.db)
            
            active_accounts = len(self.client_manager.clients)
            
            if active_accounts == 0:
                logger.error(f"   ❌ Нет активных аккаунтов!")
                self.errors.append("Нет активных аккаунтов")
                self.results['accounts'] = False
                return
            
            logger.info(f"   ✅ Загружено аккаунтов: {active_accounts}")
            
            # Проверяем подключение каждого
            connected = 0
            for session_name, client in self.client_manager.clients.items():
                if client and client.is_connected():
                    connected += 1
                    logger.info(f"      ✅ {session_name}: подключен")
                else:
                    logger.warning(f"      ⚠️  {session_name}: не подключен")
            
            if connected == 0:
                logger.error(f"   ❌ Нет подключенных аккаунтов!")
                self.errors.append("Нет подключенных аккаунтов")
                self.results['accounts'] = False
            else:
                logger.info(f"   ✅ Подключено: {connected}/{active_accounts}")
                self.results['accounts'] = True
                
        except Exception as e:
            logger.error(f"   ❌ Ошибка аккаунтов: {e}")
            self.errors.append(f"Аккаунты: {e}")
            self.results['accounts'] = False
    
    async def test_group_setup(self):
        """Настройка тестовой группы"""
        logger.info("")
        logger.info("4️⃣  ТЕСТ ТЕСТОВОЙ ГРУППЫ")
        logger.info("-" * 80)
        
        try:
            niche_name = self.niche_config.get('name', 'bali')
            
            # Ищем или создаем тестовую группу
            group = self.db.query(Group).filter(Group.username == self.test_group_username).first()
            
            if not group:
                logger.info(f"   ℹ️  Группа {self.test_group_username} не найдена, создаю...")
                group = Group(
                    username=self.test_group_username,
                    title=f"Тестовая группа: {self.test_group_username}",
                    niche=niche_name,
                    status='active',
                    can_post=True,
                    warm_up_until=None,  # Без warm-up для тестов
                    created_at=datetime.utcnow()
                )
                self.db.add(group)
                self.db.commit()
                logger.info(f"   ✅ Группа создана")
            else:
                # Обновляем для теста
                group.status = 'active'
                group.can_post = True
                group.warm_up_until = None
                self.db.commit()
                logger.info(f"   ✅ Группа найдена и обновлена для теста")
            
            self.results['test_group'] = True
            
        except Exception as e:
            logger.error(f"   ❌ Ошибка тестовой группы: {e}")
            self.errors.append(f"Тестовая группа: {e}")
            self.results['test_group'] = False
    
    async def test_account_manager(self):
        """Тест Account Manager (поиск и вступление)"""
        logger.info("")
        logger.info("5️⃣  ТЕСТ ACCOUNT MANAGER")
        logger.info("-" * 80)
        
        try:
            if not self.results['accounts']:
                logger.warning(f"   ⚠️  Пропущен (нет аккаунтов)")
                return
            
            # Выбираем первый аккаунт
            account = self.db.query(Account).filter(Account.status == 'active').first()
            if not account:
                logger.error(f"   ❌ Нет активных аккаунтов")
                return
            
            client = self.client_manager.clients.get(account.session_name)
            if not client or not client.is_connected():
                logger.error(f"   ❌ Клиент {account.session_name} не подключен")
                return
            
            # Тест поиска
            logger.info(f"   🔍 Тест поиска групп...")
            finder = GroupFinder(self.client_manager)
            
            # Ищем по одному простому ключевому слову
            test_keywords = ["bali test"]
            found_groups = await finder.search_groups(client, test_keywords, limit_per_keyword=1)
            
            logger.info(f"   ✅ Поиск работает, найдено: {len(found_groups)} групп")
            
            # Тест вступления в тестовую группу (если еще не вступили)
            group = self.db.query(Group).filter(Group.username == self.test_group_username).first()
            if group and not group.joined_at:
                logger.info(f"   🚪 Пробуем вступить в тестовую группу...")
                joiner = GroupJoiner(self.client_manager, self.niche_config)
                success, error = await joiner.join_group(client, account, group)
                
                if success:
                    self.db.refresh(group)
                    logger.info(f"   ✅ Успешно вступили в {self.test_group_username}")
                else:
                    logger.warning(f"   ⚠️  Не удалось вступить: {error}")
            else:
                logger.info(f"   ✅ Уже вступили в группу ранее")
            
            self.results['account_manager'] = True
            
        except Exception as e:
            logger.error(f"   ❌ Ошибка Account Manager: {e}")
            self.errors.append(f"Account Manager: {e}")
            self.results['account_manager'] = False
    
    async def test_marketer(self):
        """Тест Marketer (постинг)"""
        logger.info("")
        logger.info("6️⃣  ТЕСТ MARKETER (ПОСТИНГ)")
        logger.info("-" * 80)
        
        try:
            if not self.results['test_group']:
                logger.warning(f"   ⚠️  Пропущен (нет тестовой группы)")
                return
            
            if not self.results['accounts']:
                logger.warning(f"   ⚠️  Пропущен (нет аккаунтов)")
                return
            
            # Получаем группу
            group = self.db.query(Group).filter(Group.username == self.test_group_username).first()
            if not group:
                logger.error(f"   ❌ Тестовая группа не найдена")
                return
            
            # Выбираем аккаунт
            account = None
            if group.assigned_account_id:
                account = self.db.query(Account).filter(Account.id == group.assigned_account_id).first()
            
            if not account:
                account = self.db.query(Account).filter(Account.status == 'active').first()
                group.assigned_account_id = account.id
                self.db.commit()
            
            client = self.client_manager.clients.get(account.session_name)
            if not client or not client.is_connected():
                logger.error(f"   ❌ Клиент не подключен")
                return
            
            # Инициализация Poster
            logger.info(f"   📝 Инициализация Poster...")
            poster = Poster(self.client_manager, self.config_loader, self.niche_config)
            await poster.initialize()
            
            if len(poster.messages) == 0:
                logger.error(f"   ❌ Нет сообщений для постинга!")
                self.errors.append("Marketer: нет сообщений")
                return
            
            logger.info(f"   ✅ Загружено {len(poster.messages)} сообщений")
            
            # Выбираем первое сообщение для теста
            test_message = poster.messages[0]
            if isinstance(test_message, dict):
                test_text = test_message.get('text', str(test_message))
            else:
                test_text = str(test_message)
            
            logger.info(f"   📤 Тестовое сообщение: {test_text[:80]}...")
            
            # Постим
            logger.info(f"   📤 Постинг в {self.test_group_username}...")
            success, error = await poster.post_to_group(self.db, group, account, client)
            
            if success:
                logger.info(f"   ✅ ПОСТИНГ УСПЕШЕН!")
                logger.info(f"   ✅ Сообщение отправлено в группу {self.test_group_username}")
                self.results['marketer'] = True
            else:
                logger.error(f"   ❌ Ошибка постинга: {error}")
                self.errors.append(f"Marketer: {error}")
                self.results['marketer'] = False
            
        except Exception as e:
            logger.error(f"   ❌ Ошибка Marketer: {e}", exc_info=True)
            self.errors.append(f"Marketer: {e}")
            self.results['marketer'] = False
    
    async def test_secretary(self):
        """Тест Secretary (GPT ответы)"""
        logger.info("")
        logger.info("7️⃣  ТЕСТ SECRETARY (GPT)")
        logger.info("-" * 80)
        
        try:
            api_key = os.getenv('OPENAI_API_KEY')
            if not api_key:
                logger.error(f"   ❌ OPENAI_API_KEY не установлен")
                self.errors.append("Secretary: нет API ключа")
                self.results['secretary'] = False
                return
            
            logger.info(f"   🤖 Инициализация GPT Handler...")
            gpt_handler = GPTHandler(api_key=api_key, niche_config=self.niche_config)
            
            # Тестовое сообщение
            test_message = "Привет, нужна помощь с арендой виллы на Бали"
            logger.info(f"   📨 Тестовое сообщение: {test_message}")
            
            logger.info(f"   ⏳ Генерация ответа...")
            response = await gpt_handler.generate_response(
                incoming_message=test_message,
                conversation_history=[],
                user_info=None
            )
            
            if response:
                logger.info(f"   ✅ Ответ получен: {response[:100]}...")
                self.results['secretary'] = True
            else:
                logger.error(f"   ❌ Пустой ответ от GPT")
                self.errors.append("Secretary: пустой ответ")
                self.results['secretary'] = False
                
        except Exception as e:
            logger.error(f"   ❌ Ошибка Secretary: {e}", exc_info=True)
            self.errors.append(f"Secretary: {e}")
            self.results['secretary'] = False
    
    def print_summary(self):
        """Вывести итоговую сводку"""
        logger.info("")
        logger.info("=" * 80)
        logger.info("📊 ИТОГОВАЯ СВОДКА")
        logger.info("=" * 80)
        
        passed = sum(1 for v in self.results.values() if v)
        total = len(self.results)
        
        for test_name, result in self.results.items():
            status = "✅ ПРОЙДЕН" if result else "❌ ПРОВАЛЕН"
            logger.info(f"   {test_name.upper()}: {status}")
        
        logger.info("")
        logger.info(f"   Результат: {passed}/{total} тестов пройдено")
        
        if self.errors:
            logger.info("")
            logger.info("   ❌ ОШИБКИ:")
            for error in self.errors:
                logger.info(f"      • {error}")
        
        logger.info("")
        if passed == total:
            logger.info("   🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ! Система готова к работе.")
        else:
            logger.info("   ⚠️  ЕСТЬ ПРОБЛЕМЫ! Исправьте ошибки перед запуском рассылки.")
        logger.info("=" * 80)


async def main():
    parser = argparse.ArgumentParser(description='Быстрое тестирование всех узлов системы')
    parser.add_argument('--test-group', default='@supergruppalexus',
                       help='Username тестовой группы (default: @supergruppalexus)')
    
    args = parser.parse_args()
    
    tester = QuickTestSystem(test_group_username=args.test_group)
    await tester.run_all_tests()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Прервано пользователем")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)
