## Помощник публикаций + автопостинг в Instagram

Этот модуль умеет:
- выбирает **5 готовых Reels в день** из `output/reels/`
- раскладывает их на **случайные времена** в окне **19:00–22:30 МСК**
- генерирует готовые caption’ы (из `texts_kailas.csv` через `reels_plan.csv`)
- сохраняет очередь и статусы в SQLite
- даёт команды “что постить сегодня” и “напоминать в терминале”
- (опционально) **автопостит** в Instagram через **Instagram API with Instagram Login**
- (опционально) подтягивает очередь из **Notion** (если в базе есть публичный `VideoURL`)

### Настройка

1) Создай `.env` (не коммить) на основе `.env.example`.

2) Установи зависимости:

```bash
python3 -m pip install -r uploader/requirements.txt
```

### Команды

Сгенерировать план на сегодня (5 постов в окне 19:00–22:30 МСК):

```bash
python3 -m uploader.main plan \
  --plan output/reels_plan.csv \
  --texts texts_kailas.csv \
  --reels-dir output/reels \
  --count 5 \
  --window 19:00-22:30 \
  --tz Asia/Makassar
```

Показать план на сегодня (что/когда/какой caption):

```bash
python3 -m uploader.main today
```

Запустить “напоминалку” (пишет в терминал когда пришло время постить):

```bash
python3 -m uploader.main tick --interval-sec 30
```

Отметить ролик опубликованным (после того как ты руками сделал Trial-пост в IG):

```bash
python3 -m uploader.main mark-posted --reel-id R007
```

Импортировать готовые посты из Notion (берёт страницы со Status=Ready):

```bash
python3 -m uploader.main sync-notion
```

Запустить автопостинг (публикует “due” элементы очереди):

```bash
python3 -m uploader.main autopost --interval-sec 30
```

### Важно для автопостинга (Instagram)

- Instagram **должен скачать видео по публичному URL**. Для локальных файлов выставь
  статику и задай `MEDIA_BASE_URL` + `MEDIA_PUBLIC_ROOT`, либо храни `VideoURL` прямо в Notion.
- Нужны переменные окружения `IG_USER_ID`, `IG_ACCESS_TOKEN` (IGAA…), `IG_USERNAME`.

---

## YouTube comment auto-reply (`yt-comments`)

Сервис каждый ~30 мин обходит последние видео нашего канала, через OpenAI решает,
стоит ли отвечать на каждый верхне-уровневый комментарий, и пишет ответ в ту же ветку.

**Безопасный старт:** по умолчанию включён DRY-RUN (`YT_COMMENTS_DRY_RUN=1`) —
бот всё решает, складывает решения в `yt_comments_seen`, но в YouTube ничего не постит.

К каждому реальному ответу **автоматически добавляется хвост**: закреп на главной
канала (послание + ссылка) и Telegram для личного контакта. Текст берётся из
`BRAND_YOUTUBE` и `BRAND_TELEGRAM`, шаблон можно переопределить переменной
`YT_COMMENTS_REPLY_FOOTER` (плейсхолдеры `{youtube}` и `{telegram}`). Основной текст
пишет только модель — без дублирования ссылок в теле ответа.

### 1. Одноразовый OAuth с расширенным scope

Существующий `youtube_shorts_uploader/token.json` выписан только под `youtube.upload`
и для комментариев не подходит. Нужен отдельный токен с `youtube.force-ssl`.

Сам OAuth-скрипт работает только внутри Docker-образа (на хосте нет нужных
Python-зависимостей), поэтому запускаем его в одноразовом контейнере с
прокинутым наружу портом для callback'а:

```bash
docker compose -f docker-compose.autopost.yml --profile comments run --rm \
    -e YT_OAUTH_PORT=8765 \
    -e YT_OAUTH_BIND=0.0.0.0 \
    -p 8765:8765 \
    yt-comments \
    python -m uploader.yt_comments.main oauth
```

В консоли появится URL вида `https://accounts.google.com/o/oauth2/auth?...&redirect_uri=http://localhost:8765/`.

На сервере без браузера: сделай SSH-туннель с локальной машины ДО открытия URL:

```bash
ssh -L 8765:localhost:8765 tovgrishkoff@<server>
```

И только потом открой выведенную ссылку в своём локальном браузере —
редирект `http://localhost:8765/?code=...` через туннель попадёт в контейнер
на сервере, скрипт допишет токен в `youtube_shorts_uploader/token_comments.json`.

> На хосте часто нет `docker compose` (v2) — тогда везде используй `docker-compose` (v1),
> тот же флаг `-f` и `--profile comments`.

**Сразу проверь, на какой канал выдался токен** (должно совпасть с @GrishaGrishkoFF
или с тем, что в `YT_COMMENTS_CHANNEL_ID`):

```bash
docker-compose -f docker-compose.autopost.yml --profile comments run --rm yt-comments \
    python -m uploader.yt_comments.main whoami
```

### 1a. Залогинились «не в тот» Google / «не тот» канал

- Токен привязан к **тому Google-аккаунту**, под которым ты нажал «Разрешить».
  Нужен аккаунт, у которого в YouTube Studio есть **управление** каналом с Shorts
  (в т.ч. бренд-канал).
- Удали старый токен и пройди OAuth снова (лучше в **инкогнито** в браузере, чтобы
  не подтянулась сессия чужого Gmail):

```bash
sudo rm -f youtube_shorts_uploader/token_comments.json
sudo chown "$USER":"$USER" youtube_shorts_uploader
# снова docker-compose ... run ... oauth
```

- В `.env` уже стоит `YT_OAUTH_PROMPT=select_account` — Google покажет **список
  аккаунтов**; выбери тот, с которого заходишь в Studio на нужный канал.
- Можно подсказать почту: `YT_OAUTH_LOGIN_HINT=твой@gmail.com` (не обязывает).
- Если у одного Google **несколько каналов** и API смотрит не на тот: задай
  `YT_COMMENTS_CHANNEL_ID=UC…` (YouTube Studio → Настройки → Канал → Дополнительные
  настройки → **ID канала**), перезапусти `whoami` — в `title` должен быть правильный канал.

### 2. Запуск разового тика (рекомендую для проверки)

```bash
docker compose -f docker-compose.autopost.yml run --rm yt-comments \
    python -m uploader.yt_comments.main once --dry-run
```

Посмотри в `app.log` блок `[yt-comments][DRY]` и таблицу:

```sql
SELECT video_id, decision, skip_reason, substr(text,1,50) AS comment,
       substr(reply_text,1,80) AS suggested_reply
FROM yt_comments_seen
ORDER BY seen_at DESC LIMIT 50;
```

### 3. Боевой режим

Когда устроят формулировки — переключи `.env`:

```env
YT_COMMENTS_DRY_RUN=0
```

И подними сервис:

```bash
docker compose -f docker-compose.autopost.yml up -d yt-comments
docker logs -f yt-comments
```

### 4. Что бот точно НЕ трогает

- Свои собственные комментарии (по `author_channel_id`).
- Очень короткие реакции (`огонь`, `🔥`, `супер` и пр.) — порог `YT_COMMENTS_MIN_LETTERS`.
- Ответы-в-ответы (reply под reply) — обрабатываем только верхне-уровневые ветки.
- Уже обработанные комментарии (по `comment_id` в `yt_comments_seen`).

### 5. Квоты

YouTube Data API v3 = 10 000 единиц/день.
- list каналов/плейлистов/комментариев — 1 ед./вызов;
- ответ (`comments.insert`) — 50 ед./вызов.

При `interval=1800s`, `max_videos=20`, лимит `5 replies/tick` упрёшься скорее в OpenAI,
чем в YouTube.

