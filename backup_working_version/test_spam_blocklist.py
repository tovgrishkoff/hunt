"""Regression: user spam button blocklist + assistant/housing job bait."""

from __future__ import annotations

import ast
import importlib.util
import re
import tempfile
from pathlib import Path
from typing import Optional

import spam_blocklist

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
    text_l = (text or "").lower()
    for pattern in _extract_work_spam_patterns():
        if re.search(pattern, text_l, re.IGNORECASE | re.DOTALL):
            return pattern
    return None


ASSISTANT_SPAM = (
    "Ищу личного помощника, мелкие задачи по дому, придоставляется жалье "
    "со всеми удобствами, пишите, обсудим оплату и премии"
)

LEGIT_DEMAND = "Нужна квартира в Чангу на месяц, бюджет 1500$"
NOTIFICATION = (
    "🔔 Новое сообщение\n\n"
    "🔍 Тип: ПОИСК\n"
    "📂 Категории: Недвижимость (Спрос)\n\n"
    "📄 Сообщение:\n"
    f"{ASSISTANT_SPAM}\n\n"
    "👤 Ggdhjvj\n\n"
    "💬 Чат: Бали AntiChat\n"
    "🔗 Ссылка: https://t.me/bali_chat/932842"
)


def test_assistant_not_realty_demand() -> None:
    text = ASSISTANT_SPAM.lower()
    hits = [
        p
        for p in patterns.NICHES_KEYWORDS["Недвижимость (Спрос)"]
        if re.search(p, text, re.IGNORECASE | re.DOTALL)
    ]
    assert not hits, hits


def test_assistant_banned() -> None:
    hit = match_bait(ASSISTANT_SPAM)
    assert hit, ASSISTANT_SPAM


def test_blocklist_roundtrip() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "user_spam_blocklist.json"
        lead = spam_blocklist.extract_lead_text_from_notification(NOTIFICATION)
        assert lead and "помощника" in lead
        sender = spam_blocklist.extract_sender_from_notification(NOTIFICATION)
        assert sender.get("sender_name") == "Ggdhjvj"

        result = spam_blocklist.add_spam_entry(
            message_text=lead,
            message_id="abc",
            marked_by="1",
            sender_name=sender.get("sender_name"),
            path=path,
        )
        assert result["ok"], result
        assert spam_blocklist.is_text_blocked(ASSISTANT_SPAM, path=path)
        # typo-normalized duplicate still blocked
        twin = ASSISTANT_SPAM.replace("жалье", "жилье").replace(
            "придоставляется", "предоставляется"
        )
        assert spam_blocklist.is_text_blocked(twin, path=path)
        assert spam_blocklist.is_sender_blocked(sender_name="Ggdhjvj", path=path)
        assert not spam_blocklist.is_text_blocked(LEGIT_DEMAND, path=path)


if __name__ == "__main__":
    failed = 0
    for fn in (
        test_assistant_not_realty_demand,
        test_assistant_banned,
        test_blocklist_roundtrip,
    ):
        try:
            fn()
            print(f"OK  {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {fn.__name__}: {exc}")
    raise SystemExit(failed)
