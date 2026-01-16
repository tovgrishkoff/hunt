"""
Загрузчик конфигурации ниш и сообщений
"""
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional

class ConfigLoader:
    """Загрузчик конфигурации"""
    
    def __init__(self, config_dir: str = "/app/config"):
        self.config_dir = Path(config_dir)
    
    def load_active_niche(self) -> Dict[str, Any]:
        """Загрузить активную нишу"""
        active_file = self.config_dir / "active_niche.json"
        
        if not active_file.exists():
            # По умолчанию используем cars
            return {
                "niche": "cars",
                "config_file": str(self.config_dir / "niches" / "cars.json")
            }
        
        with open(active_file, 'r', encoding='utf-8') as f:
            active = json.load(f)
        
        return active
    
    def load_niche_config(self, niche_name: Optional[str] = None) -> Dict[str, Any]:
        """Загрузить конфигурацию ниши"""
        if niche_name is None:
            active = self.load_active_niche()
            niche_name = active.get("niche", "cars")
        
        # Для ukraine_cars используем cars.json (они используют одну конфигурацию)
        if niche_name == 'ukraine_cars':
            niche_name = 'cars'
        
        niche_file = self.config_dir / "niches" / f"{niche_name}.json"
        
        if not niche_file.exists():
            raise FileNotFoundError(f"Niche config not found: {niche_file}")
        
        with open(niche_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
            # Устанавливаем правильное имя ниши для ukraine_cars
            if niche_name == 'cars' and os.getenv('NICHE') == 'ukraine_cars':
                config['name'] = 'ukraine_cars'
            return config
    
    def load_messages(self, niche_name: Optional[str] = None) -> list:
        """Загрузить сообщения для ниши"""
        if niche_name is None:
            active = self.load_active_niche()
            niche_name = active.get("niche", "cars")
        
        # Определяем корень проекта (на хосте или в Docker)
        project_root = self.config_dir.parent
        if not (project_root / "config").exists():
            # Если config_dir = /app/config, то project_root = /app
            # Но если мы на хосте, нужно найти реальный корень
            # Пробуем найти по наличию config/niches
            current_file = Path(__file__)
            if (current_file.parent.parent.parent / "config" / "niches").exists():
                project_root = current_file.parent.parent.parent
        
        # Список возможных путей для поиска messages.json
        possible_paths = [
            # Стандартный путь: config/messages/{niche}/messages.json
            self.config_dir / "messages" / niche_name / "messages.json",
            # Путь для Lexus: lexus_assets/messages.json
            Path("/app/lexus_assets/messages.json"),
            project_root / "lexus_assets" / "messages.json",
            # Путь для Kammora: kammora_assets/messages.json
            Path("/app/kammora_assets/messages.json"),
            project_root / "kammora_assets" / "messages.json",
            # Альтернативные пути
            Path(f"/app/{niche_name}_assets/messages.json"),
            project_root / f"{niche_name}_assets" / "messages.json",
            Path(f"/app/assets/{niche_name}/messages.json"),
            project_root / "assets" / niche_name / "messages.json",
        ]
        
        # Ищем messages.json
        for messages_file in possible_paths:
            if messages_file.exists():
                try:
                    with open(messages_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        # Поддержка разных форматов
                        if isinstance(data, dict):
                            # Если это dict с ключами (uk, ru, en)
                            messages = data.get('uk', data.get('ru', data.get('en', [])))
                            if messages:
                                return messages
                            # Если весь dict - это список сообщений
                            elif isinstance(data, dict) and all(isinstance(v, (dict, str)) for v in data.values()):
                                return list(data.values())
                        elif isinstance(data, list):
                            return data
                except Exception as e:
                    # Пробуем следующий путь
                    continue
        
        # Fallback на текстовые файлы
        text_file_paths = [
            self.config_dir / "messages" / niche_name / "messages.txt",
            Path(f"/app/{niche_name}_assets/messages.txt"),
            Path("/app/lexus_assets/messages.txt"),
            Path("/app/kammora_assets/messages.txt"),
        ]
        
        for text_file in text_file_paths:
            if text_file.exists():
                try:
                    with open(text_file, 'r', encoding='utf-8') as f:
                        return [line.strip() for line in f if line.strip()]
                except Exception:
                    continue
        
        return []
    
    def switch_niche(self, niche_name: str):
        """Переключить активную нишу"""
        niche_file = self.config_dir / "niches" / f"{niche_name}.json"
        
        if not niche_file.exists():
            raise FileNotFoundError(f"Niche config not found: {niche_file}")
        
        active_file = self.config_dir / "active_niche.json"
        with open(active_file, 'w', encoding='utf-8') as f:
            json.dump({
                "niche": niche_name,
                "config_file": str(niche_file)
            }, f, indent=2, ensure_ascii=False)

