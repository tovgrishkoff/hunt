#!/usr/bin/env python3
"""
Скрипт для переавторизации Ukraine аккаунтов
Создает новые string_session для promotion_dao_bro и promotion_rod_shaihutdinov
"""
import sys
import json
import asyncio
import argparse
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def parse_proxy(proxy_string: str):
    """Парсинг прокси в формат для Telethon"""
    if not proxy_string:
        return None
    
    try:
        if proxy_string.startswith('http://'):
            parts = proxy_string.replace('http://', '').split('@')
            if len(parts) == 2:
                auth, addr = parts
                user, pwd = auth.split(':')
                host, port = addr.split(':')
                return {
                    'proxy_type': 'http',
                    'addr': host,
                    'port': int(port),
                    'username': user,
                    'password': pwd
                }
        elif proxy_string.startswith('socks5://'):
            parts = proxy_string.replace('socks5://', '').split('@')
            if len(parts) == 2:
                auth, addr = parts
                user, pwd = auth.split(':')
                host, port = addr.split(':')
                return {
                    'proxy_type': 'socks5',
                    'addr': host,
                    'port': int(port),
                    'username': user,
                    'password': pwd
                }
    except Exception as e:
        logger.error(f"Ошибка парсинга прокси: {e}")
    
    return None


def wait_for_file_value(path: Path, label: str, timeout_sec: int | None = None) -> str:
    """Ожидает появления значения в файле."""
    start = time.time()
    while True:
        if path.exists():
            value = path.read_text(encoding="utf-8").strip()
            if value:
                # очищаем файл, чтобы значение не переиспользовалось
                path.write_text("", encoding="utf-8")
                return value
        if timeout_sec is not None and (time.time() - start) > timeout_sec:
            raise TimeoutError(f"Таймаут ожидания {label} ({timeout_sec}s)")
        time.sleep(2)


async def reauth_account(account_data, args):
    """Переавторизация одного аккаунта"""
    session_name = account_data['session_name']
    phone = account_data['phone']
    api_id = int(account_data['api_id'])
    api_hash = account_data['api_hash']
    proxy_string = account_data.get('proxy')
    nickname = account_data.get('nickname', session_name)
    
    logger.info("=" * 80)
    logger.info(f"🔄 ПЕРЕАВТОРИЗАЦИЯ: {nickname} ({session_name})")
    logger.info(f"📱 Телефон: {phone}")
    logger.info("=" * 80)
    
    # Парсим прокси
    proxy_config = parse_proxy(proxy_string)
    if proxy_config:
        logger.info(f"🔗 Используем прокси: {proxy_config['addr']}:{proxy_config['port']}")
    
    # Создаем клиент с новой StringSession
    string_session_obj = StringSession()
    client = TelegramClient(string_session_obj, api_id, api_hash, proxy=proxy_config)
    
    try:
        await client.connect()
        logger.info("✅ Подключение установлено")
        
        # Запрашиваем код
        logger.info(f"\n📨 Отправка кода на {phone}...")
        await client.send_code_request(phone)
        logger.info("✅ Код отправлен! Проверьте Telegram/SMS")
        
        # Запрашиваем код у пользователя
        if args.non_interactive:
            logger.info(
                "✉️ Ожидание кода в файле: %s",
                args.code_file,
            )
            code = wait_for_file_value(Path(args.code_file), "code", args.wait_timeout)
        else:
            code = input("✉️ Введите код из Telegram/SMS: ").strip()
        
        if not code:
            logger.error("❌ Код не введен!")
            await client.disconnect()
            return None
        
        # Авторизуемся
        try:
            await client.sign_in(phone, code)
            logger.info("✅ Код подтвержден!")
        except SessionPasswordNeededError:
            logger.info("🔒 Требуется пароль 2FA")
            if args.non_interactive:
                logger.info(
                    "🔒 Ожидание пароля 2FA в файле: %s",
                    args.password_file,
                )
                password = wait_for_file_value(
                    Path(args.password_file), "2fa_password", args.wait_timeout
                )
            else:
                password = input("🔒 Введите пароль 2FA: ").strip()
            await client.sign_in(password=password)
            logger.info("✅ Авторизация с 2FA успешна!")
        except Exception as e:
            if "password" in str(e).lower() or "two" in str(e).lower():
                if args.non_interactive:
                    logger.info(
                        "🔒 Ожидание пароля 2FA в файле: %s",
                        args.password_file,
                    )
                    password = wait_for_file_value(
                        Path(args.password_file), "2fa_password", args.wait_timeout
                    )
                else:
                    password = input("🔒 Введите пароль 2FA: ").strip()
                await client.sign_in(password=password)
                logger.info("✅ Авторизация с 2FA успешна!")
            else:
                raise
        
        # Получаем информацию о пользователе
        me = await client.get_me()
        username = getattr(me, 'username', 'No username')
        first_name = getattr(me, 'first_name', 'No name')
        
        logger.info(f"✅ Авторизован как: {first_name} (@{username})")
        
        # Получаем string_session
        string_session = client.session.save()
        
        logger.info(f"\n📝 String Session создана (длина: {len(string_session)} символов)")
        
        await client.disconnect()
        
        return {
            'session_name': session_name,
            'string_session': string_session,
            'username': username,
            'first_name': first_name
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка при переавторизации: {e}", exc_info=True)
        try:
            await client.disconnect()
        except:
            pass
        return None


async def update_config_file(session_name: str, string_session: str, config_path: Path):
    """Обновить string_session в accounts_config.json"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        updated = False
        for acc in data:
            if acc.get('session_name') == session_name:
                acc['string_session'] = string_session
                updated = True
                logger.info(f"✅ Обновлен string_session для {session_name} в конфиге")
                break
        
        if updated:
            # Создаем резервную копию
            backup_path = config_path.with_suffix('.json.backup')
            if not backup_path.exists():
                with open(backup_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                logger.info(f"📦 Резервная копия создана: {backup_path}")
            
            # Сохраняем обновленный конфиг
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            return True
        else:
            logger.error(f"❌ Аккаунт {session_name} не найден в конфиге")
            return False
            
    except Exception as e:
        logger.error(f"❌ Ошибка при обновлении конфига: {e}", exc_info=True)
        return False


async def main():
    """Основная функция"""
    parser = argparse.ArgumentParser(description="Переавторизация Ukraine аккаунтов")
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Ожидать код/2FA в файлах без интерактивного ввода",
    )
    parser.add_argument(
        "--code-file",
        default="/tmp/ukraine_reauth_code.txt",
        help="Файл для кода (используется с --non-interactive)",
    )
    parser.add_argument(
        "--password-file",
        default="/tmp/ukraine_reauth_2fa.txt",
        help="Файл для пароля 2FA (используется с --non-interactive)",
    )
    parser.add_argument(
        "--wait-timeout",
        type=int,
        default=None,
        help="Таймаут ожидания кода/2FA в секундах (по умолчанию без таймаута)",
    )
    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("🔄 ПЕРЕАВТОРИЗАЦИЯ UKRAINE АККАУНТОВ")
    logger.info("=" * 80)
    
    # Загружаем конфиг
    config_path = Path(__file__).parent.parent / "accounts_config.json"
    
    if not config_path.exists():
        logger.error(f"❌ Файл accounts_config.json не найден: {config_path}")
        return
    
    with open(config_path, 'r', encoding='utf-8') as f:
        accounts_config = json.load(f)
    
    # Находим аккаунты для переавторизации (все 3 Ukraine аккаунта)
    accounts_to_reauth = ['promotion_dao_bro', 'promotion_alex_ever', 'promotion_rod_shaihutdinov']
    accounts_data = {}
    
    for acc in accounts_config:
        session_name = acc.get('session_name')
        if session_name in accounts_to_reauth:
            accounts_data[session_name] = acc
    
    if not accounts_data:
        logger.error("❌ Аккаунты для переавторизации не найдены в конфиге")
        return
    
    logger.info(f"\n📋 Найдено {len(accounts_data)} аккаунтов для переавторизации:")
    for session_name in accounts_to_reauth:
        if session_name in accounts_data:
            logger.info(f"   • {session_name}")
    
    logger.info("\n" + "=" * 80)
    logger.info("⚠️  ВНИМАНИЕ:")
    logger.info("   Для каждого аккаунта вам нужно будет:")
    logger.info("   1. Ввести код из Telegram/SMS")
    logger.info("   2. Ввести пароль 2FA (если требуется)")
    logger.info("=" * 80)
    
    if not args.non_interactive:
        input("\nНажмите Enter для начала переавторизации...")
    
    results = []
    
    for session_name in accounts_to_reauth:
        if session_name not in accounts_data:
            logger.warning(f"⚠️ Аккаунт {session_name} не найден в конфиге, пропускаем")
            continue
        
        account_data = accounts_data[session_name]
        result = await reauth_account(account_data, args)
        
        if result:
            # Обновляем конфиг
            success = await update_config_file(
                result['session_name'],
                result['string_session'],
                config_path
            )
            
            if success:
                results.append(result)
                logger.info(f"\n✅ {session_name} успешно переавторизован и обновлен в конфиге!")
            else:
                logger.error(f"\n❌ Не удалось обновить конфиг для {session_name}")
        else:
            logger.error(f"\n❌ Не удалось переавторизовать {session_name}")
        
        if session_name != accounts_to_reauth[-1]:
            logger.info("\n" + "=" * 80)
            if not args.non_interactive:
                input("Нажмите Enter для перехода к следующему аккаунту...")
    
    logger.info("\n" + "=" * 80)
    logger.info("✅ ПЕРЕАВТОРИЗАЦИЯ ЗАВЕРШЕНА")
    logger.info("=" * 80)
    
    if results:
        logger.info(f"\n✅ Успешно переавторизовано: {len(results)} аккаунтов")
        for result in results:
            logger.info(f"   • {result['session_name']} (@{result['username']})")
        
        logger.info("\n🔄 СЛЕДУЮЩИЕ ШАГИ:")
        logger.info("   1. Перезапустите контейнер ukraine-account-manager")
        logger.info("   2. Запустите скрипт check_and_join_writeable_groups.sh")
        logger.info("   3. Все 3 аккаунта должны теперь работать!")
    else:
        logger.error("\n❌ Не удалось переавторизовать ни одного аккаунта")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n🛑 Прервано пользователем")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n❌ Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)
