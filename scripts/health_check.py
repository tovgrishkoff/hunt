#!/usr/bin/env python3
"""
Скрипт диагностики системы
Проверяет подключение к БД, наличие аккаунтов и доступность папок
"""
import sys
import os
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.database.session import SessionLocal, init_db
from shared.database.models import Account, Group
from shared.config.loader import ConfigLoader
from sqlalchemy import text
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def check_database_connection():
    """Проверка подключения к PostgreSQL"""
    try:
        db = SessionLocal()
        try:
            # Простой запрос для проверки подключения
            result = db.execute(text("SELECT 1")).scalar()
            if result == 1:
                return True, "✅ Подключение к PostgreSQL работает"
        except Exception as e:
            return False, f"❌ Ошибка подключения к БД: {e}"
        finally:
            db.close()
    except Exception as e:
        return False, f"❌ Не удалось создать сессию БД: {e}"


def check_accounts():
    """Проверка наличия активных аккаунтов"""
    try:
        db = SessionLocal()
        try:
            active_accounts = db.query(Account).filter(Account.status == 'active').all()
            if len(active_accounts) > 0:
                return True, f"✅ Найдено {len(active_accounts)} активных аккаунтов"
            else:
                return False, "❌ Нет активных аккаунтов в БД"
        except Exception as e:
            return False, f"❌ Ошибка при проверке аккаунтов: {e}"
        finally:
            db.close()
    except Exception as e:
        return False, f"❌ Не удалось проверить аккаунты: {e}"


def check_groups():
    """Проверка наличия групп в БД"""
    try:
        db = SessionLocal()
        try:
            total_groups = db.query(Group).count()
            active_groups = db.query(Group).filter(Group.status == 'active').count()
            
            if total_groups > 0:
                return True, f"✅ Найдено {total_groups} групп (активных: {active_groups})"
            else:
                return False, "❌ Нет групп в БД"
        except Exception as e:
            return False, f"❌ Ошибка при проверке групп: {e}"
        finally:
            db.close()
    except Exception as e:
        return False, f"❌ Не удалось проверить группы: {e}"


def check_directories():
    """Проверка доступности папок"""
    checks = []
    
    # Проверка папки sessions
    sessions_dir = Path(__file__).parent.parent / "sessions"
    if sessions_dir.exists():
        if os.access(sessions_dir, os.W_OK):
            checks.append((True, f"✅ Папка sessions/ доступна для записи"))
        else:
            checks.append((False, f"❌ Папка sessions/ недоступна для записи"))
    else:
        checks.append((False, f"❌ Папка sessions/ не существует"))
    
    # Проверка папки data/logs
    logs_dir = Path(__file__).parent.parent / "data" / "logs"
    if logs_dir.exists():
        if os.access(logs_dir, os.W_OK):
            checks.append((True, f"✅ Папка data/logs/ доступна для записи"))
        else:
            checks.append((False, f"❌ Папка data/logs/ недоступна для записи"))
    else:
        # Создаем папку, если её нет
        try:
            logs_dir.mkdir(parents=True, exist_ok=True)
            checks.append((True, f"✅ Папка data/logs/ создана"))
        except Exception as e:
            checks.append((False, f"❌ Не удалось создать папку data/logs/: {e}"))
    
    # Проверка папки config
    config_dir = Path(__file__).parent.parent / "config"
    if config_dir.exists():
        checks.append((True, f"✅ Папка config/ существует"))
    else:
        checks.append((False, f"❌ Папка config/ не существует"))
    
    # Проверка папки config/niches
    niches_dir = config_dir / "niches"
    if niches_dir.exists():
        niche_files = list(niches_dir.glob("*.json"))
        checks.append((True, f"✅ Папка config/niches/ существует ({len(niche_files)} файлов)"))
    else:
        checks.append((False, f"❌ Папка config/niches/ не существует"))
    
    return checks


def check_config():
    """Проверка конфигурации"""
    try:
        # Определяем правильный путь к конфигам (на хосте или в Docker)
        config_dir = Path(__file__).parent.parent / "config"
        if not config_dir.exists():
            # Пробуем путь внутри Docker
            config_dir = Path("/app/config")
        
        config_loader = ConfigLoader(config_dir=str(config_dir))
        active_niche = config_loader.load_active_niche()
        niche_config = config_loader.load_niche_config()
        
        return True, f"✅ Активная ниша: {niche_config.get('display_name', 'unknown')} ({niche_config.get('name', 'unknown')})"
    except Exception as e:
        return False, f"❌ Ошибка загрузки конфига: {e}"


def check_openai_key():
    """Проверка наличия OpenAI API ключа"""
    api_key = os.getenv('OPENAI_API_KEY')
    if api_key:
        return True, "✅ OPENAI_API_KEY установлен"
    else:
        return False, "⚠️ OPENAI_API_KEY не установлен (Secretary не будет работать)"


def main():
    """Основная функция диагностики"""
    print("=" * 80)
    print("🔍 ДИАГНОСТИКА СИСТЕМЫ")
    print("=" * 80)
    print()
    
    results = []
    
    # Проверка базы данных
    print("📊 Проверка базы данных...")
    success, message = check_database_connection()
    results.append(("База данных", success, message))
    print(f"  {message}")
    
    if success:
        # Проверка аккаунтов
        print()
        print("👥 Проверка аккаунтов...")
        success, message = check_accounts()
        results.append(("Аккаунты", success, message))
        print(f"  {message}")
        
        # Проверка групп
        print()
        print("📋 Проверка групп...")
        success, message = check_groups()
        results.append(("Группы", success, message))
        print(f"  {message}")
    
    # Проверка папок
    print()
    print("📁 Проверка папок...")
    dir_checks = check_directories()
    for success, message in dir_checks:
        results.append(("Папки", success, message))
        print(f"  {message}")
    
    # Проверка конфигурации
    print()
    print("⚙️ Проверка конфигурации...")
    success, message = check_config()
    results.append(("Конфигурация", success, message))
    print(f"  {message}")
    
    # Проверка OpenAI ключа
    print()
    print("🔑 Проверка OpenAI API ключа...")
    success, message = check_openai_key()
    results.append(("OpenAI API", success, message))
    print(f"  {message}")
    
    # Итоговый отчет
    print()
    print("=" * 80)
    print("📊 ИТОГОВЫЙ ОТЧЕТ")
    print("=" * 80)
    
    passed = sum(1 for _, success, _ in results if success)
    total = len(results)
    
    for category, success, message in results:
        status = "✅ OK" if success else "❌ FAIL"
        print(f"{status} - {category}")
    
    print()
    print(f"✅ Пройдено: {passed}/{total}")
    print(f"{'❌' if passed < total else '✅'} Ошибок: {total - passed}")
    print("=" * 80)
    
    if passed == total:
        print()
        print("✅ Все проверки пройдены! Система готова к работе.")
        return 0
    else:
        print()
        print("⚠️ Обнаружены проблемы! Проверьте ошибки выше.")
        return 1


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n🛑 Прервано пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

