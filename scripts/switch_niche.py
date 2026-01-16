#!/usr/bin/env python3
"""
Скрипт переключения активной ниши
Обновляет active_niche.json и перезапускает все сервисы
"""
import sys
import json
import subprocess
from pathlib import Path


def switch_niche(niche_name: str, project_root: Path = None):
    """
    Переключить активную нишу
    
    Args:
        niche_name: Название ниши (например, 'cars' или 'real_estate')
        project_root: Корневая директория проекта
    """
    if project_root is None:
        project_root = Path(__file__).parent.parent
    
    config_dir = project_root / "config"
    niches_dir = config_dir / "niches"
    active_niche_file = config_dir / "active_niche.json"
    niche_file = niches_dir / f"{niche_name}.json"
    
    # Проверяем, существует ли файл ниши
    if not niche_file.exists():
        print(f"❌ Ошибка: файл конфигурации ниши не найден: {niche_file}")
        print(f"   Доступные ниши: {', '.join([f.stem for f in niches_dir.glob('*.json')])}")
        sys.exit(1)
    
    # Загружаем конфигурацию ниши для проверки
    try:
        with open(niche_file, 'r', encoding='utf-8') as f:
            niche_config = json.load(f)
        display_name = niche_config.get('display_name', niche_name)
    except Exception as e:
        print(f"❌ Ошибка при чтении конфигурации ниши: {e}")
        sys.exit(1)
    
    # Обновляем active_niche.json
    try:
        active_config = {
            "niche": niche_name,
            "config_file": str(niche_file.relative_to(project_root))
        }
        
        with open(active_niche_file, 'w', encoding='utf-8') as f:
            json.dump(active_config, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Активная ниша обновлена: {display_name} ({niche_name})")
        print(f"   Файл: {active_niche_file}")
        
    except Exception as e:
        print(f"❌ Ошибка при обновлении active_niche.json: {e}")
        sys.exit(1)
    
    # Перезапускаем все сервисы
    services = ['account-manager', 'marketer', 'activity', 'secretary']
    
    print(f"\n🔄 Перезапуск сервисов...")
    
    for service in services:
        try:
            # Останавливаем сервис
            result = subprocess.run(
                ['docker-compose', '-f', str(project_root / 'docker-compose.yml'), 'stop', service],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0 and 'No such service' not in result.stderr:
                print(f"  ⚠️ Предупреждение при остановке {service}: {result.stderr.strip()}")
            
            # Запускаем сервис
            result = subprocess.run(
                ['docker-compose', '-f', str(project_root / 'docker-compose.yml'), 'up', '-d', service],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                print(f"  ✅ {service} перезапущен")
            else:
                print(f"  ⚠️ Ошибка при запуске {service}: {result.stderr.strip()}")
                
        except subprocess.TimeoutExpired:
            print(f"  ⚠️ Таймаут при перезапуске {service}")
        except Exception as e:
            print(f"  ⚠️ Ошибка при перезапуске {service}: {e}")
    
    print(f"\n✅ Переключение ниши завершено!")
    print(f"   Активная ниша: {display_name} ({niche_name})")
    print(f"   Все сервисы перезапущены и загружают новую конфигурацию")


def main():
    """Основная функция"""
    if len(sys.argv) < 2:
        print("Использование: python switch_niche.py <niche_name>")
        print("\nПримеры:")
        print("  python switch_niche.py cars")
        print("  python switch_niche.py real_estate")
        sys.exit(1)
    
    niche_name = sys.argv[1]
    
    # Определяем корневую директорию проекта
    script_path = Path(__file__).resolve()
    project_root = script_path.parent.parent
    
    print("=" * 80)
    print("🔄 ПЕРЕКЛЮЧЕНИЕ НИШИ")
    print("=" * 80)
    print(f"Ниша: {niche_name}")
    print(f"Проект: {project_root}")
    print("=" * 80)
    print()
    
    try:
        switch_niche(niche_name, project_root)
    except KeyboardInterrupt:
        print("\n🛑 Прервано пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
