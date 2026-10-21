# Jay Shambo Threads — внедрение промптов из Notion

Источник: [Jay Shambo | Threads](https://coordinated-work-a49.notion.site/Jay-Shambo-Threads-787d280c31a045cab325b233052be345)

## Что сделано

1. **Общий + автор + комментатор** — `uploader/threads_prompts.py`  
   Автор = common + author; комментатор = common + commentator (не оба ролевых сразу).
2. **Карточки продуктов** — `uploader/data/threads_products.json` + `uploader/threads_products.py`  
   Кайлас 2027, Индия к 8 марта, Бали (premium / sacred / weekend), запрет Непал–Госайкунда, статусы.
3. **Авторский планировщик** — `uploader/threads_text_autopost.py`  
   ~5 корневых постов/сутки: 2 дискуссии + 1 прогрев + 2 продающих; история 14 дней; стоп без аватара.
4. **Комментатор** — `uploader/threads_replies.py`  
   Новый промпт; вопрос не обязателен; только утверждённые URL; бан Госайкунды.

## Runtime path

Прод крутится из `/home/tovgrishkoff/resolve_batch_render/`.  
Файлы в этом каталоге репозитория — зеркало для review/deploy.

## Env

```
THREADS_AVATAR_ID=24c2a891-8d11-4bdc-8bdf-3bc844607a36
# or THREADS_AVATAR_PATH=/path/to/avatar.md
THREADS_TEXT_MAX_PER_DAY=5
THREADS_TEXT_WINDOWS=08:00-09:15,10:30-11:45,13:00-14:30,16:00-17:30,19:00-21:00
```

## До запуска (из Notion §6)

Утвердить цены/даты/статусы карточек; подключить полный текст аватара и одобренные тексты Григория.

## Длина постов (обновление)
- Жёсткий лимит: `THREADS_TEXT_MAX_CHARS=260` (цель 180–260 без воды).
- Обрезка только по границе предложения/слова (`fit_threads_text`), без обрыва на полслове.
- Промпт автора: коротко, цепляюще, экспертно (горы / ретриты / маршруты).
