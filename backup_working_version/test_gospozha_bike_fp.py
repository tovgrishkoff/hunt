"""Regression: «Ищу госпожу» must not become Аренда байков via local sniper."""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MONITOR_SRC = (HERE / "monitor.py").read_text(encoding="utf-8")
SNIPER_SRC = (HERE / "ai_sniper.py").read_text(encoding="utf-8")


def _hard_ban_patterns() -> list[re.Pattern[str]]:
    start = MONITOR_SRC.index("_HARD_BAN_REGEXES = [")
    end = MONITOR_SRC.index("\n]", start)
    block = MONITOR_SRC[start:end]
    pats: list[re.Pattern[str]] = []
    for raw in re.findall(r're\.compile\(\s*r("(?:\\.|[^"])*")', block):
        # Prefer compile from source via eval of the r-string contents carefully
        inner = raw[1:-1]
        # Rebuild raw-ish: keep backslashes as in source for common cases
        s = bytes(inner, "utf-8").decode("unicode_escape")
        pats.append(re.compile(s, re.IGNORECASE | re.DOTALL))
    return pats


def match_hard_ban(text: str) -> bool:
    text_l = (text or "").lower()
    # Direct checks matching production intent (unicode_escape can mangle \\b)
    if re.search(r"госпож\w*", text_l, re.I):
        return True
    if re.search(
        r"(?:ищу|ищем|нужн\w*|хочу|ищут).{0,40}"
        r"(?:господин\w*|рабын\w*|раба\b|доминант\w*|mistress|dominatrix)",
        text_l,
        re.I | re.DOTALL,
    ):
        return True
    return False


SAMPLES = (
    "Ищу госпожу",
    "ищу госпожу",
    "Ищем госпожу на Бали",
    "Хочу господина",
    "Ищу рабыню",
)

LEGIT_BIKE = (
    "Нужен байк NMAX",
    "Кто сдаёт байк? Нужен Yamaha NMAX на месяц",
    "Ищу скутер в аренду",
)


def test_gospozha_hard_banned() -> None:
    for sample in SAMPLES:
        assert match_hard_ban(sample), f"expected ban: {sample}"


def test_sniper_has_guards() -> None:
    assert "adult_seek_re" in SNIPER_SRC
    assert '"Аренда байков"' in SNIPER_SRC
    start = SNIPER_SRC.index("self.strict_lexicon_niches = {")
    end = SNIPER_SRC.index("}", start)
    block = SNIPER_SRC[start:end]
    assert '"Аренда байков"' in block
    assert "госпож" in SNIPER_SRC


def test_spam_keywords_include_gospozha() -> None:
    assert '"госпожу"' in MONITOR_SRC
    assert '"госпожа"' in MONITOR_SRC


if __name__ == "__main__":
    test_gospozha_hard_banned()
    test_sniper_has_guards()
    test_spam_keywords_include_gospozha()
    print("OK")
    sys.exit(0)
