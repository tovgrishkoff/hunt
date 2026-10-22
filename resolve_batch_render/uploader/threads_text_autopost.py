"""Scheduled native TEXT posts for Threads @grishkoff_travel (META_2).

Cadence: ~5 root posts/day, Mon–Sat (Sunday off).
Daily pack: 2 discussion + 1 warmup + 2 selling (order shuffled).
Prompts: Notion Jay Shambo server spec (common + author).
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx
from loguru import logger

from uploader.db import connect, next_due, record_attempt, upsert_item
from uploader.threads_products import (
    active_products,
    flagship_product_ids_for_day,
    product_url,
    require_avatar_for_autopublish,
)
from uploader.threads_prompts import (
    author_system_prompt,
    author_user_prompt,
    fit_threads_text,
    strip_punct_dashes,
)

GEO_POOL: list[dict[str, str]] = [
    {
        "key": "bali",
        "label": "Бали",
        "angles": "визы/visa run, Чангу vs Убуд, сезон дождей, удалёнка, ретрит vs тусовка",
    },
    {
        "key": "kailas",
        "label": "Кайлас / Тибет",
        "angles": "кора 3 дня / маршрут 52 км (НИКОГДА не за 1 день), Долма-Ла 5630 м, смысл vs галочка, акклиматизация, пермит",
    },
    {
        "key": "maldives",
        "label": "Мальдивы",
        "angles": "local islands vs resort, трансферы, сезоны, бюджет без overwater",
    },
    {
        "key": "vietnam",
        "label": "Вьетнам",
        "angles": "e-visa, Дананг/Нячанг/Дalat, еда, симки, переезды север-юг",
    },
    {
        "key": "china",
        "label": "Китай",
        "angles": "оплата/Alipay, VPN мифы, маршруты, виза, города vs природа",
    },
    {
        "key": "india",
        "label": "Индия / Гоа",
        "angles": "ретрит vs туризм, Гоа север/юг, Холи, ашрамы без розовых очков",
    },
    {
        "key": "asia",
        "label": "Азия (общий)",
        "angles": "хабы пересадок, сезонность, ошибки первой длинной поездки",
    },
    {
        "key": "south_africa",
        "label": "Южная Африка",
        "angles": "Кейптаун, сафари без люкса, безопасность, сезоны",
    },
    {
        "key": "mexico",
        "label": "Мексика",
        "angles": "Канкун vs Мерида vs CDMX, цифровой номад, безопасность районов",
    },
    {
        "key": "peru",
        "label": "Перу",
        "angles": "Мачу-Пикчу окна, высота, Куско, бюджет трек",
    },
    {
        "key": "latam",
        "label": "Южная Америка",
        "angles": "хабы перелётов, визы, что брать в один заезд",
    },
]

DEFAULT_RSS = (
    "https://www.tourdom.ru/rss/",
    "https://www.atorus.ru/rss/news",
)

NEWS_GEO_KEYWORDS: dict[str, tuple[str, ...]] = {
    "bali": ("бали", "индонез", "денпасар", "bali", "indonesia"),
    "kailas": ("кайлас", "тибет", "лхаса", "kailash", "tibet", "манас"),
    "maldives": ("мальдив", "maldives", "мале"),
    "vietnam": ("вьетнам", "vietnam", "ханой", "хань", "нячанг", "дананг"),
    "china": ("китай", "china", "пекин", "шанхай", "хайнань"),
    "india": ("индия", "гоа", "india", "goa", "холи", "ашрам"),
    "asia": ("азия", "тайланд", "пхукет", "бангкок", "камбодж", "лаос"),
    "south_africa": ("африка", "кейптаун", "юар", "south africa"),
    "mexico": ("мексик", "mexico", "канкун"),
    "peru": ("перу", "peru", "мачу"),
    "latam": ("аргентин", "чили", "бразил", "колумби", "южн. америк", "латинск"),
}


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = _env(name)
    if not raw:
        return default
    return raw.lower() not in {"0", "false", "no", "off"}


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = _env(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def threads_text_meta_index() -> int:
    return _env_int("THREADS_TEXT_META_TARGET", 2)


def _windows() -> list[tuple[int, int]]:
    # 5 windows → ~5 root posts/day across MSK waking hours
    raw = _env(
        "THREADS_TEXT_WINDOWS",
        "08:00-09:15,10:30-11:45,13:00-14:30,16:00-17:30,19:00-21:00",
    )
    out: list[tuple[int, int]] = []
    for part in raw.split(","):
        part = part.strip()
        if "-" not in part or ":" not in part:
            continue
        a, b = part.split("-", 1)
        try:
            h1, m1 = [int(x) for x in a.strip().split(":", 1)]
            h2, m2 = [int(x) for x in b.strip().split(":", 1)]
            out.append((h1 * 60 + m1, h2 * 60 + m2))
        except ValueError:
            continue
    return out or [
        (8 * 60, 9 * 60 + 15),
        (10 * 60 + 30, 11 * 60 + 45),
        (13 * 60, 14 * 60 + 30),
        (16 * 60, 17 * 60 + 30),
        (19 * 60, 21 * 60),
    ]


def _is_posting_day(day: datetime.date) -> bool:
    """Mon–Sat only. Sunday = off. Override via THREADS_TEXT_SKIP_WEEKDAYS=6."""
    raw = _env("THREADS_TEXT_SKIP_WEEKDAYS", "6")  # 0=Mon … 6=Sun
    skip: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            skip.add(int(part))
        except ValueError:
            continue
    return day.weekday() not in skip


def _day_count(con: Any, day_key: str) -> int:
    row = con.execute(
        "SELECT COUNT(*) FROM upload_queue "
        "WHERE platform='threads_text' AND status='posted' "
        "AND scheduled_at LIKE ?",
        (f"{day_key}%",),
    ).fetchone()
    return int(row[0] or 0)


def _day_planned_count(con: Any, day_key: str) -> int:
    row = con.execute(
        "SELECT COUNT(*) FROM upload_queue "
        "WHERE platform='threads_text' AND status='planned' "
        "AND scheduled_at LIKE ?",
        (f"{day_key}%",),
    ).fetchone()
    return int(row[0] or 0)


def _last_scheduled_at(con: Any) -> datetime | None:
    row = con.execute(
        "SELECT scheduled_at FROM upload_queue "
        "WHERE platform='threads_text' AND status IN ('planned','posted') "
        "ORDER BY scheduled_at DESC LIMIT 1"
    ).fetchone()
    if not row or not row[0]:
        return None
    try:
        return datetime.fromisoformat(str(row[0]))
    except ValueError:
        return None


def pick_random_slot(
    tz: ZoneInfo, *, con: Any | None = None
) -> tuple[str, int]:
    """Return (iso slot, window_index). Mon–Sat only; 5 windows → daily pack."""
    now = datetime.now(tz=tz)
    per_day = max(1, _env_int("THREADS_TEXT_MAX_PER_DAY", 5))
    # Spread ~5 posts across the day (~2h gaps).
    min_gap_h = max(0.75, _env_float("THREADS_TEXT_MIN_GAP_HOURS", 2.0))
    wins = _windows()
    weights = [1.0, 1.05, 1.0, 1.1, 1.15][: len(wins)]
    while len(weights) < len(wins):
        weights.append(1.0)

    last_at = _last_scheduled_at(con) if con is not None else None
    earliest = now + timedelta(minutes=20)
    if last_at is not None:
        gap_floor = last_at + timedelta(hours=min_gap_h)
        if gap_floor > earliest:
            earliest = gap_floor

    candidates: list[tuple[datetime, int]] = []
    for day_offset in range(0, 21):
        day = (now + timedelta(days=day_offset)).date()
        if not _is_posting_day(day):
            continue
        day_key = day.isoformat()
        if con is not None:
            scheduled_today = _day_count(con, day_key) + _day_planned_count(
                con, day_key
            )
            if scheduled_today >= per_day:
                continue

        order = list(range(len(wins)))
        random.shuffle(order)
        order.sort(
            key=lambda i: random.random() / max(0.2, weights[i]),
            reverse=True,
        )
        for wi in order:
            start_min, end_min = wins[wi]
            if end_min <= start_min:
                continue
            span = max(1, end_min - start_min)
            for _ in range(8):
                minute = start_min + random.randint(0, span)
                slot = datetime(
                    day.year,
                    day.month,
                    day.day,
                    minute // 60,
                    minute % 60,
                    tzinfo=tz,
                )
                if slot <= earliest:
                    continue
                candidates.append((slot, wi))
                break
        if candidates:
            break

    if not candidates:
        # Skip Sundays in fallback chain
        fallback = now + timedelta(hours=min_gap_h)
        for _ in range(8):
            if _is_posting_day(fallback.date()):
                break
            fallback += timedelta(days=1)
            fallback = fallback.replace(hour=8, minute=30, second=0, microsecond=0)
        return fallback.isoformat(timespec="seconds"), max(0, len(wins) - 1)

    slot, wi = random.choice(candidates)
    return slot.isoformat(timespec="seconds"), wi


def _tour_urls() -> dict[str, str]:
    """Approved product URLs; env overrides keep deploy flexibility."""
    kailas = _env(
        "BRAND_SITE",
        product_url(
            "kailas_lhasa_2027",
            fallback="https://jayshambo.com/tours/kai-las-svyaschennaya-kora-iz-lhasy",
        ),
    )
    bali = _env(
        "THREADS_TEXT_BALI_TOUR_URL",
        product_url(
            "bali_premium_ocean",
            fallback="https://jayshambo.com/tours/puteshestvie-k-sebe-bali-tury-avtorskie-retrit-tury",
        ),
    )
    india = _env(
        "THREADS_TEXT_INDIA_TOUR_URL",
        product_url(
            "india_private_8march_2027",
            fallback=(
                "https://jayshambo.com/tours/"
                "dusha-indii-tam-gde-ostanavlivaetsya-vremya"
            ),
        ),
    )
    bali_sacred = product_url(
        "bali_sacred",
        fallback=(
            "https://jayshambo.com/tours/"
            "put-k-sebe-retreat-puteshestvie-po-sakralnomu-bali"
        ),
    )
    bali_weekend = product_url(
        "bali_weekend",
        fallback="https://jayshambo.com/tours/retrit-vyhodnogo-dnya-bali",
    )
    return {
        "kailas": kailas,
        "bali": bali,
        "india": india,
        "bali_sacred": bali_sacred,
        "bali_weekend": bali_weekend,
        "catalog": product_url(
            "catalog", fallback="https://jayshambo.com/tours"
        ),
    }


def _pick_geo(recent_geos: list[str]) -> dict[str, str]:
    # Nepal / Gosaikunda must never appear as a promo geo.
    blocked = {"nepal", "gosaikunda"}
    pool = [
        g
        for g in GEO_POOL
        if g["key"] not in recent_geos[-4:] and g["key"] not in blocked
    ]
    return random.choice(pool or GEO_POOL)


def _role_of_kind(kind: str) -> str:
    base = str(kind).split(":", 1)[0]
    if base.startswith("promo"):
        return "selling"
    if base in {"warmup", "tip", "geo_tip", "story", "news", "relocation"}:
        return "warmup" if base in {"warmup", "tip", "geo_tip", "story", "news"} else "warmup"
    if base == "discussion":
        return "discussion"
    return "other"


def _day_role_counts(con: Any, day_key: str) -> dict[str, int]:
    rows = con.execute(
        "SELECT source_id FROM upload_queue "
        "WHERE platform='threads_text' AND status IN ('planned','posted') "
        "AND scheduled_at LIKE ?",
        (f"{day_key}%",),
    ).fetchall()
    counts = {"discussion": 0, "warmup": 0, "selling": 0}
    for row in rows:
        role = _role_of_kind(str(row[0] or ""))
        if role in counts:
            counts[role] += 1
    return counts


def _promo_kinds_available() -> list[str]:
    mapping = {
        "kailas_lhasa_2027": "promo_kailas",
        "india_private_8march_2027": "promo_india",
        "bali_premium_ocean": "promo_bali",
        "bali_sacred": "promo_bali_sacred",
        "bali_weekend": "promo_bali_weekend",
    }
    out: list[str] = []
    for product in active_products():
        pid = str(product.get("id") or "")
        status = str(product.get("status") or "").lower()
        if status == "unavailable":
            continue
        kind = mapping.get(pid)
        if kind:
            out.append(kind)
    return out or ["promo_kailas", "promo_bali"]


def _pick_selling_kind(recent_kinds: list[str]) -> str:
    options = _promo_kinds_available()
    recent_bases = [str(k).split(":", 1)[0] for k in recent_kinds[-8:]]
    fresh = [k for k in options if k not in recent_bases]
    pool = fresh or options
    # Prefer flagships early in the day pack.
    preferred = [
        k
        for k in ("promo_kailas", "promo_india", "promo_bali")
        if k in pool
    ]
    return random.choice(preferred or pool)


def _pick_kind(
    recent_kinds: list[str],
    *,
    window_idx: int = 2,
    con: Any | None = None,
    day_key: str = "",
) -> str:
    """Fill the Notion daily pack: 2 discussion, 1 warmup, 2 selling."""
    targets = {
        "discussion": 2,
        "warmup": 1,
        "selling": 2,
    }
    counts = {"discussion": 0, "warmup": 0, "selling": 0}
    if con is not None and day_key:
        counts = _day_role_counts(con, day_key)
    missing = [role for role, need in targets.items() if counts[role] < need]
    if not missing:
        # Day already full of roles; keep organic discussion rather than spam promo.
        return "discussion"
    # Prefer underfilled roles; slight bias by window for variety.
    random.shuffle(missing)
    if window_idx <= 1 and "discussion" in missing:
        role = "discussion"
    elif window_idx >= 3 and "selling" in missing:
        role = "selling"
    else:
        role = missing[0]
    if role == "discussion":
        return "discussion"
    if role == "warmup":
        return random.choice(["warmup", "geo_tip", "tip"])
    return _pick_selling_kind(recent_kinds)


def _product_id_for_kind(kind: str) -> str:
    mapping = {
        "promo_kailas": "kailas_lhasa_2027",
        "promo_india": "india_private_8march_2027",
        "promo_bali": "bali_premium_ocean",
        "promo_bali_sacred": "bali_sacred",
        "promo_bali_weekend": "bali_weekend",
    }
    return mapping.get(kind, "")


def _link_for_kind(kind: str) -> str:
    urls = _tour_urls()
    if kind == "promo_kailas":
        return urls["kailas"]
    if kind == "promo_india":
        return urls["india"]
    if kind == "promo_bali_sacred":
        return urls["bali_sacred"]
    if kind == "promo_bali_weekend":
        return urls["bali_weekend"]
    if kind.startswith("promo_bali"):
        return urls["bali"]
    return ""


def _rss_urls() -> list[str]:
    raw = _env("THREADS_TEXT_RSS", "")
    if raw:
        return [u.strip() for u in raw.split(",") if u.strip()]
    return list(DEFAULT_RSS)


def _xml_text(el: ET.Element | None) -> str:
    if el is None or el.text is None:
        return ""
    return el.text.strip()


def _parse_rss_items(xml_text: str, *, source_url: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items

    # RSS 2.0
    for item in root.findall(".//item"):
        title = _xml_text(item.find("title"))
        link = _xml_text(item.find("link"))
        desc = _xml_text(item.find("description"))
        pub = _xml_text(item.find("pubDate"))
        if not title:
            continue
        items.append(
            {
                "title": re.sub(r"<[^>]+>", "", title),
                "link": link or source_url,
                "summary": re.sub(r"<[^>]+>", "", desc)[:400],
                "published": pub,
                "source": urlparse(source_url).netloc or source_url,
            }
        )

    # Atom
    if not items:
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for entry in root.findall(".//a:entry", ns):
            title = _xml_text(entry.find("a:title", ns))
            link_el = entry.find("a:link", ns)
            link = ""
            if link_el is not None:
                link = link_el.attrib.get("href", "")
            summary = _xml_text(entry.find("a:summary", ns)) or _xml_text(
                entry.find("a:content", ns)
            )
            if not title:
                continue
            items.append(
                {
                    "title": re.sub(r"<[^>]+>", "", title),
                    "link": link or source_url,
                    "summary": re.sub(r"<[^>]+>", "", summary)[:400],
                    "published": _xml_text(entry.find("a:updated", ns)),
                    "source": urlparse(source_url).netloc or source_url,
                }
            )
    return items


def _news_matches_geo(text: str) -> str | None:
    low = text.lower()
    # Strict destination match only — no generic «туризм/авиа» (даёт оффтоп).
    for key, words in NEWS_GEO_KEYWORDS.items():
        if any(w in low for w in words):
            return key
    return None


def _used_news_hashes(con: Any) -> set[str]:
    rows = con.execute(
        "SELECT source_id FROM upload_queue "
        "WHERE platform='threads_text' AND source_id LIKE 'news:%'"
    ).fetchall()
    out: set[str] = set()
    for r in rows:
        sid = str(r[0] or "")
        if sid.startswith("news:"):
            out.add(sid.split(":", 1)[1])
    return out


def _item_hash(link: str, title: str) -> str:
    raw = f"{link}|{title}".encode("utf-8", errors="ignore")
    return hashlib.sha1(raw).hexdigest()[:10]


_REFILL_LOCK = Path(
    _env("THREADS_TEXT_LOCK", "/tmp/threads_text_refill.lock")
)


def fetch_news_candidate(con: Any) -> dict[str, str] | None:
    """Pull a fresh geo-relevant RSS item not used before."""
    used = _used_news_hashes(con)
    bag: list[dict[str, str]] = []
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; GrishkoffTravelBot/1.0)",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }
    with httpx.Client(timeout=20.0, follow_redirects=True, headers=headers) as client:
        for url in _rss_urls():
            try:
                r = client.get(url)
                if r.status_code >= 400:
                    logger.warning(f"[threads-text] rss {url} status={r.status_code}")
                    continue
                for item in _parse_rss_items(r.text, source_url=url):
                    blob = f"{item['title']} {item['summary']}"
                    geo = _news_matches_geo(blob)
                    if not geo:
                        continue
                    h = _item_hash(item["link"], item["title"])
                    if h in used:
                        continue
                    # Prefer fresher-looking items when pubDate parses
                    score = 0
                    if item.get("published"):
                        try:
                            dt = parsedate_to_datetime(item["published"])
                            age_h = (
                                datetime.now(tz=dt.tzinfo) - dt
                            ).total_seconds() / 3600
                            if age_h <= 72:
                                score += 3
                            elif age_h <= 168:
                                score += 1
                        except Exception:
                            pass
                    item = dict(item)
                    item["geo_key"] = geo
                    item["hash"] = h
                    item["_score"] = str(score)
                    bag.append(item)
            except Exception:
                logger.exception(f"[threads-text] rss fetch failed {url}")

    if not bag:
        return None
    bag.sort(key=lambda x: int(x.get("_score") or 0), reverse=True)
    # Soft shuffle among top
    top = bag[:8]
    return random.choice(top)


def _recent_captions(con: Any, limit: int = 70) -> list[str]:
    """Prefer ~14 days of root posts (~5/day) for anti-repeat checks."""
    rows = con.execute(
        "SELECT caption, scheduled_at FROM upload_queue "
        "WHERE platform='threads_text' AND status IN ('posted','planned') "
        "AND caption IS NOT NULL AND caption != '' "
        "ORDER BY scheduled_at DESC LIMIT ?",
        (max(limit, 20),),
    ).fetchall()
    cutoff = datetime.now() - timedelta(days=14)
    out: list[str] = []
    for r in rows:
        scheduled = str(r[1] or "")
        try:
            when = datetime.fromisoformat(scheduled)
            if when.tzinfo is not None:
                when = when.replace(tzinfo=None)
            if when < cutoff:
                continue
        except ValueError:
            pass
        t = str(r[0] or "").strip().replace("\n", " ")
        if t:
            out.append(t[:160])
        if len(out) >= limit:
            break
    return out


def _recent_geos(con: Any, limit: int = 8) -> list[str]:
    rows = con.execute(
        "SELECT source_id FROM upload_queue "
        "WHERE platform='threads_text' AND status IN ('posted','planned') "
        "ORDER BY scheduled_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    geos: list[str] = []
    for r in rows:
        sid = str(r[0] or "")
        if ":" in sid:
            # tip:bali / geo_tip:vietnam / news:hash — skip bare news hashes
            left, right = sid.split(":", 1)
            if left in {
                "geo_tip",
                "relocation",
                "tip",
                "discussion",
                "story",
                "warmup",
            } and right in {g["key"] for g in GEO_POOL}:
                geos.append(right)
    return geos


def _extract_json_text(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            raise
        data = json.loads(m.group(0))
    text = str(data.get("text") or "").strip()
    if not text:
        raise RuntimeError("Empty threads text from LLM")
    return text


def generate_threads_text(
    *,
    kind: str,
    avoid_openings: list[str] | None = None,
    geo: dict[str, str] | None = None,
    news: dict[str, str] | None = None,
) -> str:
    """Generate post via Claude (preferred) or OpenAI fallback."""
    labels = {
        "discussion": "дискуссионный: ясная позиция и место для другого опыта",
        "warmup": "прогрев: одна полезная деталь или критерий выбора без жёсткой продажи",
        "tip": "прогрев: одна причина и что он проверяет сам",
        "geo_tip": "прогрев: неочевидная деталь места",
        "relocation": "прогрев: быт в стране и вывод",
        "story": "прогрев: подтверждённая история или наблюдение без выдумки",
        "news": "прогрев: новость и что она меняет для поездки",
        "promo_kailas": "продающий: Кайлас 2027, без продажи сезона 2026",
        "promo_india": "продающий: Индия к 8 марта 2027, только утверждённые условия",
        "promo_bali": "продающий: премиальный Бали / новогодние каникулы без ложного NYE",
        "promo_bali_sacred": "продающий: сакральный Бали, не смешивать с премиум-пакетом",
        "promo_bali_weekend": "продающий: короткий ретрит выходного дня",
    }
    geo = geo or random.choice(GEO_POOL)
    link = _link_for_kind(kind)
    product_id = _product_id_for_kind(kind)

    news_context = "нет"
    if news:
        news_context = (
            f"Источник: {news.get('source','')}\n"
            f"Заголовок: {news.get('title','')}\n"
            f"Кратко: {news.get('summary','')[:280]}"
        )
        gk = news.get("geo_key")
        for g in GEO_POOL:
            if g["key"] == gk:
                geo = g
                break

    max_chars = _env_int("THREADS_TEXT_MAX_CHARS", 260)
    prompt = author_user_prompt(
        kind=kind,
        kind_label=labels.get(kind, kind),
        geo_label=geo.get("label", "путешествия"),
        geo_angles=geo.get("angles", "практика путешествий"),
        news_context=news_context,
        link=link,
        product_id=product_id,
        history_lines=avoid_openings or [],
        max_chars=max_chars,
    )

    provider = _env("THREADS_TEXT_LLM", "claude").lower()
    text = ""
    if provider in {"claude", "anthropic", "auto"}:
        try:
            text = _generate_with_claude(prompt)
            logger.info(f"[threads-text] llm=claude kind={kind}")
        except Exception:
            if provider != "auto":
                raise
            logger.exception("[threads-text] Claude failed → OpenAI fallback")
    if not text:
        text = _generate_with_openai(prompt)
        logger.info(f"[threads-text] llm=openai kind={kind}")
    return _normalize_text(text, kind=kind)


def _author_system() -> str:
    return author_system_prompt(include_products=True)


def _generate_with_claude(prompt: str) -> str:
    from anthropic import Anthropic

    api_key = _env("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    model = _env(
        "THREADS_TEXT_CLAUDE_MODEL",
        _env("CLAUDE_MODEL", "claude-sonnet-4-5-20250929"),
    )
    client = Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=model,
        max_tokens=_env_int("THREADS_TEXT_CLAUDE_MAX_TOKENS", 700),
        system=_author_system(),
        messages=[{"role": "user", "content": prompt}],
    )
    parts = [b.text for b in msg.content if getattr(b, "type", None) == "text"]
    raw = "\n".join(parts).strip()
    return _extract_json_text(raw)


def _generate_with_openai(prompt: str) -> str:
    from openai import OpenAI

    api_key = _env("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    model = _env(
        "THREADS_TEXT_OPENAI_MODEL",
        _env("INGEST_AI_CAPTION_MODEL", "gpt-4o-mini"),
    )
    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _author_system()},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=1.05,
    )
    raw = (resp.choices[0].message.content or "").strip()
    return _extract_json_text(raw)


_ONE_DAY_KORA_RE = re.compile(
    r"(?:"
    r"52\s*(?:км|километр\w*)\s*за\s*(?:один\s+)?(?:1\s+)?день"
    r"|за\s*(?:один|1)\s*день.{0,40}(?:52|кор)"
    r"|(?:кор\w*).{0,40}за\s*(?:один|1)\s*день"
    r"|веду\s+кор\w*.{0,30}(?:за\s*)?(?:один|1)\s*день"
    r"|кор\w*\s+за\s*(?:один|1)\s*день"
    r")",
    flags=re.IGNORECASE | re.DOTALL,
)


def _mentions_one_day_kora(text: str) -> bool:
    """True if text claims the Kailas kora is done in one day."""
    low = (text or "").lower().replace("ё", "е")
    if "кор" not in low and "кайлас" not in low and "kailash" not in low:
        return False
    if _ONE_DAY_KORA_RE.search(low):
        return True
    # «52 км … за день» without «три/3»
    if re.search(r"52\s*(?:км|километр)", low) and re.search(
        r"за\s+день\b", low
    ):
        if not re.search(r"(?:за\s+)?(?:три|3)\s+дн", low):
            return True
    return False


def _normalize_text(text: str, *, kind: str) -> str:
    text = text.replace("\r", "").strip()
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" #\w+", "", text)
    text = strip_punct_dashes(text)
    # Hard ban: never promote Nepal–Gosaikunda wording.
    banned = ("госайкунд", "gosaikunda", "непал с госа")
    low = text.lower()
    if any(b in low for b in banned):
        raise RuntimeError("Generated text mentions banned Nepal–Gosaikunda route")
    if _mentions_one_day_kora(text):
        raise RuntimeError(
            "Generated text claims 1-day Kailas kora (must be 3 days / 52 km)"
        )
    want = _link_for_kind(kind)
    max_chars = _env_int("THREADS_TEXT_MAX_CHARS", 260)
    if kind.startswith("promo"):
        # Reserve room for the approved URL so we never clip mid-word then append.
        url_room = (len(want) + 1) if want else 0
        body_limit = max(80, max_chars - url_room)
        text = fit_threads_text(re.sub(r"https?://\S+", "", text).strip(), max_chars=body_limit)
        if want:
            text = f"{text.rstrip()} {want}".strip()
        found = re.findall(r"https?://\S+", text)
        if len(found) > 1:
            for extra in found[1:]:
                text = text.replace(extra, "", 1)
        # Never sell 2026 Kailas as the offer.
        if "kailas" in kind and re.search(r"\b2026\b", text) and "2027" not in text:
            text = text.replace("2026", "2027")
    else:
        text = re.sub(r"https?://\S+", "", text).strip()
    return fit_threads_text(text, max_chars=max_chars)


def _recent_kinds(con: Any, limit: int = 10) -> list[str]:
    rows = con.execute(
        "SELECT source_id FROM upload_queue "
        "WHERE platform='threads_text' AND status IN ('posted','planned') "
        "ORDER BY scheduled_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [str(r[0] or "") for r in rows if r and str(r[0] or "").strip()]


def _source_id_for(kind: str, *, geo: dict[str, str] | None, news: dict[str, str] | None) -> str:
    if kind == "news" and news:
        return f"news:{news['hash']}"
    product_id = _product_id_for_kind(kind)
    if kind.startswith("promo") and product_id:
        return f"{kind}:{product_id}"
    if kind in {"geo_tip", "relocation", "tip", "discussion", "story", "warmup"} and geo:
        return f"{kind}:{geo['key']}"
    return kind


def refill_queue(*, db_path: str, tz_name: str, count: int | None = None) -> int:
    """Generate and schedule native TEXT posts if queue is low."""
    if not _env_bool("THREADS_TEXT_AUTOPOST", True):
        return 0

    # Prevent double-refill race (container tick + manual / two ticks).
    lock_path = _REFILL_LOCK
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
    except FileExistsError:
        try:
            age = datetime.now().timestamp() - lock_path.stat().st_mtime
            if age < 120:
                logger.info("[threads-text] refill skipped (lock held)")
                return 0
            lock_path.unlink(missing_ok=True)
            return refill_queue(db_path=db_path, tz_name=tz_name, count=count)
        except Exception:
            return 0

    try:
        return _refill_queue_unlocked(db_path=db_path, tz_name=tz_name, count=count)
    finally:
        try:
            lock_path.unlink(missing_ok=True)
        except Exception:
            pass


def _refill_queue_unlocked(
    *, db_path: str, tz_name: str, count: int | None = None
) -> int:
    try:
        require_avatar_for_autopublish()
    except RuntimeError as exc:
        logger.error(f"[threads-text] refill halted: {exc}")
        return 0

    n = count or _env_int("THREADS_TEXT_BATCH_SIZE", 10)
    con = connect(db_path)
    planned = con.execute(
        "SELECT COUNT(*) FROM upload_queue "
        "WHERE platform='threads_text' AND status='planned'"
    ).fetchone()[0]
    # Keep about 3 days of the 5-post pack ahead.
    min_q = _env_int("THREADS_TEXT_QUEUE_MIN", 15)
    if int(planned or 0) >= min_q:
        logger.info(f"[threads-text] queue ok planned={planned}")
        return 0

    tz = ZoneInfo(tz_name)
    recent = _recent_kinds(con)
    avoid = _recent_captions(con)
    geos_recent = _recent_geos(con)
    need = max(0, min_q - int(planned or 0))
    to_add = min(n, max(need, 1) if need else 0)
    if int(planned or 0) == 0:
        to_add = min(n, max(min_q, 10))

    logger.info(
        f"[threads-text] daily flagships={flagship_product_ids_for_day()}"
    )
    added = 0
    for _ in range(to_add):
        slot, window_idx = pick_random_slot(tz, con=con)
        day_key = slot[:10]
        kind = _pick_kind(
            recent, window_idx=window_idx, con=con, day_key=day_key
        )
        geo = _pick_geo(geos_recent)
        if "bali" in kind:
            geo = next(g for g in GEO_POOL if g["key"] == "bali")
        elif "kailas" in kind:
            geo = next(
                (g for g in GEO_POOL if g["key"] == "kailas"),
                {
                    "key": "kailas",
                    "label": "Кайлас / Тибет",
                    "angles": "кора 3 дня / 52 км (не за 1 день), высота, смысл пути vs галочка, подготовка 2027",
                },
            )
        elif "india" in kind:
            geo = next(
                (g for g in GEO_POOL if g["key"] == "india"),
                {
                    "key": "india",
                    "label": "Индия",
                    "angles": "индивидуальный формат, 10 дней, к 8 марта, без копирования группового тарифа",
                },
            )
        news: dict[str, str] | None = None

        if kind == "news":
            news = fetch_news_candidate(con)
            if news is None:
                logger.warning("[threads-text] no fresh RSS item → fallback warmup")
                kind = "warmup"

        try:
            text = generate_threads_text(
                kind=kind,
                avoid_openings=avoid,
                geo=geo,
                news=news,
            )
        except Exception:
            logger.exception(f"[threads-text] generate failed kind={kind}")
            continue

        # Soft brand cue on selling posts without punctuation dashes.
        if kind.startswith("promo") and "jay shambo" not in text.lower():
            text = f"{text.rstrip()}\nJay Shambo Travel, если откликается."

        post_id = f"TT-{uuid.uuid4().hex[:10].upper()}"
        sid = _source_id_for(kind, geo=geo, news=news)
        upsert_item(
            con,
            reel_id=post_id,
            scheduled_at=slot,
            video_path="",
            caption=text,
            status="planned",
            source="threads_text_gen",
            source_id=sid,
            platform="threads_text",
        )
        recent.append(sid)
        geos_recent.append(geo["key"])
        avoid.insert(0, text[:140].replace("\n", " "))
        added += 1
        logger.success(
            f"[threads-text] queued {post_id} kind={sid} win={window_idx} at {slot}"
        )
    return added


def publish_due_threads_text(*, db_path: str, tz_name: str) -> bool:
    """Publish one due TEXT post to Threads META_N."""
    if not _env_bool("THREADS_TEXT_AUTOPOST", True):
        return False

    from uploader.meta_accounts import load_meta_targets
    from uploader.threads_publisher import publish_threads_text

    con = connect(db_path)
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz=tz).isoformat(timespec="seconds")
    per_day = _env_int("THREADS_TEXT_MAX_PER_DAY", 5)
    if _day_count(con, datetime.now(tz=tz).date().isoformat()) >= per_day:
        return False

    due = next_due(con, now_iso=now, platform="threads_text")
    if due is None:
        return False

    text = (due.caption or "").strip()
    if not text:
        record_attempt(
            con,
            reel_id=due.reel_id,
            scheduled_at=due.scheduled_at,
            status="skipped",
            last_error="empty caption",
        )
        return False

    idx = threads_text_meta_index()
    targets = [
        t for t in load_meta_targets() if t.index == idx and t.publish_threads
    ]
    if not targets:
        logger.error("[threads-text] no META_N PUBLISH_THREADS target")
        return False

    logger.info(
        f"[threads-text] publishing {due.reel_id} kind={due.source_id} "
        f"len={len(text)} → META_{idx}"
    )
    try:
        result = publish_threads_text(target=targets[0], text=text)
    except Exception as exc:
        record_attempt(
            con,
            reel_id=due.reel_id,
            scheduled_at=due.scheduled_at,
            status="planned",
            last_error=str(exc)[:500],
        )
        logger.exception(f"[threads-text] publish failed {due.reel_id}")
        return False

    record_attempt(
        con,
        reel_id=due.reel_id,
        scheduled_at=due.scheduled_at,
        status="posted",
        ig_media_id=result.post_id,
        last_api_response=json.dumps(
            {
                "threads_post_id": result.post_id,
                "kind": due.source_id or "",
            },
            ensure_ascii=False,
        ),
        last_error="",
    )
    logger.success(
        f"[threads-text] posted {due.reel_id} id={result.post_id} "
        f"account={result.account}"
    )
    return True


def threads_text_tick(*, db_path: str, tz_name: str) -> None:
    refill_queue(db_path=db_path, tz_name=tz_name)
    publish_due_threads_text(db_path=db_path, tz_name=tz_name)
