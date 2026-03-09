#!/usr/bin/env python3
"""
Статистика просмотров и лайков Stories из БД: кому какой аккаунт ставил просмотры и реакции.

Использование:
  cd /path/to/telegram_promotion_system_bali
  python scripts/show_story_views_from_db.py
  python scripts/show_story_views_from_db.py --account promotion_new_account
  python scripts/show_story_views_from_db.py --limit 50 --days 7
"""
import argparse
import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timedelta

# Корень проекта в PYTHONPATH
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import func, and_, Integer
from shared.database.session import SessionLocal
from shared.database.models import Account, StoryView


def run(session_name: str = "promotion_new_account", limit: int = 100, days: int = 30):
    db = SessionLocal()
    try:
        account = db.query(Account).filter(Account.session_name == session_name).first()
        if not account:
            print(f"Аккаунт с session_name={session_name!r} не найден в БД.")
            return

        since = datetime.utcnow() - timedelta(days=days)
        rows = (
            db.query(
                StoryView.username,
                StoryView.user_id,
                func.count(StoryView.id).label("views"),
                func.sum(func.cast(StoryView.reacted, type_=Integer)).label("reactions"),
                func.max(StoryView.viewed_at).label("last_seen"),
            )
            .filter(
                and_(
                    StoryView.account_id == account.id,
                    StoryView.viewed_at >= since,
                )
            )
            .group_by(StoryView.username, StoryView.user_id)
            .order_by(func.count(StoryView.id).desc())
            .limit(limit)
            .all()
        )
    except Exception as e:
        print(f"Ошибка запроса: {e}")
        raise
    finally:
        db.close()

    # Реакции по типам для каждого user (ключ как в таблице: username или ID{user_id})
    db2 = SessionLocal()
    try:
        reaction_rows = (
            db2.query(
                StoryView.username,
                StoryView.user_id,
                StoryView.reaction_type,
                func.count(StoryView.id).label("cnt"),
            )
            .filter(
                and_(
                    StoryView.account_id == account.id,
                    StoryView.viewed_at >= since,
                    StoryView.reacted == True,
                )
            )
            .group_by(StoryView.username, StoryView.user_id, StoryView.reaction_type)
            .all()
        )
        reactions_by_user = defaultdict(lambda: defaultdict(int))
        for username, user_id, rtype, cnt in reaction_rows:
            key = (username or f"ID{user_id}").strip() if username else f"ID{user_id}"
            reactions_by_user[key][rtype or "?"] = cnt
    finally:
        db2.close()

    # Вывод
    print()
    print("=" * 90)
    print(f"СТАТИСТИКА ПРОСМОТРОВ И ЛАЙКОВ STORIES — аккаунт: {session_name}")
    print(f"Период: последние {days} дн.  (не более {limit} получателей)")
    print("=" * 90)
    print(f"{'Получатель':<30} {'Просмотров':>10} {'Лайков':>8} {'Последний просмотр':<22} Реакции")
    print("-" * 90)

    for row in rows:
        username = (row.username or f"ID{row.user_id}").strip() or f"ID{row.user_id}"
        if len(username) > 28:
            username = username[:25] + "..."
        views = row.views or 0
        reactions = int(row.reactions or 0)
        last_seen = row.last_seen.strftime("%Y-%m-%d %H:%M") if row.last_seen else "—"
        reaction_str = ", ".join(f"{emoji}×{n}" for emoji, n in reactions_by_user.get(username, {}).items()) or "—"
        print(f"{username:<30} {views:>10} {reactions:>8} {last_seen:<22} {reaction_str}")

    print("-" * 90)
    total_views = sum(r.views or 0 for r in rows)
    total_react = sum(int(r.reactions or 0) for r in rows)
    print(f"{'ИТОГО (в выборке)':<30} {total_views:>10} {total_react:>8}")
    print("=" * 90)
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Статистика просмотров/лайков Stories из БД")
    parser.add_argument("--account", default="promotion_new_account", help="session_name аккаунта")
    parser.add_argument("--limit", type=int, default=100, help="Макс. число получателей в таблице")
    parser.add_argument("--days", type=int, default=30, help="За последние N дней")
    args = parser.parse_args()
    run(session_name=args.account, limit=args.limit, days=args.days)
