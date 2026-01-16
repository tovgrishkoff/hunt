# 🚀 Быстрый старт системы Ukraine/Lexus

## ✅ Текущий статус

- ✅ БД инициализирована (3 таблицы)
- ✅ 3 аккаунта добавлены
- ✅ 480 групп добавлены (статус: `new`)
- ✅ Контейнеры запущены

## 🚀 Запуск Scout и Smart Joiner

### Вариант 1: Ручной тестовый запуск (рекомендуется для начала)

```bash
# 1. Тест Scout (поиск новых групп)
./scripts/monitoring/test_scout.sh ukraine_cars

# 2. Тест Smart Joiner (вступление в группы)
./scripts/monitoring/test_joiner.sh ukraine_cars 3
```

### Вариант 2: Прямой запуск через docker exec

```bash
# Scout
docker exec ukraine-account-manager python3 services/account-manager/scout.py ukraine_cars

# Smart Joiner (вступить в 5 групп)
docker exec ukraine-account-manager python3 services/account-manager/smart_joiner.py ukraine_cars 5
```

### Вариант 3: Автоматизация через Cron

```bash
# Установить Cron задачи
./install-cron.sh

# Или вручную
crontab crontab.ukraine
```

## 📊 Проверка результатов

### Проверка статуса системы
```bash
./scripts/monitoring/check_ukraine_status.sh
```

### Проверка групп (куда вступили)
```bash
./scripts/monitoring/check_ukraine_groups.sh
```

### Проверка аккаунтов
```bash
./scripts/monitoring/check_ukraine_accounts.sh
```

### Проверка логов
```bash
# Логи account-manager
docker logs ukraine-account-manager --tail=100

# Следить за логами в реальном времени
docker logs -f ukraine-account-manager
```

## 🔄 Типичный цикл работы

1. **Scout** находит новые группы → добавляет в БД со статусом `new`
2. **Smart Joiner** берет группы со статусом `new` → вступает → меняет статус на `joined`
3. После 24 часов warm-up → группы готовы для постинга
4. **Marketer** постит в готовые группы (через Cron)

## ⚙️ Настройка Cron (автоматизация)

Согласно `crontab.ukraine`:
- **Scout**: каждые 2 часа (в 00 и 30 минут)
- **Smart Joiner**: каждые 2 часа (в 15 и 45 минут)
- **Marketer**: по расписанию (утро/вечер)

## 📋 Команды для быстрой проверки

```bash
# Общий статус
./scripts/monitoring/check_ukraine_status.sh

# Сколько групп готово к вступлению
docker exec ukraine-postgres psql -U telegram_user_ukraine -d ukraine_db -c "
SELECT COUNT(*) as new_groups FROM targets WHERE status = 'new' AND niche = 'ukraine_cars';
"

# Сколько групп уже вступили
docker exec ukraine-postgres psql -U telegram_user_ukraine -d ukraine_db -c "
SELECT COUNT(*) as joined_groups FROM targets WHERE status = 'joined' AND niche = 'ukraine_cars';
"

# Последние вступления
docker exec ukraine-postgres psql -U telegram_user_ukraine -d ukraine_db -c "
SELECT 
    TO_CHAR(joined_at, 'YYYY-MM-DD HH24:MI:SS') as joined_time,
    link as group_link,
    (SELECT session_name FROM accounts WHERE id = assigned_account_id) as account
FROM targets 
WHERE status = 'joined' AND niche = 'ukraine_cars'
ORDER BY joined_at DESC
LIMIT 10;
"
```

---

*Система готова к работе!* 🎉
