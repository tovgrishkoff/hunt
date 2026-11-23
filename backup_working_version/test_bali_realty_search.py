#!/usr/bin/env python3
"""Bali realty / search regression: demand must pass spam + hit Спрос niche.

Root-cause coverage (2026-11-24):
- bare «пишите в лс» used to mark real housing demand as spam
- classic Bali phrases must resolve to Недвижимость (Спрос)
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import List, Optional, Set, Tuple

logging.basicConfig(level=logging.WARNING)
logging.getLogger("monitor").setLevel(logging.ERROR)
logging.getLogger("ai_classifier").setLevel(logging.ERROR)
logging.getLogger("ai_sniper").setLevel(logging.ERROR)

from monitor import MessageMonitor  # noqa: E402


CASES: List[Tuple[str, str, Set[str], Optional[str], bool]] = [
    # text, niche, forbidden, msg_type, must_not_be_spam
    (
        "Сниму виллу в Убуде на 2 месяца, бюджет 1500$, пишите в лс",
        "Недвижимость (Спрос)",
        {"Недвижимость (Предложение)", "Продажа недвижимости"},
        "ПОИСК",
        True,
    ),
    (
        "Ищу квартиру в Чангу на месяц в аренду. Пишите в ЛС!",
        "Недвижимость (Спрос)",
        {"Недвижимость (Предложение)"},
        "ПОИСК",
        True,
    ),
    (
        "🇦🇪 СРОЧНО ИЩЕМ КВАРТИРУ В ДУБАЕ!\nАренда на год, без комиссии.\nЕсть варианты? Срочно пишите в ЛС!",
        "Недвижимость (Спрос)",
        {"Недвижимость (Предложение)"},
        "ПОИСК",
        True,
    ),
    (
        "Ищу квартиру 300-350$\nЦентр отопление\nКровать + диван",
        "Недвижимость (Спрос)",
        {"Недвижимость (Предложение)"},
        "ПОИСК",
        True,
    ),
    (
        "Нужен байк на месяц в Чангу, Yamaha NMAX, пишите в лс",
        "Аренда байков",
        {"Аренда авто"},
        "ПОИСК",
        True,
    ),
    (
        "Ищу фотографа на Бали завтра, бюджет 200$, детали в лс",
        "Фотограф",
        set(),
        "ПОИСК",
        True,
    ),
    (
        "Ищу комнату/виллу/гест",
        "Недвижимость (Спрос)",
        {"Недвижимость (Предложение)"},
        "ПОИСК",
        True,
    ),
]

# Real job spam must stay spam (not pass as ПОИСК housing)
SPAM_MUST: List[str] = [
    "Халтурка на руки 5000 детали в лс",
    "Есть дело, не белое но на руки 20.000р детали в лс",
]


async def main() -> int:
    mon = MessageMonitor(_DummyBot(), _DummyDb(), openai_api_key=None)
    # No GPT during unit smoke — patterns/sniper only.
    mon.ai_classifier = None

    failed = 0
    total = len(CASES) + len(SPAM_MUST)
    for text, niche, forbidden, msg_type, must_not_spam in CASES:
        if must_not_spam and mon.is_spam_message(text):
            print(f"FAIL spam-FP: {text[:80]!r}")
            failed += 1
            continue
        result = await mon._hybrid_classify_message(text)
        niches = set(result.get("niches") or [])
        got_type = result.get("message_type")
        is_spam = bool(result.get("is_spam"))
        ok = (
            niche in niches
            and niches.isdisjoint(forbidden)
            and (msg_type is None or got_type == msg_type)
            and not is_spam
        )
        status = "OK" if ok else "FAIL"
        if not ok:
            failed += 1
        print(
            f"{status}: niche={niche!r} got={sorted(niches)} "
            f"type={got_type} spam={is_spam} :: {text[:70]!r}"
        )
    for text in SPAM_MUST:
        ok = mon.is_spam_message(text)
        if not ok:
            failed += 1
        print(f"{'OK' if ok else 'FAIL'}: expect_spam :: {text[:70]!r}")
    print(f"\n{total - failed}/{total} passed")
    return 1 if failed else 0


class _DummyBot:
    pass


class _DummyDb:
    pass


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
