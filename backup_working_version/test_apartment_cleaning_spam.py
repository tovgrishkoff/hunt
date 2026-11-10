"""Regression: apartment-cleaning job bait must not land in realty demand."""

from __future__ import annotations

import ast
import importlib.util
import re
import sys
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MONITOR_SRC = (HERE / "monitor.py").read_text(encoding="utf-8")


def _load_patterns():
    spec = importlib.util.spec_from_file_location(
        "patterns_under_test", ROOT / "patterns.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


patterns = _load_patterns()


def _extract_work_spam_patterns() -> list[str]:
    start = MONITOR_SRC.index("work_spam_patterns = [")
    end = MONITOR_SRC.index("\n        ]", start)
    block = MONITOR_SRC[start:end]
    return [ast.literal_eval(raw) for raw in re.findall(r'r("(?:\\.|[^"])*")', block)]


def match_bait(text: str) -> Optional[str]:
    """Match against work_spam_patterns only (same extractor as escort tests)."""
    text_l = (text or "").lower()
    for pattern in _extract_work_spam_patterns():
        if re.search(pattern, text_l, re.IGNORECASE | re.DOTALL):
            return pattern
    return None


CLEANING_SPAM = (
    "Нужны люди для уборки квартиры после дня рождения друга. "
    "Веселуха была очень страшная.Покормлю,дам покурить калик,"
    "выпить хороший виски, а за уборку 5-10к как бонус)"
)

CLEANING_SPAM_SHORT = "Нужны люди для уборки квартиры после вечеринки, 8к"

LEGIT_DEMAND = "Нужна квартира в Чангу на месяц, бюджет 1500$"
LEGIT_DEMAND_2 = "Ищу виллу снять на Бали, 2 спальни"
LEGIT_OFFER = (
    "Сдаётся апартамент в Убуде, ежедневная уборка, бассейн, "
    "от 1200$ / месяц"
)
LEGIT_PHOTO = "Ищу фотографа на свадьбу в Убуде, бюджет 700$"


def test_patterns_do_not_match_cleaning_as_demand() -> None:
    text = CLEANING_SPAM.lower()
    hits = [
        p
        for p in patterns.NICHES_KEYWORDS["Недвижимость (Спрос)"]
        if re.search(p, text, re.IGNORECASE | re.DOTALL)
    ]
    assert not hits, f"demand patterns still hit cleaning spam: {hits}"


def test_legit_demand_still_matches() -> None:
    for sample in (LEGIT_DEMAND, LEGIT_DEMAND_2):
        text = sample.lower()
        assert any(
            re.search(p, text, re.IGNORECASE | re.DOTALL)
            for p in patterns.NICHES_KEYWORDS["Недвижимость (Спрос)"]
        ), sample


def test_cleaning_banned() -> None:
    for sample in (CLEANING_SPAM, CLEANING_SPAM_SHORT):
        hit = match_bait(sample)
        assert hit, f"expected cleaning ban, got through: {sample}"


def test_legit_not_banned() -> None:
    for sample in (LEGIT_DEMAND, LEGIT_DEMAND_2, LEGIT_OFFER, LEGIT_PHOTO):
        hit = match_bait(sample)
        assert not hit, f"false positive ({hit}): {sample}"


if __name__ == "__main__":
    failed = 0
    for fn in (
        test_patterns_do_not_match_cleaning_as_demand,
        test_legit_demand_still_matches,
        test_cleaning_banned,
        test_legit_not_banned,
    ):
        try:
            fn()
            print(f"OK  {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {fn.__name__}: {exc}")
    print("HIT", match_bait(CLEANING_SPAM), "|", CLEANING_SPAM[:60])
    raise SystemExit(failed)
