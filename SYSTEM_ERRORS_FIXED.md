# 🔧 Исправления системных ошибок Lexus - 2026-01-10

## ❌ Проблемы

В логах Lexus появлялись системные ошибки:

```
ERROR - Failed to resolve target @rent_kyiv_7: A wait of 65709 seconds is required (caused by ResolveUsernameRequest)
ERROR - Failed to resolve target @carssaleukm: Cannot send requests while disconnected
ERROR - Failed to resolve target @AvtochatUA: A wait of 65709 seconds is required (caused by ResolveUsernameRequest)
```

### Типы ошибок:

1. **FloodWait ошибки** - "A wait of 65709 seconds is required"
   - Telegram API ограничивает количество запросов
   - Требуется ждать ~18 часов

2. **Ошибки отключенного клиента** - "Cannot send requests while disconnected"
   - Клиент потерял подключение во время выполнения запросов
   - Нужна проверка подключения перед запросами

---

## ✅ Исправления

### 1. Исправлена функция `resolve_target` в `promotion_system.py`

**Добавлено:**
- ✅ Проверка подключения клиента перед запросами (`client.is_connected()`)
- ✅ Правильная обработка `FloodWaitError` (логируется как WARNING, не ERROR)
- ✅ Обработка ошибок отключенного клиента (`RPCError` и общие `Exception`)
- ✅ Улучшена обработка ошибок с проверкой сообщения об ошибке

**Код:**
```python
async def resolve_target(self, client: TelegramClient, target: str):
    """Разрешение цели: username/link/ID -> entity"""
    try:
        # Проверяем подключение клиента перед запросами
        if not client.is_connected():
            self.logger.warning(f"⚠️ Client is disconnected, cannot resolve target {target}")
            return None
        
        # ... остальной код ...
        
    except FloodWaitError as e:
        # FloodWait - это не критическая ошибка, логируем как предупреждение
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
        if "disconnected" in error_msg.lower() or "not connected" in error_msg.lower():
            self.logger.warning(f"⚠️ Client disconnected, cannot resolve target {target}: {error_msg}")
        else:
            self.logger.warning(f"⚠️ Failed to resolve target {target}: {error_msg}")
        return None
    except Exception as e:
        error_msg = str(e)
        if "disconnected" in error_msg.lower() or "not connected" in error_msg.lower() or "Cannot send requests" in error_msg:
            self.logger.warning(f"⚠️ Client disconnected, cannot resolve target {target}: {error_msg}")
        else:
            self.logger.error(f"❌ Failed to resolve target {target}: {error_msg}")
        return None
```

### 2. Исправлена функция `try_send_photo_with_text` в `promotion_system.py`

**Добавлено:**
- ✅ Проверка подключения клиента перед проверкой прав
- ✅ Проверка подключения клиента перед отправкой файла
- ✅ Правильная обработка `FloodWaitError`
- ✅ Улучшена обработка ошибок отключенного клиента в блоке проверки прав
- ✅ Улучшена обработка ошибок при отправке файла

**Код:**
```python
# В блоке проверки прав:
# Проверяем подключение клиента перед проверкой прав
if not client.is_connected():
    self.logger.warning(f"⚠️ Client {account_name} is disconnected, skipping {target}")
    continue

# В блоке отправки:
# Проверяем подключение клиента перед отправкой
if not client.is_connected():
    self.logger.warning(f"⚠️ Client {account_name} is disconnected before sending to {target}, trying next account...")
    continue

# В обработке исключений:
except FloodWaitError as e:
    wait_seconds = e.seconds
    wait_minutes = wait_seconds // 60
    wait_hours = wait_minutes // 60
    if wait_hours > 0:
        self.logger.warning(f"⚠️ Account {account_name} FloodWait {wait_hours}ч {wait_minutes % 60}м для {target}, trying next account...")
    else:
        self.logger.warning(f"⚠️ Account {account_name} FloodWait {wait_minutes}м для {target}, trying next account...")
    continue

except RPCError as e:
    error_msg = str(e)
    if "disconnected" in error_msg.lower() or "not connected" in error_msg.lower() or "Cannot send requests" in error_msg:
        self.logger.warning(f"⚠️ Client {account_name} disconnected for {target}: {error_msg}, trying next account...")
        continue
    # ... остальная обработка ...
```

### 3. Добавлен импорт `FloodWaitError`

**Изменено:**
```python
from telethon.errors import RPCError, FloodWaitError
```

### 4. Исправлен скрипт `daily_lexus_groups_check.py`

**Добавлено:**
- ✅ Проверка подключения клиента в `get_group_info`
- ✅ Улучшена обработка ошибок в `check_membership_and_permissions`
- ✅ Правильная обработка `FloodWaitError` и ошибок отключенного клиента

---

## 🚀 Результат

После исправлений:

1. ✅ **FloodWait ошибки** обрабатываются корректно - логируются как WARNING, не ERROR
2. ✅ **Ошибки отключенного клиента** проверяются перед запросами, не падают с критической ошибкой
3. ✅ **Система продолжает работать** даже при FloodWait или отключенных клиентах
4. ✅ **Улучшена логика** - система пытается использовать другие аккаунты при проблемах с одним

---

## 📋 Файлы изменены

1. `/home/tovgrishkoff/PIAR/telegram_promotion_system_bali/promotion_system.py`
   - Функция `resolve_target` (строка 669)
   - Функция `try_send_photo_with_text` (строка 946-1043)
   - Добавлен импорт `FloodWaitError`

2. `/home/tovgrishkoff/PIAR/telegram_promotion_system_bali/scripts/daily_lexus_groups_check.py`
   - Функция `get_group_info` (строка 187)
   - Функция `check_membership_and_permissions` (строка 237)

---

## 🔄 Перезапуск

Контейнер `lexus-scheduler` был перезапущен для применения изменений:

```bash
docker restart lexus-scheduler
```

---

*Исправления применены: 2026-01-10 11:45*
