#!/usr/bin/env python3
"""
Добавление аккаунтов Lev Moiseev и Lera Katina в БД для системы Bali.

Запуск: из корня проекта
  python3 scripts/add_lev_lera_bali_accounts.py

После добавления запустите авторизацию:
  python3 authorize_lev_lera_bali.py
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.database.session import SessionLocal, init_db
from shared.database.models import Account

ACCOUNTS_DATA = [
    {
        "session_name": "promotion_lev_moiseev",
        "phone": "+380639597698",
        "api_id": 33654773,
        "api_hash": "5698a681018432cb744a204f41ef5182",
        "proxy": None,
        "nickname": "Lev Moiseev",
        "string_session": None,
    },
    {
        "session_name": "promotion_lera_katina",
        "phone": "+380937392435",
        "api_id": 30513372,
        "api_hash": "1d275ee48d6e35ed6fa9df5b0d642769",
        "proxy": None,
        "nickname": "Lera Katina",
        "string_session": None,
    },
]


def main() -> None:
    print("=" * 60)
    print("🏝️  ДОБАВЛЕНИЕ АККАУНТОВ LEV И LERA ДЛЯ БАЛИ")
    print("=" * 60)

    try:
        init_db()
        print("✅ БД инициализирована")
    except Exception as e:
        print(f"⚠️  БД уже инициализирована: {e}")

    db = SessionLocal()
    try:
        added = 0
        updated = 0
        for acc_data in ACCOUNTS_DATA:
            existing = db.query(Account).filter(
                Account.session_name == acc_data["session_name"]
            ).first()

            if existing:
                existing.api_id = acc_data["api_id"]
                existing.api_hash = acc_data["api_hash"]
                existing.phone = acc_data.get("phone")
                existing.proxy = acc_data.get("proxy")
                existing.nickname = acc_data.get("nickname")
                existing.status = "active"
                existing.niche = "bali"
                updated += 1
                print(f"✅ Обновлен: {acc_data['session_name']}")
            else:
                new_account = Account(
                    session_name=acc_data["session_name"],
                    api_id=acc_data["api_id"],
                    api_hash=acc_data["api_hash"],
                    phone=acc_data.get("phone"),
                    proxy=acc_data.get("proxy"),
                    nickname=acc_data.get("nickname"),
                    string_session=acc_data.get("string_session"),
                    status="active",
                    niche="bali",
                )
                db.add(new_account)
                added += 1
                print(f"✅ Добавлен: {acc_data['session_name']}")

        db.commit()
        print(f"\n✅ Готово! Добавлено: {added}, Обновлено: {updated}")
        print("\n📋 Следующий шаг: авторизуйте аккаунты:")
        print("   python3 authorize_lev_lera_bali.py")

    except Exception as e:
        db.rollback()
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    main()
