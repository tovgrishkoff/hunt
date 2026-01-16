#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тестовый скрипт для проверки рассылки Kammora
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, '.')

from promotion_system import PromotionSystem

async def test_kammora():
    """Тест рассылки Kammora в режиме dry-run"""
    system = PromotionSystem()
    
    # Загружаем конфигурацию
    system.load_accounts()
    system.load_targets()
    system.load_messages()
    system.load_niche_messages()
    system.load_group_niches()
    system.load_group_accounts()
    system.load_kammora_messages()
    
    print("=" * 80)
    print("🧪 ТЕСТ РАССЫЛКИ KAMMORA (DRY-RUN)")
    print("=" * 80)
    
    # Проверяем загрузку Kammora
    if not system.kammora_messages:
        print("❌ Kammora messages не загружены!")
        return
    
    print(f"\n✅ Kammora messages загружены:")
    print(f"   RU: {len(system.kammora_messages.get('ru', []))} вариантов")
    print(f"   EN: {len(system.kammora_messages.get('en', []))} вариантов")
    
    # Находим группы kammora
    kammora_groups = [g for g in system.targets if system.group_niches.get(g) == 'kammora']
    print(f"\n📋 Найдено групп kammora: {len(kammora_groups)}")
    
    if not kammora_groups:
        print("❌ Нет групп с нишей kammora в targets.txt")
        return
    
    # Показываем первые 3 группы
    print(f"\n🔍 Первые 3 группы для теста:")
    for group in kammora_groups[:3]:
        print(f"   - {group}")
    
    # Запускаем тестовую рассылку (dry-run, только 2 поста)
    print(f"\n🚀 Запускаем тестовую рассылку (dry-run, max 2 поста)...")
    print("=" * 80)
    
    await system.post_to_targets(dry_run=True, interval_seconds=2, max_posts=2)
    
    print("\n" + "=" * 80)
    print("✅ Тест завершен!")

if __name__ == "__main__":
    asyncio.run(test_kammora())




