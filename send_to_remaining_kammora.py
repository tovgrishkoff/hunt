#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для рассылки Kammora в оставшиеся группы, которые еще не получили посты
"""

import asyncio
import sys
from pathlib import Path
from telethon.errors import RPCError

sys.path.insert(0, '.')

from promotion_system import PromotionSystem

async def send_to_remaining_kammora():
    """Рассылка в оставшиеся группы kammora"""
    
    system = PromotionSystem()
    
    # Загружаем конфигурацию
    system.load_accounts()
    system.load_targets()
    system.load_messages()
    system.load_niche_messages()
    system.load_group_niches()
    system.load_group_accounts()
    system.load_kammora_messages()
    system.load_group_post_history()
    
    print("=" * 80)
    print("🚀 РАССЫЛКА KAMMORA В ОСТАВШИЕСЯ ГРУППЫ")
    print("=" * 80)
    
    # Находим группы kammora, куда еще не отправляли
    kammora_groups = [k for k, v in system.group_niches.items() if v == 'kammora']
    posted_groups = set(system.group_post_history.keys())
    remaining_groups = [g for g in kammora_groups if g not in posted_groups]
    
    print(f"\n📋 Всего групп kammora: {len(kammora_groups)}")
    print(f"✅ Уже отправлено: {len(set(kammora_groups) & posted_groups)}")
    print(f"⏳ Осталось отправить: {len(remaining_groups)}")
    
    if not remaining_groups:
        print("\n✅ Все группы kammora уже получили посты!")
        return
    
    print(f"\n📤 Группы для рассылки:")
    for i, group in enumerate(remaining_groups, 1):
        print(f"   {i:2}. {group}")
    
    # Инициализируем клиентов
    await system.initialize_clients()
    
    if not system.clients:
        print("❌ Нет доступных клиентов!")
        return
    
    print(f"\n✅ Инициализировано клиентов: {len(system.clients)}")
    
    print("\n" + "=" * 80)
    print("🚀 НАЧИНАЕМ РАССЫЛКУ...")
    print("=" * 80)
    
    sent_count = 0
    
    for group in remaining_groups:
        print(f"\n📤 Обработка {group}...")
        
        # Определяем язык группы
        target_lower = group.lower().replace('@', '')
        russian_indicators = ['аренд', 'недвижим', 'квартир', 'дом', 'объяв', 'сосед', 'obyavlen', 'russians', 'bali_o', 'balioby']
        english_indicators = ['house', 'rent', 'estate', 'property', 'real', 'sale', 'apart', 'accommod', 'housing', 'roommate', 'share', 'bali_arenda', 'balifornia']
        
        russian_score = sum(1 for ind in russian_indicators if ind in target_lower)
        english_score = sum(1 for ind in english_indicators if ind in target_lower)
        
        use_ru = russian_score > english_score
        
        # Выбираем сообщение
        if use_ru and system.kammora_messages.get('ru'):
            kammora_list = system.kammora_messages['ru']
            lang_name = "Russian"
        elif system.kammora_messages.get('en'):
            kammora_list = system.kammora_messages['en']
            lang_name = "English"
        else:
            print(f"   ❌ Нет доступных сообщений для {group}")
            continue
        
        import random
        kammora_item = random.choice(kammora_list)
        photo_path = kammora_item.get('photo', '')
        caption = kammora_item.get('text', '')
        
        if not photo_path or not caption:
            print(f"   ❌ Некорректный элемент Kammora для {group}")
            continue
        
        print(f"   🌐 Язык: {lang_name}")
        print(f"   📷 Фото: {photo_path}")
        
        # Переформулируем через GPT
        final_caption = caption
        if system.chatgpt is not None:
            try:
                gpt_caption = await system.chatgpt.rephrase_text(caption, max_tokens=300)
                if gpt_caption:
                    final_caption = gpt_caption.strip()
                    print(f"   ✍️  GPT переформулировал текст")
            except Exception as e:
                print(f"   ⚠️  Ошибка GPT: {e}, используем оригинальный текст")
        
        # Пробуем отправить через каждый доступный аккаунт
        photo_file = Path(photo_path)
        if not photo_file.exists():
            print(f"   ❌ Файл фото не найден: {photo_path}")
            continue
        
        available_accounts = {name: client for name, client in system.clients.items() 
                             if system.daily_posts.get(name, 0) < system.max_daily_posts}
        
        sent_successfully = False
        for client_name, client in available_accounts.items():
            print(f"   👤 Пробуем аккаунт: {client_name}")
            
            try:
                # Разрешаем entity для этого аккаунта
                entity = await system.resolve_target(client, group)
                if entity is None:
                    print(f"      ❌ Не удалось разрешить {group}")
                    continue
                
                # Отправляем фото
                sent_message = await client.send_file(
                    entity,
                    str(photo_file),
                    caption=final_caption
                )
                
                print(f"      ✅ УСПЕШНО отправлено в {group} через {client_name}!")
                print(f"      📝 Текст: {final_caption[:80]}...")
                
                # Обновляем историю и счетчики
                system.mark_group_posted(group, client_name)
                system.account_usage[client_name] = system.account_usage.get(client_name, 0) + 1
                system.daily_posts[client_name] = system.daily_posts.get(client_name, 0) + 1
                sent_count += 1
                sent_successfully = True
                break
                
            except RPCError as e:
                error_msg = str(e)
                print(f"      ❌ Ошибка: {error_msg[:60]}...")
                continue
            except Exception as e:
                print(f"      ❌ Неожиданная ошибка: {e}")
                continue
        
        if not sent_successfully:
            print(f"   ❌ Не удалось отправить в {group} через все доступные аккаунты")
        
        # Задержка между постами
        await asyncio.sleep(10)
    
    print("\n" + "=" * 80)
    print(f"✅ РАССЫЛКА ЗАВЕРШЕНА")
    print(f"   Успешно отправлено: {sent_count}/{len(remaining_groups)}")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(send_to_remaining_kammora())




