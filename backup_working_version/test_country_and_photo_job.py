"""Geo detection + photographer job vacancy regression."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from monitor import MessageMonitor  # noqa: E402


def test_krasnodar_is_russia_not_bali() -> None:
    mon = object.__new__(MessageMonitor)
    assert mon._get_country_from_chat_title("КРАСНОДАР не РОСТОВ ЧАТ 🥳") == "Россия"
    assert mon._get_country_from_chat_title("krasnodar_4atik") == "Россия"
    assert mon._get_country_from_chat_title("БалиЧат Маркет") == "Бали"
    assert mon._get_country_from_chat_title("Случайный чат без гео") is None
    assert mon._get_country_from_chat_title("Вьетнам Чат Bazaar") == "Вьетнам"
    assert mon._get_country_from_chat_title("Дубай аренда квартиры") == "Дубай"
    assert mon._get_country_from_chat_title("Ереван чат") == "Армения"


def test_photo_job_vacancy_banned() -> None:
    mon = object.__new__(MessageMonitor)
    spam = (
        "📸 Требуются фотографы для постоянной работы с моделями и одеждой. "
        "Официальное трудоустройство. Напиши свой город мне в личку"
    )
    legit = "Ищу фотографа на завтра в Чангу, семейная съёмка, бюджет 150$"
    assert mon.is_spam_message(spam), spam
    assert not mon.is_spam_message(legit), legit


if __name__ == "__main__":
    test_krasnodar_is_russia_not_bali()
    test_photo_job_vacancy_banned()
    print("ok")
