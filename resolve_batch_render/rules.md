# Resolve Batch Render — Rules

**Обновлено:** 2026-07-20

---

## 1. Secrets (не в git)

```
.env
output/upload_queue.sqlite3
output/pinterest_oauth.json
youtube_shorts_uploader/token.json
youtube_shorts_uploader/token_comments.json
youtube_shorts_uploader/token_7x7.json
```

---

## 2. Что куда (не путать)

| Артефакт | Назначение |
|----------|------------|
| `output/subtitles/*.srt` | **Внутрь видео** при монтаже, не в пост |
| `texts_kailas.csv` | Подпись **Instagram** |
| Whisper + OpenAI | Описание **YouTube** при publish |
| `post_texts/R###.txt` | Готовый IG caption |
| Notion | Журнал, даты, SEO |

---

## 3. Pipeline rules

1. **Ingest** не ставит слоты — только `schedule_crosspost.sh`
2. Один **reel_id** = все платформы в **один день**
3. `rebuild-texts` — только **неиспользованные** text_id из CSV
4. После успешного post: `R2_DELETE_AFTER_POST`, `LOCAL_DELETE_AFTER_POST` (осторожно при отладке)
5. IG token long-lived ~60 дней — проверять expiry

---

## 4. Docker / OOM

```bash
docker-compose -f docker-compose.autopost.yml up -d --build \
  reels-autopost yt-autopost pinterest-autopost
```

- Exit **137** / ffmpeg **-9** = OOM kill → `reels-autopost`/`yt-autopost`/`pinterest`/`tg-stories` ≥768m (10-bit HEVC)
- Feed temp names must be unique across containers (never PID-only); see `uploader/publish_media.py`
- `./Daily_REELS.sh` после каждого рестарта
- Volume `./:/app` — rebuild после изменения кода

---

## 5. Расписание env

```env
UPLOAD_TIMES=09:00,13:00,19:00
UPLOAD_YT_TIMES=10:00,14:00,20:00
UPLOAD_PINTEREST_TIMES=11:00,15:00,21:00
TZ=Europe/Moscow
CAPTION_SUFFIX=\n\nНапиши «КАЙЛАС»
```

---

## 6. Cron

```cron
# Ingest каждые 15 мин (без слотов)
*/15 * * * * .../scripts/ingest_new_reels.sh
```

После **новой партии** вручную один раз:

```bash
./scripts/schedule_crosspost.sh
docker exec reels-autopost python -m uploader.main --tz Europe/Moscow \
  sync-notion-schedule --min-reel-num 424
```

---

## 7. Pinterest OAuth

```bash
./scripts/pinterest_oauth.sh manual
# URL открывать на ноутбуке, code вставить на сервер
```

Scopes нужны: `boards:read boards:write pins:read pins:write user_accounts:read`

---

## 8. YouTube comments

- Отдельный token: `youtube.force-ssl` scope
- `YT_COMMENTS_DRY_RUN=0` только после проверки
- Profile: `docker compose --profile comments up -d yt-comments`
- Footer обязателен (brand links)

---

## 9. Локальный рендер checklist

1. `generate-plan` → `build-keyword-timeline`
2. Import SRT в Resolve
3. `render-batch` → `output/reels/R###.mov`
4. `scp` mov + `render_results.csv` на сервер
5. `./scripts/full_reels_pipeline.sh`

---

## 10. Документация

| Файл | Содержание |
|------|------------|
| `ARCHITECTURE.md` | Потоки, Docker, модули |
| `prd.md` | KPI, backlog |
| `rules.md` | Этот файл |
| `schema.md` | SQLite, CSV, paths |

Detailed ops: `README_AUTOPOSTING.md`, `uploader/README.md`
