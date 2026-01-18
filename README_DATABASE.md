# 📊 Работа с базой данных подписчиков Bali Bot

## 🔍 Просмотр подписчиков

### 1. Полная информация о всех подписчиках

```bash
docker exec bali-postgres psql -U grishkoff -d bali_bot -c "SELECT * FROM subscribers ORDER BY created_at DESC;"
```

### 2. Краткая сводка по подписчикам

```bash
docker exec bali-postgres psql -U grishkoff -d bali_bot -c "
SELECT 
    s.user_id,
    s.subscription_active as активна,
    CASE 
        WHEN s.trial_until > NOW() THEN 'Триал активен'
        WHEN s.subscription_active THEN 'Подписка'
        ELSE 'Нет подписки'
    END as статус,
    s.trial_until as триал_до,
    s.subscription_until as подписка_до,
    s.created_at as зарегистрирован,
    COALESCE(ub.balance, 0) as баланс,
    COALESCE(ub.total_referrals, 0) as рефералов,
    jsonb_array_length(s.categories) as категорий
FROM subscribers s
LEFT JOIN user_balance ub ON s.user_id = ub.user_id
ORDER BY s.created_at DESC;
"
```

### 3. Список категорий конкретного подписчика

```bash
# Замените USER_ID на нужный ID
docker exec bali-postgres psql -U grishkoff -d bali_bot -c "
SELECT user_id, categories 
FROM subscribers 
WHERE user_id = USER_ID;
"
```

Пример:
```bash
docker exec bali-postgres psql -U grishkoff -d bali_bot -c "
SELECT user_id, categories 
FROM subscribers 
WHERE user_id = 210147380;
"
```

### 4. Подписчики конкретной категории

```bash
# Поиск всех подписчиков категории "Фотограф"
docker exec bali-postgres psql -U grishkoff -d bali_bot -c "
SELECT user_id, categories 
FROM subscribers 
WHERE categories @> '[\"Фотограф\"]'::jsonb;
"
```

### 5. Статистика по категориям

```bash
docker exec bali-postgres psql -U grishkoff -d bali_bot -c "
SELECT 
    jsonb_array_elements_text(categories) as категория,
    COUNT(*) as подписчиков
FROM subscribers
GROUP BY категория
ORDER BY подписчиков DESC;
"
```

### 6. Активные триалы

```bash
docker exec bali-postgres psql -U grishkoff -d bali_bot -c "
SELECT user_id, trial_until, 
    EXTRACT(DAY FROM (trial_until - NOW())) as дней_осталось
FROM subscribers 
WHERE trial_until > NOW()
ORDER BY trial_until;
"
```

### 7. Активные подписки

```bash
docker exec bali-postgres psql -U grishkoff -d bali_bot -c "
SELECT user_id, subscription_until, subscription_active
FROM subscribers 
WHERE subscription_active = true
ORDER BY subscription_until DESC;
"
```

---

## 💰 Финансовая информация

### 1. Балансы всех пользователей

```bash
docker exec bali-postgres psql -U grishkoff -d bali_bot -c "
SELECT * FROM user_balance ORDER BY balance DESC;
"
```

### 2. Реферальная статистика

```bash
docker exec bali-postgres psql -U grishkoff -d bali_bot -c "
SELECT 
    user_id,
    referral_code as код,
    total_referrals as приглашено,
    total_earned as заработано,
    balance as баланс
FROM user_balance
WHERE total_referrals > 0 OR total_earned > 0
ORDER BY total_earned DESC;
"
```

### 3. История платежей

```bash
docker exec bali-postgres psql -U grishkoff -d bali_bot -c "
SELECT * FROM payments ORDER BY paid_at DESC;
"
```

### 4. Общая статистика по платежам

```bash
docker exec bali-postgres psql -U grishkoff -d bali_bot -c "
SELECT 
    COUNT(*) as всего_платежей,
    SUM(total_amount) as общая_сумма,
    AVG(total_amount) as средний_чек,
    currency as валюта
FROM payments
GROUP BY currency;
"
```

---

## 📋 Структура базы данных

### Список всех таблиц

```bash
docker exec bali-postgres psql -U grishkoff -d bali_bot -c "\dt"
```

### Структура таблицы subscribers

```bash
docker exec bali-postgres psql -U grishkoff -d bali_bot -c "\d subscribers"
```

### Структура таблицы messages

```bash
docker exec bali-postgres psql -U grishkoff -d bali_bot -c "\d messages"
```

---

## 📨 Работа с сообщениями

### 1. Необработанные сообщения

```bash
docker exec bali-postgres psql -U grishkoff -d bali_bot -c "
SELECT id, category, sender_name, chat_title, 
    LEFT(message_text, 50) as текст_начало,
    created_at
FROM messages 
WHERE is_processed = false
ORDER BY created_at DESC;
"
```

### 2. Статистика по категориям сообщений

```bash
docker exec bali-postgres psql -U grishkoff -d bali_bot -c "
SELECT 
    category as категория,
    COUNT(*) as всего_сообщений,
    SUM(CASE WHEN is_processed THEN 1 ELSE 0 END) as обработано,
    SUM(CASE WHEN is_processed THEN 0 ELSE 1 END) as необработано
FROM messages
GROUP BY category
ORDER BY всего_сообщений DESC;
"
```

### 3. Последние сообщения

```bash
docker exec bali-postgres psql -U grishkoff -d bali_bot -c "
SELECT 
    category,
    sender_name,
    chat_title,
    LEFT(message_text, 100) as текст,
    created_at
FROM messages
ORDER BY created_at DESC
LIMIT 20;
"
```

---

## 🚫 Забаненные пользователи

```bash
docker exec bali-postgres psql -U grishkoff -d bali_bot -c "
SELECT * FROM banned_users ORDER BY banned_at DESC;
"
```

---

## 📈 Общая статистика

### Сводная статистика по боту

```bash
docker exec bali-postgres psql -U grishkoff -d bali_bot -c "
SELECT 
    (SELECT COUNT(*) FROM subscribers) as всего_пользователей,
    (SELECT COUNT(*) FROM subscribers WHERE subscription_active = true) as активных_подписок,
    (SELECT COUNT(*) FROM subscribers WHERE trial_until > NOW()) as активных_триалов,
    (SELECT COUNT(*) FROM messages) as всего_сообщений,
    (SELECT COUNT(*) FROM messages WHERE is_processed = false) as необработано_сообщений,
    (SELECT COUNT(*) FROM banned_users) as забанено;
"
```

---

## 🔧 Полезные команды

### Подключение к базе данных (интерактивный режим)

```bash
docker exec -it bali-postgres psql -U grishkoff -d bali_bot
```

После подключения вы можете выполнять SQL-запросы напрямую.

### Выход из psql
Внутри psql используйте команду:
```
\q
```

### Экспорт данных в CSV

```bash
docker exec bali-postgres psql -U grishkoff -d bali_bot -c "
COPY (SELECT * FROM subscribers) TO STDOUT WITH CSV HEADER;
" > subscribers_export.csv
```

### Количество записей в каждой таблице

```bash
docker exec bali-postgres psql -U grishkoff -d bali_bot -c "
SELECT 
    'subscribers' as таблица, COUNT(*) as записей FROM subscribers
UNION ALL
SELECT 'messages', COUNT(*) FROM messages
UNION ALL
SELECT 'payments', COUNT(*) FROM payments
UNION ALL
SELECT 'user_balance', COUNT(*) FROM user_balance
UNION ALL
SELECT 'banned_users', COUNT(*) FROM banned_users
UNION ALL
SELECT 'referrals', COUNT(*) FROM referrals;
"
```

---

## 🐳 Docker контейнеры

### Список запущенных контейнеров проекта

```bash
docker ps | grep -E "bali|mvp2105"
```

### Логи контейнера бота

```bash
docker logs bali-bot --tail 100 -f
```

### Логи контейнера мониторинга

```bash
docker logs bali-user-monitor --tail 100 -f
```

### Логи базы данных

```bash
docker logs bali-postgres --tail 100 -f
```

---

## 🔐 Учетные данные

- **База данных**: `bali_bot`
- **Пользователь**: `grishkoff`
- **Пароль**: `testpass`
- **Порт**: `5434` (внешний), `5432` (внутренний контейнера)
- **Контейнер**: `bali-postgres`

---

## 📝 Примечания

1. Все команды выполняются из любой директории на сервере
2. Для выполнения команд требуются права на работу с Docker
3. ID пользователя `210147380` - это администратор проекта (whitelisted)
4. Триал длится 7 дней с момента регистрации
5. Категории хранятся в формате JSONB для гибкости поиска
6. Время в базе данных хранится в UTC
















