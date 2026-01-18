#!/usr/bin/env python3
"""Тест мультиязычных паттернов"""

import re
import sys
sys.path.insert(0, '/home/tovgrishkoff/mvp2105')

from patterns import NICHES_KEYWORDS

# Тестовые сообщения
test_messages = [
    # Украинское сообщение (которое было пропущено)
    {
        "text": "Всім привіт, терміново шукаю відеографа з проф камерою та фотографа окремо для івенту забудовника. Напишіть будь-ласка в особисті 🙏🏻",
        "language": "UA",
        "expected": ["Фотограф", "Видеограф"]
    },
    # Русское сообщение
    {
        "text": "привет, ищу фотографа на такую съемку💕",
        "language": "RU",
        "expected": ["Фотограф"]
    },
    # Английское сообщение
    {
        "text": "Hello! Looking for a photographer for a photo shoot this weekend. Please DM me!",
        "language": "EN",
        "expected": ["Фотограф"]
    },
    # Английское - видеограф
    {
        "text": "Urgently need videographer with professional camera for event. Contact me!",
        "language": "EN",
        "expected": ["Видеограф"]
    }
]

print("🌍 Тест мультиязычных паттернов")
print("=" * 80)

for i, test in enumerate(test_messages, 1):
    text = test["text"]
    lang = test["language"]
    expected = test["expected"]
    
    print(f"\n{i}. [{lang}] {text[:60]}...")
    print("-" * 80)
    
    # Проверяем паттерны
    found_niches = set()
    matched_by_niche = {}
    
    text_lower = text.lower()
    
    for niche, patterns in NICHES_KEYWORDS.items():
        collected = []
        match_score = 0
        
        for pattern in patterns:
            try:
                m = re.search(pattern, text_lower)
                if m:
                    snippet = m.group(0)
                    if snippet and snippet not in collected:
                        collected.append(snippet)
                        match_score += 1
                        
                        if match_score >= 3:
                            break
            except Exception as e:
                pass
        
        if collected and match_score >= 1:
            found_niches.add(niche)
            matched_by_niche[niche] = collected
    
    # Результат
    if found_niches:
        print(f"✅ Найдены ниши: {list(found_niches)}")
        for niche, keywords in matched_by_niche.items():
            print(f"   📋 {niche}: {keywords}")
        
        # Проверяем ожидания
        expected_set = set(expected)
        if found_niches == expected_set:
            print(f"✅ Соответствует ожиданиям!")
        else:
            missing = expected_set - found_niches
            extra = found_niches - expected_set
            if missing:
                print(f"⚠️  Не найдено: {list(missing)}")
            if extra:
                print(f"⚠️  Лишнее: {list(extra)}")
    else:
        print(f"❌ Ниши НЕ найдены")
        print(f"   Ожидалось: {expected}")

print("\n" + "=" * 80)

