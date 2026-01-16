#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Улучшенный парсер текстов Kammora
"""

import json
import re
from pathlib import Path

def parse_kammora_messages():
    """Парсинг файла telegram_messages_ready.txt"""
    
    messages_file = Path('kammora_extracted/telegram_messages_ready.txt')
    if not messages_file.exists():
        print(f"❌ Файл {messages_file} не найден")
        return None
    
    with messages_file.open('r', encoding='utf-8') as f:
        lines = f.readlines()
    
    messages = {
        'en': [],
        'ru': [],
        'en_alt': [],
        'ru_alt': []
    }
    
    current_section = None
    current_variant = None
    current_text = []
    in_text_block = False
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # Определяем секцию
        if '🇬🇧 АНГЛИЙСКИЕ ВЕРСИИ' in line:
            current_section = 'en'
            i += 1
            continue
        elif '🇷🇺 РУССКИЕ ВЕРСИИ' in line:
            current_section = 'ru'
            i += 1
            continue
        
        # Ищем варианты с фото
        if 'Вариант' in line and 'kolazh_variant' in line:
            # Сохраняем предыдущий вариант, если был
            if current_variant and current_text and current_section:
                text = '\n'.join(current_text).strip()
                if text:
                    if current_section in ['en', 'ru']:
                        variant_num = int(re.search(r'variant_(\d+)', line).group(1))
                        photo_suffix = '_ru.jpg' if current_section == 'ru' else '.jpg'
                        messages[current_section].append({
                            'variant': variant_num,
                            'photo': f'kammora_assets/photos/kolazh_variant_{variant_num}{photo_suffix}',
                            'text': text
                        })
            
            # Начинаем новый вариант
            variant_match = re.search(r'variant_(\d+)', line)
            if variant_match:
                current_variant = int(variant_match.group(1))
                current_text = []
                in_text_block = True
            i += 1
            continue
        
        # Ищем альтернативы
        if 'Альтернатива' in line and not 'kolazh' in line:
            # Сохраняем предыдущий вариант
            if current_variant and current_text and current_section:
                text = '\n'.join(current_text).strip()
                if text:
                    photo_suffix = '_ru.jpg' if current_section == 'ru' else '.jpg'
                    messages[current_section].append({
                        'variant': current_variant,
                        'photo': f'kammora_assets/photos/kolazh_variant_{current_variant}{photo_suffix}',
                        'text': text
                    })
            
            # Начинаем альтернативу
            alt_match = re.search(r'Альтернатива (\d+)', line)
            if alt_match:
                current_variant = None
                current_alt = int(alt_match.group(1))
                current_text = []
                in_text_block = True
            i += 1
            continue
        
        # Разделитель - конец блока
        if line.startswith('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━'):
            if in_text_block and current_text:
                text = '\n'.join(current_text).strip()
                if text:
                    if current_variant and current_section in ['en', 'ru']:
                        photo_suffix = '_ru.jpg' if current_section == 'ru' else '.jpg'
                        messages[current_section].append({
                            'variant': current_variant,
                            'photo': f'kammora_assets/photos/kolazh_variant_{current_variant}{photo_suffix}',
                            'text': text
                        })
                    elif current_alt:
                        alt_key = f'{current_section}_alt'
                        messages[alt_key].append({
                            'alt': current_alt,
                            'text': text
                        })
                current_text = []
                in_text_block = False
                current_variant = None
                current_alt = None
            i += 1
            continue
        
        # Собираем текст
        if in_text_block and line and not line.startswith('═'):
            current_text.append(line)
        
        i += 1
    
    # Сохраняем последний блок, если остался
    if current_variant and current_text and current_section:
        text = '\n'.join(current_text).strip()
        if text:
            photo_suffix = '_ru.jpg' if current_section == 'ru' else '.jpg'
            messages[current_section].append({
                'variant': current_variant,
                'photo': f'kammora_assets/photos/kolazh_variant_{current_variant}{photo_suffix}',
                'text': text
            })
    
    # Сохраняем в JSON
    output_file = Path('kammora_assets/messages.json')
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with output_file.open('w', encoding='utf-8') as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Создан файл {output_file}")
    print(f"📊 Статистика:")
    print(f"   Английские с фото: {len(messages['en'])}")
    print(f"   Русские с фото: {len(messages['ru'])}")
    print(f"   Английские альтернативы: {len(messages['en_alt'])}")
    print(f"   Русские альтернативы: {len(messages['ru_alt'])}")
    
    # Показываем пример
    if messages['en']:
        print(f"\n📝 Пример английского сообщения:")
        print(f"   Вариант: {messages['en'][0]['variant']}")
        print(f"   Фото: {messages['en'][0]['photo']}")
        print(f"   Текст: {messages['en'][0]['text'][:100]}...")
    
    return messages

if __name__ == "__main__":
    parse_kammora_messages()




