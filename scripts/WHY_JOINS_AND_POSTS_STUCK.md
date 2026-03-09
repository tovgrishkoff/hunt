# Почему не идут вступления и посты (Bali)

## Цепочка причин

### 1. Вступления (new=0, joined_last_24h=0)

- **Очередь new=0** — нечего вступать. Finder при каждом слоте (05:00, 07:00, 09:00, 11:00 и др. Jakarta) ищет группы по ключевым словам; если все найденные чаты **уже есть в БД**, новых не добавляется.
- **Что сделано:** в `config/niches/bali.json` добавлен `manager.limit_per_keyword: 50` (было по умолчанию 20 в finder). В scheduler вызов finder передаёт этот лимит — при поиске будет браться до 50 результатов на ключевое слово, чаще появятся новые группы в статусе `new`.
- **Аккаунты для вступления:** account-manager использует только аккаунты с **niche=bali** (из `config/bali_accounts_config.json`). Если у части аккаунтов в БД **niche=NULL**, они не участвуют в поиске и вступлениях.  
  **Фикс:** `./scripts/fix_bali_accounts_niche_for_stories.sh` — выставляет niche=bali нужным аккаунтам.

### 2. Посты (ready=0)

- **ready** считается по группам с `status IN ('active','joined')`, прошедшим warm-up и с лимитом постов в день.
- В отчёте **postable_status=0** — нет ни одной группы в статусе **active** или **joined**. Все группы в других статусах: pending (198), inaccessible (105), no_accounts_left (73), read_only (54).
- Поэтому постер не находит готовых групп и постов нет.

**Откуда берутся active/joined:**

- Группы попадают в **active/joined** после успешного вступления (account-manager переводит `new` → `joined`/`active`).
- Сейчас вступлений нет (new=0), новых active/joined не появляется.
- Часть групп уже была переведена в **no_accounts_left** (все аккаунты для этой группы попали в блоклист, например «не участник»). Их можно **вернуть в игру**, сбросив блоклист и статус.

## Чеклист действий

1. **Разблокировать постинг для уже имеющихся групп (no_accounts_left → active, сброс блоклиста «не участник»):**
   ```bash
   cd /home/tovgrishkoff/PIAR/telegram_promotion_system_bali
   ./scripts/fix_bali_blocklist_for_posting.sh -y
   ```
   После этого 73 группы перейдут в `active`; постер снова будет пробовать в них постить.

2. **Разблокировать warm-up** (если группы active/joined есть, но все «в прогреве»):
   ```bash
   ./scripts/fix_bali_warmup_for_posting.sh -y
   ```

3. **Убедиться, что аккаунты участвуют в поиске и вступлениях (niche=bali):**
   ```bash
   ./scripts/fix_bali_accounts_niche_for_stories.sh
   ```

4. **Перезапустить account-manager**, чтобы подхватить новый `limit_per_keyword`:
   ```bash
   docker-compose restart account-manager
   ```

5. **Проверить логи:**
   - Вступления: `docker logs telegram-bali-account-manager --tail 200 | grep -E 'STEP 1|STEP 2|JOIN|joined|new|Найдено|FloodWait'`
   - Посты: `docker logs telegram-bali-marketer --tail 150 | grep -E 'ready|Found|Найдено|ошибк|error'`

6. **Повторная проверка:** `./scripts/daily_check.sh` — смотреть блоки 2a (new), 2a1 (joined_last_24h), 3 (ready_count), 4 (посты за 24 ч).

## Итог

- **Вступления:** new=0 из-за того, что finder не находил новых групп (все результаты уже в БД). Увеличен `limit_per_keyword` до 50 в конфиге Bali; после рестарта account-manager при поиске будет получать больше результатов и чаще добавлять группы в очередь `new`.
- **Посты:** ready=0 из-за отсутствия групп active/joined. После `fix_bali_blocklist_for_posting.sh` часть групп вернётся в active; при необходимости — `fix_bali_warmup_for_posting.sh`. Дальше посты появятся в ближайший слот marketer (08:00, 12:00, 15:00, 18:00 Jakarta).
