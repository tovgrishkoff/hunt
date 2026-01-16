import random
import json
import re
from pathlib import Path
from datetime import datetime

class MessageVariationsGenerator:
    def __init__(self):
        self.greetings = [
            "Привет!", "Всем привет!", "Доброе утро!", "Добрый день!", "Добрый вечер!",
            "Привет всем!", "Всем доброго дня!", "Приветики!", "Хай!", "Салют!",
            "Доброго времени суток!", "Приветствую!", "Здравствуйте!", "Добро пожаловать!"
        ]
        
        self.attention_grabbers = [
            "Кто знает", "Подскажите", "Помогите", "Нужна помощь", "Ищу",
            "Кто может посоветовать", "Кто пользовался", "Кто снимал", "Кто делал",
            "Ребят, кто знает", "Всем, кто знает", "Кто может помочь", "Кто подскажет"
        ]
        
        self.locations = [
            "на Бали", "в Семиньяке", "в Убуде", "в Чангу", "в Куте", "в Денпасаре",
            "в Сануре", "в Нуса-Дуа", "в Джимбаране", "в Танах-Лоте", "в Улувату",
            "в Чангу", "в Переренане", "в Амеде", "в Ловине", "в Мундуке"
        ]
        
        self.quality_indicators = [
            "хорошего", "качественного", "профессионального", "опытного", "проверенного",
            "надежного", "крутого", "топового", "лучшего", "отличного", "супер",
            "классного", "замечательного", "превосходного", "идеального"
        ]
        
        self.service_types = [
            "специалиста", "мастера", "профессионала", "эксперта", "исполнителя",
            "работника", "сотрудника", "представителя", "агента", "консультанта"
        ]
        
        self.emojis = {
            'photo': ['📸', '📷', '🖼️', '✨', '🌟'],
            'video': ['🎥', '📹', '🎬', '✨', '🌟'],
            'hair': ['💇‍♀️', '💇‍♂️', '✨', '🌟'],
            'makeup': ['💄', '💋', '✨', '🌟'],
            'manicure': ['💅', '✨', '🌟'],
            'eyebrows': ['👁️', '✨', '🌟'],
            'eyelashes': ['👁️', '✨', '🌟'],
            'transport': ['🚐', '🚗', '🏍️', '✨', '🌟'],
            'housing': ['🏠', '🏘️', '✨', '🌟'],
            'tourism': ['🏝️', '🌴', '✨', '🌟'],
            'designer': ['🎨', '✨', '🌟'],
            'cosmetology': ['💆‍♀️', '✨', '🌟'],
            'hookah': ['🚬', '✨', '🌟'],
            'playstation': ['🎮', '✨', '🌟'],
            'currency': ['💱', '💰', '✨', '🌟'],
            'general': ['✨', '🌟', '💫', '⭐']
        }
        
        self.specific_requests = [
            "для фотосессии", "для съемки", "для мероприятия", "для вечеринки",
            "для свадьбы", "для дня рождения", "для девичника", "для мальчишника",
            "для корпоратива", "для бизнеса", "для рекламы", "для соцсетей",
            "для Instagram", "для блога", "для YouTube", "для TikTok",
            "для travel-съемки", "для fashion-съемки", "для портретной съемки",
            "для коммерческой съемки", "для студийной съемки", "для пляжной съемки",
            "для водной съемки", "для съемки на закате", "для романтической съемки",
            "для семейной съемки", "для детской съемки", "для свадебной съемки",
            "для рекламного ролика", "для клипа", "для фильма", "для сериала",
            "с опытом работы", "с портфолио", "с хорошими отзывами", "с гарантией",
            "с современным оборудованием", "с креативным подходом", "с индивидуальным подходом",
            "с хорошими ценами", "с быстрым результатом", "с качественным результатом",
            "с русскоязычным персоналом", "с пониманием", "с доставкой", "с установкой"
        ]
        
        self.urgency_indicators = [
            "срочно", "быстро", "немедленно", "сегодня", "завтра", "на этой неделе",
            "в ближайшее время", "как можно скорее", "в приоритете", "важно"
        ]
        
        self.personal_touches = [
            "Хочу качественный результат", "Нужен профессиональный подход",
            "Важно качество", "Хочу крутой результат", "Нужен опытный специалист",
            "Хочу элегантный результат", "Нужен креативный подход", "Хочу современный стиль",
            "Нужен индивидуальный подход", "Хочу лучший результат", "Нужен топовый специалист",
            "Хочу супер результат", "Нужен классный подход", "Хочу замечательный результат",
            "Нужен превосходный специалист", "Хочу идеальный результат"
        ]

    def generate_variation(self, base_message, niche='general'):
        """Генерация вариации сообщения"""
        # Извлекаем основную информацию из базового сообщения
        words = base_message.split()
        
        # Определяем тип услуги
        service_type = self.detect_service_type(base_message)
        
        # Создаем вариацию
        variation_parts = []
        
        # Приветствие
        greeting = random.choice(self.greetings)
        variation_parts.append(greeting)
        
        # Внимание
        attention = random.choice(self.attention_grabbers)
        variation_parts.append(attention)
        
        # Качество
        quality = random.choice(self.quality_indicators)
        variation_parts.append(quality)
        
        # Тип услуги
        if service_type:
            variation_parts.append(service_type)
        
        # Локация
        location = random.choice(self.locations)
        variation_parts.append(location)
        
        # Специфический запрос
        if random.random() < 0.7:  # 70% шанс добавить специфический запрос
            specific_request = random.choice(self.specific_requests)
            variation_parts.append(specific_request)
        
        # Персональный оттенок
        if random.random() < 0.5:  # 50% шанс добавить персональный оттенок
            personal_touch = random.choice(self.personal_touches)
            variation_parts.append(personal_touch)
        
        # Эмодзи
        emoji = random.choice(self.emojis.get(niche, self.emojis['general']))
        variation_parts.append(emoji)
        
        # Собираем сообщение
        variation = " ".join(variation_parts)
        
        # Добавляем знаки препинания
        if not variation.endswith(('!', '?', '.')):
            variation += "!"
            
        return variation

    def detect_service_type(self, message):
        """Определение типа услуги из сообщения"""
        message_lower = message.lower()
        
        if any(word in message_lower for word in ['фотограф', 'фото', 'съемк']):
            return 'фотографа'
        elif any(word in message_lower for word in ['видеограф', 'видео', 'съемк']):
            return 'видеографа'
        elif any(word in message_lower for word in ['маникюр', 'ногт']):
            return 'мастера маникюра'
        elif any(word in message_lower for word in ['волос', 'прическ']):
            return 'мастера по волосам'
        elif any(word in message_lower for word in ['макияж', 'макияж']):
            return 'визажиста'
        elif any(word in message_lower for word in ['брови', 'бров']):
            return 'мастера по бровям'
        elif any(word in message_lower for word in ['ресниц', 'ресниц']):
            return 'мастера по ресницам'
        elif any(word in message_lower for word in ['транспорт', 'трансфер']):
            return 'транспортную компанию'
        elif any(word in message_lower for word in ['недвижимость', 'риелтор']):
            return 'риелтора'
        elif any(word in message_lower for word in ['туризм', 'гид']):
            return 'туроператора'
        elif any(word in message_lower for word in ['дизайн', 'дизайнер']):
            return 'дизайнера'
        elif any(word in message_lower for word in ['косметолог', 'косметологи']):
            return 'косметолога'
        elif any(word in message_lower for word in ['кальян', 'hookah']):
            return 'кальянную'
        elif any(word in message_lower for word in ['playstation', 'приставк']):
            return 'аренду Playstation'
        elif any(word in message_lower for word in ['валюта', 'обмен']):
            return 'обменник валют'
        else:
            return 'специалиста'

    def generate_multiple_variations(self, base_message, count=10, niche='general'):
        """Генерация множественных вариаций"""
        variations = []
        for _ in range(count):
            variation = self.generate_variation(base_message, niche)
            if variation not in variations:  # Избегаем дубликатов
                variations.append(variation)
        return variations

    def enhance_existing_messages(self, file_path, niche='general', add_count=20):
        """Улучшение существующих сообщений в файле"""
        path = Path(file_path)
        if not path.exists():
            print(f"File {file_path} not found")
            return
            
        # Читаем существующие сообщения
        with path.open('r', encoding='utf-8') as f:
            lines = [line.strip() for line in f.readlines()]
        
        existing_messages = [line for line in lines if line]
        
        # Генерируем новые вариации
        new_messages = []
        for base_message in existing_messages[:5]:  # Берем первые 5 как основу
            variations = self.generate_multiple_variations(base_message, add_count // 5, niche)
            new_messages.extend(variations)
        
        # Добавляем случайные комбинации
        for _ in range(add_count // 2):
            random_message = self.generate_variation("", niche)
            new_messages.append(random_message)
        
        # Объединяем и убираем дубликаты
        all_messages = existing_messages + new_messages
        unique_messages = list(dict.fromkeys(all_messages))  # Сохраняем порядок
        
        # Записываем обратно
        with path.open('w', encoding='utf-8') as f:
            for message in unique_messages:
                f.write(message + '\n\n')
        
        print(f"Enhanced {file_path}: {len(existing_messages)} -> {len(unique_messages)} messages")

    def create_anti_detection_variations(self, base_message, niche='general'):
        """Создание вариаций для анти-детекции"""
        variations = []
        
        # Разные стили написания
        styles = [
            self.generate_variation(base_message, niche),
            self.generate_variation(base_message, niche),
            self.generate_variation(base_message, niche),
        ]
        
        # Добавляем случайные элементы
        for style in styles:
            # Случайные опечатки (редко)
            if random.random() < 0.1:
                style = self.add_typo(style)
            
            # Случайные сокращения
            if random.random() < 0.2:
                style = self.add_abbreviation(style)
            
            variations.append(style)
        
        return variations

    def add_typo(self, message):
        """Добавление случайной опечатки"""
        if len(message) < 10:
            return message
            
        # Простые опечатки
        typos = {
            'о': 'а', 'а': 'о', 'е': 'и', 'и': 'е',
            'т': 'д', 'д': 'т', 'п': 'б', 'б': 'п'
        }
        
        words = message.split()
        if words:
            word_idx = random.randint(0, len(words) - 1)
            word = words[word_idx]
            if len(word) > 3:
                char_idx = random.randint(1, len(word) - 2)
                char = word[char_idx]
                if char in typos:
                    word = word[:char_idx] + typos[char] + word[char_idx + 1:]
                    words[word_idx] = word
                    return ' '.join(words)
        
        return message

    def add_abbreviation(self, message):
        """Добавление сокращений"""
        abbreviations = {
            'на Бали': 'на Бали',
            'для фотосессии': 'для фото',
            'для видеосъемки': 'для видео',
            'профессионального': 'проф',
            'качественного': 'кач',
            'опытного': 'опыт'
        }
        
        for full, short in abbreviations.items():
            if full in message and random.random() < 0.3:
                message = message.replace(full, short)
                break
        
        return message

    def generate_time_based_variations(self, base_message, niche='general'):
        """Генерация вариаций в зависимости от времени"""
        now = datetime.now()
        hour = now.hour
        
        time_greetings = {
            'morning': ['Доброе утро!', 'С добрым утром!', 'Утренний привет!'],
            'day': ['Добрый день!', 'Доброго дня!', 'Дневной привет!'],
            'evening': ['Добрый вечер!', 'Вечерний привет!', 'Спокойного вечера!'],
            'night': ['Доброй ночи!', 'Ночной привет!', 'Поздний привет!']
        }
        
        if 6 <= hour < 12:
            time_period = 'morning'
        elif 12 <= hour < 18:
            time_period = 'day'
        elif 18 <= hour < 22:
            time_period = 'evening'
        else:
            time_period = 'night'
        
        greeting = random.choice(time_greetings[time_period])
        variation = self.generate_variation(base_message, niche)
        
        # Заменяем приветствие на временное
        words = variation.split()
        if words and words[0].endswith('!'):
            words[0] = greeting
            variation = ' '.join(words)
        
        return variation

def main():
    """Основная функция для тестирования"""
    generator = MessageVariationsGenerator()
    
    # Тестируем генерацию вариаций
    base_message = "Ищу хорошего фотографа на Бали для свадебной съемки"
    
    print("=== Генерация вариаций ===")
    variations = generator.generate_multiple_variations(base_message, 10, 'photo')
    for i, variation in enumerate(variations, 1):
        print(f"{i}. {variation}")
    
    print("\n=== Временные вариации ===")
    time_variations = []
    for _ in range(5):
        time_var = generator.generate_time_based_variations(base_message, 'photo')
        time_variations.append(time_var)
    
    for i, variation in enumerate(time_variations, 1):
        print(f"{i}. {variation}")
    
    print("\n=== Анти-детекция вариации ===")
    anti_detection = generator.create_anti_detection_variations(base_message, 'photo')
    for i, variation in enumerate(anti_detection, 1):
        print(f"{i}. {variation}")

if __name__ == "__main__":
    main()
