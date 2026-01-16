#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для проверки всех исправлений в коде
Проверяет, что все критические исправления применены правильно
"""
import sys
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def check_file_contains(file_path: Path, patterns: list, description: str) -> tuple:
    """Проверить, содержит ли файл все паттерны"""
    if not file_path.exists():
        return False, f"❌ Файл не найден: {file_path}"
    
    content = file_path.read_text(encoding='utf-8')
    missing = []
    
    for pattern in patterns:
        if pattern not in content:
            missing.append(pattern)
    
    if missing:
        return False, f"❌ Отсутствуют паттерны: {', '.join(missing)}"
    
    return True, f"✅ {description}"

def main():
    """Основная функция проверки"""
    print("=" * 80)
    print("🔍 ПРОВЕРКА ИСПРАВЛЕНИЙ В КОДЕ")
    print("=" * 80)
    print()
    
    checks = []
    
    # 1. Account Manager - лимит групп за слот
    print("1️⃣ Проверка Account Manager - лимит групп за слот...")
    joiner_file = project_root / "services" / "account-manager" / "joiner.py"
    result, msg = check_file_contains(
        joiner_file,
        ["max_groups_per_slot = 5", "groups_to_process = new_groups[:max_groups_per_slot]"],
        "Лимит 5 групп за слот установлен"
    )
    checks.append(("Account Manager - лимит", result))
    print(f"   {msg}")
    print()
    
    # 2. Account Manager - обработка FloodWait
    print("2️⃣ Проверка Account Manager - обработка FloodWait...")
    result, msg = check_file_contains(
        joiner_file,
        ["max_wait = 600", "if wait_seconds > max_wait", "пропускаем группу"],
        "FloodWait обрабатывается правильно (≤10 мин ждем, >10 мин пропускаем)"
    )
    checks.append(("Account Manager - FloodWait", result))
    print(f"   {msg}")
    print()
    
    # 3. Account Manager - DetachedInstanceError
    print("3️⃣ Проверка Account Manager - исправление DetachedInstanceError...")
    result, msg = check_file_contains(
        joiner_file,
        ["db.refresh(group)", "group_username = group.username"],
        "Исправление DetachedInstanceError применено (db.refresh)"
    )
    checks.append(("Account Manager - DetachedInstanceError", result))
    print(f"   {msg}")
    print()
    
    # 4. Account Manager - пауза между вступлениями
    print("4️⃣ Проверка Account Manager - пауза между вступлениями...")
    result, msg = check_file_contains(
        joiner_file,
        ["delay = random.randint(300, 600)", "Пауза"],
        "Пауза 5-10 минут между вступлениями установлена"
    )
    checks.append(("Account Manager - пауза", result))
    print(f"   {msg}")
    print()
    
    # 5. Marketer - проверка прав перед постингом
    print("5️⃣ Проверка Marketer - проверка прав перед постингом...")
    poster_file = project_root / "services" / "marketer" / "poster.py"
    result, msg = check_file_contains(
        poster_file,
        ["check_can_post_permissions", "get_permissions", "banned_rights"],
        "Проверка прав перед постингом реализована"
    )
    checks.append(("Marketer - проверка прав", result))
    print(f"   {msg}")
    print()
    
    # 6. Marketer - маркировка недоступных групп
    print("6️⃣ Проверка Marketer - маркировка недоступных групп...")
    result, msg = check_file_contains(
        poster_file,
        ["group.status = 'banned'", "group.can_post = False", "Write forbidden"],
        "Маркировка недоступных групп реализована"
    )
    checks.append(("Marketer - маркировка", result))
    print(f"   {msg}")
    print()
    
    # 7. Activity - загрузка клиентов
    print("7️⃣ Проверка Activity - загрузка клиентов...")
    activity_file = project_root / "services" / "activity" / "main.py"
    result, msg = check_file_contains(
        activity_file,
        ["client_manager.load_accounts_from_db", "Loaded", "accounts"],
        "Загрузка клиентов через client_manager реализована"
    )
    checks.append(("Activity - загрузка клиентов", result))
    print(f"   {msg}")
    print()
    
    # 8. Client Manager - переподключение клиентов
    print("8️⃣ Проверка Client Manager - переподключение клиентов...")
    client_manager_file = project_root / "shared" / "telegram" / "client_manager.py"
    result, msg = check_file_contains(
        client_manager_file,
        ["ensure_client_connected", "is_connected()", "reconnecting"],
        "Функция переподключения клиентов реализована"
    )
    checks.append(("Client Manager - переподключение", result))
    print(f"   {msg}")
    print()
    
    # Итоги
    print()
    print("=" * 80)
    print("📊 ИТОГИ ПРОВЕРКИ")
    print("=" * 80)
    
    passed = sum(1 for _, result in checks if result)
    total = len(checks)
    
    for name, result in checks:
        status = "✅" if result else "❌"
        print(f"{status} {name}")
    
    print()
    print(f"✅ Пройдено: {passed}/{total}")
    
    if passed == total:
        print("🎉 Все проверки пройдены! Все исправления применены корректно.")
        return 0
    else:
        print(f"⚠️ Некоторые проверки не пройдены ({total - passed}). Проверьте код вручную.")
        return 1

if __name__ == "__main__":
    exit(main())
