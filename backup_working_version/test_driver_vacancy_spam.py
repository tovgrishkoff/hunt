"""Regression: driver vacancy covers (kladman) must not hit Transport."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from monitor import MessageMonitor, _HARD_BAN_REGEXES  # noqa: E402
from patterns import NICHES_KEYWORDS  # noqa: E402


SPAM_SAMPLES = [
    "Требуется надёжный и ответственный водитель для выполнения регулярных рейсов."
    "Доход - от 50 000 до 100 000 ₽ за один рейс. Маршруты, график, требования и остальное в лс",
    "Водитель на личном автомобиле для перевозки документов по городу, 15 000 за день, ГСМ компенсируем",
    "Водитель для детей, возить в школу и по кружкам, от 10000 за смену",
    "Нужен водитель для регулярных рейсов, детали в лс",
]

LEGIT_SAMPLES = [
    "Ищу трансфер из аэропорта Денпасар в Убуд на завтра",
    "Нужно такси в Чангу, сколько стоит?",
    "Заказать трансфер Семеньяк — аэропорт вечером",
    "Ищу частного водителя на Бали на день, трансфер по острову",
    "Нужен водитель/трансфер из аэропорта в Чангу",
]


def niches_from_patterns(text: str) -> set[str]:
    text_l = text.lower()
    found: set[str] = set()
    for niche, patterns in NICHES_KEYWORDS.items():
        for pattern in patterns:
            if re.search(pattern, text_l, re.IGNORECASE):
                found.add(niche)
                break
    return found


def hard_banned(text: str) -> bool:
    # Mirror MessageMonitor._normalize_for_moderation lightly: lowercase is enough here
    t = text.lower()
    return any(rx.search(t) for rx in _HARD_BAN_REGEXES)


def test_spam_banned_and_not_transport() -> None:
    for text in SPAM_SAMPLES:
        assert hard_banned(text), f"expected hard ban: {text[:80]}"
        assert "Транспорт" not in niches_from_patterns(text), text[:80]


def test_legit_transport_still_matches() -> None:
    for text in LEGIT_SAMPLES:
        assert not hard_banned(text), f"false hard ban: {text}"
        assert "Транспорт" in niches_from_patterns(text), text


def test_monitor_is_spam_message() -> None:
    # Avoid full Bot/DB init: only need the spam helpers on the class
    mon = object.__new__(MessageMonitor)
    for text in SPAM_SAMPLES:
        assert mon.is_spam_message(text), text[:80]
    for text in LEGIT_SAMPLES:
        assert not mon.is_spam_message(text), text


if __name__ == "__main__":
    test_spam_banned_and_not_transport()
    test_legit_transport_still_matches()
    test_monitor_is_spam_message()
    print("ok")
