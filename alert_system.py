#!/usr/bin/env python3
"""
Система алертов для уведомления администратора о проблемах
"""

import asyncio
import logging
from datetime import datetime, timedelta
from telethon import TelegramClient
from telethon.sessions import StringSession

class AlertSystem:
    def __init__(self, admin_id: int = 210147380):
        """
        Инициализация системы алертов
        
        Args:
            admin_id: Telegram ID администратора для уведомлений
        """
        self.admin_id = admin_id
        self.alert_client = None
        self.last_alerts = {}  # Для предотвращения спама
        self.alert_cooldown = timedelta(minutes=30)  # Не чаще раза в 30 минут для одного типа
        self.logger = logging.getLogger(__name__)
        
    async def initialize(self, api_id: int, api_hash: str, string_session: str = None, session_name: str = "alert_bot"):
        """Инициализация клиента для отправки алертов"""
        try:
            if string_session:
                self.alert_client = TelegramClient(
                    StringSession(string_session),
                    api_id,
                    api_hash
                )
            else:
                self.alert_client = TelegramClient(
                    f"sessions/{session_name}",
                    api_id,
                    api_hash
                )
            
            await self.alert_client.start()
            
            if await self.alert_client.is_user_authorized():
                self.logger.info("✅ Alert system initialized")
                return True
            else:
                self.logger.error("❌ Alert client not authorized")
                return False
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize alert system: {e}")
            return False
    
    def _can_send_alert(self, alert_type: str) -> bool:
        """Проверка, можно ли отправить алерт (защита от спама)"""
        now = datetime.now()
        
        if alert_type not in self.last_alerts:
            return True
        
        last_alert_time = self.last_alerts[alert_type]
        if now - last_alert_time >= self.alert_cooldown:
            return True
        
        return False
    
    async def send_alert(self, alert_type: str, message: str, force: bool = False):
        """
        Отправка алерта администратору
        
        Args:
            alert_type: Тип алерта (для cooldown)
            message: Текст сообщения
            force: Игнорировать cooldown
        """
        if not self.alert_client:
            self.logger.warning("Alert system not initialized, cannot send alert")
            return False
        
        if not force and not self._can_send_alert(alert_type):
            self.logger.info(f"Alert {alert_type} skipped due to cooldown")
            return False
        
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            full_message = f"🚨 **ALERT** [{timestamp}]\n\n{message}\n\n🔧 Type: `{alert_type}`"
            
            await self.alert_client.send_message(self.admin_id, full_message)
            self.last_alerts[alert_type] = datetime.now()
            self.logger.info(f"✅ Alert sent: {alert_type}")
            return True
        except Exception as e:
            self.logger.error(f"❌ Failed to send alert: {e}")
            return False
    
    async def alert_no_clients(self):
        """Алерт: нет доступных клиентов"""
        message = """
❌ **Система постинга не работает**

**Проблема:** Нет доступных клиентов для постинга

**Возможные причины:**
- Все аккаунты отключились
- Проблемы с авторизацией
- Сетевые проблемы

**Действия:**
1. Проверьте логи: `docker logs telegram-promotion-advanced`
2. Перезапустите систему: `cd ~/PIAR/telegram_promotion_system && docker-compose restart`
3. Проверьте сессии аккаунтов
"""
        await self.send_alert("no_clients", message)
    
    async def alert_client_disconnected(self, account_name: str, reason: str = ""):
        """Алерт: клиент отключен"""
        message = f"""
⚠️ **Аккаунт отключен**

**Аккаунт:** `{account_name}`
**Причина:** {reason or "Неизвестно"}

Система попытается автоматически переподключиться.
Если проблема повторяется, проверьте аккаунт вручную.
"""
        await self.send_alert(f"disconnected_{account_name}", message)
    
    async def alert_posting_failed(self, target: str, error: str, account: str):
        """Алерт: ошибка при постинге"""
        message = f"""
❌ **Ошибка постинга**

**Группа:** {target}
**Аккаунт:** {account}
**Ошибка:** {error}

Пост не был отправлен. Проверьте доступ к группе и статус аккаунта.
"""
        await self.send_alert("posting_failed", message)
    
    async def alert_all_accounts_banned(self, banned_count: int):
        """Алерт: все аккаунты забанены"""
        message = f"""
🚫 **КРИТИЧЕСКАЯ ПРОБЛЕМА**

Все аккаунты ({banned_count}) получили баны или ограничения!

**Срочные действия:**
1. Проверьте статус всех аккаунтов
2. Возможно нужно добавить новые аккаунты
3. Проверьте стратегию постинга (слишком частые посты?)
"""
        await self.send_alert("all_banned", message, force=True)
    
    async def alert_system_started(self, accounts_count: int):
        """Алерт: система запущена"""
        message = f"""
✅ **Система постинга запущена**

Инициализировано аккаунтов: {accounts_count}
Расписание: 6 раз в день (06:00, 09:00, 12:00, 15:00, 18:00, 21:00)

Мониторинг активен.
"""
        await self.send_alert("system_started", message)
    
    async def alert_reconnect_failed(self, account_name: str, attempts: int):
        """Алерт: не удалось переподключить аккаунт"""
        message = f"""
🔴 **Не удалось переподключить аккаунт**

**Аккаунт:** `{account_name}`
**Попыток:** {attempts}

Требуется ручное вмешательство!
Проверьте сессию и авторизацию аккаунта.
"""
        await self.send_alert(f"reconnect_failed_{account_name}", message, force=True)
    
    async def alert_health_check(self, active_clients: int, total_clients: int, last_post_time: str = None):
        """Периодическая проверка здоровья (раз в день)"""
        status = "✅" if active_clients == total_clients else "⚠️"
        
        message = f"""
{status} **Отчет о работе системы**

**Активных аккаунтов:** {active_clients}/{total_clients}
**Последний пост:** {last_post_time or "Нет данных"}

{"Все работает нормально." if active_clients == total_clients else "Есть неактивные аккаунты!"}
"""
        await self.send_alert("health_check", message)
    
    async def close(self):
        """Закрытие соединения"""
        if self.alert_client:
            await self.alert_client.disconnect()


