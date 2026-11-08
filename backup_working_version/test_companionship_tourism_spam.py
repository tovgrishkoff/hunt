"""Regression: dating/companionship bait must not become Tourism leads."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from monitor import MessageMonitor  # noqa: E402


SPAM_SAMPLES = [
    (
        "Чатик, привет! Я тут первую неделю, ищу того, кто покажет мне остров "
        "и будет приятной компанией. Гиды, пожалуйста, не пишите, экскурсии не нужны"
    ),
    "Ищу приятную компанию на Бали, покажет остров",
    "Гиды не пишите, ищу просто приятную компанию прогуляться",
    "Только прилетел, ищу кто покажет остров и будет приятной компанией",
]

LEGIT_SAMPLES = [
    "Ищем гида на индивидуальную экскурсию по Убуду",
    "Нужен тур с гидом на целый день, храмы и водопады",
    "Подскажите хорошего гида для поездки по острову",
]


def test_companionship_spam_banned() -> None:
    mon = object.__new__(MessageMonitor)
    for sample in SPAM_SAMPLES:
        assert mon.is_spam_message(sample), sample


def test_legit_tourism_not_banned() -> None:
    mon = object.__new__(MessageMonitor)
    for sample in LEGIT_SAMPLES:
        assert not mon.is_spam_message(sample), sample


if __name__ == "__main__":
    test_companionship_spam_banned()
    test_legit_tourism_not_banned()
    print("ok")
