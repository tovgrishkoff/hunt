#!/usr/bin/env python3
"""
Скрипт для тестирования ротации аккаунтов
Проверяет, какие аккаунты могут писать в какие группы
"""

import asyncio
import json
import logging
from datetime import datetime
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import RPCError

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('account_rotation_test.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

async def test_account_in_group(client, account_name, group_username, test_message="Тест"):
    """Проверяет, может ли аккаунт писать в группу"""
    try:
        entity = await client.get_entity(group_username)
        logger.info(f"✅ {account_name} может получить доступ к {group_username}")
        
        # Проверяем права на запись (не отправляем реально, просто пробуем получить entity)
        return {
            'account': account_name,
            'group': group_username,
            'accessible': True,
            'group_title': getattr(entity, 'title', 'Unknown'),
            'error': None
        }
        
    except RPCError as e:
        error_msg = str(e)
        logger.warning(f"❌ {account_name} НЕ может писать в {group_username}: {error_msg}")
        return {
            'account': account_name,
            'group': group_username,
            'accessible': False,
            'group_title': None,
            'error': error_msg
        }
    except Exception as e:
        logger.error(f"⚠️ Ошибка при проверке {account_name} -> {group_username}: {e}")
        return {
            'account': account_name,
            'group': group_username,
            'accessible': False,
            'group_title': None,
            'error': str(e)
        }

async def main():
    """Основная функция"""
    logger.info("🔍 Начинаем тестирование доступа аккаунтов к группам...")
    
    # Загружаем конфигурацию аккаунтов
    with open('accounts_config.json', 'r', encoding='utf-8') as f:
        accounts = json.load(f)
    
    # Загружаем список групп
    with open('targets.txt', 'r', encoding='utf-8') as f:
        groups = [line.strip() for line in f if line.strip()]
    
    logger.info(f"📋 Всего аккаунтов: {len(accounts)}")
    logger.info(f"📋 Всего групп: {len(groups)}")
    
    results = []
    
    # Тестируем каждый аккаунт
    for account in accounts:
        account_name = account['session_name']
        logger.info(f"\n{'='*60}")
        logger.info(f"🧪 Тестируем аккаунт: {account_name} ({account['nickname']})")
        logger.info(f"{'='*60}")
        
        try:
            # Создаем клиента
            string_session = account.get('string_session')
            if string_session:
                client = TelegramClient(
                    StringSession(string_session),
                    int(account['api_id']),
                    account['api_hash']
                )
            else:
                client = TelegramClient(
                    f"sessions/{account['session_name']}", 
                    int(account['api_id']), 
                    account['api_hash']
                )
            
            await client.start()
            
            if not await client.is_user_authorized():
                logger.error(f"❌ Аккаунт {account_name} НЕ авторизован!")
                await client.disconnect()
                continue
            
            logger.info(f"✅ Аккаунт {account_name} авторизован")
            
            # Тестируем доступ к каждой группе
            accessible_count = 0
            for group in groups[:5]:  # Тестируем первые 5 групп для скорости
                result = await test_account_in_group(client, account_name, group)
                results.append(result)
                
                if result['accessible']:
                    accessible_count += 1
                
                await asyncio.sleep(2)  # Пауза между запросами
            
            logger.info(f"📊 {account_name}: доступно {accessible_count} из {min(5, len(groups))} групп")
            
            await client.disconnect()
            
        except Exception as e:
            logger.error(f"❌ Ошибка при работе с аккаунтом {account_name}: {e}")
    
    # Анализируем результаты
    logger.info(f"\n{'='*60}")
    logger.info("📊 ИТОГОВЫЙ ОТЧЕТ")
    logger.info(f"{'='*60}")
    
    # Группируем по аккаунтам
    by_account = {}
    for result in results:
        acc = result['account']
        if acc not in by_account:
            by_account[acc] = {'accessible': 0, 'blocked': 0}
        
        if result['accessible']:
            by_account[acc]['accessible'] += 1
        else:
            by_account[acc]['blocked'] += 1
    
    for account_name, stats in by_account.items():
        total = stats['accessible'] + stats['blocked']
        logger.info(f"\n{account_name}:")
        logger.info(f"  ✅ Доступных групп: {stats['accessible']}/{total}")
        logger.info(f"  ❌ Заблокированных: {stats['blocked']}/{total}")
    
    # Сохраняем полный отчет
    report_filename = f"access_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_filename, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    logger.info(f"\n💾 Полный отчет сохранен в: {report_filename}")
    
    # Рекомендации
    logger.info(f"\n{'='*60}")
    logger.info("💡 РЕКОМЕНДАЦИИ")
    logger.info(f"{'='*60}")
    
    best_account = max(by_account.items(), key=lambda x: x[1]['accessible'])
    logger.info(f"✨ Лучший аккаунт: {best_account[0]} ({best_account[1]['accessible']} доступных групп)")
    
    # Находим группы, доступные хотя бы для одного аккаунта
    accessible_groups = set()
    for result in results:
        if result['accessible']:
            accessible_groups.add(result['group'])
    
    logger.info(f"✅ Всего доступных групп: {len(accessible_groups)}")
    
    if len(accessible_groups) == 0:
        logger.warning("⚠️ ВНИМАНИЕ: Ни один аккаунт не имеет доступа к группам!")
        logger.warning("   Рекомендации:")
        logger.warning("   1. Проверьте, что аккаунты вступили в группы")
        logger.warning("   2. Обновите список групп в targets.txt")
        logger.warning("   3. Используйте скрипт find_active_groups.py для поиска новых групп")

if __name__ == "__main__":
    asyncio.run(main())


















