# 📋 ЕЖЕДНЕВНАЯ ПРОВЕРКА СИСТЕМЫ

## 🚀 Быстрая проверка (1 команда)
./scripts/test_full_process.sh
```bash
cd /home/tovgrishkoff/PIAR/telegram_promotion_system_bali && ./scripts/daily_check.sh
```

⚠️ **ВНИМАНИЕ:** Если скрипт показывает 0 постов, проверьте логи на ошибки:
```bash
docker logs telegram-bali-marketer --tail 50 | grep -E "ERROR|AttributeError"
docker logs telegram-bali-account-manager --tail 50 | grep -E "ERROR|STEP|joined"
```

---

## 📊 Ручная проверка (по шагам)

### 1. Статус сервисов

```bash
# Проверка, что все сервисы работают
docker-compose ps

# Или только нужные
docker ps | grep telegram-bali
```

**Ожидаемый результат:**
- `telegram-bali-postgres` - running
- `telegram-bali-marketer` - running
- `telegram-bali-account-manager` - running

---

### 2. Статистика групп в БД

```bash
# Общая статистика по статусам
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT status, COUNT(*) 
FROM groups 
WHERE niche = 'bali' 
GROUP BY status 
ORDER BY status;
"
```

**Что смотреть:**
- `new` - должно уменьшаться (группы вступают)
- `active` - должно увеличиваться (группы готовы к постингу)

---

### 3. Группы, готовые к постингу

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

**Что смотреть:**
- Есть ли группы с `warm_up_until <= NOW()` - готовы к постингу
- `last_post_at` - когда последний раз постили

---

### 4. Последние посты (с фото)

```bash
# Последние 10 постов с информацией о фото
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT 
    g.username,
    p.sent_at,
    CASE WHEN p.photo_path IS NOT NULL THEN '📷' ELSE '📝' END as type,
    LEFT(p.message_text, 60) as message_preview,
    p.success
FROM posts p
JOIN groups g ON p.group_id = g.id
WHERE p.sent_at >= CURRENT_DATE - INTERVAL '1 day'
ORDER BY p.sent_at DESC
LIMIT 10;
"
```

**Что смотреть:**
- Есть ли новые посты за сегодня
- Есть ли посты с фото (📷)
- Успешность постинга (`success = true`)

---

### 5. Статистика по категориям постов

```bash
# Какие категории сообщений использовались
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT 
    g.username,
    CASE 
        WHEN p.photo_path LIKE '%apart%' THEN 'sale_property (инвестиции)'
        WHEN p.photo_path LIKE '%lexus%' THEN 'rental_property (аренда)'
        WHEN p.photo_path IS NOT NULL THEN 'с фото'
        ELSE 'текст'
    END as post_type,
    p.sent_at
FROM posts p
JOIN groups g ON p.group_id = g.id
WHERE p.sent_at >= CURRENT_DATE - INTERVAL '1 day'
ORDER BY p.sent_at DESC;
"
```

---

### 6. Логи Account Manager (вступление в группы)

```bash
# Последние логи вступления
docker logs telegram-bali-account-manager --tail 50 | grep -E "STEP|joined|Saved|Slot"

# Или все логи за последний час
docker logs telegram-bali-account-manager --since 1h | grep -E "STEP|joined|Saved"
```

**Что смотреть:**
- `STEP 1: SEARCHING FOR NEW GROUPS` - поиск работает
- `Saved X new groups` - новые группы найдены
- `STEP 2: JOINING NEW GROUPS` - вступление работает
- `Slot X completed: Y joined` - успешные вступления

---

### 7. Логи Marketer (постинг)

```bash
# Последние логи постинга
docker logs telegram-bali-marketer --tail 50 | grep -E "✅|❌|📋|🎯|📷"

# Или логи с фото
docker logs telegram-bali-marketer --tail 100 | grep -E "📷|photo|Фото"
```

**Что смотреть:**
- `✅ Пост отправлен` - успешные посты
- `📷 Фото:` - посты с фото отправляются
- `🎯 Using sale_property messages` - правильный выбор категорий

---

### 8. Проверка новых групп в БД

```bash
# Новые группы, добавленные за последние 24 часа
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT username, title, status, created_at
FROM groups 
WHERE niche = 'bali' 
  AND created_at >= CURRENT_DATE - INTERVAL '1 day'
ORDER BY created_at DESC
LIMIT 20;
"
```

---

### 9. Статистика аккаунтов

```bash
# Активные аккаунты и их статус
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT 
    session_name,
    status,
    created_at
FROM accounts
WHERE status = 'active'
ORDER BY created_at DESC
LIMIT 10;
"
```

---

### 10. Проверка ошибок

```bash
# Ошибки в логах marketer
docker logs telegram-bali-marketer --tail 200 | grep -i "error\|failed\|❌"

# Ошибки в логах account-manager
docker logs telegram-bali-account-manager --tail 200 | grep -i "error\|failed\|❌"
```

---

## 📝 Скрипт для автоматической проверки

Создайте файл `scripts/daily_check.sh`:

```bash
#!/bin/bash
cd /home/tovgrishkoff/PIAR/telegram_promotion_system_bali

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║          📊 ЕЖЕДНЕВНАЯ ПРОВЕРКА СИСТЕМЫ                     ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# 1. Статус сервисов
echo "1️⃣ СТАТУС СЕРВИСОВ:"
docker-compose ps | grep telegram-bali
echo ""

# 2. Статистика групп
echo "2️⃣ СТАТИСТИКА ГРУПП:"
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT status, COUNT(*) 
FROM groups 
WHERE niche = 'bali' 
GROUP BY status 
ORDER BY status;
"
echo ""

# 3. Готовые к постингу
echo "3️⃣ ГОТОВЫЕ К ПОСТИНГУ:"
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT COUNT(*) as ready_count
FROM groups 
WHERE niche = 'bali' 
  AND status = 'active' 
  AND warm_up_until <= NOW()
  AND assigned_account_id IS NOT NULL;
"
echo ""

# 4. Посты за сегодня
echo "4️⃣ ПОСТЫ ЗА СЕГОДНЯ:"
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT 
    COUNT(*) as total_posts,
    COUNT(CASE WHEN photo_path IS NOT NULL THEN 1 END) as posts_with_photo,
    COUNT(CASE WHEN success = true THEN 1 END) as successful_posts
FROM posts
WHERE sent_at >= CURRENT_DATE;
"
echo ""

# 5. Последние посты
echo "5️⃣ ПОСЛЕДНИЕ 5 ПОСТОВ:"
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT 
    g.username,
    p.sent_at,
    CASE WHEN p.photo_path IS NOT NULL THEN '📷' ELSE '📝' END as type,
    p.success
FROM posts p
JOIN groups g ON p.group_id = g.id
ORDER BY p.sent_at DESC
LIMIT 5;
"
echo ""

echo "✅ Проверка завершена!"
```

---

## 🎯 Что проверять каждый день:

1. ✅ **Сервисы работают** (docker-compose ps)
2. ✅ **Группы вступают** (статус `new` уменьшается, `active` увеличивается)
3. ✅ **Посты отправляются** (есть новые записи в таблице `posts`)
4. ✅ **Фото отправляются** (есть посты с `photo_path`)
5. ✅ **Нет критических ошибок** (проверка логов)

---

## ⚡ Быстрая команда (всё сразу):

```bash
cd /home/tovgrishkoff/PIAR/telegram_promotion_system_bali && \
echo "📊 СТАТИСТИКА:" && \
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT 
    'Группы готовые к постингу' as metric,
    COUNT(*)::text as value
FROM groups 
WHERE niche = 'bali' AND status = 'active' AND warm_up_until <= NOW()
UNION ALL
SELECT 
    'Посты за сегодня',
    COUNT(*)::text
FROM posts
WHERE sent_at >= CURRENT_DATE
UNION ALL
SELECT 
    'Посты с фото за сегодня',
    COUNT(*)::text
FROM posts
WHERE sent_at >= CURRENT_DATE AND photo_path IS NOT NULL;
"
```

---

*Обновлено: 2026-01-13*
