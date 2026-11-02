import openai
import json
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import hashlib
import sqlite3
import os

logger = logging.getLogger(__name__)

class AIClassifier:
    def __init__(self, api_key: str, cache_duration: int = 3600):
        """
        Инициализация AI классификатора с системой обучения
        
        Args:
            api_key: OpenAI API ключ
            cache_duration: Время кэширования результатов в секундах (по умолчанию 1 час)
        """
        self.api_key = api_key
        self.cache_duration = cache_duration
        self.cache: Dict[str, Tuple[Dict, datetime]] = {}
        
        # Настройка OpenAI
        openai.api_key = api_key
        
        # Доступные ниши для классификации
        self.available_niches = [
            "Фотограф",
            "Видеограф",
            "Недвижимость (Спрос)",
            "Недвижимость (Предложение)",
            "Маникюр",
            "Волосы",
            "Аренда авто",
            "Реснички",
            "Брови",
            "Макияж",
            "Косметология",
            "Продажа недвижимости",
            "Аренда байков",
            "Обмен валют",
            "Кальяны",
            "Аренда Playstation",
            "Медиа-студия",
            "Туризм",
            "Транспорт",
        ]
        
        # Инициализация базы данных для обучения
        self._init_learning_db()

    def _init_learning_db(self):
        """Инициализация базы данных для хранения обучающих данных"""
        self.learning_db_path = "ai_learning.db"
        
        # Создаем таблицы если их нет
        with sqlite3.connect(self.learning_db_path) as conn:
            cursor = conn.cursor()
            
            # Таблица для хранения примеров классификации
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS classification_examples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_text TEXT NOT NULL,
                    original_classification TEXT,
                    corrected_classification TEXT,
                    is_corrected BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица для хранения статистики точности
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS accuracy_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    total_classifications INTEGER DEFAULT 0,
                    correct_classifications INTEGER DEFAULT 0,
                    accuracy_rate REAL DEFAULT 0.0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()

    def _create_message_hash(self, message_text: str) -> str:
        """Создает хеш сообщения для кэширования"""
        normalized_text = ' '.join(message_text.lower().split())
        return hashlib.md5(normalized_text.encode('utf-8')).hexdigest()

    def _is_cache_valid(self, message_hash: str) -> bool:
        """Проверяет, действителен ли кэш для сообщения"""
        if message_hash not in self.cache:
            return False
        
        cached_result, timestamp = self.cache[message_hash]
        return (datetime.now() - timestamp).total_seconds() < self.cache_duration

    def _get_cached_result(self, message_hash: str) -> Optional[Dict]:
        """Получает результат из кэша"""
        if self._is_cache_valid(message_hash):
            result, _ = self.cache[message_hash]
            logger.info(f"📋 Использован кэшированный результат для сообщения")
            return result
        return None

    def _cache_result(self, message_hash: str, result: Dict):
        """Сохраняет результат в кэш"""
        self.cache[message_hash] = (result, datetime.now())
        
        # Очистка старых записей кэша
        current_time = datetime.now()
        expired_hashes = []
        for hash_key, (_, timestamp) in self.cache.items():
            if (current_time - timestamp).total_seconds() > self.cache_duration:
                expired_hashes.append(hash_key)
        
        for hash_key in expired_hashes:
            del self.cache[hash_key]

    def _create_enhanced_prompt(self, message_text: str) -> str:
        """Создает краткий оптимизированный промпт для классификации"""
        return f"""
Ты - эксперт по классификации сообщений в Telegram.
Твоя задача: определить, относится ли сообщение к одной из ниш списка, и выявить тип (ПОИСК, ПРЕДЛОЖЕНИЕ, ОБЩЕНИЕ, СПАМ).

СПИСОК НИШ:
{', '.join(self.available_niches)}

ПРАВИЛА КЛАССИФИКАЦИИ:
1. **ТОЧНОСТЬ:** Выбирай нишу, только если уверен. Если сообщение не подходит ни под одну нишу (например, продажа телефона, одежды, билетов) — ставь niches: [] и тип "ОБЩЕНИЕ".
2. **НЕДВИЖИМОСТЬ:**
   - "Недвижимость (Спрос)" = ищут жильё в аренду (сниму/ищу квартиру/виллу).
   - "Недвижимость (Предложение)" = сдают жильё (сдам/сдается/посуточно).
   - "Продажа недвижимости" = только покупка/продажа жилья/земли (не аренда).
   - Обмен валют и поиск соседей без жилья — это НЕ недвижимость.
   - Барахолка / «продам по N лир», «нижний/верхний ряд», мелкие цены в лирах без слов квартира/вилла/дом — это НЕ недвижимость (личная вещь), niches: [].
3. **СПАМ:** Любые предложения "легкого заработка", "обнала", "удаленной работы на WB", "баз данных", "восстановления аккаунтов" — это СПАМ.
   - «Приму у себя», «без предоплат» + 🔞 / знакомства — эскорт/порно, НЕ недвижимость: is_spam=true, niches: [].
4. **ТИП СООБЩЕНИЯ:**
   - ПОИСК: Автор ищет услугу/товар (готов платить).
   - ПРЕДЛОЖЕНИЕ: Автор предлагает услугу/товар.
   - ОБЩЕНИЕ: Вопросы, обсуждения, продажа личных вещей (не профильных).

ТВОЙ ОТВЕТ ДОЛЖЕН БЫТЬ СТРОГИМ JSON:
{{
    "message_type": "ПОИСК|ПРЕДЛОЖЕНИЕ|ОБЩЕНИЕ|СПАМ",
    "is_spam": true/false,
    "niches": ["Название ниши" или пусто],
    "confidence": 0-100,
    "reason": "Краткая причина",
    "context": "",
    "urgency": "не срочно",
    "budget": ""
}}

Сообщение для анализа: "{message_text}"
"""
    async def classify_message(self, message_text: str) -> Dict:
        """
        Классифицирует сообщение с помощью ChatGPT с улучшенным промптом
        
        Returns:
            Dict с полями:
            - message_type: str - тип сообщения
            - is_spam: bool - является ли спамом
            - niches: List[str] - найденные ниши
            - context: str - контекст потребности
            - urgency: str - срочность
            - budget: str - бюджет
            - confidence: float - уверенность в классификации
            - reason: str - причина классификации
        """
        # ✂️ ВАЖНАЯ ПРАВКА: Обрезаем текст ДО создания промпта
        # 800 символов (~200 токенов) достаточно для понимания сути
        # Это страховка от длинных лонгридов и пересылок
        truncated_text = message_text[:800]
        
        message_hash = self._create_message_hash(truncated_text)  # Используем обрезанный текст для хеша
        
        # Проверяем кэш
        cached_result = self._get_cached_result(message_hash)
        if cached_result:
            return cached_result

        try:
            # Используем улучшенный промпт с обрезанным текстом
            prompt = self._create_enhanced_prompt(truncated_text)

            # Отправляем запрос к ChatGPT
            # 🔄 СМЕНА МОДЕЛИ на gpt-4o-mini - цена упадет в 3-4 раза
            client = openai.OpenAI(api_key=self.api_key)
            # 🚫 Отключение истории - messages создается заново для каждого вызова (правильно)
            messages = [
                {"role": "system", "content": "Ты - эксперт по анализу сообщений в Telegram. Анализируй объективно и точно. Всегда отвечай в формате JSON."},
                {"role": "user", "content": prompt}
            ]
            
            # Логирование перед отправкой запроса для отладки
            model_name = "gpt-4o-mini"
            logger.info(f"🚀 ОТПРАВЛЯЮ ЗАПРОС. МОДЕЛЬ: {model_name}")
            print(f"🚀 ОТПРАВЛЯЮ ЗАПРОС. МОДЕЛЬ: {model_name}")
            
            response = client.chat.completions.create(
                model=model_name,  # Заменено с gpt-3.5-turbo-0125 для экономии 3-4x
                messages=messages,  # Создается заново каждый раз - история не накапливается
                max_tokens=300,
                temperature=0.1
            )

            # Парсим ответ
            response_text = response.choices[0].message.content.strip()
            
            # Извлекаем JSON из ответа
            if response_text.startswith('```json'):
                response_text = response_text[7:-3]
            elif response_text.startswith('```'):
                response_text = response_text[3:-3]
            
            result = json.loads(response_text)
            
            # Валидация и нормализация результата
            result = self._validate_and_normalize_result(result)
            
            # Кэшируем результат
            self._cache_result(message_hash, result)
            
            # Сохраняем пример для обучения
            self._save_classification_example(message_text, result)
            
            logger.info(f"🤖 AI классификация: тип={result.get('message_type')}, спам={result.get('is_spam')}, ниши={result.get('niches')}, уверенность={result.get('confidence')}%")
            
            return result

        except Exception as e:
            error_str = str(e).lower()
            logger.error(f"❌ Ошибка AI классификации: {e}")
            
            # Проверяем, является ли это критической ошибкой API (недоступность, неверный ключ и т.д.)
            is_critical_api_error = any(keyword in error_str for keyword in [
                'api', 'authentication', 'unauthorized', 'invalid', 'key', 'quota', 
                'rate limit', 'connection', 'timeout', 'network', 'unreachable'
            ])
            
            if is_critical_api_error:
                logger.warning(f"⚠️ КРИТИЧЕСКАЯ ошибка API OpenAI: {e}. AI классификатор недоступен.")
                # Возвращаем специальный результат, который указывает на недоступность AI
                default_result = {
                    "message_type": "ОБЩЕНИЕ",
                    "is_spam": False,
                    "niches": [],
                    "context": "",
                    "urgency": "не срочно",
                    "budget": "",
                    "confidence": 0,  # Нулевая уверенность = AI недоступен
                    "reason": f"AI API недоступен: {str(e)[:100]}",
                    "ai_unavailable": True  # Флаг недоступности AI
                }
            else:
                # Для других ошибок (парсинг, валидация) возвращаем обычный результат
                default_result = {
                    "message_type": "ОБЩЕНИЕ",
                    "is_spam": False,
                    "niches": [],
                    "context": "",
                    "urgency": "не срочно",
                    "budget": "",
                    "confidence": 50,
                    "reason": f"Ошибка AI классификации: {str(e)[:100]}",
                    "ai_unavailable": False
                }
            
            # НЕ кэшируем результат при ошибке, чтобы при следующем запросе попробовать снова
            return default_result

    def _validate_and_normalize_result(self, result: Dict) -> Dict:
        """Валидирует и нормализует результат классификации"""
        # Проверяем обязательные поля
        if not isinstance(result.get('message_type'), str):
            result['message_type'] = 'ОБЩЕНИЕ'
        
        if not isinstance(result.get('is_spam'), bool):
            result['is_spam'] = False
        
        if not isinstance(result.get('niches'), list):
            result['niches'] = []
        
        if not isinstance(result.get('context'), str):
            result['context'] = ""
        
        if not isinstance(result.get('urgency'), str):
            result['urgency'] = "не срочно"
        
        if not isinstance(result.get('budget'), str):
            result['budget'] = ""
        
        if not isinstance(result.get('confidence'), (int, float)):
            result['confidence'] = 50
        
        if not isinstance(result.get('reason'), str):
            result['reason'] = "Классификация выполнена"
        
        # Нормализуем ниши (приводим к стандартному виду)
        normalized_niches = []
        for niche in result.get('niches', []):
            if niche in self.available_niches:
                normalized_niches.append(niche)
        result['niches'] = normalized_niches
        
        return result

    def _save_classification_example(self, message_text: str, classification: Dict):
        """Сохраняет пример классификации для обучения"""
        try:
            with sqlite3.connect(self.learning_db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO classification_examples 
                    (message_text, original_classification) 
                    VALUES (?, ?)
                ''', (message_text, json.dumps(classification, ensure_ascii=False)))
                conn.commit()
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения примера классификации: {e}")

    def correct_classification(self, message_text: str, corrected_result: Dict):
        """
        Корректирует классификацию и сохраняет для обучения
        
        Args:
            message_text: исходный текст сообщения
            corrected_result: исправленная классификация
        """
        try:
            with sqlite3.connect(self.learning_db_path) as conn:
                cursor = conn.cursor()
                
                # Ищем последний пример с таким текстом
                cursor.execute('''
                    SELECT id, original_classification 
                    FROM classification_examples 
                    WHERE message_text = ? 
                    ORDER BY created_at DESC 
                    LIMIT 1
                ''', (message_text,))
                
                row = cursor.fetchone()
                if row:
                    example_id, original_classification = row
                    
                    # Обновляем запись с исправлением
                    cursor.execute('''
                        UPDATE classification_examples 
                        SET corrected_classification = ?, is_corrected = TRUE 
                        WHERE id = ?
                    ''', (json.dumps(corrected_result, ensure_ascii=False), example_id))
                    
                    conn.commit()
                    logger.info(f"✅ Классификация исправлена и сохранена для обучения")
                    
                    # Обновляем статистику точности
                    self._update_accuracy_stats()
                else:
                    logger.warning(f"⚠️ Пример классификации не найден для исправления")
                    
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения исправления: {e}")

    def _update_accuracy_stats(self):
        """Обновляет статистику точности классификации"""
        try:
            with sqlite3.connect(self.learning_db_path) as conn:
                cursor = conn.cursor()
                
                # Подсчитываем статистику
                cursor.execute('''
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN is_corrected = FALSE THEN 1 ELSE 0 END) as correct
                    FROM classification_examples
                ''')
                
                row = cursor.fetchone()
                if row:
                    total, correct = row
                    accuracy = (correct / total * 100) if total > 0 else 0
                    
                    # Обновляем статистику
                    cursor.execute('''
                        INSERT OR REPLACE INTO accuracy_stats 
                        (id, total_classifications, correct_classifications, accuracy_rate, updated_at)
                        VALUES (1, ?, ?, ?, CURRENT_TIMESTAMP)
                    ''', (total, correct, accuracy))
                    
                    conn.commit()
                    logger.info(f"📊 Статистика точности обновлена: {accuracy:.1f}%")
                    
        except Exception as e:
            logger.error(f"❌ Ошибка обновления статистики: {e}")

    def get_learning_stats(self) -> Dict:
        """Возвращает статистику обучения"""
        try:
            with sqlite3.connect(self.learning_db_path) as conn:
                cursor = conn.cursor()
                
                # Получаем общую статистику
                cursor.execute('SELECT * FROM accuracy_stats WHERE id = 1')
                accuracy_row = cursor.fetchone()
                
                # Получаем количество исправлений
                cursor.execute('SELECT COUNT(*) FROM classification_examples WHERE is_corrected = TRUE')
                corrections_count = cursor.fetchone()[0]
                
                # Получаем общее количество примеров
                cursor.execute('SELECT COUNT(*) FROM classification_examples')
                total_examples = cursor.fetchone()[0]
                
                return {
                    "total_examples": total_examples,
                    "corrections_count": corrections_count,
                    "accuracy_rate": accuracy_row[3] if accuracy_row else 0,
                    "total_classifications": accuracy_row[1] if accuracy_row else 0,
                    "correct_classifications": accuracy_row[2] if accuracy_row else 0
                }
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики обучения: {e}")
            return {}

    def get_cache_stats(self) -> Dict:
        """Возвращает статистику кэша"""
        return {
            "cache_size": len(self.cache),
            "cache_duration": self.cache_duration,
            "total_cached_results": len(self.cache)
        }

    def clear_cache(self):
        """Очищает кэш"""
        self.cache.clear()
        logger.info("🧹 Кэш AI классификатора очищен")

    def export_learning_data(self, filename: str = "ai_learning_export.json"):
        """Экспортирует данные обучения в JSON файл"""
        try:
            with sqlite3.connect(self.learning_db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT message_text, original_classification, corrected_classification, is_corrected, created_at
                    FROM classification_examples
                    ORDER BY created_at DESC
                ''')
                
                data = []
                for row in cursor.fetchall():
                    data.append({
                        "message_text": row[0],
                        "original_classification": json.loads(row[1]) if row[1] else None,
                        "corrected_classification": json.loads(row[2]) if row[2] else None,
                        "is_corrected": bool(row[3]),
                        "created_at": row[4]
                    })
                
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                
                logger.info(f"📤 Данные обучения экспортированы в {filename}")
                
        except Exception as e:
            logger.error(f"❌ Ошибка экспорта данных обучения: {e}") 