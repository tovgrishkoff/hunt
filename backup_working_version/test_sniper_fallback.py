#!/usr/bin/env python3
"""Проверка локального sniper fallback (без OpenAI)."""

from __future__ import annotations

import asyncio
import sys
from typing import List, Set, Tuple

from monitor import MessageMonitor


class _Dummy:
    pass


POSITIVE: List[Tuple[str, str]] = [
    ("Ищу SMM-менеджера для ведения инстаграма", "SMM"),
    ("Нужен SEO специалист, продвижение сайта", "SEO"),
    ("Ищу мобилографа на завтра", "Мобилографы"),
    ("Нужен разработчик, сделать телеграм бота", "Тех. специалисты"),
    ("Сниму виллу в Убуде на месяц", "Недвижимость (Спрос)"),
    ("Сдам квартиру в Чангу 1200$/мес", "Недвижимость (Предложение)"),
    ("Нужен трансфер из аэропорта в Чангу", "Транспорт"),
    ("Кто сдаёт байк? Нужен NMAX", "Аренда байков"),
    ("Ищу ugc креатора для бренда", "UGC"),
    ("Заказ по нейросетям: нужен ChatGPT", "Заказы по AI"),
]

NEGATIVES: List[str] = [
    "Привет, как дела?",
    "Сегодня хорошая погода",
    "Куплю USDT за наличные",
    "Просто болтаем про жизнь",
    # Барахолка / еда ≠ Продажа недвижимости (local sniper false positive)
    "Продам свинину недорогой",
    "Сдам свинину недорогой",
    "Продам кроссовки",
]


async def main() -> int:
    # Без openai_api_key → только patterns + sniper
    mon = MessageMonitor(_Dummy(), _Dummy(), openai_api_key=None)
    assert mon.semantic_sniper is not None, "sniper must init"
    assert mon.ai_classifier is None

    ok = fail = 0
    print("=== POSITIVE (patterns or sniper) ===")
    for text, need in POSITIVE:
        r = await mon._hybrid_classify_message(text)
        niches = set() if r.get("is_spam") else set(r.get("niches") or [])
        status = "OK" if need in niches else "FAIL"
        ok += status == "OK"
        fail += status == "FAIL"
        print(
            f"[{status}] need={need!r} got={sorted(niches)} "
            f"reason={r.get('reason')} | {text[:60]}"
        )

    print("\n=== NEGATIVE ===")
    for text in NEGATIVES:
        r = await mon._hybrid_classify_message(text)
        niches = set() if r.get("is_spam") else set(r.get("niches") or [])
        status = "OK" if not niches else "FAIL"
        ok += status == "OK"
        fail += status == "FAIL"
        print(f"[{status}] got={sorted(niches)} reason={r.get('reason')} | {text}")

    # Simulate GPT unavailable → sniper path with classifier present
    print("\n=== GPT UNAVAILABLE PATH ===")
    mon2 = MessageMonitor(_Dummy(), _Dummy(), openai_api_key="sk-fake")
    if mon2.ai_classifier:
        mon2.ai_classifier._paused_until = __import__("datetime").datetime.now() + __import__(
            "datetime"
        ).timedelta(hours=1)
        # Force pause without calling API: classify_message should return ai_unavailable
        r = await mon2.ai_classifier.classify_message("Ищу SMM менеджера")
        assert r.get("ai_unavailable"), r
        full = await mon2._hybrid_classify_message("Ищу SMM-менеджера для ведения инстаграма")
        niches = set(full.get("niches") or [])
        status = "OK" if "SMM" in niches else "FAIL"
        ok += status == "OK"
        fail += status == "FAIL"
        print(f"[{status}] paused GPT → got={sorted(niches)} reason={full.get('reason')}")

    # False positive: прогулка/компания ≠ Макияж
    print("\n=== FALSE POSITIVE GUARDS ===")
    nuanu = (
        "Хочу Нуану сегодня посетить, погулять по красивой территории, "
        "встретить закат.\n\nЕсли найду компанию себе, буду рада"
    )
    sniper_result = mon.semantic_sniper.classify_fallback(nuanu)
    status = "OK" if not sniper_result.get("niches") else "FAIL"
    ok += status == "OK"
    fail += status == "FAIL"
    print(
        f"[{status}] Nuanu meetup must not be Макияж: "
        f"got={sniper_result.get('niches')} reason={sniper_result.get('reason')}"
    )

    pork = "Продам свинину недорогой"
    pork_result = mon.semantic_sniper.classify_fallback(pork)
    status = "OK" if not pork_result.get("niches") else "FAIL"
    ok += status == "OK"
    fail += status == "FAIL"
    print(
        f"[{status}] pork offer must not be Продажа недвижимости: "
        f"got={pork_result.get('niches')} reason={pork_result.get('reason')}"
    )

    house = "Продам дом в Убуде"
    house_result = mon.semantic_sniper.classify_fallback(house)
    status = (
        "OK"
        if "Продажа недвижимости" in (house_result.get("niches") or [])
        else "FAIL"
    )
    ok += status == "OK"
    fail += status == "FAIL"
    print(
        f"[{status}] real house sale must stay Продажа недвижимости: "
        f"got={house_result.get('niches')} reason={house_result.get('reason')}"
    )

    print(f"\nTOTAL {ok}/{ok + fail} passed, {fail} failed")
    return fail


if __name__ == "__main__":
    sys.exit(asyncio.get_event_loop().run_until_complete(main()))
