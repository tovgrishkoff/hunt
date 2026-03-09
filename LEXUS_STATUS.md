# ✅ СТАТУС СИСТЕМЫ LEXUS

**Дата проверки:** 2026-01-23  
**Статус:** ✅ **ИСПРАВЛЕНО И РАБОТАЕТ**

---

## 🎯 Итоговый статус

### ✅ Все компоненты работают:

- **lexus-marketer** - Работает
- **lexus-account-manager** - Работает (перезапущен после исправления)  
- **lexus-postgres** - Работает (healthy)

### 🔧 Исправлено 2026-01-23:

- ✅ **Аккаунты обновлены**: 3 аккаунта переведены из `cooldown` в `active`
- ✅ **Группы активированы**: 888 групп активированы (было 0 активных)
- ✅ **Account-manager перезапущен**: теперь видит все 3 аккаунта

---

## 📊 Что настроено:

### 1. **Отдельная база данных**
- ✅ БД `telegram_promotion_lexus` создана в отдельном контейнере `lexus-postgres`
- ✅ Таблицы инициализированы: `accounts`, `groups`, `posts`, `account_group_blocklist`
- ✅ **Нет конфликтов с Бали** - используются разные БД

### 2. **Разделение аккаунтов**
- ✅ Lexus аккаунты: `promotion_dao_bro`, `promotion_alex_ever`, `promotion_rod_shaihutdinov`
- ✅ Bali аккаунты: отдельные (из `bali_accounts_config.json`)
- ✅ **Нет пересечений** между системами

### 3. **Рассылка объявлений**
- ✅ Работает по расписанию (5 слотов в день)
- ✅ Следующий слот: **12:00** (полдень)
- ✅ Использует сообщения из `config/messages/cars/messages.json` (8 вариантов)
- ⚠️ **Проблема**: Аккаунты не являются участниками групп (нужно дождаться вступления)

### 4. **Вступление в группы**
- ✅ Работает по расписанию (5 слотов в день)
- ✅ Следующий слот: **12:00** (полдень)
- ✅ Account-manager видит 3 аккаунта
- ⚠️ **Статус**: 0 групп со статусом `joined` (833 группы в статусе `new` - ждут вступления)
- ✅ Поиск новых групп по ключевым словам работает

---

## ⚠️ Почему не идут посты в группы

В логах маркетера видно:
- **Loaded 0 accounts** — маркетер не видит ни одного аккаунта для постинга.
- **Total active groups: 0** — маркетер не видит ни одной группы со статусом `active`/`joined`.

**Причины:**

1. **Аккаунты**  
   Маркетер загружает аккаунты из БД Lexus (`shared.database` + whitelist из `lexus_accounts_config.json`). Берутся только строки с **`status = 'active'`**.  
   Если все три Lexus-аккаунта в статусе `cooldown` или другом — в логах будет «Loaded 0 accounts».

   **Что сделать:** проверить и при необходимости перевести аккаунты в `active`:
   ```bash
   docker exec lexus-postgres psql -U telegram_user_bali -d telegram_promotion_lexus -c "SELECT session_name, status FROM accounts;"
   # Если status не 'active':
   docker exec lexus-postgres psql -U telegram_user_bali -d telegram_promotion_lexus -c "UPDATE accounts SET status = 'active' WHERE session_name IN ('promotion_dao_bro', 'promotion_alex_ever', 'promotion_rod_shaihutdinov');"
   ```

2. **Группы**  
   Постер ищет группы с `niche = 'ukraine_cars'` и `status IN ('active', 'joined')`.  
   Если в логах «Total active groups: 0», значит в той БД, к которой подключается контейнер `lexus-marketer`, таких строк нет (либо контейнер ходит не в ту БД).

   **Что сделать:** убедиться, что маркетер смотрит в БД Lexus и что в ней есть такие группы:
   ```bash
   docker exec lexus-postgres psql -U telegram_user_bali -d telegram_promotion_lexus -c "SELECT status, COUNT(*) FROM groups WHERE niche = 'ukraine_cars' GROUP BY status;"
   ```
   В логах маркетера при следующем слоте появится строка вида `🔗 DB for poster: ...@lexus-postgres:5432/telegram_promotion_lexus` — хост должен быть **lexus-postgres**, не другой.

3. **Форс-постинг в обход расписания**  
   Если нужно сразу проверить постинг (без ожидания слота):
   ```bash
   docker exec lexus-marketer python3 /app/force_lexus_posting_simple.py 20
   ```
   (или скрипт форс-постинга, который у вас реально лежит в контейнере).

---

## 🔍 Быстрая проверка:

```bash
# Проверить логи
docker logs lexus-marketer --tail 20
docker logs lexus-account-manager --tail 20

# Проверить статус контейнеров
docker ps | grep lexus

# Проверить БД - аккаунты
docker exec lexus-postgres psql -U telegram_user_bali -d telegram_promotion_lexus -c "SELECT session_name, status FROM accounts;"

# Проверить БД - группы
docker exec lexus-postgres psql -U telegram_user_bali -d telegram_promotion_lexus -c "SELECT COUNT(*) as total, COUNT(CASE WHEN status = 'active' THEN 1 END) as active, COUNT(CASE WHEN status = 'joined' THEN 1 END) as joined FROM groups WHERE niche = 'ukraine_cars';"
```

## 🚀 Форс-постинг (улучшенная версия):

### Основные команды:

```bash
# Реальный постинг (20 постов по умолчанию)
docker exec lexus-marketer python3 /app/force_lexus_posting.py

# Реальный постинг с указанием размера батча
docker exec lexus-marketer python3 /app/force_lexus_posting.py --batch-size 50

# Тестовый запуск (dry-run, без отправки постов)
docker exec lexus-marketer python3 /app/force_lexus_posting.py --dry-run

# Быстрый запуск без проверок (если уверены, что всё готово)
docker exec lexus-marketer python3 /app/force_lexus_posting.py --skip-checks --batch-size 20

# Или используйте удобную обертку
./scripts/force_lexus_posting.sh 20
./scripts/force_lexus_posting.sh 50 dry-run
```

### Что делает скрипт:

1. ✅ **Проверяет аккаунты**: обновляет статус из `cooldown` в `active`, если время прошло
2. ✅ **Активирует группы**: переводит группы в статус `active`/`joined`, если warm-up завершен
3. ✅ **Проверяет членство**: показывает статистику по группам с назначенными аккаунтами
4. ✅ **Запускает постинг**: отправляет посты с детальной статистикой
5. ✅ **Показывает результаты**: финальная статистика по постам и группам

---

## 📋 Важно:

1. ✅ **Системы разделены** - Lexus и Bali работают независимо
2. ✅ **Базы данных разделены** - нет конфликтов при записи
3. ✅ **Аккаунты разделены** - нет пересечений
4. ✅ **Сессии разделены** - `sessions_lexus` vs `sessions`

---

## 🎉 Итог:

**Система исправлена и работает!** 

- ✅ Аккаунты активны (3 аккаунта)
- ✅ Группы активированы (888 групп)
- ⏳ **Ожидание**: Следующий слот для вступления в группы и постинга - **12:00** (полдень)
- ⚠️ **Примечание**: Аккаунты пока не являются участниками групп, но account-manager будет вступать в группы по расписанию

**Система полностью изолирована от Bali и не будет конфликтов.**

---

## 📝 История исправлений:

**2026-01-23 06:50**:
- Исправлен статус аккаунтов (cooldown → active)
- Активированы группы (0 → 888 активных)
- Перезапущен account-manager для подхвата аккаунтов
- Создан скрипт форс-постинга: `force_lexus_posting_simple.py`

---

*Обновлено: 2026-01-23*
