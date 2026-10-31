# Resolve Batch Render — Schema

**Обновлено:** 2026-07-20

---

## 1. SQLite — `output/upload_queue.sqlite3`

### Table: `upload_queue`

| Column | Type | Description |
|--------|------|-------------|
| reel_id | TEXT | R411, COPY_xxx — PK part |
| scheduled_at | TEXT | ISO datetime TZ — PK part |
| video_path | TEXT | Local path to .mov |
| platform | TEXT | instagram \| youtube \| pinterest |
| caption | TEXT | IG caption or derived |
| status | TEXT | planned \| posted \| skipped |
| r2_key | TEXT | Cloudflare R2 object key |
| video_url | TEXT | Public URL for IG API |
| yt_video_id | TEXT | YouTube video ID |
| yt_video_url | TEXT | YouTube watch URL |
| source | TEXT | local \| notion |
| source_id | TEXT | Notion page id |
| ig_container_id | TEXT | IG container |
| ig_media_id | TEXT | IG media id |
| last_api_response | TEXT | Debug |
| last_error | TEXT | Last failure |
| attempts | INT | Retry count |
| created_at, updated_at | TEXT | ISO |

**Primary key:** `(reel_id, scheduled_at)`  
**Index:** `(platform, status, scheduled_at)`

Env: `UPLOAD_DB_PATH=output/upload_queue.sqlite3`

---

## 2. CSV — texts_kailas.csv

Колонки (ориентир):

| Column | Purpose |
|--------|---------|
| text_id | T001, T002, … |
| full_text | IG caption body |
| short_text | Optional shorter variant |

~30 texts (T001–T030); для партий >10 новых — добавить T031+.

---

## 3. CSV — render_results.csv

| Column | Purpose |
|--------|---------|
| reel_id | R421 |
| text_id | T015 |
| status | rendered \| error_render |

Mapping reel → text при ingest.

---

## 4. CSV — reels_plan*.csv

Plan batch from `generate-plan`: reel slots, clips, music, text_id assignments.

---

## 5. File paths

| Path | Content |
|------|---------|
| `output/reels/R###.mov` | Rendered vertical video 1080×1920 |
| `output/reels/copy_*.MOV` | iPhone originals |
| `output/post_texts/R###.txt` | Final IG caption |
| `output/transcripts/copy_*.txt` | Whisper transcripts |
| `output/reels_plan_auto_ingest.csv` | Auto text assignment log |
| `output/.ingest_reels_state.json` | Ingest dedupe state |
| `output/pinterest_oauth.json` | OAuth tokens |

---

## 6. OAuth tokens

| File | Scope / use |
|------|-------------|
| `youtube_shorts_uploader/token.json` | `youtube.upload` — Shorts upload |
| `youtube_shorts_uploader/token_comments.json` | `youtube.force-ssl` — comments |
| `output/pinterest_oauth.json` | Pinterest pins API |

---

## 7. Environment (`.env` key groups)

### Instagram + R2
```env
IG_USER_ID=
IG_ACCESS_TOKEN=
IG_USERNAME=grishkoff
R2_ACCOUNT_ID=
R2_BUCKET=
R2_PUBLIC_BASE_URL=
R2_AUTUPLOAD=1
R2_DELETE_AFTER_POST=1
LOCAL_DELETE_AFTER_POST=1
```

### YouTube
```env
OPENAI_API_KEY=
AUDIO_DIR=output/audio
YOUTUBE_PRIVACY_STATUS=unlisted
```

### Pinterest
```env
PINTEREST_APP_ID=
PINTEREST_APP_SECRET=
PINTEREST_ACCESS_TOKEN=
PINTEREST_BOARD_ID=
PINTEREST_SANDBOX=1
```

### Notion
```env
NOTION_TOKEN=
NOTION_DATABASE_ID=
```

### Schedule
```env
UPLOAD_TIMES=09:00,13:00,19:00
UPLOAD_YT_TIMES=10:00,14:00,20:00
UPLOAD_PINTEREST_TIMES=11:00,15:00,21:00
TZ=Asia/Makassar
```

### Ingest AI (copy_ workflow)
```env
INGEST_AI_CAPTION_REGEX=^copy_
INGEST_AUTO_PLAN_IG=0
CAPTION_SUFFIX=\n\nНапиши «КАЙЛАС»
```

---

## 8. CLI commands (reference)

```bash
docker exec reels-autopost python -m uploader.main --tz Asia/Makassar <cmd>
```

| Command | Purpose |
|---------|---------|
| `ingest-reels` | New mov → post_texts, Notion |
| `rebuild-texts` | Reassign unused texts |
| `schedule-crosspost` | 3/day multi-platform |
| `sync-notion-schedule` | Push dates to Notion |
| `autopost` | IG worker loop |
| `autopost-yt` | YT worker loop |
| `autopost-pinterest` | Pinterest worker |
| `today` | Today's queue |
| `next-due-summary` | Next slots |
| `mark-posted --reel-id R411` | Manual mark |
| `pinterest-oauth` | OAuth flow |

---

## 9. Useful SQL

```bash
sqlite3 output/upload_queue.sqlite3 \
  "SELECT platform, status, COUNT(*) FROM upload_queue GROUP BY 1,2;"

sqlite3 output/upload_queue.sqlite3 \
  "SELECT reel_id, platform, scheduled_at, status FROM upload_queue
   WHERE status='planned' ORDER BY scheduled_at LIMIT 20;"
```
