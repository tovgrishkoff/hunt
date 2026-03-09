#!/usr/bin/env python3
"""
Скрипт для обновления accounts_config.json новыми string_session из файлов
Созданных скриптом reauthorize_new_accounts.py
"""
import json
import sys
from pathlib import Path

def update_accounts_config():
    """Обновить accounts_config.json новыми сессиями из файлов"""
    config_file = Path('accounts_config.json')
    
    if not config_file.exists():
        print(f"❌ Файл {config_file} не найден!")
        return False
    
    # Загружаем текущую конфигурацию
    with open(config_file, 'r', encoding='utf-8') as f:
        accounts = json.load(f)
    
    # Ищем файлы с новыми сессиями
    session_files = [
        Path('new_session_promotion_oleg_petrov.txt'),
        Path('new_session_promotion_anna_truncher.txt'),
        Path('new_session_promotion_lisa_soak.txt'),
        Path('new_session_promotion_Masha Sinugina.txt'),
    ]
    
    updated_count = 0
    
    for session_file in session_files:
        if not session_file.exists():
            print(f"⚠️ Файл {session_file} не найден, пропускаем")
            continue
        
        # Извлекаем session_name из имени файла
        session_name = session_file.stem.replace('new_session_', '')
        
        # Читаем файл и извлекаем string_session
        with open(session_file, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Ищем строку "String Session:" и берем следующую строку
        lines = content.split('\n')
        string_session = None
        for i, line in enumerate(lines):
            if 'String Session:' in line or 'StringSession:' in line:
                if i + 1 < len(lines):
                    string_session = lines[i + 1].strip()
                    break
        
        if not string_session:
            print(f"⚠️ Не удалось найти string_session в {session_file}")
            continue
        
        # Обновляем accounts_config.json
        found = False
        for account in accounts:
            if account['session_name'] == session_name:
                old_session = account.get('string_session', 'None')[:50] + '...' if account.get('string_session') else 'None'
                account['string_session'] = string_session
                print(f"✅ Обновлен {session_name}:")
                print(f"   Старая сессия: {old_session}")
                print(f"   Новая сессия: {string_session[:50]}...")
                updated_count += 1
                found = True
                break
        
        if not found:
            print(f"⚠️ Аккаунт {session_name} не найден в accounts_config.json")
    
    if updated_count > 0:
        # Сохраняем обновленную конфигурацию
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(accounts, f, ensure_ascii=False, indent=2)
        print(f"\n✅ Обновлено {updated_count} аккаунтов в {config_file}")
        return True
    else:
        print("\n❌ Не было обновлено ни одного аккаунта")
        return False

if __name__ == "__main__":
    print("="*80)
    print("🔄 ОБНОВЛЕНИЕ accounts_config.json НОВЫМИ СЕССИЯМИ")
    print("="*80)
    print()
    
    if update_accounts_config():
        print("\n" + "="*80)
        print("✅ ГОТОВО! Теперь перезапустите контейнеры:")
        print("   docker-compose restart account-manager marketer")
        print("="*80)
        sys.exit(0)
    else:
        print("\n" + "="*80)
        print("❌ Ошибка при обновлении")
        print("="*80)
        sys.exit(1)
