#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для поиска Telegram групп/чатов, где можно разместить объявления о сдаче апартаментов
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

async def search_telegram_groups():
    """Поиск групп в Telegram по ключевым словам"""
    
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
    print("🔍 ПОИСК ГРУПП ДЛЯ РАЗМЕЩЕНИЯ ОБЪЯВЛЕНИЙ О СДАЧЕ АПАРТАМЕНТОВ")
    print("=" * 80)
    print(f"\n👤 Используем аккаунт: {client_name}")
    
    # Ключевые слова для поиска
    search_keywords = [
        'bali rent',
        'bali apartment',
        'bali villa',
        'bali property',
        'bali real estate',
        'аренда балі',
        'аренда бали',
        'недвижимость бали',
        'квартиры бали',
        'villa bali',
        'canggu rent',
        'canggu apartment',
        'ubud rent',
        'seminyak rent',
        'bali housing',
        'bali accommodation',
        'bali roommates',
        'bali share',
        'bali sale',
        'bali buy sell',
        'bali объявления',
        'bali объяв',
        'bali оbyavlenia',
        'bali arenda',
        'bali rental'
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
    results_file = Path('logs/found_rental_groups.json')
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
            existing_targets = {line.strip() for line in f if line.strip()}
    
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
    asyncio.run(search_telegram_groups())




