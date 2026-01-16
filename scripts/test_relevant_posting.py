#!/usr/bin/env python3
"""
Тестовый скрипт для проверки релевантного постинга
Проверяет загрузку маппинга групп, сообщений и выбор релевантных сообщений
"""
import sys
import json
import os
from pathlib import Path
from typing import Dict, List

# Определяем корень проекта
project_root = Path(__file__).parent.parent.parent
os.chdir(project_root)


def load_group_niches() -> Dict[str, str]:
    """Загрузка маппинга групп к категориям"""
    # Определяем корень проекта (scripts -> telegram_promotion_system_bali)
    project_root = Path(__file__).parent.parent
    
    group_niches_paths = [
        project_root / 'group_niches.json',
        Path('group_niches.json'),
        Path('/app/group_niches.json'),
    ]
    
    for path in group_niches_paths:
        if path.exists():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    mapping = json.load(f)
                    print(f"✅ Загружен group_niches.json из {path}")
                    return mapping
            except Exception as e:
                print(f"⚠️ Ошибка загрузки {path}: {e}")
    
    print(f"⚠️ group_niches.json не найден. Проверенные пути:")
    for path in group_niches_paths:
        print(f"  - {path} (exists: {path.exists()})")
    
    return {}


def load_messages_by_category() -> Dict[str, List[Dict]]:
    """Загрузка сообщений по категориям"""
    messages_by_category = {}
    
    # Определяем корень проекта (scripts -> telegram_promotion_system_bali)
    project_root = Path(__file__).parent.parent
    
    messages_paths = [
        project_root / 'config' / 'messages' / 'bali' / 'messages.json',
        Path('config/messages/bali/messages.json'),
        Path('/app/config/messages/bali/messages.json'),
    ]
    
    messages_file = None
    for path in messages_paths:
        if path.exists():
            messages_file = path
            print(f"✅ Найден messages.json: {path}")
            break
    
    if not messages_file:
        print(f"⚠️ messages.json не найден. Проверенные пути:")
        for path in messages_paths:
            print(f"  - {path} (exists: {path.exists()})")
        return messages_by_category
    
    try:
        with open(messages_file, 'r', encoding='utf-8') as f:
            all_messages = json.load(f)
        
        for message in all_messages:
            source_file = message.get('source_file', 'general')
            category = source_file.replace('messages_', '').replace('.txt', '')
            
            if category not in messages_by_category:
                messages_by_category[category] = []
            
            messages_by_category[category].append(message)
        
    except Exception as e:
        print(f"⚠️ Ошибка загрузки сообщений: {e}")
    
    return messages_by_category


def get_relevant_messages(group_link: str, group_niches: Dict[str, str], 
                          messages_by_category: Dict[str, List[Dict]], 
                          all_messages: List[Dict]) -> List[Dict]:
    """Получить релевантные сообщения для группы"""
    normalized_link = group_link.lstrip('t.me/').lstrip('@')
    if not normalized_link.startswith('@'):
        normalized_link = '@' + normalized_link
    
    sub_niche = group_niches.get(normalized_link)
    
    if sub_niche and sub_niche not in ['disabled_kammora', 'ukraine_cars']:
        if sub_niche in messages_by_category:
            return messages_by_category[sub_niche]
    
    return all_messages


def test_group_niches_loading(group_niches: Dict[str, str]) -> bool:
    """Тест загрузки маппинга групп к категориям"""
    print("\n" + "="*80)
    print("🧪 ТЕСТ 1: Загрузка маппинга групп к категориям")
    print("="*80)
    
    if not group_niches:
        print("❌ ОШИБКА: Маппинг групп не загружен!")
        return False
    
    print(f"✅ Загружено {len(group_niches)} групп с категориями")
    
    test_groups = [
        "@bali_yes",
        "@scooters_bali",
        "@pvbali",
        "@balimotocats",
        "@bali_rents"
    ]
    
    print("\n📋 Примеры маппинга:")
    found = 0
    for group in test_groups:
        category = group_niches.get(group)
        if category:
            print(f"  ✅ {group:30} → {category}")
            found += 1
        else:
            print(f"  ⚠️  {group:30} → НЕ НАЙДЕН")
    
    if found == 0:
        print("❌ ОШИБКА: Ни одна тестовая группа не найдена в маппинге!")
        return False
    
    print(f"\n✅ Найдено {found}/{len(test_groups)} тестовых групп")
    return True


def test_messages_loading(messages_by_category: Dict[str, List[Dict]]) -> bool:
    """Тест загрузки сообщений по категориям"""
    print("\n" + "="*80)
    print("🧪 ТЕСТ 2: Загрузка сообщений по категориям")
    print("="*80)
    
    if not messages_by_category:
        print("❌ ОШИБКА: Сообщения по категориям не загружены!")
        return False
    
    print(f"✅ Загружено {len(messages_by_category)} категорий")
    
    total_messages = sum(len(msgs) for msgs in messages_by_category.values())
    print(f"✅ Всего сообщений: {total_messages}")
    
    test_categories = [
        "bike_rental",
        "car_rental",
        "photographer",
        "rental_property",
        "currency",
        "designer"
    ]
    
    print("\n📋 Примеры категорий:")
    found = 0
    for category in test_categories:
        messages = messages_by_category.get(category, [])
        if messages:
            print(f"  ✅ {category:30} → {len(messages):3} сообщений")
            if messages:
                example = messages[0].get('text', '')[:60]
                print(f"      Пример: {example}...")
            found += 1
        else:
            print(f"  ⚠️  {category:30} → НЕТ СООБЩЕНИЙ")
    
    if found == 0:
        print("❌ ОШИБКА: Ни одна тестовая категория не найдена!")
        return False
    
    print(f"\n✅ Найдено {found}/{len(test_categories)} тестовых категорий")
    return True


def test_relevant_messages_selection(group_niches: Dict[str, str], 
                                     messages_by_category: Dict[str, List[Dict]],
                                     all_messages: List[Dict]) -> bool:
    """Тест выбора релевантных сообщений для групп"""
    print("\n" + "="*80)
    print("🧪 ТЕСТ 3: Выбор релевантных сообщений для групп")
    print("="*80)
    
    test_cases = [
        ("@bali_yes", "car_rental"),
        ("@scooters_bali", "bike_rental"),
        ("@pvbali", "designer"),
        ("@balimotocats", "currency"),
        ("@bali_rents", "rental_property"),
        ("@unknown_group", None),
    ]
    
    print("\n📋 Проверка выбора сообщений:")
    passed = 0
    failed = 0
    
    for group_link, expected_category in test_cases:
        messages = get_relevant_messages(group_link, group_niches, 
                                        messages_by_category, all_messages)
        
        if not messages:
            print(f"  ❌ {group_link:30} → НЕТ СООБЩЕНИЙ")
            failed += 1
            continue
        
        if expected_category:
            # Проверяем, что все сообщения из нужной категории
            all_from_category = all(
                msg.get('source_file', '').replace('messages_', '').replace('.txt', '') == expected_category
                for msg in messages
            )
            
            if all_from_category:
                print(f"  ✅ {group_link:30} → {expected_category:20} ({len(messages):3} сообщений)")
                passed += 1
            else:
                print(f"  ⚠️  {group_link:30} → {expected_category:20} ({len(messages):3} сообщений, но не все из категории)")
                failed += 1
        else:
            print(f"  ✅ {group_link:30} → все сообщения ({len(messages):3} сообщений)")
            passed += 1
    
    print(f"\n✅ Успешно: {passed}/{len(test_cases)}")
    if failed > 0:
        print(f"❌ Ошибок: {failed}/{len(test_cases)}")
        return False
    
    return True


def test_message_structure(messages_by_category: Dict[str, List[Dict]]) -> bool:
    """Тест структуры сообщений"""
    print("\n" + "="*80)
    print("🧪 ТЕСТ 4: Структура сообщений")
    print("="*80)
    
    if not messages_by_category:
        print("❌ ОШИБКА: Сообщения не загружены!")
        return False
    
    test_categories = list(messages_by_category.keys())[:5]
    
    print("\n📋 Проверка структуры сообщений:")
    all_valid = True
    
    for category in test_categories:
        messages = messages_by_category[category]
        if not messages:
            continue
        
        msg = messages[0]
        required_fields = ['text', 'source_file']
        
        missing_fields = [field for field in required_fields if field not in msg]
        
        if missing_fields:
            print(f"  ❌ {category:30} → Отсутствуют поля: {', '.join(missing_fields)}")
            all_valid = False
        else:
            text = msg.get('text', '')
            source_file = msg.get('source_file', '')
            print(f"  ✅ {category:30} → text: {len(text):3} символов, source_file: {source_file}")
    
    if all_valid:
        print("\n✅ Все сообщения имеют правильную структуру")
    else:
        print("\n❌ Некоторые сообщения имеют неправильную структуру")
    
    return all_valid


def test_category_coverage(group_niches: Dict[str, str], 
                          messages_by_category: Dict[str, List[Dict]]) -> bool:
    """Тест покрытия категорий сообщениями"""
    print("\n" + "="*80)
    print("🧪 ТЕСТ 5: Покрытие категорий сообщениями")
    print("="*80)
    
    # Получаем все уникальные категории из group_niches
    unique_categories = set()
    for category in group_niches.values():
        if category not in ['disabled_kammora', 'ukraine_cars']:
            unique_categories.add(category)
    
    print(f"📋 Уникальных категорий в маппинге: {len(unique_categories)}")
    print(f"📋 Категорий с сообщениями: {len(messages_by_category)}")
    
    # Проверяем, какие категории есть в маппинге, но нет сообщений
    missing_categories = unique_categories - set(messages_by_category.keys())
    
    if missing_categories:
        print(f"\n⚠️  Категории без сообщений ({len(missing_categories)}):")
        for cat in sorted(missing_categories)[:10]:
            print(f"  - {cat}")
        if len(missing_categories) > 10:
            print(f"  ... и еще {len(missing_categories) - 10}")
    else:
        print("\n✅ Все категории из маппинга имеют сообщения")
    
    # Проверяем, какие категории есть в сообщениях, но не используются
    unused_categories = set(messages_by_category.keys()) - unique_categories
    
    if unused_categories:
        print(f"\nℹ️  Категории с сообщениями, но не используемые в маппинге ({len(unused_categories)}):")
        for cat in sorted(unused_categories)[:10]:
            print(f"  - {cat}")
        if len(unused_categories) > 10:
            print(f"  ... и еще {len(unused_categories) - 10}")
    
    return len(missing_categories) == 0


def main():
    """Главная функция тестирования"""
    print("="*80)
    print("🧪 ТЕСТИРОВАНИЕ СИСТЕМЫ РЕЛЕВАНТНОГО ПОСТИНГА")
    print("="*80)
    
    # Загружаем данные
    print("\n📥 Загрузка данных...")
    group_niches = load_group_niches()
    messages_by_category = load_messages_by_category()
    
    # Получаем все сообщения для fallback
    all_messages = []
    for msgs in messages_by_category.values():
        all_messages.extend(msgs)
    
    if not all_messages:
        # Пробуем загрузить напрямую
        project_root = Path(__file__).parent.parent
        messages_paths = [
            project_root / 'config' / 'messages' / 'bali' / 'messages.json',
            Path('config/messages/bali/messages.json'),
            Path('/app/config/messages/bali/messages.json'),
        ]
        for path in messages_paths:
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    all_messages = json.load(f)
                break
    
    print(f"✅ Загружено: {len(group_niches)} групп, {len(messages_by_category)} категорий, {len(all_messages)} сообщений")
    
    # Запускаем тесты
    tests = [
        ("Загрузка маппинга групп", lambda: test_group_niches_loading(group_niches)),
        ("Загрузка сообщений", lambda: test_messages_loading(messages_by_category)),
        ("Выбор релевантных сообщений", lambda: test_relevant_messages_selection(
            group_niches, messages_by_category, all_messages)),
        ("Структура сообщений", lambda: test_message_structure(messages_by_category)),
        ("Покрытие категорий", lambda: test_category_coverage(group_niches, messages_by_category)),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n❌ ОШИБКА в тесте '{test_name}': {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))
    
    # Итоговый отчет
    print("\n" + "="*80)
    print("📊 ИТОГОВЫЙ ОТЧЕТ")
    print("="*80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ ПРОЙДЕН" if result else "❌ ПРОВАЛЕН"
        print(f"  {status} - {test_name}")
    
    print("\n" + "="*80)
    if passed == total:
        print(f"✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ ({passed}/{total})")
        print("✅ Система готова к постингу!")
        return True
    else:
        print(f"⚠️  ПРОЙДЕНО: {passed}/{total}")
        print("⚠️  Есть проблемы, которые нужно исправить перед постингом")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
