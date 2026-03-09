#!/usr/bin/env python3
"""
Добавляет список travel-чатов в БД Bali-комбайна (таблица groups).

Группы попадают в очередь: account-manager по расписанию вступает в них,
после warm-up marketer постит туда сообщения india_holi (ретрит/Холи).

Запуск из корня проекта:
  cd /home/tovgrishkoff/PIAR/telegram_promotion_system_bali
  python3 scripts/add_travel_groups_to_bali_db.py

Или с указанием БД:
  POSTGRES_PORT=5438 python3 scripts/add_travel_groups_to_bali_db.py
"""
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

# Корень проекта в PYTHONPATH
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select
from lexus_db.session import AsyncSessionLocal
from lexus_db.models import Target


# Только публичные @username (инвайт-ссылки в БД не храним)
TRAVEL_USERNAMES = [
    "@travelfriendschat",
    "@mytbilisi_chat",
    "@EduVKrym",
    "@KrymskiiMost",
    "@turkey_hotels_travelask",
    "@gofortravel_chat",
    "@wrenjapanchat",
    "@krasnaya_polyana",
    "@Dombay7",
    "@cyprus_f0rum",
    "@dubai_topchat",
    "@batumi_group",
    "@Phuket",
    "@teriberka51",
    "@travelchat24",
    "@trvlclick_chat",
    "@armeniarus_chat",
    "@travelask_all_chats",
]

NICHE = "bali"
STATUS_NEW = "new"


async def main() -> None:
    added = 0
    skipped = 0
    async with AsyncSessionLocal() as session:
        for username in TRAVEL_USERNAMES:
            username = username.strip()
            if not username.startswith("@"):
                username = "@" + username
            try:
                r = await session.execute(select(Target).where(Target.username == username))
                existing = r.scalars().first()
                if existing:
                    if existing.niche != NICHE or existing.status != STATUS_NEW:
                        existing.niche = NICHE
                        existing.status = STATUS_NEW
                        existing.updated_at = datetime.utcnow()
                        print(f"  Обновлена: {username} -> niche={NICHE}, status={STATUS_NEW}")
                        added += 1
                    else:
                        skipped += 1
                        print(f"  Пропуск (уже есть): {username}")
                    continue
                target = Target(
                    username=username,
                    title=username,
                    niche=NICHE,
                    status=STATUS_NEW,
                    can_post=True,
                )
                session.add(target)
                print(f"  + {username}")
                added += 1
            except Exception as e:
                print(f"  Ошибка {username}: {e}")
                await session.rollback()
                continue
        await session.commit()
    print(f"\nГотово: добавлено/обновлено {added}, пропущено {skipped}.")
    print("Account-manager по расписанию будет вступать в эти группы; после warm-up marketer постит india_holi.")


if __name__ == "__main__":
    asyncio.run(main())
