#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для повторной рассылки Kammora в группы, где были отправлены некорректные тексты
Использует другие аккаунты и правильный текст про апартаменты
"""

import asyncio
import sys
from pathlib import Path
from telethon.errors import RPCError

sys.path.insert(0, '.')

from promotion_system import PromotionSystem

async def fix_kammora_posts():
    """Повторная рассылка с правильным текстом в проблемные группы"""
    
    # Группы, куда нужно отправить правильные посты
    groups_to_fix = ['@rentallbali', '@onerealestatebali', '@rent_in_bali']
    
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
    print("🔧 ПОВТОРНАЯ РАССЫЛКА KAMMORA С ПРАВИЛЬНЫМ ТЕКСТОМ")
    print("=" * 80)
    print(f"\n📋 Группы для исправления: {len(groups_to_fix)}")
    for group in groups_to_fix:
        print(f"   • {group}")
    
    # Инициализируем клиентов
    await system.initialize_clients()
    
    if not system.clients:
        print("❌ Нет доступных клиентов!")
        return
    
    print(f"\n✅ Инициализировано клиентов: {len(system.clients)}")
    
    # Временно удаляем эти группы из истории, чтобы можно было постить снова
    for group in groups_to_fix:
        if group in system.group_post_history:
            del system.group_post_history[group]
            print(f"   🔄 Удалена история постинга для {group}")
    
    # Сохраняем измененную историю
    system.save_group_post_history()
    
    print("\n" + "=" * 80)
    print("🚀 НАЧИНАЕМ РАССЫЛКУ...")
    print("=" * 80)
    
    sent_count = 0
    
    for group in groups_to_fix:
        print(f"\n📤 Обработка {group}...")
        
        # Проверяем, что группа настроена на kammora
        if system.group_niches.get(group) != 'kammora':
            print(f"   ⚠️  Группа {group} не настроена на kammora, пропускаем")
            continue
        
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
        print(f"   📝 Оригинальный текст: {caption[:80]}...")
        
        # Переформулируем через GPT (правильным методом)
        final_caption = caption
        if system.chatgpt is not None:
            try:
                gpt_caption = await system.chatgpt.rephrase_text(caption, max_tokens=300)
                if gpt_caption:
                    final_caption = gpt_caption.strip()
                    print(f"   ✍️  GPT переформулировал текст")
                    print(f"   📝 Новый текст: {final_caption[:80]}...")
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
                print(f"      📝 Текст: {final_caption[:100]}...")
                print(f"      📨 ID сообщения: {sent_message.id}")
                
                # Обновляем историю и счетчики
                system.mark_group_posted(group, client_name)
                system.account_usage[client_name] = system.account_usage.get(client_name, 0) + 1
                system.daily_posts[client_name] = system.daily_posts.get(client_name, 0) + 1
                sent_count += 1
                sent_successfully = True
                break  # Успешно отправили, выходим из цикла
                
            except RPCError as e:
                error_msg = str(e)
                print(f"      ❌ Ошибка: {error_msg[:80]}...")
                continue  # Пробуем следующий аккаунт
            except Exception as e:
                print(f"      ❌ Неожиданная ошибка: {e}")
                continue  # Пробуем следующий аккаунт
        
        if not sent_successfully:
            print(f"   ❌ Не удалось отправить в {group} через все доступные аккаунты")
        
        # Небольшая задержка между постами
        await asyncio.sleep(5)
    
    print("\n" + "=" * 80)
    print(f"✅ РАССЫЛКА ЗАВЕРШЕНА")
    print(f"   Успешно отправлено: {sent_count}/{len(groups_to_fix)}")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(fix_kammora_posts())
