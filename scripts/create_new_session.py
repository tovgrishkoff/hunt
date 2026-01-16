#!/usr/bin/env python3
"""
Интерактивный скрипт для создания новой сессии аккаунта
Удаляет старую сессию, создает новую через авторизацию, обновляет БД и config
"""
import sys
import json
import asyncio
from pathlib import Path

# Добавляем путь к shared модулям
sys.path.insert(0, str(Path(__file__).parent.parent))

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from shared.database.session import SessionLocal, init_db
from shared.database.models import Account
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def create_new_session(session_name: str, api_id: int, api_hash: str, phone: str, proxy: str = None, password: str = None, skip_proxy: bool = False):
    """
    Создать новую сессию для аккаунта
    
    Args:
        session_name: Имя сессии
        api_id: API ID
        api_hash: API Hash
        phone: Номер телефона
        proxy: Прокси (опционально)
        password: 2FA пароль (если требуется)
    
    Returns:
        StringSession или None
    """
    logger.info("=" * 80)
    logger.info(f"🔄 СОЗДАНИЕ НОВОЙ СЕССИИ ДЛЯ: {session_name}")
    logger.info("=" * 80)
    
    # Определяем путь к session файлу
    sessions_dir = Path(__file__).parent.parent / "sessions"
    sessions_dir.mkdir(exist_ok=True)
    session_file = sessions_dir / f"{session_name}.session"
    
    # Удаляем старую сессию если есть
    if session_file.exists():
        logger.info(f"🗑️  Удаление старой сессии: {session_file}")
        session_file.unlink()
        # Также удаляем journal файл если есть
        journal_file = sessions_dir / f"{session_name}.session-journal"
        if journal_file.exists():
            journal_file.unlink()
    
    # Парсим прокси если есть (и не пропущен)
    proxy_config = None
    if proxy and not skip_proxy:
        if proxy.startswith('http://'):
            parts = proxy.replace('http://', '').split('@')
            if len(parts) == 2:
                auth, addr = parts
                user, pwd = auth.split(':')
                host, port = addr.split(':')
                proxy_config = {
                    'proxy_type': 'http',
                    'addr': host,
                    'port': int(port),
                    'username': user,
                    'password': pwd
                }
        elif proxy.startswith('socks5://'):
            parts = proxy.replace('socks5://', '').split('@')
            if len(parts) == 2:
                auth, addr = parts
                user, pwd = auth.split(':')
                host, port = addr.split(':')
                proxy_config = {
                    'proxy_type': 'socks5',
                    'addr': host,
                    'port': int(port),
                    'username': user,
                    'password': pwd
                }
    
    try:
        # Создаем клиент с StringSession с самого начала (не файловую сессию)
        logger.info(f"📱 Создание клиента для {phone}...")
        string_session_obj = StringSession()
        client = TelegramClient(string_session_obj, api_id, api_hash, proxy=proxy_config)
        
        await client.connect()
        
        # Проверяем авторизацию
        if not await client.is_user_authorized():
            logger.info("📱 Отправка кода подтверждения в Telegram...")
            logger.info(f"📱 Телефон: {phone}")
            
            # Запрашиваем код
            try:
                await client.send_code_request(phone=phone)
                logger.info("✅ Код отправлен в Telegram!")
                logger.info("")
                code = input("📱 Введите код из Telegram: ").strip()
                
                try:
                    await client.sign_in(phone=phone, code=code)
                    logger.info("✅ Авторизация успешна!")
                except SessionPasswordNeededError:
                    logger.info("🔐 Требуется 2FA пароль")
                    if password:
                        await client.sign_in(password=password)
                        logger.info("✅ Авторизация с 2FA успешна!")
                    else:
                        password_input = input("🔐 Введите 2FA пароль: ").strip()
                        await client.sign_in(password=password_input)
                        logger.info("✅ Авторизация с 2FA успешна!")
            except Exception as e:
                logger.error(f"❌ Ошибка при авторизации: {e}")
                await client.disconnect()
                return None
        
        # Получаем StringSession - она уже создана, просто сохраняем
        logger.info("🔄 Сохранение StringSession...")
        
        # Проверяем, что сессия авторизована
        if not await client.is_user_authorized():
            logger.error("❌ Сессия не авторизована")
            await client.disconnect()
            return None
        
        try:
            # StringSession уже создана и авторизована, просто сохраняем
            string_session = string_session_obj.save()
            
            if string_session and len(string_session) > 50:
                logger.info(f"✅ StringSession создана! (длина: {len(string_session)})")
                await client.disconnect()
                return string_session
            else:
                logger.error(f"❌ StringSession пустая (длина: {len(string_session) if string_session else 0})")
                logger.info("💡 Попробуем получить через encode()...")
                # Пробуем альтернативный метод
                try:
                    # Используем encode() метод
                    encoded = string_session_obj.encode()
                    if encoded and len(encoded) > 50:
                        logger.info(f"✅ StringSession получена через encode()! (длина: {len(encoded)})")
                        await client.disconnect()
                        return encoded
                except:
                    pass
                
                logger.error("❌ Не удалось получить StringSession")
                await client.disconnect()
                return None
                
        except Exception as e:
            logger.error(f"❌ Ошибка при сохранении StringSession: {e}", exc_info=True)
            try:
                await client.disconnect()
            except:
                pass
            return None
        
    except Exception as e:
        logger.error(f"❌ Ошибка при создании сессии: {e}", exc_info=True)
        try:
            await client.disconnect()
        except:
            pass
        return None


def update_config_file(session_name: str, string_session: str, config_file: Path):
    """Обновить StringSession в accounts_config.json"""
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            accounts_config = json.load(f)
        
        # Находим аккаунт в конфиге
        updated = False
        for acc in accounts_config:
            if acc.get('session_name') == session_name:
                acc['string_session'] = string_session
                updated = True
                logger.info(f"✅ StringSession обновлена в accounts_config.json для {session_name}")
                break
        
        if updated:
            # Сохраняем обновленный конфиг
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(accounts_config, f, indent=2, ensure_ascii=False)
            logger.info(f"✅ Файл accounts_config.json обновлен")
        else:
            logger.warning(f"⚠️ Аккаунт {session_name} не найден в accounts_config.json")
        
        return updated
        
    except Exception as e:
        logger.error(f"❌ Ошибка при обновлении config файла: {e}")
        return False


async def update_database(session_name: str, string_session: str):
    """Обновить StringSession в БД"""
    db = SessionLocal()
    try:
        account = db.query(Account).filter(Account.session_name == session_name).first()
        if not account:
            logger.warning(f"⚠️ Аккаунт {session_name} не найден в БД")
            return False
        
        account.string_session = string_session
        account.status = 'active'  # Активируем аккаунт
        db.commit()
        
        logger.info(f"✅ StringSession обновлен в БД для {session_name}")
        logger.info(f"✅ Аккаунт {session_name} активирован")
        return True
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Ошибка при обновлении БД: {e}")
        return False
    finally:
        db.close()


async def main():
    """Основная функция"""
    if len(sys.argv) < 2:
        print("Использование: python3 scripts/create_new_session.py <session_name>")
        print("")
        print("Примеры:")
        print("  python3 scripts/create_new_session.py promotion_dao_bro")
        print("  python3 scripts/create_new_session.py promotion_oleg_petrov")
        sys.exit(1)
    
    session_name = sys.argv[1]
    
    logger.info("=" * 80)
    logger.info("🔄 СОЗДАНИЕ НОВОЙ СЕССИИ")
    logger.info("=" * 80)
    
    # Инициализация БД
    try:
        init_db()
    except Exception as e:
        logger.warning(f"⚠️ БД уже инициализирована: {e}")
    
    # Загружаем конфиг
    base_dir = Path(__file__).parent.parent
    config_file = base_dir / "accounts_config.json"
    
    if not config_file.exists():
        logger.error(f"❌ Файл accounts_config.json не найден: {config_file}")
        return
    
    with open(config_file, 'r', encoding='utf-8') as f:
        accounts_config = json.load(f)
    
    # Находим аккаунт в конфиге
    account_config = None
    for acc in accounts_config:
        if acc.get('session_name') == session_name:
            account_config = acc
            break
    
    if not account_config:
        logger.error(f"❌ Аккаунт {session_name} не найден в accounts_config.json")
        logger.info("Доступные аккаунты:")
        for acc in accounts_config:
            logger.info(f"  - {acc.get('session_name')}")
        return
    
    # Извлекаем данные
    api_id = account_config.get('api_id')
    api_hash = account_config.get('api_hash')
    phone = account_config.get('phone')
    proxy = account_config.get('proxy')
    password = account_config.get('password')  # 2FA пароль если есть
    
    if not api_id or not api_hash or not phone:
        logger.error(f"❌ Недостаточно данных для {session_name}")
        logger.error(f"   Требуется: api_id, api_hash, phone")
        return
    
    logger.info(f"📋 Данные аккаунта:")
    logger.info(f"   Телефон: {phone}")
    logger.info(f"   API ID: {api_id}")
    logger.info(f"   Прокси: {'Да' if proxy else 'Нет'}")
    logger.info(f"   2FA: {'Да' if password else 'Нет'}")
    logger.info("")
    
    # Создаем новую сессию
    string_session = await create_new_session(
        session_name=session_name,
        api_id=api_id,
        api_hash=api_hash,
        phone=phone,
        proxy=proxy,
        password=password
    )
    
    if not string_session:
        logger.error("❌ Не удалось создать новую сессию")
        return
    
    logger.info("")
    logger.info("=" * 80)
    logger.info("📝 ОБНОВЛЕНИЕ КОНФИГУРАЦИИ")
    logger.info("=" * 80)
    
    # Обновляем config файл
    update_config_file(session_name, string_session, config_file)
    
    # Обновляем БД
    await update_database(session_name, string_session)
    
    logger.info("")
    logger.info("=" * 80)
    logger.info("✅ ГОТОВО!")
    logger.info("=" * 80)
    logger.info("")
    logger.info("🔄 Перезапустите контейнеры для применения изменений:")
    logger.info("   docker-compose restart account-manager marketer activity secretary")
    logger.info("")
    logger.info("📊 Проверьте логи:")
    logger.info("   docker-compose logs marketer --tail 50 | grep -E '(Loaded|accounts)'")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Прервано пользователем")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)

