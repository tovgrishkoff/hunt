"""Regression: escort/job-bait ads must be banned as spam."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Optional

MONITOR_PATH = Path(__file__).resolve().parent / "monitor.py"
SRC = MONITOR_PATH.read_text(encoding="utf-8")


def _extract_patterns() -> list[str]:
    """Pull work_spam_patterns list from _match_job_bait_spam without importing aiogram."""
    start = SRC.index("work_spam_patterns = [")
    end = SRC.index("\n        ]", start)
    block = SRC[start:end]
    return re.findall(r'r("(?:\\.|[^"])*")', block)


def match_bait(text: str) -> Optional[str]:
    text_l = (text or "").lower()
    for raw in _extract_patterns():
        pattern = ast_literal_str(raw)
        if re.search(pattern, text_l, re.IGNORECASE):
            return pattern
    return None


def ast_literal_str(raw: str) -> str:
    # raw is like r"pattern" from source — evaluate as Python string literal content
    import ast

    return ast.literal_eval(raw)


BAIT_SAMPLES = [
    (
        "Пара часов с пользой: упаковать декорации после фотосъёмки. "
        "На месте объясним каждый шаг. Сумма 7000. Интересно? Все детали в личке."
    ),
    "Нужно приехать по адресу и сделать фото объекта, 2000р",
    (
        "Есть несколько заказов по участкам и загородным домам. "
        "Где-то привести участок в порядок, где-то убрать старые конструкции, "
        "что-то установить. Подойдут люди, которые хорошо знакомы с инструментом. "
        "От 25 000 на руки"
    ),
    "Нужен человек с машиной для перевозки старых вещей, дам 6к",
    (
        "Есть необычная халтурка, фотограф участков, техника и расходы на нас, "
        "20 000 на руки, детали лично"
    ),
    "Вечірній підробіток. Деталі в особисті повідомлення.|Є халтура на вечір. Пиши в приват.",
    "На массовку нужно несколько парней, по 7 000р каждому, обедом угощаем",
    (
        "Ищу человека в авто направление. Подбор, сопровождение и организация сделок. "
        "9 800р в день, проезд или бенз компенсируем"
    ),
    (
        "Требуется перевозчик! Рейсы на дальние расстояния до 1000 км. Не наркотики, "
        "работа легальная, от 25 лет, только граждане России. Оклад в месяц от 150 000 р"
    ),
    (
        "Мы в поисках людей на вакансию монтажник будешь получать  прибыль от 90 000 в неделю "
        "| Мы открываем набор людей на вакансию бармен у нас есть ночная и дневная смена, "
        "с хорошей ставкой от 80 000 в неделю и очень хорошие чаевые "
        "| Устал от одиночества ? Могу тебе помочь скоротать твои дни "
        "| Нужны люди для нашей компании в Фото-студию  фотографыабсолютно любой пол. "
        "Ставка от 100 000 в неделю и больше"
    ),
    (
        "Приглашаем исполнителей на интересные поручения. Квесты, съёмки, различные мероприятия "
        "и другие направления. Не во всех направлениях нужен опыт, главное, ответственно "
        "подходить к поручениям.От 15 000 за день"
    ),
    "Нужны дворники, оплата 10 тысяч в день, жилье предоставляем.",
    "Нужен муж на час, подвинуть мебель в доме и прикрутить пару полок, 5500 по окончанию",
]

LEGIT_SAMPLES = [
    "Ищу фотографа на свадьбу в Убуде, бюджет 700$",
    "Сниму виллу на Бали на месяц, бюджет 3000$",
    "Нужен видеограф снять reels для бренда одежды",
    "Куплю квартиру в Чангу до 300к",
]


def test_bait_blocked() -> None:
    for sample in BAIT_SAMPLES:
        hit = match_bait(sample)
        assert hit, f"expected bait ban, got through: {sample[:80]}"


def test_legit_not_blocked() -> None:
    for sample in LEGIT_SAMPLES:
        hit = match_bait(sample)
        assert not hit, f"false positive ({hit}): {sample}"


if __name__ == "__main__":
    failed = 0
    for fn in (test_bait_blocked, test_legit_not_blocked):
        try:
            fn()
            print(f"OK  {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {fn.__name__}: {exc}")
    # show which pattern hits each bait
    for sample in BAIT_SAMPLES:
        print("HIT", match_bait(sample), "|", sample[:60])
    raise SystemExit(failed)
