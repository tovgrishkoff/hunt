#!/usr/bin/env python3
"""
Расширение базы групп для просмотра Stories
Автоматический поиск и добавление новых групп
"""

import asyncio
from telethon import TelegramClient
import json

# Новые группы для добавления в систему Stories
NEW_TARGET_GROUPS = [
    # Бали - основные чаты
    '@balirussian',
    '@balilife',
    '@balichatroommates',  # Возможно открыт для Stories
    '@bali_people',
    '@bali_friends',
    
    # Бали - бизнес и недвижимость
    '@bali_business',
    '@bali_property',
    '@balirealestate',
    '@rent_bali',
    
    # Бали - туризм и развлечения
    '@balitravel',
    '@balitoursim',
    '@baliguide',
    '@baliadventures',
    
    # Бали - экспаты и жизнь
    '@baliexpats',
    '@baliliving',
    '@lifeinbali',
    '@expatsbali',
    
    # Бали - работа и сотрудничество
    '@bali_jobs',
    '@balivacancy',
    '@bali_collab',
    
    # Индонезия общее
    '@indonesia_chat',
    '@jakarta_expats',
    
    # Дополнительные ниши
    '@bali_surf',
    '@balifood',
    '@bali_yoga',
    '@balievents',
]

async def check_and_add_groups():
    """Проверка доступности новых групп"""
    # Загружаем конфигурацию
    with open('accounts_config.json', 'r') as f:
        accounts = json.load(f)
    
    if not accounts:
        print("❌ No accounts found")
        return
    
    # Используем первый аккаунт для проверки
    account = accounts[0]
    
    client = TelegramClient(
        f'sessions/{account["session_name"]}',
        int(account['api_id']),
        account['api_hash']
    )
    
    await client.start()
    
    print(f"\n🔍 Проверяю доступность {len(NEW_TARGET_GROUPS)} групп...\n")
    
    accessible_groups = []
    private_groups = []
    not_found = []
    
    for group in NEW_TARGET_GROUPS:
        try:
            entity = await client.get_entity(group)
            
            # Пробуем получить участников
            try:
                participants = await client.get_participants(entity, limit=5)
                accessible_groups.append({
                    'username': group,
                    'title': entity.title if hasattr(entity, 'title') else 'Unknown',
                    'members_count': len(participants)
                })
                print(f"✅ {group} - доступна ({entity.title})")
            except Exception as e:
                if "private" in str(e).lower() or "banned" in str(e).lower():
                    private_groups.append(group)
                    print(f"🔒 {group} - приватная или забанены")
                else:
                    private_groups.append(group)
                    print(f"⚠️ {group} - {str(e)[:50]}")
                    
        except Exception as e:
            not_found.append(group)
            print(f"❌ {group} - не найдена")
        
        await asyncio.sleep(2)  # Задержка между запросами
    
    await client.disconnect()
    
    # Результаты
    print(f"\n" + "="*60)
    print(f"📊 РЕЗУЛЬТАТЫ ПРОВЕРКИ:")
    print(f"="*60)
    print(f"✅ Доступных групп: {len(accessible_groups)}")
    print(f"🔒 Приватных/забаненных: {len(private_groups)}")
    print(f"❌ Не найдено: {len(not_found)}")
    
    if accessible_groups:
        print(f"\n✨ РЕКОМЕНДУЕМЫЕ К ДОБАВЛЕНИЮ:")
        print(f"-" * 60)
        for group in accessible_groups:
            print(f"  {group['username']}")
            print(f"    Название: {group['title']}")
            print(f"    Участников проверено: {group['members_count']}")
            print()
    
    # Генерируем обновленный код для stories_only_system.py
    if accessible_groups:
        print(f"\n📝 КОД ДЛЯ ДОБАВЛЕНИЯ В stories_only_system.py:")
        print(f"-" * 60)
        print("target_groups = [")
        print("    # Существующие группы")
        print("    '@bali_ubud_changu',")
        print("    '@canggu_people',")
        print("    '@events_travels_group',")
        print("    '@balichat',")
        print("    '@bali_villa_arenda',")
        print("    '@mybalitrips',")
        print("    '@baliforum',")
        print("    # Новые доступные группы")
        for group in accessible_groups:
            print(f"    '{group['username']}',  # {group['title']}")
        print("]")

if __name__ == "__main__":
    asyncio.run(check_and_add_groups())

