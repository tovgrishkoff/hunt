# 🎮 РУКОВОДСТВО ПО УПРАВЛЕНИЮ СИСТЕМОЙ

## 👉 Ваша главная задача: Управление через `group_niches.json`

---

## 📋 **КАК УПРАВЛЯТЬ СИСТЕМОЙ:**

### 1️⃣ **Просмотр новых групп в БД:**

```bash
# Посмотреть все новые группы (которые еще не вступили)
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT username, title, niche, status, created_at 
FROM groups 
WHERE status = 'new' 
ORDER BY created_at DESC 
LIMIT 20;
"
```

### 2️⃣ **Добавление групп в `group_niches.json`:**

Откройте файл:
```bash
nano group_niches.json
```

**Пример добавления:**
```json
{
  "@bali_rents": "rental_property",
  "@bali_business": "general",
  "@bali_digital_nomads": "general",
  "...остальные группы...": "..."
}
```

**Категории для использования:**
- `rental_property` - Аренда недвижимости
- `sale_property` - Продажа недвижимости
- `car_rental` - Аренда авто
- `bike_rental` - Аренда мотоциклов
- `general` - Общие группы
- `tourism` - Туризм
- `business` - Бизнес
- `it` - IT/Технологии
- `designer` - Дизайн
- `photographer` - Фотография
- `videographer` - Видеосъемка
- И другие (см. `config/messages/bali/messages.json`)

---

## 🔍 **ЗАПУСК РАЗВЕДКИ (Поиск новых групп):**

### Вариант 1: Через Account Manager (автоматически)

Account Manager уже работает и автоматически ищет группы по расписанию.

### Вариант 2: Ручной запуск через finder.py

```bash
# Поиск групп по недвижимости
docker exec -d telegram-bali-account-manager python3 /app/services/account-manager/finder.py

# Проверка логов
docker logs -f telegram-bali-account-manager | tail -50
```

---

## 📊 **МОНИТОРИНГ СИСТЕМЫ:**

### Проверка статуса групп:

```bash
# Группы, готовые для постинга
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

### Проверка последних постов:

```bash
# Последние посты
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT g.username, p.sent_at, p.success, p.error_message
FROM posts p
JOIN groups g ON p.group_id = g.id
ORDER BY p.sent_at DESC
LIMIT 10;
"
```

### Проверка логов:

```bash
# Логи постинга
docker logs telegram-bali-marketer --tail 100

# Логи вступления в группы
docker logs telegram-bali-account-manager --tail 100
```

---

## 🎯 **ТИПИЧНЫЙ РАБОЧИЙ ПРОЦЕСС:**

### Раз в 2-3 дня:

1. **Проверьте новые группы:**
   ```bash
   docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
   SELECT username, title, niche, status 
   FROM groups 
   WHERE status IN ('new', 'active') 
   ORDER BY created_at DESC 
   LIMIT 30;
   "
   ```

2. **Откройте `group_niches.json`:**
   ```bash
   nano group_niches.json
   ```

3. **Добавьте новые группы с категориями:**
   - Если группа про недвижимость → `rental_property` или `sale_property`
   - Если группа общая → `general`
   - Если группа про бизнес → `general` или `business`
   - И т.д.

4. **Сохраните файл** - система автоматически подхватит изменения при следующем запуске постинга

---

## 🚀 **БЫСТРЫЕ КОМАНДЫ:**

### Запуск постинга вручную:
```bash
docker exec telegram-bali-marketer python3 /app/services/marketer/poster.py bali 5
```

### Проверка статуса сервисов:
```bash
docker ps | grep telegram-bali
```

### Перезапуск сервиса:
```bash
docker-compose restart marketer
docker-compose restart account-manager
```

---

## 📝 **ПРИМЕРЫ ДОБАВЛЕНИЯ ГРУПП:**

### Группа про недвижимость:
```json
{
  "@bali_property_rent": "rental_property",
  "@bali_villa_sale": "sale_property"
}
```

### Группа общая:
```json
{
  "@bali_chat": "general",
  "@bali_community": "general"
}
```

### Группа про бизнес:
```json
{
  "@bali_business_network": "general",
  "@bali_entrepreneurs": "general"
}
```

---

## ⚠️ **ВАЖНО:**

1. **Всегда используйте формат `@username`** (с @ в начале)
2. **Проверяйте запятые** в JSON (последний элемент без запятой)
3. **Категория должна существовать** в `config/messages/bali/messages.json`
4. **Если категория не найдена** - используется fallback (все сообщения)

---

## 🎉 **РЕЗУЛЬТАТ:**

После добавления групп в `group_niches.json`:
- ✅ Система автоматически выберет релевантные сообщения
- ✅ Группы получат посты из правильной категории
- ✅ Больше релевантности = больше конверсий!

---

*Руководство создано: 2026-01-13*
