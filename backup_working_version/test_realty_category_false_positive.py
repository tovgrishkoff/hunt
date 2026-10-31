"""Regression: crypto/currency messages must not become 'Продажа недвижимости'.

Bug: bare stem 'дом' matched inside 'переводом'
(e.g. 'Куплю ... крипту ... переводом' → false realty category).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Set

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from patterns import NICHES_KEYWORDS  # noqa: E402


def _load_monitor_helpers() -> dict:
    """Load housing/currency regexes from monitor.py without importing aiogram."""
    src = Path(__file__).resolve().parent.joinpath("monitor.py").read_text(encoding="utf-8")
    lines = src.splitlines()
    # Constants live between REAL_ESTATE_NEGATIVE_KEYWORDS and BIKE_STRONG_KEYWORDS.
    start = next(i for i, line in enumerate(lines) if line.startswith("CURRENCY_CONTEXT_RE"))
    end = next(i for i, line in enumerate(lines) if line.startswith("BIKE_STRONG_KEYWORDS"))
    ns: dict = {"re": re}
    exec("\n".join(lines[start:end]), ns)
    return ns


HELPERS = _load_monitor_helpers()
HOUSING_CONTEXT_RE = HELPERS["HOUSING_CONTEXT_RE"]
CURRENCY_CONTEXT_RE = HELPERS["CURRENCY_CONTEXT_RE"]
REAL_ESTATE_NICHES = {"Продажа недвижимости", "Сдача недвижимости"}


def niches_from_patterns(text: str) -> Set[str]:
    text_l = (text or "").lower()
    found: Set[str] = set()
    for niche, patterns in NICHES_KEYWORDS.items():
        for pattern in patterns:
            if re.search(pattern, text_l):
                found.add(niche)
                break
    return found


def postprocess_like_monitor(text: str, niches: Set[str]) -> Set[str]:
    """Mirror monitor._postprocess_niches currency/realty conflict rule."""
    text_lower = (text or "").lower()
    has_housing = bool(HOUSING_CONTEXT_RE.search(text_lower))
    has_currency = bool(CURRENCY_CONTEXT_RE.search(text_lower))
    niches = set(niches)
    if (
        niches & REAL_ESTATE_NICHES
        and ("Обмен валют" in niches or has_currency)
        and not has_housing
    ):
        niches = {n for n in niches if n not in REAL_ESTATE_NICHES}
    return niches


def test_crypto_transfer_not_realty() -> None:
    text = (
        "Куплю вашу крипту за евро наличкой или переводом в Бандунге. "
        "Встреча в Dago"
    )
    found = niches_from_patterns(text)
    assert "Обмен валют" in found, found
    assert "Продажа недвижимости" not in found, found
    assert "Сдача недвижимости" not in found, found


def test_real_house_buy_still_matches() -> None:
    assert "Продажа недвижимости" in niches_from_patterns("Куплю дом в Чангу до 300к")
    assert "Продажа недвижимости" in niches_from_patterns("Куплю квартиру на Бали")
    assert "Продажа недвижимости" in niches_from_patterns("Продам виллу 3br Canggu")
    assert "Сдача недвижимости" in niches_from_patterns("Сниму дом в Убуде на месяц")


def test_housing_context_ignores_perevodom() -> None:
    assert not HOUSING_CONTEXT_RE.search("оплата переводом в бандунге")
    assert HOUSING_CONTEXT_RE.search("куплю дом в чангу")
    assert CURRENCY_CONTEXT_RE.search("крипту за евро переводом")


def test_postprocess_drops_realty_for_crypto() -> None:
    text = "Куплю вашу крипту за евро наличкой или переводом в Бандунге"
    result = postprocess_like_monitor(
        text, {"Обмен валют", "Продажа недвижимости"}
    )
    assert "Продажа недвижимости" not in result
    assert "Обмен валют" in result


if __name__ == "__main__":
    tests = [
        test_crypto_transfer_not_realty,
        test_real_house_buy_still_matches,
        test_housing_context_ignores_perevodom,
        test_postprocess_drops_realty_for_crypto,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"OK  {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {fn.__name__}: {exc}")
    raise SystemExit(failed)
