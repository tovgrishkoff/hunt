#!/usr/bin/env python3
"""
Скрипт для обновления API_ID и API_HASH в accounts_config.json
"""
import json
import sys

def update_api_credentials(session_name, new_api_id, new_api_hash):
    """Обновление API credentials для аккаунта"""
    config_file = 'accounts_config.json'
    
    try:
        # Загружаем конфигурацию
        with open(config_file, 'r', encoding='utf-8') as f:
            accounts = json.load(f)
        
        # Находим аккаунт
        account = None
        for acc in accounts:
            if acc['session_name'] == session_name:
                account = acc
                break
        
        if not account:
            print(f"❌ Аккаунт {session_name} не найден в конфигурации")
            return False
        
        # Обновляем API credentials
        old_api_id = account['api_id']
        old_api_hash = account['api_hash']
        
        account['api_id'] = int(new_api_id)
        account['api_hash'] = new_api_hash
        
        # Сохраняем обновленную конфигурацию
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(accounts, f, indent=2, ensure_ascii=False)
        
        print("="*80)
        print("✅ API credentials обновлены!")
        print("="*80)
        print(f"Аккаунт: {account['nickname']} ({account['phone']})")
        print(f"Старый API_ID: {old_api_id}")
        print(f"Новый API_ID: {new_api_id}")
        print(f"Старый API_HASH: {old_api_hash[:20]}...")
        print(f"Новый API_HASH: {new_api_hash[:20]}...")
        print("="*80)
        
        return True
        
    except FileNotFoundError:
        print(f"❌ Файл {config_file} не найден")
        return False
    except json.JSONDecodeError as e:
        print(f"❌ Ошибка парсинга JSON: {e}")
        return False
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

def main():
    print("🔑 Обновление API credentials в accounts_config.json")
    print("="*80)
    print()
    print("Сначала получите новые API_ID и API_HASH:")
    print("1. Зайдите на https://my.telegram.org/apps")
    print("2. Войдите с номером телефона аккаунта")
    print("3. Создайте новое приложение")
    print("4. Скопируйте api_id и api_hash")
    print()
    print("="*80)
    
    session_name = input("Введите session_name аккаунта (например, promotion_andrey_virgin): ").strip()
    if not session_name:
        print("❌ session_name не может быть пустым")
        return
    
    new_api_id = input("Введите новый API_ID: ").strip()
    if not new_api_id:
        print("❌ API_ID не может быть пустым")
        return
    
    try:
        int(new_api_id)  # Проверка, что это число
    except ValueError:
        print("❌ API_ID должен быть числом")
        return
    
    new_api_hash = input("Введите новый API_HASH: ").strip()
    if not new_api_hash:
        print("❌ API_HASH не может быть пустым")
        return
    
    print()
    confirm = input(f"Обновить API для {session_name}? (y/n): ").strip().lower()
    if confirm != 'y':
        print("❌ Отменено")
        return
    
    if update_api_credentials(session_name, new_api_id, new_api_hash):
        print("\n✅ Готово! Теперь попробуйте авторизоваться снова:")
        print("   python3 authorize_new_no_proxy.py")
    else:
        print("\n❌ Не удалось обновить API credentials")

if __name__ == "__main__":
    main()

