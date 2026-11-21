"""Regression: bare «нужны грузчики» must not become an SMM lead."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
MONITOR_SRC = (HERE / "monitor.py").read_text(encoding="utf-8")
SNIPER_SRC = (HERE / "ai_sniper.py").read_text(encoding="utf-8")


def _extract_work_spam_patterns() -> list[str]:
    start = MONITOR_SRC.index("work_spam_patterns = [")
    end = MONITOR_SRC.index("\n        ]", start)
    block = MONITOR_SRC[start:end]
    return [ast.literal_eval(raw) for raw in re.findall(r'r("(?:\\.|[^"])*")', block)]


def match_bait(text: str) -> Optional[str]:
    text_l = (text or "").lower()
    for pattern in _extract_work_spam_patterns():
        if re.search(pattern, text_l, re.IGNORECASE | re.DOTALL):
            return pattern
    return None


SAMPLES = (
    "нужны грузчики",
    "Нужны грузчики",
    "Ищем грузчиков на завтра",
    "Need movers tomorrow",
)


def test_movers_banned_as_job_bait() -> None:
    for sample in SAMPLES:
        hit = match_bait(sample)
        assert hit, f"expected movers ban, got through: {sample}"


def test_smm_strict_lexicon_in_sniper() -> None:
    assert '"SMM"' in SNIPER_SRC
    assert "strict_lexicon_niches" in SNIPER_SRC
    # Block must list SMM among strict niches
    start = SNIPER_SRC.index("self.strict_lexicon_niches = {")
    end = SNIPER_SRC.index("}", start)
    block = SNIPER_SRC[start:end]
    assert '"SMM"' in block
    assert "movers_job_re" in SNIPER_SRC


def test_smm_lexicon_covers_smmshchik() -> None:
    assert "смм(?:щик" in SNIPER_SRC or r"сммщик" in SNIPER_SRC


if __name__ == "__main__":
    test_movers_banned_as_job_bait()
    test_smm_strict_lexicon_in_sniper()
    test_smm_lexicon_covers_smmshchik()
    print("OK")
    sys.exit(0)
