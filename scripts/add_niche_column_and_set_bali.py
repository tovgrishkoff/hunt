#!/usr/bin/env python3
"""
Добавляет колонку niche в таблицу accounts и проставляет niche='bali'
для аккаунтов из config/bali_accounts_config.json (allowed_accounts).

После этого секретарь, activity и маркетолог могут брать список Bali-аккаунтов
из БД (единый источник правды), без зависимости от корневого bali_accounts_config.json.

Запуск из корня проекта:
  python3 scripts/add_niche_column_and_set_bali.py
"""
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text
from shared.database.session import SessionLocal, init_db


def load_bali_allowed() -> set:
    """Список session_name из config/bali_accounts_config.json или корневого."""
    for name in [
        PROJECT_ROOT / "config" / "bali_accounts_config.json",
        PROJECT_ROOT / "bali_accounts_config.json",
    ]:
        if name.exists():
            with open(name, encoding="utf-8") as f:
                data = json.load(f)
                allowed = data.get("allowed_accounts") or []
                if allowed:
                    return set(allowed)
    return set()


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        # Добавить колонку niche (PostgreSQL не поддерживает IF NOT EXISTS для ADD COLUMN)
        try:
            db.execute(text("ALTER TABLE accounts ADD COLUMN niche VARCHAR(50)"))
            db.commit()
            print("✅ Колонка accounts.niche добавлена")
        except Exception as e:
            db.rollback()
            if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                print("✅ Колонка accounts.niche уже есть")
            else:
                print(f"⚠️ ALTER TABLE: {e}")

        allowed = load_bali_allowed()
        if not allowed:
            print("⚠️ Нет allowed_accounts в config/bali_accounts_config.json")
            return

        # Проставить niche='bali' для этих аккаунтов
        updated = 0
        for session_name in allowed:
            r = db.execute(
                text("UPDATE accounts SET niche = 'bali' WHERE session_name = :n"),
                {"n": session_name},
            )
            updated += r.rowcount
        db.commit()
        print(f"✅ Установлено niche='bali' для {updated} аккаунтов: {sorted(allowed)}")
        print("\nТеперь секретарь, activity и маркетолог берут Bali-аккаунты из БД.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
