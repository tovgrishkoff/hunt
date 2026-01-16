#!/usr/bin/env python3
"""
Скрипт для поиска названий активных групп по их ID из логов
"""

import asyncio
import json
import logging
from telethon import TelegramClient
from telethon.sessions import StringSession

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Активные группы из логов (исключая заблокированные)
ACTIVE_GROUPS = [
    1032422089, 1180252758, 2123818093, 2358631846, 1824741898, 1626526675,
    1540608753, 1492919625, 1278052827, 1467162873, 2233860276, 1670908431,
    1919571432, 1858490178, 1894542948, 1609129624, 1141864847, 1394199452,
    1173391726, 1761990621, 1341855810, 1640527500, 2040562327, 1940107962,
    2054222920, 1618739515, 1374655693, 2343300452, 1399990845, 1268089422,
    2307116540, 1269265162, 2371997825, 1703113785, 1276625951, 1302872889,
    1699177401, 1775894772, 1772266000, 1508876175
]

# Заблокированные группы (исключаем их)
BANNED_GROUPS = [1388027785, 1437172130, 2428157434, 1490984268, 1646544705]

async def get_group_info(client, group_id):
    """Получить информацию о группе по ID"""
    try:
        # Пробуем получить сущность по ID
        entity = await client.get_entity(group_id)
        
        info = {
            'id': group_id,
            'title': getattr(entity, 'title', 'Unknown'),
            'username': getattr(entity, 'username', None),
            'type': type(entity).__name__,
            'participants_count': getattr(entity, 'participants_count', None)
        }
        
        # Формируем @username если есть
        if info['username']:
            info['mention'] = f"@{info['username']}"
        else:
            info['mention'] = f"ID:{group_id}"
            
        return info
        
    except Exception as e:
        logger.warning(f"Не удалось получить информацию о группе {group_id}: {e}")
        return {
            'id': group_id,
            'title': 'Unknown',
            'username': None,
            'type': 'Unknown',
            'participants_count': None,
            'mention': f"ID:{group_id}",
            'error': str(e)
        }

async def main():
    """Основная функция"""
    # Загружаем конфигурацию аккаунтов
    with open('accounts_config.json', 'r', encoding='utf-8') as f:
        accounts = json.load(f)
    
    # Используем первый доступный аккаунт
    account = accounts[0]
    
    # Создаем клиент
    client = TelegramClient(
        StringSession(account['string_session']),
        account['api_id'],
        account['api_hash']
    )
    
    try:
        await client.connect()
        
        if not await client.is_user_authorized():
            logger.error("Клиент не авторизован")
            return
            
        logger.info(f"Подключен как {account['nickname']}")
        
        # Получаем информацию о группах
        groups_info = []
        
        for group_id in ACTIVE_GROUPS:
            if group_id not in BANNED_GROUPS:
                logger.info(f"Получаем информацию о группе {group_id}...")
                info = await get_group_info(client, group_id)
                groups_info.append(info)
                
                # Небольшая пауза между запросами
                await asyncio.sleep(1)
        
        # Сохраняем результаты
        with open('active_groups_info.json', 'w', encoding='utf-8') as f:
            json.dump(groups_info, f, ensure_ascii=False, indent=2)
        
        # Выводим краткую статистику
        logger.info(f"\n📊 НАЙДЕНО АКТИВНЫХ ГРУПП: {len(groups_info)}")
        
        # Группируем по типам
        by_type = {}
        with_username = 0
        
        for group in groups_info:
            group_type = group['type']
            if group_type not in by_type:
                by_type[group_type] = 0
            by_type[group_type] += 1
            
            if group['username']:
                with_username += 1
        
        logger.info(f"📈 Статистика:")
        for group_type, count in by_type.items():
            logger.info(f"  {group_type}: {count}")
        logger.info(f"  С @username: {with_username}")
        logger.info(f"  Без @username: {len(groups_info) - with_username}")
        
        # Показываем топ-10 групп с наибольшим количеством участников
        groups_with_participants = [g for g in groups_info if g['participants_count']]
        groups_with_participants.sort(key=lambda x: x['participants_count'] or 0, reverse=True)
        
        logger.info(f"\n🏆 ТОП-10 ГРУПП ПО КОЛИЧЕСТВУ УЧАСТНИКОВ:")
        for i, group in enumerate(groups_with_participants[:10], 1):
            participants = group['participants_count'] or 0
            mention = group['mention']
            title = group['title'][:50] + "..." if len(group['title']) > 50 else group['title']
            logger.info(f"  {i:2d}. {mention} - {participants:,} участников - {title}")
        
        logger.info(f"\n✅ Результаты сохранены в active_groups_info.json")
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
