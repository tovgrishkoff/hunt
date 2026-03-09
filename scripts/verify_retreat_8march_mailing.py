#!/usr/bin/env python3
"""
Проверка: сообщения про ретрит 7–10 марта на Бали попадают в рассылку по всем ретрит-чатам.
"""
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def load_messages():
    """Загрузка из bali_assets (как постер)"""
    for p in [
        PROJECT_ROOT / "bali_assets" / "messages.json",
        PROJECT_ROOT / "config" / "messages" / "bali" / "messages.json",
    ]:
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f), str(p)
    return [], None


def load_group_niches():
    """Загрузка маппинга групп"""
    p = PROJECT_ROOT / "group_niches.json"
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def main():
    print("=" * 70)
    print("🔍 ПРОВЕРКА: Ретрит 7–10 марта в рассылке по ретрит-чатам")
    print("=" * 70)

    all_messages, messages_path = load_messages()
    if not all_messages:
        print("❌ Сообщения не найдены!")
        return 1
    print(f"\n✅ Загружено {len(all_messages)} сообщений из {messages_path}")

    # Группируем по категориям (как постер)
    messages_by_category = {}
    for msg in all_messages:
        src = msg.get("source_file", "general")
        cat = src.replace("messages_", "").replace(".txt", "")
        if cat not in messages_by_category:
            messages_by_category[cat] = []
        messages_by_category[cat].append(msg)

    # Ретрит-пул (как в poster.py)
    retreat_cats = ["india_holi", "india_retreat", "bali_retreat", "tibet_kailash"]
    retreat_pool = []
    for cat in retreat_cats:
        retreat_pool.extend(messages_by_category.get(cat, []))

    # Наши приоритетные (8 марта + Кайлас)
    march_8_msgs = [m for m in retreat_pool if "8 марта" in m.get("text", "") or "7–10 марта" in m.get("text", "")]
    priority_msgs = [m for m in retreat_pool if m.get("priority", 0) >= 1]

    print(f"\n📦 РЕТРИТ-ПУЛ (для india_holi, india_retreat, travel-чатов):")
    print(f"   Всего сообщений: {len(retreat_pool)}")
    print(f"   — bali_retreat: {len(messages_by_category.get('bali_retreat', []))}")
    print(f"   — india_holi: {len(messages_by_category.get('india_holi', []))}")
    print(f"   — india_retreat: {len(messages_by_category.get('india_retreat', []))}")
    print(f"   — tibet_kailash: {len(messages_by_category.get('tibet_kailash', []))}")

    print(f"\n🎯 Сообщения про 7–10 марта / 8 марта: {len(march_8_msgs)}")
    for i, m in enumerate(march_8_msgs[:5], 1):
        t = m.get("text", "")[:70]
        print(f"   {i}. {t}...")
    if len(march_8_msgs) > 5:
        print(f"   ... и ещё {len(march_8_msgs) - 5}")

    print(f"\n⭐ Приоритетные (priority>=1): {len(priority_msgs)}")
    bali_prior = [m for m in priority_msgs if "bali_retreat" in m.get("source_file", "")]
    print(f"   — bali_retreat (8 марта): {len(bali_prior)}")

    # Группы, куда пойдёт ретрит-пул
    group_niches = load_group_niches()
    india_holi_groups = [g for g, n in group_niches.items() if n == "india_holi"]
    india_retreat_groups = [g for g, n in group_niches.items() if n == "india_retreat"]

    # travel-ключевые слова — группы без явной ниши, но с travel/bali и т.д.
    travel_keywords = [
        "travel", "путешеств", "тур", "yoga", "йога", "retreat", "ретрит",
        "bali", "бали", "community", "чат", "expat", "номад",
    ]

    print(f"\n📋 ГРУППЫ ДЛЯ РЕТРИТ-РАССЫЛКИ:")
    print(f"   india_holi: {len(india_holi_groups)} групп")
    for g in india_holi_groups[:8]:
        print(f"      {g}")
    if len(india_holi_groups) > 8:
        print(f"      ... и ещё {len(india_holi_groups) - 8}")

    print(f"\n   india_retreat: {len(india_retreat_groups)} групп")
    for g in india_retreat_groups[:8]:
        print(f"      {g}")
    if len(india_retreat_groups) > 8:
        print(f"      ... и ещё {len(india_retreat_groups) - 8}")

    # Группы с travel-ключевыми в username (дополнительно получают retreat pool)
    other_travel = [
        g for g in group_niches
        if group_niches.get(g) not in ("india_holi", "india_retreat")
        and any(kw in g.lower() for kw in travel_keywords)
    ]
    print(f"\n   Другие travel-чаты (по ключевым словам): ~{len(other_travel)} групп")

    total_retreat_groups = len(india_holi_groups) + len(india_retreat_groups)
    print(f"\n   ИТОГО ретрит-групп (india_holi + india_retreat): {total_retreat_groups}")

    # Итог
    print("\n" + "=" * 70)
    if march_8_msgs and total_retreat_groups > 0:
        print("✅ Ретрит 7–10 марта попадает в рассылку:")
        print(f"   • {len(march_8_msgs)} сообщений в пуле")
        print(f"   • Приоритет 5x — выбираются чаще")
        print(f"   • {total_retreat_groups}+ групп получат ретрит-контент")
        print("\n⚠️  Постинг идёт по расписанию (08:00, 12:00, 15:00, 18:00 Jakarta)")
        print("   Для немедленного поста: python3 scripts/test_posting_now.py")
    else:
        print("❌ Проблема: сообщений 8 марта или ретрит-групп не найдено")
        return 1
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
