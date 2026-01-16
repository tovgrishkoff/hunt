# 🎮 КАК УПРАВЛЯТЬ СИСТЕМОЙ

## 📋 СОДЕРЖАНИЕ

1. [Быстрый старт](#быстрый-старт)
2. [Управление сервисами](#управление-сервисами)
3. [Управление группами](#управление-группами)
4. [Мониторинг](#мониторинг)
5. [Обновление сообщений](#обновление-сообщений)
6. [Типичные задачи](#типичные-задачи)

---

## 🚀 БЫСТРЫЙ СТАРТ

### Проверка статуса системы:

```bash
cd /home/tovgrishkoff/PIAR/telegram_promotion_system_bali

# Статус всех сервисов
docker-compose ps

# Или через скрипт
./scripts/manage_containers.sh status
```

### Запуск/остановка:

```bash
# Запустить все сервисы
docker-compose up -d

# Остановить все сервисы
docker-compose down

# Перезапустить конкретный сервис
docker-compose restart marketer
docker-compose restart account-manager
```

---

## 🔧 УПРАВЛЕНИЕ СЕРВИСАМИ

### 1. Marketer (Постинг сообщений)

```bash
# Запустить постинг вручную (5 групп)
docker exec telegram-bali-marketer python3 /app/services/marketer/poster.py bali 5

# Логи в реальном времени
docker logs -f telegram-bali-marketer

# Последние 50 строк логов
docker logs telegram-bali-marketer --tail 50
```

### 2. Account Manager (Вступление в группы)

```bash
# Логи в реальном времени
docker logs -f telegram-bali-account-manager

# Последние 50 строк
docker logs telegram-bali-account-manager --tail 50

# Запуск поиска групп вручную (если нужно)
docker exec -d telegram-bali-account-manager python3 /app/services/account-manager/finder.py
```

### 3. PostgreSQL (База данных)

```bash
# Подключение к БД
docker exec -it telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali

# Выполнить SQL-запрос
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "SELECT COUNT(*) FROM groups;"
```

---

## 📊 УПРАВЛЕНИЕ ГРУППАМИ

### Главный файл: `group_niches.json`

Это **ваш основной инструмент управления**! Система автоматически использует этот файл для выбора релевантных сообщений.

### Просмотр новых групп в БД:

```bash
# Новые группы (последние 20)
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT username, title, status, created_at 
FROM groups 
WHERE niche = 'bali' 
  AND status IN ('new', 'active')
ORDER BY created_at DESC 
LIMIT 20;
"
```

### Добавление групп в маппинг:

```bash
# Открыть файл
nano group_niches.json
```

**Формат:**
```json
{
  "@bali_rents": "bali_rent",
  "@WorkExBali": "bali_it_bots",
  "@bali_chat": "bali_it_bots"
}
```

**Доступные категории для Бали:**
- `bali_rent` → сообщения про аренду недвижимости
- `bali_it_bots` → сообщения про ботов/разработку (general)

**Полный список категорий** (см. `config/messages/bali/messages.json`):
- `rental_property` - Аренда недвижимости
- `sale_property` - Продажа недвижимости
- `car_rental` - Аренда авто
- `bike_rental` - Аренда мотоциклов
- `general` - Общие сообщения
- `tourism` - Туризм
- `designer` - Дизайн
- `photographer` - Фотография
- `videographer` - Видеосъемка
- И другие...

### Изменение статуса группы:

```bash
# Пометить группу как read_only (не постить туда)
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
UPDATE groups 
SET status = 'read_only' 
WHERE username = '@rent_bali';
"

# Вернуть группу в активные
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
UPDATE groups 
SET status = 'active' 
WHERE username = '@bali_chat';
"
```

---

## 📈 МОНИТОРИНГ

### Статистика групп:

```bash
# Статистика по статусам
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT status, COUNT(*) 
FROM groups 
WHERE niche = 'bali' 
GROUP BY status;
"
```

### Группы, готовые для постинга:

```bash
# Группы, которые прошли warm-up и готовы к постингу
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT username, status, warm_up_until, last_post_at, daily_posts_count
FROM groups 
WHERE niche = 'bali' 
  AND status = 'active' 
  AND warm_up_until <= NOW()
  AND assigned_account_id IS NOT NULL
ORDER BY last_post_at ASC NULLS FIRST
LIMIT 10;
"
```

### Последние посты:

```bash
# Последние 10 постов
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT g.username, p.sent_at, p.success, LEFT(p.message_text, 50) as message_preview
FROM posts p
JOIN groups g ON p.group_id = g.id
ORDER BY p.sent_at DESC
LIMIT 10;
"
```

### Статистика аккаунтов:

```bash
# Аккаунты и их статус
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT id, phone, status, created_at
FROM accounts
ORDER BY created_at DESC
LIMIT 10;
"
```

---

## 📝 ОБНОВЛЕНИЕ СООБЩЕНИЙ

### 1. Редактирование исходных файлов:

Все сообщения хранятся в файлах `messages_*.txt` в корне проекта:
- `messages_general.txt` - общие сообщения
- `messages_rental_property.txt` - недвижимость
- `messages_car_rental.txt` - аренда авто
- И т.д.

```bash
# Открыть файл для редактирования
nano messages_general.txt
```

### 2. Обновление JSON:

```bash
# Запустить скрипт объединения
python3 scripts/merge_all_messages.py
```

Этот скрипт:
- Читает все `messages_*.txt` файлы
- Объединяет их в `config/messages/bali/messages.json`
- Сохраняет `source_file` для каждой категории

### 3. Перезапуск marketer:

```bash
docker-compose restart marketer
```

---

## ✅ ТИПИЧНЫЕ ЗАДАЧИ

### Задача 1: Добавить новые группы в систему

```bash
# 1. Проверить новые группы в БД
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT username, title, status 
FROM groups 
WHERE status = 'new' 
ORDER BY created_at DESC 
LIMIT 20;
"

# 2. Открыть group_niches.json
nano group_niches.json

# 3. Добавить группы с категориями
# 4. Сохранить файл
# Система автоматически подхватит изменения!
```

### Задача 2: Проверить, работает ли постинг

```bash
# 1. Проверить логи marketer
docker logs telegram-bali-marketer --tail 50 | grep -E "(✅|❌|📋|🎯)"

# 2. Проверить последние посты в БД
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT g.username, p.sent_at, p.success
FROM posts p
JOIN groups g ON p.group_id = g.id
ORDER BY p.sent_at DESC
LIMIT 5;
"
```

### Задача 3: Запустить постинг вручную

```bash
# Запустить постинг в 5 групп
docker exec telegram-bali-marketer python3 /app/services/marketer/poster.py bali 5

# Запустить постинг в 10 групп
docker exec telegram-bali-marketer python3 /app/services/marketer/poster.py bali 10
```

### Задача 4: Проверить, вступают ли боты в группы

```bash
# Логи Account Manager
docker logs telegram-bali-account-manager --tail 50 | grep -E "(вступ|join|new|active)"

# Статистика по статусам
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT status, COUNT(*) 
FROM groups 
WHERE niche = 'bali' 
GROUP BY status;
"
```

### Задача 5: Добавить новые сообщения

```bash
# 1. Открыть нужный файл
nano messages_general.txt

# 2. Добавить новые сообщения (по одному на строку)

# 3. Обновить JSON
python3 scripts/merge_all_messages.py

# 4. Перезапустить marketer
docker-compose restart marketer
```

### Задача 6: Пометить группу как недоступную

```bash
# Если группа - канал или требует админ-прав
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
UPDATE groups 
SET status = 'read_only' 
WHERE username = '@problematic_group';
"
```

---

## 🎯 РЕЖИМ РАБОТЫ СИСТЕМЫ

### Автоматический режим:

1. **Account Manager** работает по расписанию:
   - Ищет новые группы
   - Вступает в них
   - Устанавливает warm-up период (24 часа)

2. **Marketer** работает по расписанию:
   - Проверяет группы, готовые для постинга
   - Выбирает релевантные сообщения из `group_niches.json`
   - Отправляет сообщения

3. **Ваша задача:**
   - Раз в 2-3 дня проверять новые группы
   - Добавлять их в `group_niches.json`
   - Обновлять сообщения при необходимости

---

## 📚 ДОПОЛНИТЕЛЬНЫЕ РЕСУРСЫ

- **Полное руководство:** `MANAGEMENT_GUIDE.md`
- **Быстрый старт:** `QUICK_START.md`
- **Цикл автоматизации:** `AUTOMATION_CYCLE.md`
- **Обновление сообщений:** `MESSAGES_UPDATE_GUIDE.md`
- **Маппинг категорий:** `CATEGORY_MAPPING_INFO.md`

---

## ⚠️ ВАЖНЫЕ ЗАМЕЧАНИЯ

1. **Всегда используйте формат `@username`** в `group_niches.json`
2. **Проверяйте запятые** в JSON (последний элемент без запятой)
3. **Категория должна существовать** в `messages.json`
4. **После изменения `group_niches.json`** система подхватит изменения автоматически
5. **После изменения `messages_*.txt`** нужно запустить `merge_all_messages.py`

---

*Обновлено: 2026-01-13*
