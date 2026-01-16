#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для отключения аккаунта promotion_alex_ever от рассылки в украинские группы
Создает файл конфигурации с исключенными аккаунтами для ниши ukraine_cars
"""

import json
from pathlib import Path
from datetime import datetime

def disable_account_for_ukraine_cars():
    """Отключение аккаунта promotion_alex_ever от рассылки в украинские группы"""
    
    config_file = Path('ukraine_cars_accounts_config.json')
    
    # Загружаем существующую конфигурацию или создаем новую
    if config_file.exists():
        with config_file.open('r', encoding='utf-8') as f:
            config = json.load(f)
    else:
        config = {
            'excluded_accounts': [],
            'description': 'Конфигурация аккаунтов для ниши ukraine_cars',
            'excluded_accounts_description': 'Список session_name аккаунтов, которые НЕ должны использоваться для рассылки в украинские группы'
        }
    
    # Добавляем promotion_alex_ever в список исключенных
    excluded_account = 'promotion_alex_ever'
    
    if excluded_account not in config.get('excluded_accounts', []):
        config.setdefault('excluded_accounts', []).append(excluded_account)
        config['last_updated'] = datetime.now().isoformat()
        
        # Сохраняем конфигурацию
        with config_file.open('w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        print("=" * 80)
        print("✅ АККАУНТ ОТКЛЮЧЕН ОТ РАССЫЛКИ В УКРАИНСКИЕ ГРУППЫ")
        print("=" * 80)
        print(f"📝 Аккаунт: {excluded_account} (@alexever85)")
        print(f"📋 Файл конфигурации: {config_file}")
        print(f"🚫 Аккаунт исключен из рассылки для ниши 'ukraine_cars'")
        print("\n💡 Для включения обратно удалите аккаунт из списка excluded_accounts")
    else:
        print(f"ℹ️ Аккаунт {excluded_account} уже в списке исключенных")

if __name__ == "__main__":
    disable_account_for_ukraine_cars()


