#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Импорт валидных групп из лога check_and_cleanup_groups.log в БД.

Парсит строки вида "✅ @username - доступна (OK)" и добавляет эти группы
в таблицу targets с niche=bali, status=new. Account-manager будет вступать
в них новыми аккаунтами.

Запуск из корня проекта:
  python3 scripts/import_valid_groups_from_check_log.py
  python3 scripts/import_valid_groups_from_check_log.py --dry-run
"""
import argparse
import asyncio
import re
import sys
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select
from lexus_db.session import AsyncSessionLocal
from lexus_db.models import Target

NICHE = "bali"
STATUS_NEW = "new"
# Строка в логе: "  ✅ @Arenda_Bali_Villy - доступна (OK)"
PATTERN = re.compile(r"(@[a-zA-Z0-9_]+)\s+-\s+доступна\s+\(OK\)", re.IGNORECASE)


def extract_valid_usernames(log_path: Path) -> List[str]:
    usernames = []
    seen = set()
    if not log_path.exists():
        return usernames
    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if "доступна (OK)" not in line:
                continue
            m = PATTERN.search(line)
            if m:
                username = m.group(1)
                if username not in seen:
                    seen.add(username)
                    usernames.append(username)
    return usernames


async def main() -> None:
    parser = argparse.ArgumentParser(description="Импорт валидных групп из лога проверки в БД")
    parser.add_argument("--log", type=Path, default=None, help="Путь к check_and_cleanup_groups.log")
    parser.add_argument("--dry-run", action="store_true", help="Только вывести список, не писать в БД")
    parser.add_argument(
        "--reset-ok-to-new",
        action="store_true",
        help="Группы из лога «доступна (OK)», которые уже в БД со статусом inaccessible/pending/no_accounts_left, перевести в status=new (очередь вступлений)",
    )
    args = parser.parse_args()
    log_path = args.log or (PROJECT_ROOT / "logs" / "check_and_cleanup_groups.log")
    if not log_path.is_absolute():
        log_path = PROJECT_ROOT / log_path
    usernames = extract_valid_usernames(log_path)
    print("В логе найдено валидных групп:", len(usernames))
    if not usernames:
        return
    if args.dry_run:
        for u in usernames[:50]:
            print(" ", u)
        if len(usernames) > 50:
            print(" ... и ещё", len(usernames) - 50)
        print("\n--dry-run: в БД ничего не записано. Запустите без --dry-run для импорта.")
        return

    # Режим: перевести «валидные по логу» группы из БД в status=new (если сейчас не active/joined)
    if args.reset_ok_to_new:
        reset_statuses = ("inaccessible", "pending", "no_accounts_left", "banned", "read_only", "error")
        async with AsyncSessionLocal() as session:
            r = await session.execute(
                select(Target).where(
                    Target.username.in_(usernames),
                    Target.status.in_(reset_statuses),
                )
            )
            to_reset = r.scalars().all()
            for t in to_reset:
                t.status = STATUS_NEW
                t.niche = NICHE
                print(" -> new:", t.username)
            await session.commit()
        print("\nГотово: переведено в new для вступления:", len(to_reset))
        return

    added = skipped = 0
    async with AsyncSessionLocal() as session:
        for username in usernames:
            username = username.strip()
            if not username.startswith("@"):
                username = "@" + username
            try:
                r = await session.execute(select(Target).where(Target.username == username))
                if r.scalars().first():
                    skipped += 1
                    continue
                session.add(Target(username=username, title=username, niche=NICHE, status=STATUS_NEW, can_post=True))
                added += 1
                print(" +", username)
            except Exception as e:
                print(" Ошибка", username, e)
                await session.rollback()
        await session.commit()
    print("\nГотово: добавлено", added, ", уже в БД (пропущено)", skipped)
    print("Account-manager по расписанию будет вступать в новые группы (niche=bali, status=new).")


if __name__ == "__main__":
    asyncio.run(main())
