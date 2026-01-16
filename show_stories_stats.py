#!/usr/bin/env python3
"""
Скрипт для отображения статистики просмотров Stories из логов
"""

import re
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Tuple


def parse_log_file(log_file: Path) -> Dict:
    """Парсинг лог-файла и извлечение статистики"""
    stats = {
        'accounts': defaultdict(lambda: {'stories': 0, 'reactions': 0, 'cycles': 0}),
        'daily': defaultdict(lambda: {'stories': 0, 'reactions': 0, 'cycles': 0}),
        'total_stories': 0,
        'total_reactions': 0,
        'total_cycles': 0,
    }
    
    # Паттерны для поиска
    account_pattern = re.compile(r'📊\s+(\w+):\s+(\d+)\s+Stories,\s+(\d+)\s+реакций')
    cycle_pattern = re.compile(r'✅\s+Цикл завершен:\s+(\d+)\s+просмотров,\s+(\d+)\s+реакций')
    date_pattern = re.compile(r'(\d{4}-\d{2}-\d{2})\s+\d{2}:\d{2}:\d{2}')
    
    current_date = None
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            for line in f:
                # Извлекаем дату
                date_match = date_pattern.search(line)
                if date_match:
                    current_date = date_match.group(1)
                
                # Статистика по аккаунтам
                account_match = account_pattern.search(line)
                if account_match:
                    account = account_match.group(1)
                    stories = int(account_match.group(2))
                    reactions = int(account_match.group(3))
                    
                    stats['accounts'][account]['stories'] += stories
                    stats['accounts'][account]['reactions'] += reactions
                    stats['accounts'][account]['cycles'] += 1
                    stats['total_stories'] += stories
                    stats['total_reactions'] += reactions
                    
                    if current_date:
                        stats['daily'][current_date]['stories'] += stories
                        stats['daily'][current_date]['reactions'] += reactions
                
                # Статистика циклов
                cycle_match = cycle_pattern.search(line)
                if cycle_match:
                    stories = int(cycle_match.group(1))
                    reactions = int(cycle_match.group(2))
                    stats['total_cycles'] += 1
                    
                    if current_date:
                        stats['daily'][current_date]['cycles'] += 1
                        
    except FileNotFoundError:
        print(f"❌ Файл {log_file} не найден")
        return None
    except Exception as e:
        print(f"❌ Ошибка при чтении файла: {e}")
        return None
    
    return stats


def format_number(num: int) -> str:
    """Форматирование чисел с разделителями"""
    return f"{num:,}".replace(',', ' ')


def print_stats(stats: Dict):
    """Красивый вывод статистики"""
    if not stats:
        return
    
    print("\n" + "="*80)
    print("📊 СТАТИСТИКА ПРОСМОТРОВ STORIES В TELEGRAM")
    print("="*80)
    
    # Общая статистика
    print("\n📈 ОБЩАЯ СТАТИСТИКА:")
    print(f"   👁️  Всего просмотрено Stories: {format_number(stats['total_stories'])}")
    print(f"   ❤️  Всего поставлено реакций: {format_number(stats['total_reactions'])}")
    print(f"   🔄 Всего циклов просмотра: {format_number(stats['total_cycles'])}")
    
    if stats['total_stories'] > 0:
        reaction_rate = (stats['total_reactions'] / stats['total_stories']) * 100
        print(f"   📊 Процент реакций: {reaction_rate:.1f}%")
    
    # Статистика по аккаунтам
    print("\n👤 СТАТИСТИКА ПО АККАУНТАМ:")
    print("-" * 80)
    
    # Сортируем по количеству просмотров
    sorted_accounts = sorted(
        stats['accounts'].items(),
        key=lambda x: x[1]['stories'],
        reverse=True
    )
    
    for account, data in sorted_accounts:
        print(f"\n   📱 {account}:")
        print(f"      👁️  Stories: {format_number(data['stories'])}")
        print(f"      ❤️  Реакций: {format_number(data['reactions'])}")
        print(f"      🔄 Циклов: {format_number(data['cycles'])}")
        
        if data['stories'] > 0:
            avg_stories = data['stories'] / data['cycles'] if data['cycles'] > 0 else 0
            reaction_rate = (data['reactions'] / data['stories']) * 100
            print(f"      📊 Среднее за цикл: {avg_stories:.1f} Stories")
            print(f"      📊 Процент реакций: {reaction_rate:.1f}%")
    
    # Статистика по дням (последние 7 дней)
    print("\n📅 СТАТИСТИКА ПО ДНЯМ (последние 7 дней):")
    print("-" * 80)
    
    sorted_days = sorted(stats['daily'].items(), reverse=True)[:7]
    
    if sorted_days:
        for date_str, data in sorted_days:
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                date_formatted = date_obj.strftime('%d.%m.%Y')
            except:
                date_formatted = date_str
            
            print(f"\n   📆 {date_formatted}:")
            print(f"      👁️  Stories: {format_number(data['stories'])}")
            print(f"      ❤️  Реакций: {format_number(data['reactions'])}")
            print(f"      🔄 Циклов: {format_number(data['cycles'])}")
            
            if data['stories'] > 0:
                reaction_rate = (data['reactions'] / data['stories']) * 100
                print(f"      📊 Процент реакций: {reaction_rate:.1f}%")
    else:
        print("   ⚠️  Нет данных по дням")
    
    print("\n" + "="*80 + "\n")


def main():
    """Главная функция"""
    log_file = Path(__file__).parent / "logs" / "stories_only_system.log"
    
    if not log_file.exists():
        print(f"❌ Файл логов не найден: {log_file}")
        print(f"   Проверьте путь к файлу логов")
        return
    
    print(f"📂 Чтение логов из: {log_file}")
    stats = parse_log_file(log_file)
    
    if stats:
        print_stats(stats)
    else:
        print("❌ Не удалось получить статистику")


if __name__ == '__main__':
    main()








