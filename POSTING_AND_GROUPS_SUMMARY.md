# Постинг в группы и поиск новых групп (Bali)

## Общая схема

```
Account Manager (по расписанию)          Marketer (по расписанию)
        │                                        │
        ▼                                        ▼
  STEP 1: Поиск групп                    Группы из БД:
  (GroupFinder + ключевые слова)         status IN ('active','joined')
        │                                warm_up_until <= NOW()
        ▼                                        │
  Сохранение в БД (status 'new')                ▼
        │                                Постинг от аккаунтов
  STEP 2: Вступление                    (bali_accounts_config: 5 аккаунтов)
  (GroupJoiner → status 'joined')
        │
        ▼
  warm_up_until = now + 24h
  (после прогрева группа готова к постингу)
```

---

## 1. Поиск новых групп (Account Manager)

**Контейнер:** `telegram-bali-account-manager`

**Расписание:** `config/niches/bali.json` → `joining_schedule` (Asia/Jakarta):
- 05:00, 07:00, 09:00, 11:00, 13:00, 15:00, 17:00, 17:35, 19:00
- Если в очереди есть группы со статусом **new** — слот запускается сразу (режим быстрой обработки).

**Шаг 1 — Поиск:**
- Ключевые слова: `config/niches/bali.json` → `manager.search_keywords` (43 шт.) + авто из сообщений ниши (80 шт.) = **123 ключевых слова**.
- Поиск: Telegram `SearchRequest` по каждому ключу (лимит 20 результатов на ключ).
- Фильтр: мусор (порно, казино и т.д.), группы без username, уже есть в БД, нельзя постить — отбрасываются.
- Найденные группы сохраняются в БД со статусом **new**.

**Шаг 2 — Вступление:**
- Берутся группы со статусом **new**.
- Аккаунты: только из `bali_accounts_config.json` → `allowed_accounts` (5 аккаунтов).
- Лимиты: `limits.max_joins_per_day` = 60, `join_batch_size` = 30, задержки 40–120 сек между вступлениями.
- После успешного вступления: status → **joined**, `warm_up_until` = now + 24 часа.

**Логи:** `/app/logs/account_manager.log` (в контейнере), смотреть через:
```bash
docker logs telegram-bali-account-manager 2>&1 | grep -E "STEP|Search keywords|Saved|joined|failed|Slot"
```

---

## 2. Постинг в группы (Marketer)

**Контейнер:** `telegram-bali-marketer` (NICHE=bali)

**Расписание:** `config/niches/bali.json` → `marketer.posting_schedule` (Asia/Jakarta):
- 08:00, 12:00, 15:00, 18:00

**Группы для постинга:**
- `status IN ('active', 'joined')`
- `warm_up_until IS NULL OR warm_up_until <= NOW()`
- `can_post = true` (или не задано)
- `daily_posts_count < 2` (лимит постов в день на группу)

**Аккаунты:** только из `bali_accounts_config.json` → `allowed_accounts` (5 аккаунтов).

**Размер батча:** `marketer.batch_size` = 20 групп за один запуск.

---

## 3. Текущее состояние (пример по БД)

| Статус групп (bali) | Количество |
|----------------------|------------|
| joined               | 21         |
| pending              | 78         |
| no_accounts_left     | 83         |
| inaccessible         | 99         |
| banned               | 7          |
| read_only            | 5          |

**Готовы к постингу:** группы со статусом joined/active с прошедшим warm_up — сейчас 21 такая группа.

---

## 4. Частые проблемы

### Поиск находит группы, но вступление даёт 0 joined, 2 failed
- Возможные причины: группа приватная/приглашение по ссылке, лимиты Telegram (FloodWait), аккаунт забанен в группе, прокси/сеть.
- Смотреть в логах account-manager: сообщения об ошибке при `JoinChannelRequest` (ChannelPrivateError, UserBannedInChannelError, FloodWait и т.д.).

### В логах «Slot X completed: 0 joined, 0 failed»
- В очереди не было групп со статусом **new** (поиск в этот раз не добавил новых или очередь уже обработана).

### Постинг не идёт / мало постов
- Проверить: есть ли группы в статусе joined/active с прошедшим warm_up.
- Проверить: `bali_accounts_config.json` и что аккаунты в БД со статусом active.
- Логи marketer: `docker logs telegram-bali-marketer 2>&1 | grep -E "БАТЧ|Найдено|постинг"`.

---

## 5. Конфиги и файлы

| Что | Файл |
|-----|------|
| Ниша по умолчанию | `config/active_niche.json` → `"niche": "bali"` |
| Ключевые слова поиска | `config/niches/bali.json` → `manager.search_keywords` |
| Расписание вступлений | `config/niches/bali.json` → `joining_schedule` |
| Расписание постинга | `config/niches/bali.json` → `marketer.posting_schedule` |
| Лимиты (вступления, прогрев) | `config/niches/bali.json` → `limits` |
| Аккаунты для Bali (постинг, секретарь, поиск/вступление) | `bali_accounts_config.json` → `allowed_accounts` |

---

## 6. Полезные команды

```bash
# Статистика групп Bali
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT status, COUNT(*) FROM groups WHERE niche = 'bali' GROUP BY status ORDER BY status;"

# Группы, готовые к постингу
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT username, status, warm_up_until FROM groups 
WHERE niche = 'bali' AND status IN ('active','joined') 
AND (warm_up_until IS NULL OR warm_up_until <= NOW()) LIMIT 20;"

# Последние слоты account-manager (поиск + вступление)
docker logs telegram-bali-account-manager 2>&1 | grep -E "STEP|Saved|Slot.*completed" | tail -20

# Последние батчи постинга
docker logs telegram-bali-marketer 2>&1 | grep -E "БАТЧ|Найдено|аккаунт" | tail -30
```
