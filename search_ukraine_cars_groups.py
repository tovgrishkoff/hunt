#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для поиска Telegram групп/чатов по Украине, где выставляют объявления о продаже автомобилей
"""

import asyncio
import json
import sys
from pathlib import Path
from telethon import TelegramClient
from telethon.tl.functions.contacts import SearchRequest
from telethon.tl.types import InputPeerEmpty
from telethon.errors import FloodWaitError

sys.path.insert(0, '.')

from promotion_system import PromotionSystem

async def search_ukraine_cars_groups():
    """Поиск украинских групп по продаже автомобилей в Telegram"""
    
    system = PromotionSystem()
    system.load_accounts()
    await system.initialize_clients()
    
    if not system.clients:
        print("❌ Нет доступных клиентов!")
        return
    
    # Используем первый доступный клиент
    client_name = list(system.clients.keys())[0]
    client = system.clients[client_name]
    
    print("=" * 80)
    print("🔍 ПОИСК УКРАИНСКИХ ГРУПП ПО ПРОДАЖЕ АВТОМОБИЛЕЙ")
    print("=" * 80)
    print(f"\n👤 Используем аккаунт: {client_name}")
    
    # Ключевые слова для поиска украинских групп по продаже машин
    search_keywords = [
        # Украинские варианты
        'україна авто',
        'україна автомобілі',
        'продаж авто україна',
        'купити авто україна',
        'авто україна продаж',
        'автомобілі україна',
        'київ авто продаж',
        'київ купити авто',
        'одеса авто продаж',
        'харків авто продаж',
        'львів авто продаж',
        'дніпро авто продаж',
        'авто б/у україна',
        'авто бу україна',
        'авто з пробігом україна',
        'объявления авто украина',
        'объявления автомобили украина',
        # Русские варианты (многие группы могут использовать русский)
        'украина авто',
        'украина автомобили',
        'продажа авто украина',
        'купить авто украина',
        'авто украина продажа',
        'автомобили украина',
        'киев авто продажа',
        'киев купить авто',
        'одесса авто продажа',
        'харьков авто продажа',
        'львов авто продажа',
        'днепр авто продажа',
        'авто б/у украина',
        'авто бу украина',
        'авто с пробегом украина',
        'авто украина объявления',
        'автомобили украина объявления',
        'ukraine cars',
        'ukraine car sale',
        'ukraine auto',
        'ukraine automobile',
        'kyiv cars',
        'kyiv car sale',
        'odessa cars',
        'kharkiv cars',
        # Группы по городам
        'київ купити продати авто',
        'одеса купити продати авто',
        'харків купити продати авто',
        'львів купити продати авто',
        'киев купить продать авто',
        'одесса купить продать авто',
        'харьков купить продать авто',
        'львов купить продать авто',
    ]
    
    found_groups = set()
    all_results = []
    
    print(f"\n🔍 Ищем группы по {len(search_keywords)} ключевым словам...")
    
    for keyword in search_keywords:
        print(f"\n📝 Поиск: '{keyword}'...")
        try:
            # Используем SearchRequest для поиска
            result = await client(SearchRequest(
                q=keyword,
                limit=50
            ))
            
            # Обрабатываем результаты
            for chat in result.chats:
                if hasattr(chat, 'username') and chat.username:
                    group_username = f"@{chat.username}"
                    if group_username not in found_groups:
                        found_groups.add(group_username)
                        all_results.append({
                            'username': group_username,
                            'title': chat.title if hasattr(chat, 'title') else '',
                            'id': chat.id,
                            'members_count': chat.participants_count if hasattr(chat, 'participants_count') else 0,
                            'found_by': keyword
                        })
                        print(f"   ✅ Найдено: {group_username} - {chat.title}")
            
            # Небольшая задержка между запросами
            await asyncio.sleep(2)
            
        except FloodWaitError as e:
            print(f"   ⏳ Ожидание {e.seconds} секунд...")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            print(f"   ❌ Ошибка при поиске '{keyword}': {e}")
            continue
    
    # Сохраняем результаты
    results_file = Path('logs/found_ukraine_cars_groups.json')
    results_file.parent.mkdir(exist_ok=True)
    
    with results_file.open('w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    
    print("\n" + "=" * 80)
    print("📊 РЕЗУЛЬТАТЫ ПОИСКА")
    print("=" * 80)
    print(f"\n✅ Найдено уникальных групп: {len(found_groups)}")
    print(f"📁 Результаты сохранены в: {results_file}")
    
    # Показываем список найденных групп
    print(f"\n📋 НАЙДЕННЫЕ ГРУППЫ:")
    for i, result in enumerate(sorted(all_results, key=lambda x: x['members_count'], reverse=True), 1):
        print(f"   {i:3}. {result['username']:35} - {result['title'][:40]:40} ({result['members_count']} участников)")
        print(f"       Найдено по: {result['found_by']}")
    
    # Проверяем, какие из них уже есть в targets.txt
    targets_file = Path('targets.txt')
    existing_targets = set()
    if targets_file.exists():
        with targets_file.open('r', encoding='utf-8') as f:
            existing_targets = {line.strip() for line in f if line.strip() and not line.strip().startswith('#')}
    
    new_groups = [g['username'] for g in all_results if g['username'] not in existing_targets]
    
    print(f"\n💡 НОВЫЕ ГРУППЫ (не в targets.txt): {len(new_groups)}")
    if new_groups:
        print("   Можно добавить в targets.txt:")
        for group in new_groups[:20]:
            print(f"   • {group}")
        if len(new_groups) > 20:
            print(f"   ... и еще {len(new_groups) - 20} групп")
    
    return all_results

if __name__ == "__main__":
    asyncio.run(search_ukraine_cars_groups())


