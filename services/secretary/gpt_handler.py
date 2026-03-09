"""
Обработчик GPT-4o-mini для генерации ответов
"""
import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logging.warning("OpenAI library not installed. GPT functionality will be disabled.")

logger = logging.getLogger(__name__)


class GPTHandler:
    """Класс для работы с OpenAI GPT-4o-mini"""
    
    def __init__(self, api_key: Optional[str] = None, niche_config: Optional[Dict] = None):
        """
        Инициализация GPT обработчика
        
        Args:
            api_key: OpenAI API ключ (если None, загружается из переменных окружения)
            niche_config: Конфигурация ниши (если None, загружается из active_niche.json)
        """
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        self.niche_config = niche_config or {}
        self.config = self._load_config_from_niche()
        
        if not OPENAI_AVAILABLE:
            logger.error("❌ OpenAI library not installed. Install with: pip install openai")
            self.client = None
        elif not self.api_key:
            logger.error("❌ OPENAI_API_KEY not found in environment variables")
            self.client = None
        else:
            self.client = AsyncOpenAI(api_key=self.api_key)
            logger.info("✅ GPT Handler initialized")
    
    def _load_config_from_niche(self) -> Dict:
        """Загрузка конфигурации из нишевого конфига"""
        try:
            # Получаем конфигурацию secretary из нишевого конфига
            secretary_config = self.niche_config.get('secretary', {})
            if secretary_config:
                logger.info("✅ Loaded secretary config from niche config")
                return secretary_config
            else:
                logger.warning("⚠️ Secretary config not found in niche config, using defaults")
                return self._get_default_config()
        except Exception as e:
            logger.error(f"❌ Error loading config: {e}, using defaults")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict:
        """Дефолтная конфигурация"""
        return {
            "system_prompt": "Ты — вежливый и дружелюбный помощник. Веди себя как обычный человек, не как бот.",
            "target_action": {
                "main_account": "@MyMainAccount",
                "promotional_message": "Привет! Спасибо за интерес. Для получения подробной информации переходи в наш основной канал: @MyMainAccount."
            },
            "conversation_history_limit": 5,
            "response_style": {
                "be_natural": True,
                "use_emojis": True,
                "max_length": 500
            }
        }
    
    def format_conversation_history(self, messages: List[Dict], new_messages: str = "") -> List[Dict]:
        """
        Форматирование истории переписки для GPT с разделением на историю и новые сообщения
        
        Args:
            messages: Список сообщений в формате [{"role": "user", "content": "..."}, ...]
            new_messages: Текст новых сообщений (из буфера)
        
        Returns:
            Отформатированный список сообщений для GPT
        """
        # Ограничиваем историю
        history_limit = self.config.get('conversation_history_limit', 15)
        recent_messages = messages[-history_limit:] if len(messages) > history_limit else messages
        
        # Добавляем системный промпт в начало
        system_prompt = self.config.get('system_prompt', '')
        formatted = [{"role": "system", "content": system_prompt}]
        
        # Формируем контекст с разделением на историю и новые сообщения
        if recent_messages and new_messages:
            # Форматируем историю без меток «Пользователь»/«Ты», чтобы не выдавать автоответ
            history_text = "\n".join([
                f"{'Я' if msg.get('role') == 'assistant' else 'Собеседник'}: {msg.get('content', '')}"
                for msg in recent_messages
            ])
            
            # Добавляем контекстный промпт с историей и новыми сообщениями
            context_message = f"ИСТОРИЯ ПЕРЕПИСКИ:\n{history_text}\n\nНОВЫЕ СООБЩЕНИЯ:\n{new_messages}"
            formatted.append({"role": "user", "content": context_message})
        elif new_messages:
            # Если нет истории, просто добавляем новые сообщения
            formatted.append({"role": "user", "content": new_messages})
        else:
            # Если только история без новых сообщений
            formatted.extend(recent_messages)
        
        return formatted
    
    def _clean_response_for_sending(self, text: str) -> str:
        """
        Убирает из ответа GPT префиксы «Исполнитель:», «Ты:», «Я:», «Собеседник:»,
        чтобы в чат уходило только одно сообщение от лица бота (клиента).
        """
        if not text or not text.strip():
            return text
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        our_prefixes = ("ты:", "я:", "твой ответ:", "ответ:")
        other_prefixes = ("исполнитель:", "собеседник:", "пользователь:")
        cleaned_lines = []
        for line in lines:
            line_lower = line.lower()
            if any(line_lower.startswith(p) for p in other_prefixes):
                continue
            if any(line_lower.startswith(p) for p in our_prefixes):
                for p in our_prefixes:
                    if line_lower.startswith(p):
                        rest = line[len(p):].strip()
                        if rest:
                            cleaned_lines.append(rest)
                        break
                continue
            cleaned_lines.append(line)
        if cleaned_lines:
            return "\n".join(cleaned_lines).strip()
        # Если модель вернула только реплику «Исполнитель»/«Собеседник» — не отправляем её
        if any(text.strip().lower().startswith(p) for p in ("исполнитель:", "собеседник:", "пользователь:")):
            return "Расскажи, что предлагаешь? Какой формат и цены?"
        return text.strip()
    
    def detect_need_keywords(self, message_text: str) -> bool:
        """
        Определение ключевых слов, указывающих на потребность
        
        Args:
            message_text: Текст входящего сообщения
        
        Returns:
            True если обнаружены ключевые слова потребности
        """
        keywords = self.config.get('target_action', {}).get('keywords_for_detection', [])
        message_lower = message_text.lower()
        
        for keyword in keywords:
            if keyword in message_lower:
                return True
        
        return False
    
    def count_conversation_exchanges(self, conversation_history: List[Dict]) -> int:
        """
        Подсчет обменов сообщениями в диалоге
        
        Args:
            conversation_history: История переписки
        
        Returns:
            Количество обменов (пары вопрос-ответ)
        """
        user_messages = sum(1 for msg in conversation_history if msg.get('role') == 'user')
        return user_messages
    
    async def generate_response(
        self,
        incoming_message: str,
        conversation_history: List[Dict],
        user_info: Optional[Dict] = None
    ) -> str:
        """
        Генерация ответа через GPT-4o-mini с умным предложением бота
        
        Args:
            incoming_message: Текст входящего сообщения
            conversation_history: История переписки
            user_info: Информация о пользователе (опционально)
        
        Returns:
            Сгенерированный ответ
        """
        if not self.client:
            logger.warning("⚠️ GPT client not available, returning default response")
            return self._get_default_response()
        
        try:
            # Форматируем историю переписки с учетом новых сообщений
            formatted_history = self.format_conversation_history(conversation_history, new_messages=incoming_message)
            
            # Определяем контекст для предложения бота
            target_action_config = self.config.get('target_action', {})
            bot_username = target_action_config.get('bot_username', '@Lead_Hunbot')
            min_messages = target_action_config.get('min_messages_before_offer', 2)
            conversation_exchanges = self.count_conversation_exchanges(conversation_history) + 1  # +1 для текущего сообщения
            has_need_keywords = self.detect_need_keywords(incoming_message)
            
            # Генерируем ответ через GPT
            response_style = self.config.get('response_style', {})
            max_length = response_style.get('max_length', 500)
            
            # Системный промпт уже включен в format_conversation_history
            # Дополнительные инструкции минимальны, так как основной промпт уже содержит всю логику
            
            # Вызываем GPT API
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=formatted_history,
                max_tokens=max_length,
                temperature=0.7,
                top_p=0.9
            )
            
            generated_text = response.choices[0].message.content.strip()
            generated_text = self._clean_response_for_sending(generated_text)
            
            # Обрезаем, если слишком длинный
            if len(generated_text) > max_length:
                generated_text = generated_text[:max_length] + "..."
            
            # Логируем контекст
            logger.info(f"  ✅ Generated response ({len(generated_text)} chars, history: {len(conversation_history)} msgs, exchanges: {conversation_exchanges})")
            
            return generated_text
            
        except Exception as e:
            logger.error(f"  ❌ Error generating GPT response: {e}", exc_info=True)
            return self._get_default_response()
    
    def _get_default_response(self) -> str:
        """Получить дефолтный ответ, если GPT недоступен"""
        return "Привет! Спасибо за сообщение. Я сейчас занят, но обязательно отвечу позже! 😊"
    
    def reload_config(self, niche_config: Optional[Dict] = None):
        """Перезагрузка конфигурации (для hot-reload)"""
        if niche_config:
            self.niche_config = niche_config
        self.config = self._load_config_from_niche()
        logger.info("✅ Secretary config reloaded")

