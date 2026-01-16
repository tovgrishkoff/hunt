# 🧪 РУКОВОДСТВО ПО ТЕСТИРОВАНИЮ

## ⚠️ ВАЖНО: ВСЕГДА ТЕСТИРУЙТЕ ПЕРЕД РАССЫЛКОЙ!

**Правило:** Перед каждой рассылкой **ОБЯЗАТЕЛЬНО** делайте быстрый тест всех узлов системы в тестовой группе.

---

## 🎯 Тестовая группа

**Группа для всех тестов:** [@supergruppalexus](https://t.me/supergruppalexus)

В эту группу можно вступать и писать **каждым аккаунтом** для тестирования.

---

## 🎯 Быстрый тест всех узлов

### 1. Запуск полного теста

```bash
cd /home/tovgrishkoff/PIAR/telegram_promotion_system_bali

# Используется тестовая группа @supergruppalexus по умолчанию
DATABASE_URL=postgresql://telegram_user_bali:telegram_password_bali@localhost:5438/telegram_promotion_bali \
python3 scripts/quick_test_all.py

# Или укажите другую группу
DATABASE_URL=postgresql://telegram_user_bali:telegram_password_bali@localhost:5438/telegram_promotion_bali \
python3 scripts/quick_test_all.py --test-group @your_test_group
```

### 2. Что тестирует скрипт:

1. ✅ **БД** - подключение и наличие данных
2. ✅ **Конфигурация** - загрузка конфига ниши и сообщений
3. ✅ **Аккаунты** - подключение всех аккаунтов
4. ✅ **Тестовая группа** - создание/проверка группы
5. ✅ **Account Manager** - поиск и вступление в группы
6. ✅ **Marketer** - постинг тестового сообщения
7. ✅ **Secretary** - генерация ответов GPT

---

## 📋 Пошаговое тестирование вручную

### Шаг 1: Тест постинга (Marketer)

```bash
cd /home/tovgrishkoff/PIAR/telegram_promotion_system_bali

DATABASE_URL=postgresql://telegram_user_bali:telegram_password_bali@localhost:5438/telegram_promotion_bali \
python3 scripts/force_run.py --service marketer --group @supergruppalexus
```

**Что проверить:**
- ✅ Сообщение отправлено в тестовую группу
- ✅ Сообщение выглядит правильно
- ✅ Нет ошибок в логах

### Шаг 2: Тест Account Manager (поиск групп)

```bash
DATABASE_URL=postgresql://telegram_user_bali:telegram_password_bali@localhost:5438/telegram_promotion_bali \
python3 scripts/force_run.py --service manager --keyword "bali rent"
```

**Что проверить:**
- ✅ Находит группы по ключевым словам
- ✅ Сохраняет их в БД

### Шаг 3: Тест вступления в группу

```bash
DATABASE_URL=postgresql://telegram_user_bali:telegram_password_bali@localhost:5438/telegram_promotion_bali \
python3 scripts/force_run.py --service manager --join-group --group @supergruppalexus
```

**Что проверить:**
- ✅ Успешно вступает в группу
- ✅ Статус группы меняется на `active`
- ✅ Warm-up период установлен

### Шаг 4: Тест Secretary (GPT ответы)

```bash
DATABASE_URL=postgresql://telegram_user_bali:telegram_password_bali@localhost:5438/telegram_promotion_bali \
python3 scripts/force_run.py --service secretary
```

**Что проверить:**
- ✅ GPT генерирует ответы
- ✅ Ответы соответствуют конфигу
- ✅ Упоминается @Lead_Hunbot

---

## 🔍 Проверка логов

### Просмотр логов всех сервисов:

```bash
cd /home/tovgrishkoff/PIAR/telegram_promotion_system_bali

# Marketer
docker-compose logs --tail=50 marketer

# Account Manager
docker-compose logs --tail=50 account-manager

# Secretary
docker-compose logs --tail=50 secretary

# Activity
docker-compose logs --tail=50 activity
```

### Проверка постов в БД:

```bash
docker-compose exec -T postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT 
    COUNT(*) as total,
    COUNT(CASE WHEN success = true THEN 1 END) as successful,
    COUNT(CASE WHEN success = false THEN 1 END) as failed,
    MAX(sent_at) as last_post
FROM posts 
WHERE DATE(sent_at) = CURRENT_DATE;
"
```

---

## ⚙️ Настройка тестовой группы

### Добавить тестовую группу в БД:

```bash
# Тестовая группа уже добавлена: @supergruppalexus
# Если нужно добавить другую:
DATABASE_URL=postgresql://telegram_user_bali:telegram_password_bali@localhost:5438/telegram_promotion_bali \
python3 scripts/force_run.py --service manager --add-group --group @supergruppalexus --niche bali
```

### Убедитесь, что группа готова к тестированию:

```bash
docker-compose exec -T postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT username, status, can_post, warm_up_until 
FROM groups 
WHERE username = '@supergruppalexus';
"
```

**Проверьте:**
- `status` = `active`
- `can_post` = `true`
- `warm_up_until` = `NULL` (или прошедшая дата)

---

## 🚨 Типичные проблемы

### 1. "No messages available"
**Решение:** Проверьте, что `config/messages/bali/messages.json` существует и содержит сообщения

### 2. "No groups available"
**Решение:** 
- Убедитесь, что группы со статусом `active`
- Проверьте, что `warm_up_until` прошла или `NULL`

### 3. "Client not connected"
**Решение:** Перезапустите сервис:
```bash
docker-compose restart marketer account-manager
```

### 4. "OPENAI_API_KEY not found"
**Решение:** Проверьте `.env` файл и перезапустите secretary:
```bash
docker-compose restart secretary
```

---

## ✅ Чеклист перед запуском рассылки

- [ ] Запущен быстрый тест всех узлов
- [ ] Тестовый пост отправлен в тестовую группу
- [ ] Сообщение выглядит правильно
- [ ] Secretary отвечает на тестовые сообщения
- [ ] Нет ошибок в логах
- [ ] Аккаунты подключены и работают
- [ ] Конфигурация загружается корректно
- [ ] Есть активные группы для постинга

**Только после прохождения всех проверок запускайте рассылку!**

---

*Обновлено: 2026-01-09*
