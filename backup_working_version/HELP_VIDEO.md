# Help video for Lead Hunter bot

Сейчас ролик **отключён** (help = только контакт менеджера).

Когда понадобится снова: сохраните file_id через `/set_help_video`,
затем верните вызовы `_send_help_howto_video` в `/start` и `show_help`.

## Как один раз сохранить ролик (рекомендуется)

1. Откройте бота от админ-аккаунта.
2. Пришлите видео в бот.
3. Ответьте на это видео командой:

```text
/set_help_video
```

или отправьте видео с подписью/командой `/set_help_video`.

Бот сохранит Telegram `file_id` в `data/help_video_file_id.txt` и дальше будет слать ролик без повторной загрузки файла.

## Альтернативы

Вариант A — локальный файл:

```bash
cp /path/to/video.mp4 /home/tovgrishkoff/mvp2105/data/help_howto.mp4
docker restart bali-bot
```

Вариант B — env:

```env
HELP_VIDEO_FILE_ID=BAACAgQAAxkBAAI...
# HELP_VIDEO_PATH=data/help_howto.mp4
```
