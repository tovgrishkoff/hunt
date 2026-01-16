#!/usr/bin/env python3
"""
Объединение всех файлов messages_*.txt в один messages.json
"""
import json
import os
from pathlib import Path

def merge_all_messages():
    """Объединить все messages_*.txt в messages.json"""
    
    base_dir = Path(__file__).parent.parent
    messages_dir = base_dir
    # Сохраняем в оба места для совместимости
    output_file1 = base_dir / "bali_assets" / "messages.json"
    output_file2 = base_dir / "config" / "messages" / "bali" / "messages.json"
    
    # Создаем папки если нужно
    output_file1.parent.mkdir(parents=True, exist_ok=True)
    output_file2.parent.mkdir(parents=True, exist_ok=True)
    
    # Находим все файлы messages_*.txt
    message_files = sorted(messages_dir.glob("messages_*.txt"))
    
    print("=" * 60)
    print("🔄 ОБЪЕДИНЕНИЕ ВСЕХ СООБЩЕНИЙ")
    print("=" * 60)
    print(f"Найдено файлов: {len(message_files)}\n")
    
    all_messages = []
    
    for msg_file in message_files:
        print(f"📄 Обрабатываю: {msg_file.name}")
        
        try:
            with open(msg_file, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f if line.strip()]
            
            # Добавляем сообщения в общий список
            for msg_text in lines:
                if msg_text:  # Пропускаем пустые строки
                    all_messages.append({
                        "text": msg_text,
                        "photo": None,
                        "source_file": msg_file.name  # Для отслеживания источника
                    })
            
            print(f"   ✅ Добавлено {len(lines)} сообщений")
            
        except Exception as e:
            print(f"   ❌ Ошибка при чтении {msg_file.name}: {e}")
    
    # Сохраняем в JSON (в оба места для совместимости)
    try:
        # Сохраняем в оба файла
        for output_file in [output_file1, output_file2]:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(all_messages, f, ensure_ascii=False, indent=2)
        
        print("\n" + "=" * 60)
        print(f"✅ ГОТОВО!")
        print("=" * 60)
        print(f"📊 Всего сообщений: {len(all_messages)}")
        print(f"📁 Файлы сохранены:")
        print(f"   - {output_file1}")
        print(f"   - {output_file2}")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Ошибка при сохранении: {e}")

if __name__ == "__main__":
    merge_all_messages()
