"""Regression: grey FX ads must not land in Transport / must be spam-banned."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from monitor import MessageMonitor  # noqa: E402


FX_AML_SPAM = """ОБМЕН ВАЛЮТ | TURKEY / GEORGIA

USDT CASH / TRANSFER
TURKISH BANKS
Ziraat Bankasi
GEORGIAN BANKS
Bank of Georgia

Офисы в ключевых городах — по записи.
Курьерский сервис — по согласованию
Конфиденциальность. Проверка реквизитов
Выдаем займы под залог активов.
Без верификации. Без AML.

Нужен актуальный курс?
Пишите менеджеру."""

LEGIT_FX = "Куплю USDT за наличные, личная встреча в Чангу"
LEGIT_TRANSPORT = "Нужен трансфер из аэропорта в Чангу, такси на двоих"
LEGIT_AIRPORT_TRANSFER = "Looking for airport transfer from DPS to Canggu"


class _Dummy:
    pass


def test_fx_aml_is_spam() -> None:
    mon = object.__new__(MessageMonitor)
    assert mon.is_spam_message(FX_AML_SPAM), FX_AML_SPAM
    assert not mon.is_spam_message(LEGIT_FX), LEGIT_FX
    assert not mon.is_spam_message(LEGIT_TRANSPORT), LEGIT_TRANSPORT


async def test_niches() -> None:
    mon = MessageMonitor(_Dummy(), _Dummy(), None)
    spam = await mon._hybrid_classify_message(FX_AML_SPAM)
    assert spam.get("is_spam"), spam

    fx = await mon._hybrid_classify_message(LEGIT_FX)
    assert not fx.get("is_spam"), fx
    assert "Обмен валют" in (fx.get("niches") or []), fx
    assert "Транспорт" not in (fx.get("niches") or []), fx

    tr = await mon._hybrid_classify_message(LEGIT_TRANSPORT)
    assert "Транспорт" in (tr.get("niches") or []), tr

    en = await mon._hybrid_classify_message(LEGIT_AIRPORT_TRANSFER)
    assert "Транспорт" in (en.get("niches") or []), en


if __name__ == "__main__":
    test_fx_aml_is_spam()
    asyncio.get_event_loop().run_until_complete(test_niches())
    print("ok")
