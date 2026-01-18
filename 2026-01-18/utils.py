import json
import re
from typing import List, Dict, Optional

def load_config() -> Dict:
    """Загружает конфигурацию из файла config.json"""
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"disallow_keywords": [], "disallow_users": {}, "use_trello": False}

def is_message_allowed(message_text: str, username: Optional[str] = None) -> bool:
    """
    Проверяет, разрешено ли сообщение согласно правилам исключений.
    
    Args:
        message_text: Текст сообщения для проверки
        username: Username отправителя (опционально)
    
    Returns:
        bool: True если сообщение разрешено, False если оно должно быть отфильтровано
    """
    config = load_config()
    
    # Проверка на заблокированных пользователей
    if username and username in config["disallow_users"]:
        return False
    
    # Проверка на запрещенные ключевые слова
    for pattern in config["disallow_keywords"]:
        if re.search(pattern, message_text, re.IGNORECASE):
            return False
    
    return True 