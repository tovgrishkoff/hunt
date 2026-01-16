# 📊 Руководство по мониторингу системы Ukraine/Lexus

## 🚀 Быстрые команды

### Проверка статуса системы
```bash
./scripts/monitoring/check_ukraine_status.sh
```
Показывает:
- Статус контейнеров
- Статистику по аккаунтам и группам
- Последние посты
- Последние вступления

### Проверка логов
```bash
# Логи account-manager (последние 50 строк)
./scripts/monitoring/check_ukraine_logs.sh account-manager 50

# Логи с ошибками
./scripts/monitoring/check_ukraine_logs.sh account-manager 100 | grep -i error
```

### Проверка постов
```bash
# Посты за последний день
./scripts/monitoring/check_ukraine_posts.sh 1

# Посты за последнюю неделю
./scripts/monitoring/check_ukraine_posts.sh 7
```

### Проверка групп (куда вступили)
```bash
./scripts/monitoring/check_ukraine_groups.sh
```
Показывает:
- Статистику по статусам
- Список вступивших групп
- Новые группы (ожидают вступления)
- Ошибки вступления

### Проверка аккаунтов
```bash
./scripts/monitoring/check_ukraine_accounts.sh
```

### Мониторинг в реальном времени
```bash
# Следить за логами account-manager
./scripts/monitoring/watch_ukraine_logs.sh account-manager
```

---

## 🔧 Прямые команды Docker

### Просмотр логов
```bash
# Все логи account-manager
docker logs ukraine-account-manager

# Последние 100 строк
docker logs ukraine-account-manager --tail=100

# Следить за логами в реальном времени
docker logs -f ukraine-account-manager

# Логи с ошибками
docker logs ukraine-account-manager 2>&1 | grep -i error
```

### Проверка статуса контейнеров
```bash
# Все контейнеры Ukraine
docker ps | grep ukraine

# Детальная информация
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep ukraine
```

---

## 🗄️ Запросы к БД

### Подключение к БД
```bash
docker exec -it ukraine-postgres psql -U telegram_user_ukraine -d ukraine_db
```

### Полезные SQL запросы

#### Последние посты
```sql
SELECT 
    TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') as posted_at,
    (SELECT title FROM targets WHERE id = post_history.target_id) as group_name,
    (SELECT session_name FROM accounts WHERE id = post_history.account_id) as account,
    status,
    LEFT(message_content, 100) as message
FROM post_history
WHERE created_at >= NOW() - INTERVAL '1 day'
ORDER BY created_at DESC
LIMIT 20;
```

#### Группы, куда вступили сегодня
```sql
SELECT 
    TO_CHAR(joined_at, 'YYYY-MM-DD HH24:MI:SS') as joined_time,
    title as group_name,
    link as group_link,
    (SELECT session_name FROM accounts WHERE id = assigned_account_id) as account
FROM targets
WHERE status = 'joined' 
  AND niche = 'ukraine_cars'
  AND DATE(joined_at) = CURRENT_DATE
ORDER BY joined_at DESC;
```

#### Статистика по постам за день
```sql
SELECT 
    DATE(created_at) as date,
    COUNT(*) FILTER (WHERE status = 'success') as success,
    COUNT(*) FILTER (WHERE status = 'error') as errors,
    COUNT(*) as total
FROM post_history
WHERE created_at >= NOW() - INTERVAL '7 days'
GROUP BY DATE(created_at)
ORDER BY date DESC;
```

#### Группы, готовые к постингу
```sql
SELECT 
    title as group_name,
    link as group_link,
    (SELECT session_name FROM accounts WHERE id = assigned_account_id) as account,
    daily_posts_in_group || '/2' as posts_today,
    TO_CHAR(warmup_ends_at, 'YYYY-MM-DD HH24:MI:SS') as warmup_ends
FROM targets
WHERE status = 'joined'
  AND niche = 'ukraine_cars'
  AND warmup_ends_at < NOW()
  AND daily_posts_in_group < 2
ORDER BY last_post_at NULLS FIRST
LIMIT 20;
```

#### Аккаунты с лимитами
```sql
SELECT 
    session_name,
    status,
    daily_posts_count || '/20' as posts_today,
    CASE 
        WHEN next_allowed_action_time IS NULL THEN 'Готов'
        WHEN next_allowed_action_time > NOW() THEN 'FloodWait'
        ELSE 'Готов'
    END as availability
FROM accounts
ORDER BY daily_posts_count DESC;
```

---

## 📋 Чек-лист проверки

### Ежедневная проверка

1. **Статус контейнеров**
   ```bash
   docker ps | grep ukraine
   ```
   ✅ Все контейнеры должны быть `Up`

2. **Проверка ошибок в логах**
   ```bash
   docker logs ukraine-account-manager --tail=100 2>&1 | grep -iE "(error|exception|failed)"
   ```
   ✅ Не должно быть критических ошибок

3. **Проверка вступлений**
   ```bash
   ./scripts/monitoring/check_ukraine_groups.sh
   ```
   ✅ Группы вступают (статус `joined`)

4. **Проверка постов**
   ```bash
   ./scripts/monitoring/check_ukraine_posts.sh 1
   ```
   ✅ Посты публикуются (статус `success`)

5. **Проверка аккаунтов**
   ```bash
   ./scripts/monitoring/check_ukraine_accounts.sh
   ```
   ✅ Аккаунты активны, нет длительных FloodWait

### Еженедельная проверка

1. **Статистика за неделю**
   ```bash
   ./scripts/monitoring/check_ukraine_posts.sh 7
   ```

2. **Проверка ошибок вступления**
   ```bash
   docker exec ukraine-postgres psql -U telegram_user_ukraine -d ukraine_db -c "
   SELECT COUNT(*) as error_count 
   FROM targets 
   WHERE status = 'error' AND niche = 'ukraine_cars';
   "
   ```

3. **Проверка активности аккаунтов**
   ```bash
   docker exec ukraine-postgres psql -U telegram_user_ukraine -d ukraine_db -c "
   SELECT session_name, daily_posts_count, status
   FROM accounts
   ORDER BY daily_posts_count DESC;
   "
   ```

---

## 🚨 Типичные проблемы

### Контейнеры перезапускаются
```bash
# Проверить логи
docker logs ukraine-account-manager --tail=50

# Проверить статус
docker ps -a | grep ukraine
```

### Нет постов
```bash
# Проверить готовые группы
docker exec ukraine-postgres psql -U telegram_user_ukraine -d ukraine_db -c "
SELECT COUNT(*) FROM targets 
WHERE status = 'joined' 
  AND warmup_ends_at < NOW() 
  AND niche = 'ukraine_cars';
"

# Проверить лимиты аккаунтов
./scripts/monitoring/check_ukraine_accounts.sh
```

### Нет вступлений
```bash
# Проверить новые группы
docker exec ukraine-postgres psql -U telegram_user_ukraine -d ukraine_db -c "
SELECT COUNT(*) FROM targets 
WHERE status = 'new' AND niche = 'ukraine_cars';
"

# Проверить логи joiner
docker logs ukraine-account-manager 2>&1 | grep -i joiner | tail -20
```

### Аккаунты в FloodWait
```bash
# Проверить FloodWait
docker exec ukraine-postgres psql -U telegram_user_ukraine -d ukraine_db -c "
SELECT session_name, next_allowed_action_time, status
FROM accounts
WHERE next_allowed_action_time > NOW()
ORDER BY next_allowed_action_time;
"
```

---

## 📊 Автоматический мониторинг

### Создать cron задачу для ежедневного отчета
```bash
# Добавить в crontab
0 9 * * * /path/to/scripts/monitoring/check_ukraine_status.sh >> /path/to/logs/daily_status.log 2>&1
```

### Настроить алерты (опционально)
Можно настроить отправку отчетов на email или в Telegram при обнаружении ошибок.

---

## 🔗 Полезные файлы

- `scripts/monitoring/check_ukraine_status.sh` - Общий статус
- `scripts/monitoring/check_ukraine_logs.sh` - Логи и ошибки
- `scripts/monitoring/check_ukraine_posts.sh` - Посты
- `scripts/monitoring/check_ukraine_groups.sh` - Группы
- `scripts/monitoring/check_ukraine_accounts.sh` - Аккаунты
- `scripts/monitoring/watch_ukraine_logs.sh` - Реал-тайм мониторинг

---

*Обновлено: 2026-01-12*
