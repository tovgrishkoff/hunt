#!/usr/bin/env python3
"""Demand (ПОИСК) coverage for every Lead Hunter niche.

Especially digital niches: we need client demand («ищу / нужен»),
not bare niche mentions and not seller offers.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Dict, List, Optional, Set, Tuple

logging.basicConfig(level=logging.WARNING)
logging.getLogger("monitor").setLevel(logging.ERROR)
logging.getLogger("ai_classifier").setLevel(logging.ERROR)
logging.getLogger("ai_sniper").setLevel(logging.ERROR)

from monitor import MessageMonitor  # noqa: E402

# Force pattern-first path: disable live GPT spend during unit smoke.
# Sniper still available as fallback if patterns miss.


class _Dummy:
    pass


# (text, required_niche, forbidden_niches, require_type_or_None)
DEMAND: List[Tuple[str, str, Set[str], Optional[str]]] = [
    # —— classic ——
    ("Ищу фотографа на свадьбу в Чангу, бюджет 300$", "Фотограф", {"Видеограф"}, "ПОИСК"),
    ("Нужен видеограф на мероприятие, снимите клип", "Видеограф", {"Фотограф"}, "ПОИСК"),
    ("Сниму виллу в Убуде на 2 месяца, бюджет 1500$", "Недвижимость (Спрос)", {"Недвижимость (Предложение)", "Продажа недвижимости"}, "ПОИСК"),
    ("Ищу квартиру в Чангу на месяц в аренду", "Недвижимость (Спрос)", {"Недвижимость (Предложение)"}, "ПОИСК"),
    ("Куплю виллу на Бали до 300к$", "Продажа недвижимости", {"Недвижимость (Спрос)", "Недвижимость (Предложение)"}, "ПОИСК"),
    ("Ищу мастера маникюра, наращивание ногтей на завтра", "Маникюр", set(), "ПОИСК"),
    ("Нужен парикмахер, стрижка и окрашивание волос", "Волосы", set(), "ПОИСК"),
    ("Ищу аренду авто на неделю, нужна машина автомат", "Аренда авто", {"Аренда байков"}, "ПОИСК"),
    ("Ищу мастера по наращиванию ресниц, объём 2D", "Реснички", set(), "ПОИСК"),
    ("Нужна коррекция бровей и ламинирование бровей", "Брови", set(), "ПОИСК"),
    ("Ищу визажиста, макияж на свадьбу", "Макияж", set(), "ПОИСК"),
    ("Нужен косметолог, чистка лица и пилинг", "Косметология", set(), "ПОИСК"),
    ("Кто сдаёт байк? Нужен Yamaha NMAX на месяц", "Аренда байков", {"Аренда авто"}, "ПОИСК"),
    ("Ищу фотостудию в аренду на съёмку", "Медиа-студия", set(), "ПОИСК"),
    ("Ищем гида на индивидуальную экскурсию по Убуду", "Туризм", set(), "ПОИСК"),
    ("Нужен трансфер из аэропорта в Чангу, такси на двоих", "Транспорт", {"Аренда авто"}, "ПОИСК"),
    # —— digital demand (new niches) ——
    ("Ищу мобилографа на завтра, бюджет 100$", "Мобилографы", set(), "ПОИСК"),
    ("Нужен мобилограф для съёмки на айфон", "Мобилографы", set(), "ПОИСК"),
    ("Кто умеет снимать на телефон? Ищу мобилографа", "Мобилографы", set(), "ПОИСК"),
    ("Нужен SMM-менеджер для ведения инстаграма", "SMM", set(), "ПОИСК"),
    ("Ищу сммщика, ведение соцсетей под ключ", "SMM", set(), "ПОИСК"),
    ("Требуется SMM специалист в проект", "SMM", set(), "ПОИСК"),
    ("Ищу UGC креатора для отзывов о продукте", "UGC", set(), "ПОИСК"),
    ("Нужен ugc creator на заказ, контент от пользователей", "UGC", set(), "ПОИСК"),
    ("Нужен SEO специалист, продвижение сайта", "SEO", set(), "ПОИСК"),
    ("Ищу сео для аудита сайта", "SEO", set(), "ПОИСК"),
    ("Требуется SEO, поисковое продвижение интернет-магазина", "SEO", set(), "ПОИСК"),
    ("Ищу продюсера онлайн-курса, продюсирование запуска", "Продюсирование", set(), "ПОИСК"),
    ("Нужен продюсер под запуск курса", "Продюсирование", set(), "ПОИСК"),
    ("Нужен PR-менеджер, пиарщик в команду", "PR-менеджеры", set(), "ПОИСК"),
    ("Ищу пиар-менеджера для бренда", "PR-менеджеры", set(), "ПОИСК"),
    ("Нужна реклама в телеграм и инстаграм, закуп посевов", "Реклама TG/INST", set(), "ПОИСК"),
    ("Ищу таргетолога под рекламу в инстаграм", "Реклама TG/INST", set(), "ПОИСК"),
    ("Нужен закуп рекламы в телеграм каналах", "Реклама TG/INST", set(), "ПОИСК"),
    ("Ищу медиабайера, арбитраж трафика, CPA", "Медиабайеры", set(), "ПОИСК"),
    ("Нужен media buyer в команду", "Медиабайеры", set(), "ПОИСК"),
    ("Нужен разработчик, сделать телеграм бота", "Тех. специалисты", set(), "ПОИСК"),
    ("Ищу программиста на доработку сайта", "Тех. специалисты", set(), "ПОИСК"),
    ("Требуется no-code специалист, сделать сайт", "Тех. специалисты", set(), "ПОИСК"),
    ("Заказ по нейросетям: нужен ChatGPT специалист", "Заказы по AI", set(), "ПОИСК"),
    ("Нужен midjourney для генерации картинок на заказ", "Заказы по AI", set(), "ПОИСК"),
    ("Ищу специалиста по нейросетям, автоматизация", "Заказы по AI", set(), "ПОИСК"),
    ("Требуется сотрудник на удалённую работу", "Удаленная работа", set(), "ПОИСК"),
    ("Ищем remote employee, remote work, full-time", "Удаленная работа", set(), "ПОИСК"),
    ("Нужен удалённый сотрудник в команду", "Удаленная работа", set(), "ПОИСК"),
]

# Offer / noise: must NOT become a lead in demand-only niches (niches empty or not ПОИСК)
SUPPLY_OR_NOISE: List[Tuple[str, Set[str]]] = [
    ("Я SMM-менеджер, веду инстаграм, прайс в лс", {"SMM"}),
    ("Предлагаю услуги SEO продвижения сайта", {"SEO"}),
    ("UGC креатор, снимаю отзывы, портфолио в шапке", {"UGC"}),
    ("Я продюсер онлайн-курсов, беру проекты", {"Продюсирование"}),
    ("Пиарщик, пишу пресс-релизы, пишите в лс", {"PR-менеджеры"}),
    ("Делаю рекламу в телеграм и инстаграм, посевы", {"Реклама TG/INST"}),
    ("Медиабайер, арбитраж трафика, CPA, ROI", {"Медиабайеры"}),
    ("Я программист, делаю ботов и сайты", {"Тех. специалисты"}),
    ("Генерирую картинки в midjourney на заказ, пишите", {"Заказы по AI"}),
    ("Мобилограф, снимаю на айфон, свободные окна", {"Мобилографы"}),
    (
        "#визитка #сайт\nЗанимаюсь разработкой сайтов и Telegram-ботов для бизнеса. "
        "Если вам нужен сайт — пишите в личные сообщения",
        {"SEO", "SMM", "Тех. специалисты", "Заказы по AI"},
    ),
    ("Просто болтаем про chatgpt и нейросети", {"Заказы по AI"}),
    ("Куплю USDT дорого. Наличка на руках.", {"Аренда авто", "SMM", "SEO", "Тех. специалисты", "Удаленная работа"}),
    (
        "Dubai Photo & Film Production.\n"
        "Давно планировали профессиональную фотосессию или видеосъёмку в Дубае для себя?\n"
        "Я предлагаем полный продакшн. Вам не нужно заниматься организацией — "
        "мы берём всё на себя. По деталям и бронированию и партфолио — в личные сообщения.",
        {"Фотограф", "Видеограф"},
    ),
]


def niches_of(result: Dict) -> Set[str]:
    if result.get("is_spam"):
        return set()
    return set(result.get("niches") or [])


async def run() -> int:
    mon = MessageMonitor(_Dummy(), _Dummy(), None)
    # Prefer patterns; keep AI if present but cases should hit patterns.
    failed = 0
    total = 0
    by_niche: Dict[str, List[str]] = {}

    print("=== DEMAND (ПОИСК) ===")
    for text, need, forbid, need_type in DEMAND:
        total += 1
        result = await mon._hybrid_classify_message(text)
        got = niches_of(result)
        msg_type = result.get("message_type")
        ok = need in got and not (got & forbid)
        if need_type and ok:
            ok = msg_type == need_type
        status = "OK" if ok else "FAIL"
        if not ok:
            failed += 1
            by_niche.setdefault(need, []).append(text)
        print(
            f"[{status}] {need!r} type={msg_type} got={sorted(got)} | {text[:68]}"
        )
        if not ok:
            print(
                f"       forbid_hit={sorted(got & forbid)} "
                f"spam={result.get('is_spam')} reason={result.get('reason')}"
            )

    print("\n=== SUPPLY / NOISE (не спрос) ===")
    for text, forbid in SUPPLY_OR_NOISE:
        total += 1
        result = await mon._hybrid_classify_message(text)
        got = niches_of(result)
        msg_type = result.get("message_type")
        # Demand-only niches must not be broadcast for seller offers
        bad = got & forbid
        ok = not bad
        status = "OK" if ok else "FAIL"
        if not ok:
            failed += 1
        print(
            f"[{status}] forbid_as_ПОИСК={sorted(forbid)} "
            f"type={msg_type} got={sorted(got)} | {text[:68]}"
        )

    covered = sorted({n for _, n, _, _ in DEMAND})
    print(f"\nNiches with demand cases ({len(covered)}): {', '.join(covered)}")
    if by_niche:
        print("\nFAILED niches:")
        for niche, texts in sorted(by_niche.items()):
            print(f"  - {niche}: {len(texts)} fail(s)")
            for t in texts:
                print(f"      • {t}")

    print(f"\nTOTAL {total - failed}/{total} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.get_event_loop().run_until_complete(run()))
