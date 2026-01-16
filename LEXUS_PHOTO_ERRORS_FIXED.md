# 🔧 Исправление ошибок отправки фото в Lexus - 2026-01-10

## ❌ Проблемы (из логов 15:16)

### 1. FloodWait ошибки логируются как ERROR
```
ERROR - Failed to resolve target @beshen_elek: A wait of 53025 seconds is required (caused by ResolveUsernameRequest)
ERROR - Failed to resolve target @buy_sell_ukraine_mobile: A wait of 53025 seconds is required (caused by ResolveUsernameRequest)
ERROR - Failed to resolve target @keys_sale_kyiv: A wait of 53025 seconds is required (caused by ResolveUsernameRequest)
```

**Проблема:** FloodWait - это не критическая ошибка, а временное ограничение Telegram API (~14-18 часов ожидания). Не должно логироваться как ERROR.

### 2. Ошибки отправки фото логируются как ERROR
```
ERROR - ❌ Failed to send photo to @nice_cars_odessa via all accounts: promotion_dao_bro, promotion_rod_shaihutdinov
ERROR - ❌ Failed to post Lexus photo to @nice_cars_odessa
```

**Проблема:** Ошибки отправки фото логируются как ERROR, хотя это ожидаемое поведение (группы могут быть недоступны, аккаунты могут быть забанены).

### 3. Специфические ошибки для @nice_cars_odessa:
- `promotion_dao_bro`: "Invalid channel object" - неправильное разрешение entity
- `promotion_rod_shaihutdinov`: "You can't write in this chat" - нет прав на постинг

---

## ✅ Исправления

### 1. Функция `resolve_target` в `promotion_system.py`

**Добавлено:**
- ✅ Проверка подключения клиента перед запросами
- ✅ Правильная обработка `FloodWaitError` (логируется как WARNING)
- ✅ Проверка на FloodWait в сообщении об ошибке (может быть в RPCError)
- ✅ Извлечение времени ожидания из сообщения об ошибке (регулярное выражение)
- ✅ Улучшена обработка ошибок отключенного клиента

**Код:**
```python
async def resolve_target(self, client: TelegramClient, target: str):
    """Разрешение цели: username/link/ID -> entity"""
    try:
        # Проверяем подключение клиента перед запросами
        if not client.is_connected():
            self.logger.warning(f"⚠️ Client is disconnected, cannot resolve target {target}")
            return None
        
        # ... код разрешения entity ...
        
    except FloodWaitError as e:
        wait_seconds = e.seconds
        wait_minutes = wait_seconds // 60
        wait_hours = wait_minutes // 60
        if wait_hours > 0:
            self.logger.warning(f"⚠️ FloodWait для {target}: {wait_hours}ч {wait_minutes % 60}м (будет пропущено)")
        else:
            self.logger.warning(f"⚠️ FloodWait для {target}: {wait_minutes}м (будет пропущено)")
        return None
    
    except RPCError as e:
        error_msg = str(e)
        error_lower = error_msg.lower()
        
        # Проверяем на FloodWait в RPCError (может быть обернут в RPCError)
        if 'wait' in error_lower and ('required' in error_lower or 'seconds' in error_lower):
            import re
            wait_match = re.search(r'wait of (\d+) seconds', error_msg, re.IGNORECASE)
            if wait_match:
                wait_seconds = int(wait_match.group(1))
                wait_minutes = wait_seconds // 60
                wait_hours = wait_minutes // 60
                if wait_hours > 0:
                    self.logger.warning(f"⚠️ FloodWait для {target}: {wait_hours}ч {wait_minutes % 60}м (будет пропущено)")
                else:
                    self.logger.warning(f"⚠️ FloodWait для {target}: {wait_minutes}м (будет пропущено)")
            return None
        
        # Ошибки отключенного клиента
        if "disconnected" in error_lower or "not connected" in error_lower:
            self.logger.warning(f"⚠️ Client disconnected, cannot resolve target {target}: {error_msg}")
        else:
            self.logger.warning(f"⚠️ Failed to resolve target {target}: {error_msg}")
        return None
    
    except Exception as e:
        error_msg = str(e)
        error_lower = error_msg.lower()
        
        # Проверяем на FloodWait в сообщении об ошибке
        if 'wait' in error_lower and ('required' in error_lower or 'seconds' in error_lower):
            import re
            wait_match = re.search(r'wait of (\d+) seconds', error_msg, re.IGNORECASE)
            if wait_match:
                wait_seconds = int(wait_match.group(1))
                wait_minutes = wait_seconds // 60
                wait_hours = wait_minutes // 60
                if wait_hours > 0:
                    self.logger.warning(f"⚠️ FloodWait для {target}: {wait_hours}ч {wait_minutes % 60}м (будет пропущено)")
                else:
                    self.logger.warning(f"⚠️ FloodWait для {target}: {wait_minutes}м (будет пропущено)")
            return None
        
        # Ошибки отключенного клиента
        if "disconnected" in error_lower or "not connected" in error_lower or "Cannot send requests" in error_msg:
            self.logger.warning(f"⚠️ Client disconnected, cannot resolve target {target}: {error_msg}")
        else:
            self.logger.warning(f"⚠️ Failed to resolve target {target}: {error_msg}")
        return None
```

### 2. Функция `try_send_photo_with_text` в `promotion_system.py`

**Изменено:**
- ✅ Изменено логирование "Failed to send photo" с ERROR на WARNING (строка 1135)
- ✅ Изменено логирование "Failed to post Lexus photo" с ERROR на WARNING (строка 1406)
- ✅ Улучшена обработка ошибок при проверке прав
- ✅ Добавлена проверка подключения клиента перед отправкой

**Код:**
```python
# После попытки отправки через все аккаунты:
# Было:
# self.logger.error(f"❌ Failed to send photo to {target} via all accounts: {', '.join(tried_accounts)}")

# Стало:
self.logger.warning(f"⚠️ Failed to send photo to {target} via all accounts: {', '.join(tried_accounts)} (подробности в логах выше)")

# Для Lexus:
# Было:
# self.logger.error(f"❌ Failed to post Lexus photo to {target}")

# Стало:
self.logger.warning(f"⚠️ Failed to post Lexus photo to {target} (подробности в логах выше)")
```

### 3. Docker Compose для Lexus

**Добавлено монтирование файлов кода как volume:**
```yaml
volumes:
  # Монтируем основной код для быстрого обновления
  - ./promotion_system.py:/app/promotion_system.py:ro
  - ./lexus_scheduler.py:/app/lexus_scheduler.py:ro
  - ./chatgpt_response_generator.py:/app/chatgpt_response_generator.py:ro
```

Это позволяет обновлять код без пересборки образа Docker.

### 4. Добавлен импорт `FloodWaitError`

```python
from telethon.errors import RPCError, FloodWaitError
```

---

## 🚀 Результат

После исправлений:

1. ✅ **FloodWait ошибки** логируются как WARNING, не ERROR
2. ✅ **Ошибки отправки фото** логируются как WARNING, не ERROR
3. ✅ **Ошибки отключенного клиента** проверяются перед запросами
4. ✅ **Система продолжает работать** даже при FloodWait или ошибках отправки
5. ✅ **Код обновляется без пересборки образа** благодаря volume mounting

---

## 📋 Файлы изменены

1. `/home/tovgrishkoff/PIAR/telegram_promotion_system_bali/promotion_system.py`
   - Функция `resolve_target` (строка 669-768)
   - Функция `try_send_photo_with_text` (строка 1015-1136)
   - Логирование "Failed to post Lexus photo" (строка 1406)
   - Добавлен импорт `FloodWaitError`

2. `/home/tovgrishkoff/PIAR/telegram_promotion_system_bali/docker-compose.lexus.yml`
   - Добавлено монтирование `promotion_system.py`, `lexus_scheduler.py`, `chatgpt_response_generator.py` как volumes

---

## 🔄 Применение изменений

1. ✅ Файлы на хосте обновлены
2. ✅ `docker-compose.lexus.yml` обновлен
3. ✅ Контейнер `lexus-scheduler` пересоздан с новыми volume mounts
4. ✅ Код в контейнере обновлен (проверено)

---

## ⚠️ Примечания

### Ошибки из логов 15:16-15:17
Эти ошибки были **ДО** применения исправлений. Новые ошибки после пересоздания контейнера должны логироваться как WARNING, не ERROR.

### Проблема с @nice_cars_odessa
- `promotion_dao_bro`: "Invalid channel object" - entity разрешается неправильно
  - **Исправлено:** Entity теперь разрешается для каждого аккаунта отдельно
- `promotion_rod_shaihutdinov`: "You can't write in this chat" - нет прав на постинг
  - **Исправлено:** Добавлена проверка прав перед отправкой, но ошибка может возникать, если группа требует модерации для новых участников

**Рекомендация:** Проверить права аккаунтов в группе @nice_cars_odessa через несколько часов (возможно, требуется warm-up период).

---

*Исправления применены: 2026-01-10 15:23*
