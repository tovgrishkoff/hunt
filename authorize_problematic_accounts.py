#!/usr/bin/env python3
"""
Авторизация проблемных аккаунтов (которые не работают)
"""

import asyncio
import json
import logging
from pathlib import Path
from telethon import TelegramClient
from telethon.sessions import StringSession

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def authorize_account(account):
    """Авторизация одного аккаунта"""
    session_name = account['session_name']
    phone = account['phone']
    api_id = int(account['api_id'])
    api_hash = account['api_hash']
    
    logger.info(f"\n{'='*60}")
    logger.info(f"📱 Авторизация: {session_name}")
    logger.info(f"   Телефон: {phone}")
    logger.info(f"{'='*60}")
    
    # Проверяем текущий статус
    client = TelegramClient(f"sessions/{session_name}", api_id, api_hash)
    
    try:
        await asyncio.wait_for(client.connect(), timeout=10.0)
        
        if await client.is_user_authorized():
            me = await client.get_me()
            username = getattr(me, 'username', 'No username')
            logger.info(f"✅ Уже авторизован как @{username}")
            await client.disconnect()
            return True
        
        logger.info("📲 Отправляем код авторизации...")
        await client.send_code_request(phone)
        logger.info(f"📨 Код отправлен на {phone}")
        
        # Запрашиваем код
        print(f"\n📱 Введите код для {session_name} ({phone}):")
        code = input("Код: ").strip()
        
        try:
            await client.sign_in(phone, code)
            logger.info("✅ Авторизация успешна!")
        except Exception as e:
            error_str = str(e).lower()
            if "password" in error_str or "two-step" in error_str or "2fa" in error_str:
                logger.info("🔐 Требуется пароль 2FA")
                password = input(f"Введите пароль 2FA для {session_name}: ").strip()
                await client.sign_in(password=password)
                logger.info("✅ Авторизация с 2FA успешна!")
            else:
                raise
        
        # Проверяем авторизацию
        me = await client.get_me()
        username = getattr(me, 'username', 'No username')
        first_name = getattr(me, 'first_name', 'No name')
        logger.info(f"✅ Авторизован как {first_name} (@{username})")
        
        # Обновляем string_session в конфиге
        if hasattr(client.session, 'save'):
            try:
                session_string = client.session.save()
                account['string_session'] = session_string
                account['nickname'] = first_name
                logger.info("✅ String session обновлен в конфиге")
            except:
                pass
        
        await client.disconnect()
        return True
        
    except asyncio.TimeoutError:
        logger.error(f"❌ Таймаут подключения для {session_name}")
        try:
            await client.disconnect()
        except:
            pass
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка авторизации {session_name}: {e}")
        try:
            await client.disconnect()
        except:
            pass
        return False

async def main():
    """Главная функция - авторизуем только проблемные аккаунты"""
    config_file = Path('accounts_config.json')
    
    if not config_file.exists():
        logger.error(f"❌ Файл {config_file} не найден!")
        return
    
    # Загружаем конфигурацию
    with open(config_file, 'r', encoding='utf-8') as f:
        accounts = json.load(f)
    
    # Проверяем, какие аккаунты нужно авторизовать
    logger.info("🔍 Проверяем статус аккаунтов...\n")
    
    problematic_accounts = []
    for account in accounts:
        session_name = account['session_name']
        try:
            client = TelegramClient(f"sessions/{session_name}", account['api_id'], account['api_hash'])
            await asyncio.wait_for(client.connect(), timeout=5.0)
            if not await client.is_user_authorized():
                problematic_accounts.append(account)
                logger.info(f"❌ {session_name}: требует авторизации")
            else:
                me = await client.get_me()
                logger.info(f"✅ {session_name}: уже авторизован (@{me.username})")
            await client.disconnect()
        except asyncio.TimeoutError:
            problematic_accounts.append(account)
            logger.info(f"⚠️ {session_name}: таймаут подключения - требуется авторизация")
        except Exception as e:
            problematic_accounts.append(account)
            logger.info(f"❌ {session_name}: ошибка - требуется авторизация")
    
    if not problematic_accounts:
        logger.info("\n✅ Все аккаунты уже авторизованы!")
        return
    
    logger.info(f"\n📋 Найдено {len(problematic_accounts)} аккаунтов для авторизации\n")
    
    # Авторизуем проблемные аккаунты
    success_count = 0
    for i, account in enumerate(problematic_accounts, 1):
        logger.info(f"\n[{i}/{len(problematic_accounts)}] Авторизуем: {account['session_name']}")
        
        if await authorize_account(account):
            success_count += 1
        
        # Пауза между аккаунтами
        if i < len(problematic_accounts):
            logger.info("⏳ Пауза 3 секунды...")
            await asyncio.sleep(3)
    
    # Сохраняем обновленную конфигурацию
    with open(config_file, 'w', encoding='utf-8') as f:
        json.dump(accounts, f, indent=2, ensure_ascii=False)
    
    logger.info(f"\n{'='*60}")
    logger.info(f"📊 Результаты: {success_count}/{len(problematic_accounts)} аккаунтов авторизовано")
    logger.info(f"{'='*60}")

if __name__ == "__main__":
    asyncio.run(main())
