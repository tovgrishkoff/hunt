# Автопостинг Reels: Instagram + YouTube Shorts + Pinterest

Пайплайн на сервере: залил видео в `output/reels/` → подписи → расписание → Notion → публикация в фоне.

Связанные файлы:
- `uploader/README.md` — низкоуровневые CLI-команды
- `README.md` — монтаж и рендер в Resolve
- `Daily_REELS.sh` — проверка контейнеров и очереди

---

## Схема

```
output/reels/R###.mov
        │
        ▼
  ingest_new_reels.sh     ← подписи IG, post_texts/, Notion (без слотов)
        │
        ▼
  schedule_crosspost.sh   ← 3 ролика/день, IG + YT + Pinterest
        │
        ▼
  sync-notion-schedule    ← даты в Notion, опционально SEO YT (--yt-preview)
        │
        ▼
  reels-autopost + yt-autopost + pinterest-autopost   ← Docker
```

---

## Что куда (не путать)

| Что | Куда идёт |
|-----|-----------|
| `output/subtitles/*.srt` | только **внутрь видео** при монтаже, **не** в пост |
| `texts_kailas.csv` | подпись **Instagram** |
| Whisper + OpenAI | описание **YouTube** при публикации (уникально под ролик) |
| Notion «Журнал публикаций» | даты, IG-описание, при `--yt-preview` — SEO/теги YT |

---

## Файлы на сервере

| Путь | Назначение |
|------|------------|
| `output/reels/R###.mov` | готовые ролики (`имя = reel_id`) |
| `texts_kailas.csv` | тексты для Instagram |
| `output/render_results.csv` | (желательно) `reel_id` → `text_id` с локального рендера |
| `output/reels_plan_*.csv` | (опционально) план партии с `text_id` |
| `output/post_texts/R###.txt` | готовые подписи IG (генерируются автоматически) |
| `output/upload_queue.sqlite3` | очередь публикаций |
| `.env` | токены IG, R2, OpenAI, Notion |

---

## Расписание по умолчанию

**3 ролика в день**, один ролик в один день на **все** платформы:

| Слот | Instagram | YouTube Shorts | Pinterest |
|------|-----------|----------------|-----------|
| Утро | 09:00 МСК | 10:00 | 11:00 |
| Обед | 13:00 | 14:00 | 15:00 |
| Вечер | 19:00 | 20:00 | 21:00 |

Pinterest попадает в очередь только если в `.env` заданы `PINTEREST_ACCESS_TOKEN` и `PINTEREST_BOARD_ID`.

13 роликов ≈ 5 календарных дней.

Переопределение в `.env`:

```env
UPLOAD_TIMES=09:00,13:00,19:00
UPLOAD_YT_TIMES=10:00,14:00,20:00
UPLOAD_PINTEREST_TIMES=11:00,15:00,21:00
TZ=Asia/Makassar
```

---

## Быстрый старт (новая партия)

### 1. Залить на сервер

```bash
# с локальной машины
scp output/reels/R4*.mov server:~/resolve_batch_render/output/reels/
scp output/render_results.csv server:~/resolve_batch_render/output/   # желательно
```

### 2. Полный пайплайн

```bash
cd ~/resolve_batch_render
./scripts/full_reels_pipeline.sh              # расписание с сегодня
./scripts/full_reels_pipeline.sh 2026-05-20    # с указанной даты
```

Или по шагам:

```bash
# A) Подписи IG + Notion (без слотов в очереди)
./scripts/ingest_new_reels.sh

# B) Уникальные тексты (если не было render_results / плана)
docker exec reels-autopost python -m uploader.main --tz Asia/Makassar \
  rebuild-texts --min-reel-num 411

# C) Расписание IG + YT
./scripts/schedule_crosspost.sh 2026-05-16

# D) Notion: даты + описания
docker exec reels-autopost python -m uploader.main --tz Asia/Makassar \
  sync-notion-schedule --min-reel-num 411

# E) SEO YouTube в Notion заранее (долго, ~2 мин/ролик)
docker exec reels-autopost python -m uploader.main --tz Asia/Makassar \
  sync-notion-schedule --min-reel-num 411 --yt-preview
```

### 3. Проверка

```bash
./Daily_REELS.sh

docker exec reels-autopost python -m uploader.main --tz Asia/Makassar today
docker exec reels-autopost python -m uploader.main --tz Asia/Makassar next-due-summary
```

---

## Pinterest Standard — видео для заявки

Пошаговый сценарий записи экрана: [PINTEREST_DEMO_SCRIPT.md](PINTEREST_DEMO_SCRIPT.md)

---

## Docker (продакшен)

```bash
docker compose -f docker-compose.autopost.yml up -d reels-autopost yt-autopost pinterest-autopost
```

| Контейнер | Роль |
|-----------|------|
| `reels-autopost` | Instagram: очередь → R2 → Graph API |
| `yt-autopost` | YouTube: Whisper → OpenAI → Shorts API |
| `pinterest-autopost` | Pinterest: video pin через API v5 |

Перезапуск после изменения кода (volume `./` смонтирован):

```bash
docker compose -f docker-compose.autopost.yml up -d --build reels-autopost yt-autopost pinterest-autopost
```

---

## Откуда берётся text_id (Instagram)

Приоритет при `ingest-reels` / `rebuild-texts`:

1. `output/render_results.csv` (с локалки после рендера)
2. Sidecar: `output/post_meta/R421.json` → `{"text_id": "T015"}`
3. Имя файла: `R421_T015.mov`
4. `output/reels_plan_kailas_*.csv`
5. Авто: R411→T002, R412→T003… (только если нет плана; **не** повторяет уже опубликованные — см. `rebuild-texts`)

`rebuild-texts` назначает тексты из `texts_kailas.csv`, которые **ещё не были** в опубликованных IG-постах, и пишет `output/reels_plan_auto_ingest.csv`.

> В CSV сейчас **30 текстов** (T001–T030). На партию >10 новых роликов добавь **T031+** в `texts_kailas.csv`.

---

## Переменные `.env` (основные)

```env
# Instagram
IG_USER_ID=
IG_ACCESS_TOKEN=
IG_USERNAME=grishkoff

# R2 (публичный URL для IG API)
R2_ACCOUNT_ID=
R2_BUCKET=ig-media
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_PUBLIC_BASE_URL=
R2_AUTUPLOAD=1
R2_DELETE_AFTER_POST=1

# YouTube
OPENAI_API_KEY=
AUDIO_DIR=output/audio
YOUTUBE_PRIVACY_STATUS=unlisted

# Notion — журнал публикаций
NOTION_TOKEN=
NOTION_DATABASE_ID=

# Pinterest
PINTEREST_ACCESS_TOKEN=31c23cea93ee036f8e5a2a50d819ff7459ceef26
PINTEREST_BOARD_ID=1568734
UPLOAD_PINTEREST_TIMES=11:00,15:00,21:00
PINTEREST_DEFAULT_LINK=https://www.instagram.com/grishkoff/

# Расписание
UPLOAD_TIMES=09:00,13:00,19:00
UPLOAD_YT_TIMES=10:00,14:00,20:00
TZ=Asia/Makassar

# Ingest (опционально)
INGEST_PLAN_CSV=output/reels_plan_kailas_R411_R420.csv
INGEST_NOTION_PREFILL=1
INGEST_AUTO_PLAN_IG=0          # слоты только через schedule-crosspost.sh
INGEST_YT_PREVIEW=0

# Бренд в подписи IG
CAPTION_SUFFIX=
BRAND_SITE=
BRAND_INSTAGRAM=
BRAND_TELEGRAM=
BRAND_YOUTUBE=
```

---

## CLI (внутри Docker)

```bash
docker exec reels-autopost python -m uploader.main --tz Asia/Makassar <команда>
```

| Команда | Назначение |
|---------|------------|
| `ingest-reels` | новые `.mov` → `post_texts/`, Notion |
| `rebuild-texts` | заново назначить **неиспользованные** тексты IG |
| `schedule-crosspost` | 3/день IG+YT+Pinterest, разнести по дням |
| `autopost-pinterest` | фоновая публикация Pinterest |
| `sync-notion-schedule` | даты и описания в Notion |
| `today` | что запланировано на сегодня |
| `next-due-summary` | следующий слот по платформам |
| `mark-posted --reel-id R411` | отметить вручную после ручного поста |

Пример перепланирования партии R411+:

```bash
docker exec reels-autopost python -m uploader.main --tz Asia/Makassar \
  rebuild-texts --min-reel-num 411

docker exec reels-autopost python -m uploader.main --tz Asia/Makassar \
  schedule-crosspost --start-day 2026-05-16 --min-reel-num 411
  # после добавления PINTEREST_* в .env — перезапустить schedule-crosspost

docker exec reels-autopost python -m uploader.main --tz Asia/Makassar \
  sync-notion-schedule --min-reel-num 411
```

---

## Cron (авто после заливки)

```cron
# Каждые 15 мин: новые файлы → ingest (без слотов)
*/15 * * * * /home/tovgrishkoff/resolve_batch_render/scripts/ingest_new_reels.sh >> /home/tovgrishkoff/resolve_batch_render/output/logs/ingest.log 2>&1
```

После каждой новой партии **один раз вручную**:

```bash
./scripts/schedule_crosspost.sh
docker exec reels-autopost python -m uploader.main --tz Asia/Makassar sync-notion-schedule --min-reel-num 411
```

---

## Notion

База: **«Журнал публикаций соцсетей»**.

- Платформа Instagram / **YouTube Shorts** (именно так в select)
- «Запланировано на» — из очереди (`sync-notion-schedule`)
- «Описание» — из `post_texts/R###.txt`
- «SEO ключи», «Транскрипт», «Теги» — при `--yt-preview` или при публикации YT

`ingest` **не** обновляет даты — только `sync-notion-schedule`.

---

## Типичные ошибки

| Проблема | Решение |
|----------|---------|
| Notion не обновился | `sync-notion-schedule`, не только `ingest` |
| `YouTube` not found в Notion | в коде должно быть **YouTube Shorts** (исправлено) |
| Все ролики на один день | `./scripts/schedule_crosspost.sh <дата>` |
| Нет YouTube в очереди | `schedule-crosspost` (ingest не ставит YT) |
| Повтор текста IG | `rebuild-texts` + добавить T031+ в `texts_kailas.csv` |
| IG API не видит файл | `R2_AUTUPLOAD=1`, проверить R2 |
| YT без описания | `OPENAI_API_KEY`, `youtube_shorts_uploader/token.json` |
| `No plan CSV for R411` | не нужен план: `ingest-reels` + `render_results.csv` или `rebuild-texts` |

---

## Локальный рендер (кратко)

Полная инструкция: `README.md`, `montage/README.md`.

```bash
python3 reels_factory_main.py generate-plan ... --out-plan output/reels_plan_kailas_R411_R420.csv
python3 reels_factory_main.py build-keyword-timeline --plan ... --reel-id ALL --recreate
# импорт SRT в Resolve вручную
python3 reels_factory_main.py render-batch --plan ... --reel-id ALL
```

После рендера залить `output/reels/*.mov` и `output/render_results.csv` на сервер.

---

## Скрипты

| Скрипт | Действие |
|--------|----------|
| `scripts/ingest_new_reels.sh` | новые видео → тексты + Notion |
| `scripts/schedule_crosspost.sh [YYYY-MM-DD]` | расписание 3/день IG+YT |
| `scripts/full_reels_pipeline.sh [YYYY-MM-DD]` | ingest + schedule + notion |
| `Daily_REELS.sh` | health-check контейнеров и очереди |
