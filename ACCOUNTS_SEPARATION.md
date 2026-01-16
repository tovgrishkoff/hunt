# 🔀 Разделение аккаунтов между Bali и Lexus

## 📋 Принцип разделения

**Аккаунты полностью разделены между системами** для избежания конфликтов и путаницы в контексте:

- **Bali Secretary** обрабатывает DM только для своих аккаунтов
- **Lexus Secretary** обрабатывает DM только для своих аккаунтов
- **Bali Marketer** постит только с аккаунтов Bali
- **Lexus Scheduler** постит только с аккаунтов Lexus
- **Нет пересечений** - один аккаунт не может использоваться в обеих системах одновременно

## 📁 Конфигурационные файлы

### `lexus_accounts_config.json`
Список аккаунтов, которые используются **ТОЛЬКО в системе Lexus** (для постинга и Secretary):

```json
{
  "allowed_accounts": [
    "promotion_dao_bro",
    "promotion_rod_shaihutdinov"
  ]
}
```

### `bali_accounts_config.json`
Список аккаунтов, которые используются **ТОЛЬКО в системе Bali** (для постинга и Secretary):

```json
{
  "allowed_accounts": [
    "promotion_oleg_petrov",
    "promotion_anna_truncher",
    "promotion_artur_biggest",
    "promotion_andrey_virgin"
  ]
}
```

## 🔧 Как это работает

### Lexus Scheduler (`lexus_scheduler.py`)
1. Загружает `lexus_accounts_config.json` (whitelist)
2. Использует только аккаунты из `allowed_accounts` для постинга
3. Фильтрует аккаунты в `get_next_client()` для ниши `ukraine_cars`

### Lexus Secretary (`lexus_secretary.py`)
1. Загружает `lexus_accounts_config.json`
2. Берет только аккаунты из `allowed_accounts`
3. Создает клиенты только для этих аккаунтов
4. Пересылает DM на @grishkoff

### Bali Secretary (`services/secretary/main.py`)
1. Загружает все активные аккаунты из БД (`Account.status == 'active'`)
2. **Использует whitelist** из `bali_accounts_config.json` (если есть)
3. Иначе **автоматически исключает** аккаунты из `lexus_accounts_config.json`
4. Создает клиенты только для оставшихся аккаунтов
5. Обрабатывает DM через GPT

### Bali Marketer (`services/marketer/poster.py`)
1. Использует аккаунты из БД
2. Автоматически исключает аккаунты из `lexus_accounts_config.json` (через `client_manager`)
3. Постит только с аккаунтов Bali

## ⚠️ Важно

- Если нужно добавить аккаунт в Lexus:
  1. Добавьте его в `lexus_accounts_config.json` → `allowed_accounts`
  2. Он автоматически исключится из Bali

- Если нужно добавить аккаунт в Bali:
  1. Добавьте его в `bali_accounts_config.json` → `allowed_accounts`
  2. Убедитесь, что его нет в `lexus_accounts_config.json`

- Если нужно убрать аккаунт из Lexus:
  1. Удалите его из `lexus_accounts_config.json` → `allowed_accounts`
  2. Добавьте в `bali_accounts_config.json`, если нужен для Bali

## 🔍 Проверка разделения

### Проверить аккаунты Lexus:
```bash
# Scheduler
docker logs lexus-scheduler | grep "Lexus accounts\|allowed"

# Secretary
docker logs lexus-secretary | grep "Allowed accounts"
```

### Проверить аккаунты Bali:
```bash
# Secretary
docker logs telegram-bali-secretary | grep "whitelist\|Registered handler"

# Marketer (через БД)
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c \
  "SELECT DISTINCT account_id FROM posts WHERE DATE(sent_at) = CURRENT_DATE;"
```

### Убедиться, что нет пересечений:
```bash
# Аккаунты Lexus
docker logs lexus-secretary | grep "Allowed accounts" | tail -1

# Аккаунты Bali (должны быть другими)
docker logs telegram-bali-secretary | grep "Registered handler" | tail -5
```

## 📊 Текущее распределение

### Lexus (2 аккаунта):
- `promotion_dao_bro`
- `promotion_rod_shaihutdinov`

### Bali (4 аккаунта):
- `promotion_oleg_petrov`
- `promotion_anna_truncher`
- `promotion_artur_biggest`
- `promotion_andrey_virgin`

---

*Обновлено: 2026-01-10*
