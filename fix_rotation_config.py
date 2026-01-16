#!/usr/bin/env python3
"""
Скрипт для создания оптимальной конфигурации ротации аккаунтов
"""

import json

# Читаем текущую конфигурацию
with open('accounts_config.json', 'r', encoding='utf-8') as f:
    accounts = json.load(f)

# Создаем mapping: какой аккаунт для каких групп
# Стратегия: распределяем группы между аккаунтами
with open('targets.txt', 'r', encoding='utf-8') as f:
    groups = [line.strip() for line in f if line.strip()]

print(f"📋 Всего аккаунтов: {len(accounts)}")
print(f"📋 Всего групп: {len(groups)}")

# Распределяем группы между аккаунтами
groups_per_account = len(groups) // len(accounts) + 1

account_groups = {}
for i, account in enumerate(accounts):
    account_name = account['session_name']
    nickname = account['nickname']
    
    # Берем свой кусок групп
    start_idx = i * groups_per_account
    end_idx = min((i + 1) * groups_per_account, len(groups))
    account_group_list = groups[start_idx:end_idx]
    
    account_groups[account_name] = {
        'nickname': nickname,
        'groups': account_group_list,
        'count': len(account_group_list)
    }
    
    print(f"\n✅ {account_name} ({nickname}):")
    print(f"   Назначено групп: {len(account_group_list)}")
    for group in account_group_list[:3]:
        print(f"   - {group}")
    if len(account_group_list) > 3:
        print(f"   ... и еще {len(account_group_list) - 3}")

# Сохраняем mapping
with open('account_group_mapping.json', 'w', encoding='utf-8') as f:
    json.dump(account_groups, f, indent=2, ensure_ascii=False)

print(f"\n💾 Маппинг сохранен в account_group_mapping.json")
print(f"\n💡 Рекомендации:")
print(f"   1. Увеличить max_daily_posts с 2 до 10 (6 слотов в день)")
print(f"   2. Использовать разные аккаунты для разных групп")
print(f"   3. Перезапустить систему после изменений")


















