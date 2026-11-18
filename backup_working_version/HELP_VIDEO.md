# Help video for Lead Hunter bot

Кнопка **❓ Помощь** и команда `/help` показывают короткий текст с контактом менеджера и, если есть файл, отправляют ролик «как нажимать».

## Как подключить ролик

Вариант A — локальный файл (уже смонтирован `data/`):

```bash
cp /path/to/video.mp4 /home/tovgrishkoff/mvp2105/data/help_howto.mp4
docker restart bali-bot
```

Вариант B — Telegram `file_id` (лучше для продакшена):

1. Один раз отправьте видео боту/себе через бота.
2. Пропишите в `.env.docker`:

```env
HELP_VIDEO_FILE_ID=BAACAgQAAxkBAAI...
# опционально другой путь:
# HELP_VIDEO_PATH=data/help_howto.mp4
```

3. `docker restart bali-bot`
