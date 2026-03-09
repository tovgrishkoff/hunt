#!/bin/bash
cd /home/tovgrishkoff/PIAR/telegram_promotion_system_bali

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║          📊 ЕЖЕДНЕВНАЯ ПРОВЕРКА СИСТЕМЫ                     ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# 1. Статус сервисов
echo "1️⃣ СТАТУС СЕРВИСОВ:"
docker-compose ps | grep telegram-bali
echo ""

# 1a. Тест прокси: Bali-аккаунты из БД (config/bali_accounts_config.json + таблица accounts)
echo "1a. ТЕСТ ПРОКСИ (доступ к api.telegram.org):"
python3 -c "
import json
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path('.').resolve()))
try:
    with open('config/bali_accounts_config.json', encoding='utf-8') as f:
        bali_cfg = json.load(f)
    allowed = bali_cfg.get('allowed_accounts') or []
    if not allowed:
        with open('accounts_config.json', encoding='utf-8') as f:
            data = json.load(f)
        accounts = [{'session_name': a.get('session_name'), 'proxy': a.get('proxy')} for a in data if a.get('proxy')]
    else:
        from shared.database.session import SessionLocal, init_db
        from shared.database.models import Account
        init_db()
        db = SessionLocal()
        try:
            rows = db.query(Account).filter(Account.session_name.in_(allowed)).all()
            accounts = [{'session_name': r.session_name, 'proxy': r.proxy} for r in rows if r.proxy]
        finally:
            db.close()
    ok, fail = 0, 0
    for acc in accounts:
        p = acc.get('proxy')
        name = acc.get('session_name', '?')
        if not p:
            continue
        proxy = p.replace('https://', 'http://') if p.startswith('https') else p
        host = proxy.split('@')[-1].split(':')[0] if '@' in proxy else '?'
        r = subprocess.run(['curl', '-s', '-x', proxy, '-I', 'https://api.telegram.org',
                           '--connect-timeout', '8', '-m', '12'], capture_output=True, timeout=15)
        status = '✅' if r.returncode == 0 and b'HTTP' in r.stdout[:20] else '❌'
        if status == '✅': ok += 1
        else: fail += 1
        print(f'   {status} {name}: {host}')
    print(f'   --- Итого: {ok} OK, {fail} FAIL ---')
except Exception as e:
    print(f'   ⚠️ Ошибка: {e}')
" 2>/dev/null || echo "   (python3 или curl недоступны)"
echo ""

# 1b. Аккаунты для вступления: account-manager грузит только аккаунты с niche='bali' в БД
echo "1b. АККАУНТЫ ДЛЯ ВСТУПЛЕНИЯ (должны быть niche=bali, иначе не участвуют во вступлении):"
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT session_name, status, COALESCE(niche, '(NULL)') AS niche
FROM accounts
WHERE session_name LIKE 'promotion_%'
ORDER BY session_name;
"
echo "   Если niche NULL (promotion_new_account, promotion_new_account_2 и др.) — они не участвуют в сторис/вступлениях. Исправь: ./scripts/fix_bali_accounts_niche_for_stories.sh"
echo ""

# 2. Статистика групп (new = добавлены, ждут вступления; joined/active = вступили, можно постить)
echo "2️⃣ СТАТИСТИКА ГРУПП:"
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT status, COUNT(*) 
FROM groups 
WHERE niche = 'bali' 
GROUP BY status 
ORDER BY status;
"
echo ""

# 2a. Очередь вступлений: сколько групп ждут вступления (status=new)
echo "2a. ОЧЕРЕДЬ ВСТУПЛЕНИЙ (new = ждут вступления, 0 = нечего вступать):"
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -t -c "
SELECT COUNT(*) AS new_count FROM groups WHERE niche = 'bali' AND status = 'new';
"
echo "   (Если new=0 — finder не находит новых групп: почти все результаты поиска уже в БД. Чтобы чаще появлялись новые: добавить ключевые слова в config/niches/bali.json или увеличить limit_per_keyword в finder.)"
echo ""

# 2a1. Вступления за последние 24 ч и последние вступившие группы
echo "2a1. ВСТУПЛЕНИЯ ЗА ПОСЛЕДНИЕ 24 Ч:"
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT COUNT(*) as joined_last_24h
FROM groups
WHERE niche = 'bali' AND joined_at >= NOW() - INTERVAL '24 hours';
"
echo "   Последние 5 вступлений:"
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT username, status, joined_at
FROM groups
WHERE niche = 'bali' AND joined_at IS NOT NULL
ORDER BY joined_at DESC
LIMIT 5;
"
echo "   (Если 0 — account-manager не вступает: проверь flood_wait у аккаунтов (1b), логи: docker logs telegram-bali-account-manager --tail 150 | grep -E 'STEP 2|JOIN|joined|FloodWait')"
echo ""

# 2b. Почему мало групп для постинга (расшифровка статусов)
echo "2b. ПОЧЕМУ МАЛО ГРУПП ДЛЯ ПОСТИНГА (только active+joined постимые):"
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT status,
       COUNT(*) as cnt,
       CASE status
         WHEN 'active' THEN 'вступили, можно постить'
         WHEN 'joined' THEN 'вступили, постер помечает после поста'
         WHEN 'pending' THEN 'заявка отправлена, ждём одобрения'
         WHEN 'inaccessible' THEN 'недоступна (приватная/удалена)'
         WHEN 'no_accounts_left' THEN 'все аккаунты не могут постить'
         WHEN 'read_only' THEN 'вступили, но постить нельзя'
         WHEN 'banned' THEN 'аккаунт забанен в группе'
         WHEN 'new' THEN 'в очереди на вступление'
         ELSE 'другое'
       END as meaning
FROM groups WHERE niche = 'bali'
GROUP BY status ORDER BY cnt DESC;
"
echo ""

# 3. Готовые к постингу (постер ищет status IN ('active','joined'), warm_up пройден, можно постить)
echo "3️⃣ ГОТОВЫЕ К ПОСТИНГУ:"
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT COUNT(*) as ready_count
FROM groups 
WHERE niche = 'bali' 
  AND status IN ('active', 'joined')
  AND (warm_up_until IS NULL OR warm_up_until <= NOW())
  AND (can_post IS NULL OR can_post = true)
  AND (daily_posts_count IS NULL OR daily_posts_count < 2);
"
echo ""

# 3a. Диагностика: почему ready может быть 0 (разбивка по условиям)
echo "3a. ДИАГНОСТИКА «ГОТОВЫЕ К ПОСТИНГУ» (почему ready=0 или постит в одни и те же):"
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT 
  (SELECT COUNT(*) FROM groups WHERE niche = 'bali' AND status IN ('active','joined')) as postable_status,
  (SELECT COUNT(*) FROM groups WHERE niche = 'bali' AND status IN ('active','joined') AND (warm_up_until IS NULL OR warm_up_until <= NOW())) as after_warmup,
  (SELECT COUNT(*) FROM groups WHERE niche = 'bali' AND status IN ('active','joined') AND (warm_up_until IS NULL OR warm_up_until <= NOW()) AND (can_post IS NULL OR can_post = true)) as can_post_ok,
  (SELECT COUNT(*) FROM groups WHERE niche = 'bali' AND status IN ('active','joined') AND (warm_up_until IS NULL OR warm_up_until <= NOW()) AND (can_post IS NULL OR can_post = true) AND (COALESCE(daily_posts_count, 0) < 2)) as ready;
"
echo ""

# 3b. Если after_warmup=0 — все группы ещё «в прогреве»; когда закончится warm_up
echo "3b. WARM-UP (если after_warmup=0 — постов не будет, постер не находит готовых групп):"
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT 
  COUNT(*) FILTER (WHERE warm_up_until > NOW()) AS warm_future,
  COUNT(*) FILTER (WHERE warm_up_until IS NULL OR warm_up_until <= NOW()) AS warm_passed,
  MIN(warm_up_until) AS next_warm_ends,
  MAX(warm_up_until) AS last_warm_ends
FROM groups 
WHERE niche = 'bali' AND status IN ('active','joined');
" 2>/dev/null || true
echo "   Чтобы разблокировать постинг сейчас: ./scripts/fix_bali_warmup_for_posting.sh"
echo ""

# 3c. Расписание постинга (marketer): когда ждать постов
echo "3c. РАСПИСАНИЕ ПОСТИНГА (Asia/Jakarta):"
echo "   Слоты: 08:00, 12:00, 15:00, 18:00. Постер запускается только в эти часы."
echo "   Следующий запуск — смотри в логах: docker logs telegram-bali-marketer --tail 30 | grep -E 'Next:|Woke up|Completed slot'"
echo ""

# 3d. Блоклист (почему «0 успешно, N ошибок»: все аккаунты для группы в блоклисте)
echo "3d. БЛОКЛИСТ (account_group_blocklist для Bali):"
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT 
  (SELECT COUNT(*) FROM account_group_blocklist b JOIN groups g ON g.id = b.group_id WHERE g.niche = 'bali') AS blocklist_entries,
  (SELECT COUNT(DISTINCT b.group_id) FROM account_group_blocklist b JOIN groups g ON g.id = b.group_id WHERE g.niche = 'bali') AS groups_with_any_block,
  (SELECT COUNT(*) FROM groups WHERE niche = 'bali' AND status = 'no_accounts_left') AS no_accounts_left;
" 2>/dev/null || true
echo "   Если no_accounts_left велик и постов 0 — сбросить блоклист «не участник»: ./scripts/fix_bali_blocklist_for_posting.sh"
echo ""

# 3e. Почему не идут посты сегодня (диагностика)
echo "3e. ПОЧЕМУ НЕ ИДУТ ПОСТЫ СЕГОДНЯ:"
echo "   Время сейчас (Asia/Jakarta): $(TZ=Asia/Jakarta date '+%Y-%m-%d %H:%M')"
echo "   Слоты постинга: 08:00, 12:00, 15:00, 18:00 Jakarta (marketer запускается только в эти часы)."
MARKETER_STATUS=$(docker ps --format '{{.Names}}\t{{.Status}}' 2>/dev/null | grep -E 'telegram-bali-marketer' || true)
if [ -z "$MARKETER_STATUS" ]; then
  echo "   ❌ telegram-bali-marketer: контейнер не запущен — посты не пойдут. Запуск: docker start telegram-bali-marketer"
else
  echo "   ✅ Marketer: $MARKETER_STATUS"
fi
echo "   Готовых к постингу (ready) сейчас:"
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -t -c "
SELECT COUNT(*) FROM groups WHERE niche = 'bali' AND status IN ('active', 'joined')
  AND (warm_up_until IS NULL OR warm_up_until <= NOW())
  AND (can_post IS NULL OR can_post = true)
  AND (COALESCE(daily_posts_count, 0) < 2);
" 2>/dev/null || echo "   (не удалось получить)"
echo "   Последняя активность marketer (слоты / готовые группы / ошибки):"
docker logs telegram-bali-marketer --tail 80 2>/dev/null | grep -E 'Next run|Woke up|Completed slot|ready for posting|Found.*groups ready|Найдено.*групп|ошибк|error|Error|0 групп|no groups' | tail -12 || echo "   (логи недоступны или пусто)"
echo "   Если постов 0: проверь ready (3a), слот времени (3c), блоклист (3d) и логи: docker logs telegram-bali-marketer --tail 150"
echo ""

# 4a. Посты за последние 24 ч (всегда видна свежая активность)
echo "4️⃣ ПОСТЫ ЗА ПОСЛЕДНИЕ 24 Ч:"
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT 
    COUNT(*) as total_posts,
    COUNT(CASE WHEN photo_path IS NOT NULL THEN 1 END) as posts_with_photo,
    COUNT(CASE WHEN success = true THEN 1 END) as successful_posts,
    COUNT(CASE WHEN success = false THEN 1 END) as failed_posts,
    ROUND(
        COUNT(CASE WHEN success = true THEN 1 END)::numeric / 
        NULLIF(COUNT(*), 0) * 100, 
        1
    ) as success_rate_percent
FROM posts
WHERE sent_at >= NOW() - INTERVAL '24 hours';
"
echo ""

# 4b. Посты за календарный день Jakarta (если отчёт смотрите утром — будет вчера)
echo "4️⃣ ПОСТЫ ЗА СЕГОДНЯ (календарный день Jakarta):"
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT 
    COUNT(*) as total_posts,
    (NOW() AT TIME ZONE 'Asia/Jakarta')::date as today_jakarta
FROM posts
WHERE sent_at IS NOT NULL AND (sent_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Jakarta')::date = (NOW() AT TIME ZONE 'Asia/Jakarta')::date;
"
echo ""

# 5. Все группы с постингом за день (календарный Jakarta)
echo "5️⃣ ГРУППЫ С ПОСТИНГОМ ЗА СЕГОДНЯ (Jakarta):"
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT 
    g.username,
    COUNT(p.id) as posts,
    COUNT(CASE WHEN p.success = true THEN 1 END) as ok,
    COUNT(CASE WHEN p.success = false THEN 1 END) as fail,
    MAX(p.sent_at) as last_post
FROM posts p
JOIN groups g ON p.group_id = g.id
WHERE p.sent_at IS NOT NULL
  AND (p.sent_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Jakarta')::date = (NOW() AT TIME ZONE 'Asia/Jakarta')::date
GROUP BY g.id, g.username
ORDER BY posts DESC, last_post DESC;
"
echo ""

# 6. Проблемные группы (с частыми ошибками)
echo "6️⃣ ПРОБЛЕМНЫЕ ГРУППЫ (≥3 ошибки сегодня):"
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT 
    g.username,
    COUNT(p.id) as total_attempts,
    COUNT(CASE WHEN p.success = false THEN 1 END) as failed_attempts,
    COUNT(CASE WHEN p.success = true THEN 1 END) as successful_attempts
FROM groups g
JOIN posts p ON g.id = p.group_id
WHERE p.sent_at >= CURRENT_DATE
  AND g.niche = 'bali'
GROUP BY g.id, g.username
HAVING COUNT(CASE WHEN p.success = false THEN 1 END) >= 3
ORDER BY failed_attempts DESC
LIMIT 5;
"
echo ""

# 7. Activity: просмотры сторис (сегодня Jakarta + последние 24 ч)
echo "7️⃣ СТОРИС (просмотры за сегодня Jakarta):"
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT 
    COUNT(*) as total_views,
    COUNT(CASE WHEN reacted = true THEN 1 END) as with_reaction,
    COUNT(DISTINCT account_id) as accounts_used
FROM story_views
WHERE viewed_at IS NOT NULL
  AND (viewed_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Jakarta')::date = (NOW() AT TIME ZONE 'Asia/Jakarta')::date;
" 2>/dev/null || echo "   (таблица story_views не найдена или ошибка)"
echo "   За последние 24 ч:"
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT 
    COUNT(*) as total_views,
    COUNT(CASE WHEN reacted = true THEN 1 END) as with_reaction,
    COUNT(DISTINCT account_id) as accounts_used
FROM story_views
WHERE viewed_at >= NOW() - INTERVAL '24 hours';
" 2>/dev/null || true
echo ""

# 7a. Какие аккаунты смотрели сторис за последние 24 ч (для проверки promotion_new_account и др.)
echo "7a. АККАУНТЫ, КОТОРЫЕ СМОТРЕЛИ СТОРИС (за 24 ч):"
echo "   (promotion_* = промо-аккаунты; promotion_new_account_2 = @grishkoff; views = просмотров, reactions = реакций)"
docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c "
SELECT a.session_name, COUNT(*) as views, COUNT(CASE WHEN sv.reacted THEN 1 END) as reactions
FROM story_views sv
JOIN accounts a ON a.id = sv.account_id
WHERE sv.viewed_at >= NOW() - INTERVAL '24 hours'
GROUP BY a.session_name
ORDER BY views DESC;
" 2>/dev/null || echo "   (таблица story_views/accounts не найдена)"
echo ""

# 8. Партизанский PR (conversation-pr): диалоги в группах по config/bali_conversations.json
echo "8️⃣ ПАРТИЗАНСКИЙ PR (диалоги в группах @marisha_lovephoto):"
docker ps --format '{{.Names}}\t{{.Status}}' 2>/dev/null | grep -E 'conversation-pr|telegram-bali-conversation' || echo "   контейнер не найден"
echo "   Последние логи (если контейнер запущен):"
docker logs telegram-bali-conversation-pr --tail 15 2>/dev/null | tail -10 || echo "   (контейнер не запущен или логов нет)"
echo "   Лог групп (когда в последний раз писали):"
test -f data/conversation_pr_log.json && python3 -c "
import json
try:
    with open('data/conversation_pr_log.json') as f:
        d = json.load(f)
    for u, t in list(sorted(d.items(), key=lambda x: x[1], reverse=True))[:5]:
        print(f'     {u}: {t[:19]}')
except: print('     (нет данных)')
" 2>/dev/null || echo "     (файл data/conversation_pr_log.json не найден)"
echo "   Запуск: docker-compose up -d conversation-pr"
echo ""

# 9. Приоритет рассылки: ретрит 8 марта (bali_assets/messages.json, priority 999)
echo "9️⃣ ПРИОРИТЕТ РАССЫЛКИ (ретрит 7–10 марта, 8 марта):"
python3 scripts/verify_retreat_8march_mailing.py 2>/dev/null | head -25 || echo "   (скрипт verify_retreat_8march_mailing.py)"
echo ""

echo "✅ Проверка завершена!"
echo ""
echo "❓ Почему не идут посты сегодня: смотри блок 3e (время Jakarta, слоты, marketer, ready, логи). Частые причины: ready=0 (3a), не время слота (08/12/15/18 Jakarta), marketer не запущен, все аккаунты в блоклисте (3d)."
echo "❓ Постит в одни и те же группы: готовых к постингу мало (только status=active/joined). Чтобы постить в больше групп — нужны группы в статусе new, затем account-manager вступит (new → active/joined), после warm-up они попадут в ready."
echo "❓ Почему мало групп для постинга: смотри блок 2b. Большинство групп в pending (ждём одобрения), inaccessible (группа недоступна) или no_accounts_left (все аккаунты не могут постить). Постимые — только active и joined. Чтобы больше: находить новые группы (2a), вступать, одобренные перейдут в active; периодически проверять pending (ручной заход или скрипт)."
echo "❓ Почему не вступаем в новые: если в блоке 2a new=0 — finder не находит новых групп (все результаты поиска Telegram уже есть в БД). Логи: «Найдено новых групп: 0» / «Очередь пуста». Решение: добавить ключевые слова в config/niches/bali.json или увеличить limit_per_keyword в services/account-manager/finder.py (вызов search_groups)."
echo "❓ ready_count = 0: смотри блок 3a. Если postable_status > 0, но ready = 0 — часто из-за daily_posts_count >= 2 (сброс в полночь Jakarta). Ручной сброс: docker exec telegram-bali-postgres psql -U telegram_user_bali -d telegram_promotion_bali -c \"UPDATE groups SET daily_posts_count = 0 WHERE niche = 'bali';\""
echo "❓ Если «new» есть, но не уменьшается / нет вступлений: account-manager вступает по расписанию (05:00, 07:00, 11:00 Jakarta). Логи: docker logs telegram-bali-account-manager --tail 200 | grep -E 'STEP 2|JOIN|joined|new|очередь|Найдено|Обработаем|FloodWait'"
echo "❓ Сторис: сервис telegram-bali-activity раз в 6 часов просматривает сторис. Логи: docker logs telegram-bali-activity --tail 50"
echo "❓ Партизанский PR не идёт: проверь блок 8. Нужны 3+ Bali-аккаунтов (niche=bali), группы active/joined. Конфиг: config/bali_conversations.json. Запуск: docker-compose up -d conversation-pr"
echo "❓ Ретрит 8 марта: тексты с priority 999 в bali_assets/messages.json (5x вес). Проверка: python3 scripts/verify_retreat_8march_mailing.py"
echo "❓ Прокси FAIL: обновите accounts_config.json, затем: python3 scripts/update_all_accounts_from_config.py && docker-compose restart account-manager marketer"
echo "❓ «Аккаунт не является участником группы»: маркетер переводит группы в status=new. Проверить: python3 scripts/check_bali_accounts_membership.py --limit 50; обновить БД: python3 scripts/check_bali_accounts_membership.py --limit 50 --update-db"
echo "❓ «0 успешно, 48 ошибок» / «все в блоклисте»: постер находит группы, но для каждой все аккаунты уже в account_group_blocklist (раньше получили «не участник»). Сброс блоклиста «не участник» и no_accounts_left → active: ./scripts/fix_bali_blocklist_for_posting.sh"