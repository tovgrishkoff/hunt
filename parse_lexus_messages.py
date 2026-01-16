#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для парсинга текстов Lexus и создания структурированного JSON
"""

import json
import re
from pathlib import Path

def parse_lexus_messages():
    """Парсинг файла lexus_sales_text.txt и создание структурированного JSON"""
    
    messages_file = Path('lexus_assets/lexus_sales_text.txt')
    if not messages_file.exists():
        print(f"❌ Файл {messages_file} не найден")
        return None
    
    with messages_file.open('r', encoding='utf-8') as f:
        content = f.read()
    
    messages = {
        'uk': []  # Украинские версии с фото
    }
    
    # Разделяем на короткие и расширенные варианты
    short_section = content.split('📝 РОЗШИРЕНІ ВАРІАНТИ:')[0]
    extended_section = content.split('📝 РОЗШИРЕНІ ВАРІАНТИ:')[1] if '📝 РОЗШИРЕНІ ВАРІАНТИ:' in content else ''
    
    # Парсим короткие варианты (разделитель ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━)
    short_variants = re.split(r'━+', short_section)
    
    variant_num = 1
    for variant_text in short_variants[1:]:  # Пропускаем заголовок
        variant_text = variant_text.strip()
        if not variant_text or len(variant_text) < 20:  # Пропускаем слишком короткие
            continue
        
        # Пропускаем заголовок "КОРОТКІ ВАРІАНТИ" и рекомендации
        if 'КОРОТКІ ВАРІАНТИ' in variant_text or 'РЕКОМЕНДАЦІЇ' in variant_text or 'РЕКОМЕНДАЦИИ' in variant_text:
            continue
        
        # Очищаем текст
        lines = [line.strip() for line in variant_text.split('\n') if line.strip()]
        clean_text = '\n'.join(lines)
        
        # Пропускаем, если это рекомендации (содержит "Чергуйте", "Відправляйте" и т.д.)
        if any(word in clean_text for word in ['Чергуйте', 'Відправляйте', 'Використовуйте', 'Не використовуйте']):
            continue
        
        if clean_text and variant_num <= 8:  # У нас 8 фото вариантов
            messages['uk'].append({
                'variant': variant_num,
                'photo': f'lexus_assets/lexus_variant_{variant_num}.jpg',
                'text': clean_text
            })
            variant_num += 1
    
    # Если коротких вариантов меньше 8, добавляем расширенные
    if variant_num <= 8 and extended_section:
        # Убираем рекомендации из расширенных вариантов
        extended_section_clean = extended_section.split('💡 РЕКОМЕНДАЦІЇ')[0] if '💡 РЕКОМЕНДАЦІЇ' in extended_section else extended_section
        
        extended_variants = re.split(r'━+', extended_section_clean)
        for variant_text in extended_variants[1:]:
            variant_text = variant_text.strip()
            if not variant_text or len(variant_text) < 50:
                continue
            
            # Пропускаем рекомендации
            if any(word in variant_text for word in ['Чергуйте', 'Відправляйте', 'Використовуйте', 'Не використовуйте']):
                continue
            
            lines = [line.strip() for line in variant_text.split('\n') if line.strip()]
            clean_text = '\n'.join(lines)
            
            if clean_text and variant_num <= 8:
                messages['uk'].append({
                    'variant': variant_num,
                    'photo': f'lexus_assets/lexus_variant_{variant_num}.jpg',
                    'text': clean_text
                })
                variant_num += 1
    
    # Добавляем вариант с коллажем (используем первый текст)
    if messages['uk']:
        messages['uk'].insert(0, {
            'variant': 0,
            'photo': 'lexus_assets/lexus_collage.jpg',
            'text': messages['uk'][0]['text']  # Используем первый вариант текста
        })
    
    # Сохраняем JSON
    output_file = Path('lexus_assets/messages.json')
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with output_file.open('w', encoding='utf-8') as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Создан файл {output_file}")
    print(f"📊 Украинских вариантов: {len(messages['uk'])}")
    
    return messages

if __name__ == "__main__":
    parse_lexus_messages()

