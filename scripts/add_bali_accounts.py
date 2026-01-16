#!/usr/bin/env python3
"""
Добавление 4 аккаунтов для Бали в БД
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.database.session import SessionLocal, init_db
from shared.database.models import Account
from datetime import datetime

def add_bali_accounts():
    """Добавить 4 аккаунта для Бали"""
    
    # Данные аккаунтов из основной БД (с string_session)
    accounts_data = [
        {
            "session_name": "promotion_andrey_virgin",
            "api_id": 33336443,
            "api_hash": "9d9ee718ff58f43ccbcf028a629528fd",
            "proxy": "http://pG0d5c:8LcpzP@45.89.73.114:9670",
            "string_session": "1ApWapzMBu3uKJsjvuSXwnwDlp7Bwyjcq654YZjcoOruwZwiCUAYy0aL83fTjuBMFKZEyYZw9ztBWSd-6NLxlLUQ0CIOLZXrjug8ijnzJEnVPEUsifZxbgnoBD1LSc1XZZubWjJxvzt4QUezBo6IFkll_HZDJfKt3JpsluQ10arhMs3jZvigNtl1C7JRdaaSFsad0_2Sc5QVisYFQVb65uKeqC5__ICIH-gkN4D1syC1aAq3SqNhtVQ8FTatzqZwDeSKy8LC431qi63hE9KLOvNLzYuKeSIBo7zHRrb0a4KpTo82ypy127t8hb3ytqU9Bpe2X9TPgl-U8yQrBT7Vocinxp3pK8qA="
        },
        {
            "session_name": "promotion_artur_biggest",
            "api_id": 34601626,
            "api_hash": "eba8c7b793884b92a65c48436b646600",
            "proxy": "http://pG0d5c:8LcpzP@45.89.72.202:9136",
            "string_session": "1ApWapzMBu5nZ06-mR3wphQmGRxwB6WKBDOKoOSmIARecaNlL5i6_x15VN54Ys1_jyD5yaiOrPTZPWJfLF_0ij75VKLZDypibz6ljIkZmeo7f7B9yuFseZ7Jip2-woEmPyOmsiqe-qQ-SzM4IvIC5S8iUW99zsRrXJN8OhMiJ6zB3MNsSjypUC_EaPpta_1R58Zr6LDD89a7hUt09BYX1Xj84azRidLRisxeYl0RNM_EYExyoiKM26aJKUron99TGEDgiO6ZTPeFbdNXQsBuXqpiml6CXyH4QRolxrebJ_OrP6GTeAkptuWEHo0VHq1O9zXPmJVEvG2rnxX0u8tO2vmTHzjmgmDc="
        },
        {
            "session_name": "promotion_anna_truncher",
            "api_id": 37120288,
            "api_hash": "e576f165ace9ea847633a136dc521062",
            "proxy": "http://pG0d5c:8LcpzP@45.89.75.94:9797",
            "string_session": "1ApWapzMBu5udRrVoptgu5S_mBVZm6EgF0ZS3HDNF23ZbIC_ynJ-ym7Kl-SUK9B8o_N2RNWG0X7ZI6R6Hyrh5kQkwQekj-cx0i7IyKIstjAV7zCGwbSeuIsMAAvcTWunRU6OC9KXW676GdAscctvs8CBGOt-Oo5UHbNARKl9zOpPajfYoGL1AZPeiXI95SPWVmvUEekj-Bt2eftaHulrS1ClFEbvosZjuvsoEuggcTmwD802xzbVOx6TtXeJZSkL0s1IXt7OjpekFZQMgIy-B1tUw8EK4fjDIbW_ELweCGNNS2w2Htgdrb2FPmfQsxHtbRN9wTNo06NwxZX2zukohjDhwNkMOI-Q="
        },
        {
            "session_name": "promotion_oleg_petrov",
            "api_id": 38166279,
            "api_hash": "5326e0a7fb4803c973bc0b7025eb65af",
            "proxy": "http://Vu9TDx:0zumuH@178.171.42.229:9540",
            "string_session": "1ApWapzMBu2fJK0gaT7_P3DSVG2ZQUcBzZs_A0gCXs2hIhCEyVBQYp9B48kP1swQuFDTllhwO4-NyX5oRa78GJoO75UfxpDDVF8HqAe96P9ULBe8puNliirogBaJ58ZDzaDWhxrn8_6mNgHqiUnj9ygRljtqxQuGQ6hnml2VGEi97tg2bQ05PZ6iTus3rYoWhjS7AsyBZbhOO9-DhoJO7kst6JnmX-7xqXo9a1BLV3IlvqmK25kPo_hLUlF9dbfVloSn3W48VXAJA0LNXgrZrqzjzsqS_NHIt4Ty7RyfCTXmYtS7LLxUs5Dk1VcIPwprFBV-CcxB0eWqGwQ04HBirYH0vagv1sXI="
        }
    ]
    
    # Инициализация БД
    try:
        init_db()
        print("✅ БД инициализирована")
    except Exception as e:
        print(f"⚠️  БД уже инициализирована: {e}")
    
    db = SessionLocal()
    try:
        added = 0
        updated = 0
        
        # Получаем string_session из основной БД для каждого аккаунта
        # Пока добавляем без string_session, он будет загружен из файла сессии
        
        for acc_data in accounts_data:
            existing = db.query(Account).filter(Account.session_name == acc_data["session_name"]).first()
            
            if existing:
                # Обновляем существующий
                existing.api_id = acc_data["api_id"]
                existing.api_hash = acc_data["api_hash"]
                existing.proxy = acc_data["proxy"]
                existing.string_session = acc_data.get("string_session")
                existing.status = 'active'
                updated += 1
                print(f"✅ Обновлен: {acc_data['session_name']}")
            else:
                # Создаем новый
                new_account = Account(
                    session_name=acc_data["session_name"],
                    api_id=acc_data["api_id"],
                    api_hash=acc_data["api_hash"],
                    proxy=acc_data["proxy"],
                    string_session=acc_data.get("string_session"),
                    status='active'
                )
                db.add(new_account)
                added += 1
                print(f"✅ Добавлен: {acc_data['session_name']}")
        
        db.commit()
        print(f"\n✅ Готово! Добавлено: {added}, Обновлено: {updated}")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    print("=" * 60)
    print("🏝️  ДОБАВЛЕНИЕ АККАУНТОВ ДЛЯ БАЛИ")
    print("=" * 60)
    add_bali_accounts()
