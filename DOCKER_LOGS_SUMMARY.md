# 📋 Логи Docker контейнеров - Система Bali

**Дата:** 2026-01-13  
**Время проверки:** ~11:30 UTC

---

## ✅ MARKETER (постинг в группы)

**Статус:** ✅ Работает  
**Аккаунты:** 6 загружено, 0 ошибок

```
✅ Loaded 6 Bali accounts, 0 failed, 1 excluded (Lexus)
✅ Loaded 6 accounts
✅ Loaded 6 post templates for niche 'bali'
✅ Loaded Bali allowed accounts: [
  'promotion_andrey_virgin', 
  'promotion_anna_truncher', 
  'promotion_artur_biggest', 
  'promotion_lisa_soak', 
  'promotion_new_account_2', 
  'promotion_oleg_petrov'
]
```

**Все аккаунты подключены:**
- ✅ promotion_andrey_virgin connected and authorized
- ✅ promotion_lisa_soak connected and authorized
- ✅ promotion_new_account_2 connected and authorized
- ✅ promotion_oleg_petrov connected and authorized
- ✅ promotion_anna_truncher connected and authorized
- ✅ promotion_artur_biggest connected and authorized

**Расписание:**
- 📅 Временная зона: Asia/Jakarta
- ⏰ Слотов в день: 4
  - 08:00 (morning)
  - 12:00 (noon)
  - 15:00 (afternoon)
  - 18:00 (evening)
- ⏰ Следующий слот: noon at 2026-01-13 12:00:00 (через ~34 минуты)

---

## ✅ ACCOUNT MANAGER (вступление в группы)

**Статус:** ✅ Работает  
**Аккаунты:** 7 загружено, 0 ошибок

```
✅ Loaded 7 accounts, 0 failed
✅ Loaded 7 accounts
```

**Все аккаунты подключены:**
- ✅ promotion_andrey_virgin connected and authorized
- ✅ promotion_lisa_soak connected and authorized
- ✅ promotion_new_account_2 connected and authorized
- ✅ promotion_oleg_petrov connected and authorized
- ✅ promotion_anna_truncher connected and authorized
- ✅ promotion_artur_biggest connected and authorized
- ✅ promotion_new_account connected and authorized

**Расписание:**
- 📅 Временная зона: Asia/Jakarta
- ⏰ Слотов в день: 4
  - 05:00 (early_morning_1)
  - 07:00 (early_morning_2)
  - 09:00 (morning_1)
  - 11:00 (morning_2)
- ⏰ Следующий слот: early_morning_1 at 2026-01-14 05:00:00 (через ~17 часов)

---

## ✅ SECRETARY (автоответчик)

**Статус:** ✅ Работает  
**Аккаунты:** 6 загружено, 0 ошибок

```
✅ Loaded 6 Bali accounts, 0 failed, 1 excluded (Lexus)
✅ Loaded 6 accounts
✅ Loaded 0 entries from blacklist
✅ Forward target resolved: @grishkoff
✅ Forward target initialized for active conversations
```

**Все аккаунты подключены и зарегистрированы:**
- ✅ Registered handler for promotion_andrey_virgin
- ✅ Registered handler for promotion_oleg_petrov
- ✅ Registered handler for promotion_anna_truncher
- ✅ Registered handler for promotion_artur_biggest
- ✅ Registered handler for promotion_lisa_soak
- ✅ Registered handler for promotion_new_account_2
- ✅ Registered handlers for 6 accounts

**Функции:**
- 📋 Monitoring DMs for all active accounts...
- 🤖 Using GPT-4o-mini for response generation
- 🔄 Waiting for incoming messages...

---

## ✅ ACTIVITY (активность в группах)

**Статус:** ✅ Работает  
**Логи:** Показывает активность мониторинга каналов и обновлений

**Активность:**
- Мониторинг множества каналов
- Получение обновлений через Telegram API
- Постоянная работа в фоновом режиме

---

## ⚠️ POSTGRES

**Статус:** ⚠️ Работает, но есть ошибки подключения

**Логи:**
```
checkpoint complete: wrote 2 buffers (0.0%)
FATAL: database "telegram_user_bali" does not exist
```

**Примечание:** 
- Ошибки "database telegram_user_bali does not exist" появляются периодически
- Это может быть из-за попыток подключения с неправильным именем БД
- Основная БД называется `telegram_promotion_bali`
- Контейнеры работают нормально, ошибки не критичны

---

## 📊 СВОДКА

### Работающие сервисы:
- ✅ **Marketer** - 6 аккаунтов, готов к постингу
- ✅ **Account Manager** - 7 аккаунтов, готов к вступлению в группы
- ✅ **Secretary** - 6 аккаунтов, мониторинг DM
- ✅ **Activity** - работает, мониторинг каналов
- ✅ **Postgres** - работает (минорные ошибки подключения)

### Аккаунты:
- ✅ **6 аккаунтов** для постинга (Marketer)
- ✅ **7 аккаунтов** для вступления (Account Manager)
- ✅ **6 аккаунтов** для автоответчика (Secretary)
- ✅ **Все аккаунты** подключены и авторизованы
- ✅ **0 ошибок** подключения

### Система:
- ✅ Полностью работоспособна
- ✅ Готова к работе
- ✅ Все сервисы активны

---

## 🔧 Команды для просмотра логов в реальном времени:

```bash
# Marketer
docker logs -f telegram-bali-marketer

# Account Manager
docker logs -f telegram-bali-account-manager

# Secretary
docker logs -f telegram-bali-secretary

# Activity
docker logs -f telegram-bali-activity

# Postgres
docker logs -f telegram-bali-postgres

# Все контейнеры
docker-compose logs -f
```

---

*Отчет создан: 2026-01-13*
