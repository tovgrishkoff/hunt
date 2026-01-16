#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для парсинга текстов Kammora и создания структурированного JSON
"""

import json
import re
from pathlib import Path

def parse_kammora_messages():
    """Парсинг файла telegram_messages_ready.txt и создание структурированного JSON"""
    
    messages_file = Path('kammora_extracted/telegram_messages_ready.txt')
    if not messages_file.exists():
        print(f"❌ Файл {messages_file} не найден")
        return None
    
    with messages_file.open('r', encoding='utf-8') as f:
        content = f.read()
    
    messages = {
        'en': [],  # Английские версии с фото
        'ru': [],  # Русские версии с фото
        'en_alt': [],  # Английские альтернативы без привязки к фото
        'ru_alt': []   # Русские альтернативы без привязки к фото
    }
    
    # Парсим английские варианты
    en_section = content.split('🇬🇧 АНГЛИЙСКИЕ ВЕРСИИ')[1].split('🇷🇺 РУССКИЕ ВЕРСИИ')[0]
    
    # Ищем варианты 1-4 (с фото)
    for i in range(1, 5):
        pattern = rf'Вариант {i} \(kolazh_variant_{i}\.jpg\)(.*?)(?=━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━|Альтернатива|$)'
        match = re.search(pattern, en_section, re.DOTALL)
        if match:
            text = match.group(1).strip()
            # Убираем лишние пробелы и переносы
            text = '\n'.join(line.strip() for line in text.split('\n') if line.strip())
            messages['en'].append({
                'variant': i,
                'photo': f'kammora_assets/photos/kolazh_variant_{i}.jpg',
                'text': text
            })
    
    # Ищем альтернативы (без фото)
    alt_pattern = r'Альтернатива (\d+)(.*?)(?=━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━|$)'
    for match in re.finditer(alt_pattern, en_section, re.DOTALL):
        alt_num = match.group(1)
        text = match.group(2).strip()
        text = '\n'.join(line.strip() for line in text.split('\n') if line.strip())
        messages['en_alt'].append({
            'alt': int(alt_num),
            'text': text
        })
    
    # Парсим русские варианты
    ru_section = content.split('🇷🇺 РУССКИЕ ВЕРСИИ')[1].split('═══════════════════════════════════════════════════════════')[0]
    
    # Ищем варианты 1-4 (с фото)
    for i in range(1, 5):
        pattern = rf'Вариант {i} \(kolazh_variant_{i}_ru\.jpg\)(.*?)(?=━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━|Альтернатива|$)'
        match = re.search(pattern, ru_section, re.DOTALL)
        if match:
            text = match.group(1).strip()
            text = '\n'.join(line.strip() for line in text.split('\n') if line.strip())
            messages['ru'].append({
                'variant': i,
                'photo': f'kammora_assets/photos/kolazh_variant_{i}_ru.jpg',
                'text': text
            })
    
    # Ищем русские альтернативы
    for match in re.finditer(alt_pattern, ru_section, re.DOTALL):
        alt_num = match.group(1)
        text = match.group(2).strip()
        text = '\n'.join(line.strip() for line in text.split('\n') if line.strip())
        messages['ru_alt'].append({
            'alt': int(alt_num),
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
    
    return messages

if __name__ == "__main__":
    parse_kammora_messages()




