# Resolve Batch Render — Architecture

**Путь:** `/home/tovgrishkoff/resolve_batch_render`  
**Обновлено:** 2026-07-20

> Документы: `prd.md` · `rules.md` · `schema.md`

---

## 1. Обзор

Reels-фабрика для travel-бренда **@grishkoff** (Kailas): монтаж в DaVinci Resolve → автопостинг **Instagram + YouTube Shorts + Pinterest** + YT comment bot.

```
┌─────────────────────────────────────────────────────────────┐
│  ЛОКАЛЬНО (Mac + Resolve)                                    │
│  reels_factory_main.py → R###.mov + render_results.csv      │
└───────────────────────────┬─────────────────────────────────┘
                            │ scp
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  СЕРВЕР: output/reels/                                       │
│  ingest → schedule_crosspost → Notion sync                    │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌──────────────┬──────────────┬──────────────┬─────────────────┐
│ reels-       │ yt-          │ pinterest-   │ yt-comments     │
│ autopost     │ autopost     │ autopost     │ (profile)       │
│ IG+R2+Graph  │ Whisper+GPT  │ video pin v5 │ auto-replies    │
└──────────────┴──────────────┴──────────────┴─────────────────┘
         upload_queue.sqlite3
```

**Связь:** `content_engine` → carousels/output; этот проект — **video Reels** pipeline.

---

## 2. Два контура

### A. Монтаж (локально)

| Шаг | Команда / артефакт |
|-----|-------------------|
| План | `reels_factory_main.py generate-plan` → `output/reels_plan*.csv` |
| Таймлайн | `build-keyword-timeline` → Resolve timelines + `output/subtitles/*.srt` |
| SRT | Импорт в Resolve **вручную** |
| Рендер | `render-batch` → `output/reels/R###.mov` + `render_results.csv` |

Каталоги: `clips_catalog_normalized.csv`, `music_catalog_normalized.csv`, `texts_kailas.csv`, `template_slots.csv`

### B. Автопостинг (сервер)

| Шаг | Скрипт / CLI |
|-----|--------------|
| Ingest | `scripts/ingest_new_reels.sh` → `post_texts/`, Notion |
| Schedule | `scripts/schedule_crosspost.sh` → 3/день IG+YT+Pinterest |
| Notion | `sync-notion-schedule` |
| Publish | Docker workers poll `upload_queue.sqlite3` |

---

## 3. Docker (`docker-compose.autopost.yml`)

| Контейнер | Команда | Роль |
|-----------|---------|------|
| `reels-autopost` | `autopost --interval-sec 30` | Instagram via R2 + Graph API |
| `yt-autopost` | `autopost-yt --interval-sec 30` | YT Shorts: Whisper → OpenAI → upload |
| `pinterest-autopost` | `autopost-pinterest --interval-sec 30` | Pinterest video pins |
| `yt-comments` | profile `comments` | YT comment auto-reply bot |

Resources: `mem_limit: 512m` (OOM 137 — риск для yt-autopost).

---

## 4. Расписание (default MSK)

| Слот | Instagram | YouTube | Pinterest |
|------|-----------|---------|-----------|
| Утро | 09:00 | 10:00 | 11:00 |
| Обед | 13:00 | 14:00 | 15:00 |
| Вечер | 19:00 | 20:00 | 21:00 |

**3 ролика/день** — один reel_id на все платформы в один календарный день.

---

## 5. Модули uploader/

| Модуль | Роль |
|--------|------|
| `main.py` | CLI hub (30+ commands) |
| `db.py` | SQLite queue |
| `ingest_reels.py` | New `.mov` → captions |
| `schedule_crosspost.py` | Multi-platform scheduling |
| `instagram_publisher.py` | IG Graph API |
| `youtube_publisher.py` | YT Shorts upload |
| `pinterest_publisher.py` | Pinterest API v5 |
| `notion_schedule_sync.py` | Notion «Журнал публикаций» |
| `ai_caption.py` | Whisper + OpenAI for `copy_*` |
| `yt_comments/` | Comment bot (OpenAI + footer) |

---

## 6. Структура каталогов

```
resolve_batch_render/
├── ARCHITECTURE.md
├── reels_factory_main.py      # Resolve montage CLI
├── uploader/                  # Autoposting
├── output/
│   ├── reels/                 # R###.mov, copy_*.MOV
│   ├── post_texts/            # IG captions
│   ├── transcripts/           # Whisper cache
│   ├── upload_queue.sqlite3   # Queue
│   └── pinterest_oauth.json
├── texts_kailas.csv           # IG text pool T001+
├── youtube_shorts_uploader/   # OAuth tokens
├── scripts/                   # ingest, schedule, oauth
├── docker-compose.autopost.yml
├── Daily_REELS.sh             # Health check
└── montage/                   # Resolve docs
```

---

## 7. Команды

```bash
cd /home/tovgrishkoff/resolve_batch_render

# Health
./Daily_REELS.sh

# Docker
docker-compose -f docker-compose.autopost.yml up -d --build \
  reels-autopost yt-autopost pinterest-autopost

# Full pipeline new batch
./scripts/full_reels_pipeline.sh 2026-07-21

# Queue
docker exec reels-autopost python -m uploader.main --tz Asia/Makassar today
docker exec reels-autopost python -m uploader.main --tz Asia/Makassar next-due-summary

# YT comments
docker-compose -f docker-compose.autopost.yml --profile comments up -d yt-comments
```

---

## 8. Связанные проекты

| Проект | Связь |
|--------|-------|
| `content_engine` | Carousels/static content → R2 (shared keys) |
| SCOUT_HOTELS | Kailas lead gen (отдельно) |
| PIAR / Lead Hunter | Telegram traffic |

Legacy docs: `README_AUTOPOSTING.md`, `README_REELS.md`, `Resolve_Batch_Render_handoff.md` — архив.
