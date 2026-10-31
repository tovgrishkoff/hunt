"""Sync Notion-ready carousels (C-*) and publish to IG @grishkoff_travel + Threads."""

from __future__ import annotations

import json
import os
import random
import re
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from loguru import logger
from notion_client import Client

from uploader.db import (
    UploadItem,
    connect,
    is_posted_on_platform,
    list_planned_reel_ids,
    next_due,
    record_attempt,
    upsert_item,
)
from uploader.competitor_guard import (
    contains_competitor_brand,
    strip_competitor_brands,
)
from uploader.facebook_publisher import publish_all_fb_albums
from uploader.instagram_carousel_publisher import (
    load_carousel_config,
    publish_carousel,
)
from uploader.meta_accounts import load_meta_targets
from uploader.notion_report import load_notion_report_config, upsert_report_page
from uploader.threads_publisher import publish_threads_carousel


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


def carousel_meta_index() -> int:
    return _env_int("CAROUSEL_META_TARGET", 2)


def carousel_fb_meta_index() -> int | None:
    """META_N for Facebook album. Empty → all fb_targets() (META_3)."""
    raw = _env("CAROUSEL_FB_META_TARGET")
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _plain_text(prop: dict[str, Any] | None) -> str:
    if not prop:
        return ""
    t = prop.get("type")
    if t in ("rich_text", "title"):
        parts = prop.get(t) or []
        return "".join((p.get("plain_text") or "") for p in parts).strip()
    if t == "url":
        return (prop.get("url") or "").strip()
    if t == "select":
        v = prop.get("select") or {}
        return (v.get("name") or "").strip()
    return ""


def _article_url_from_meta(last_api: str, theme_field: str = "") -> str:
    if last_api:
        try:
            meta = json.loads(last_api)
            url = str(meta.get("article_url") or "").strip()
            if url.startswith("http"):
                return url
        except Exception:
            pass
    # Fallback: "carousel · theme · https://..."
    m = re.search(r"(https?://\S+)", theme_field or "")
    return m.group(1).rstrip(".,)") if m else ""


def _slug_from_carousel_id(carousel_id: str) -> str:
    raw = (carousel_id or "").strip()
    if raw.startswith("C-"):
        raw = raw[2:]
    return raw.strip("-")


def build_carousel_caption(
    *,
    body: str,
    title: str = "",
    article_url: str = "",
    max_chars: int = 2100,
) -> str:
    """
    Short photo-carousel summary + CTA link to the blog article.

    Example ending:
      Хотите больше деталей — читайте на сайте:
      https://jayshambo.com/blog/...
    """
    text = strip_competitor_brands((body or "").strip())
    if not text:
        text = strip_competitor_brands((title or "").strip())
    # Strip previous CTA if re-building
    text = re.split(
        r"\n\s*Хотите больше деталей\s*[—\-–]",
        text,
        maxsplit=1,
    )[0].strip()
    text = strip_competitor_brands(text)
    # Keep first ~2 paragraphs as summary
    parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    summary = "\n\n".join(parts[:2]) if parts else text
    cta = ""
    url = strip_competitor_brands((article_url or "").strip())
    # не тащим slug с именем конкурента в CTA
    if contains_competitor_brand(url):
        url = strip_competitor_brands(url)
    if url and url not in summary:
        cta = (
            "\n\nХотите больше деталей — читайте на сайте:\n"
            f"{url}"
        )
    budget = max_chars - len(cta)
    if len(summary) > budget:
        summary = summary[: max(0, budget - 1)].rstrip() + "…"
    out = f"{summary}{cta}".strip()
    return out[:max_chars]


def _lookup_article_url(carousel_id: str) -> str:
    """Find full blog URL from local notion_export.json files."""
    roots = [
        "/home/tovgrishkoff/content_engine/output",
        "/app/../content_engine/output",
        "content_engine/output",
    ]
    import glob
    from pathlib import Path

    for root in roots:
        for path in glob.glob(f"{root}/site_batch_dryrun_*/notion_export.json"):
            try:
                items = json.loads(Path(path).read_text(encoding="utf-8"))
            except Exception:
                continue
            for it in items:
                if str(it.get("carousel_id") or "") == carousel_id:
                    url = str(it.get("article_url") or "").strip()
                    if url.startswith("http"):
                        return url
    return ""


def _parse_slides_from_notion(
    *,
    last_api: str,
    r2_keys: str,
    first_url: str,
) -> list[str]:
    """Recover public slide URLs from Notion fields."""
    # Prefer structured meta written by export_carousel_notion
    if last_api:
        try:
            meta = json.loads(last_api)
            slides = meta.get("slides") or []
            urls = [
                str(s.get("url") or "").strip()
                for s in slides
                if isinstance(s, dict) and str(s.get("url") or "").strip()
            ]
            if len(urls) >= 2:
                return urls
        except Exception:
            pass

    base = _env("R2_PUBLIC_BASE_URL").rstrip("/")
    keys = [k.strip() for k in (r2_keys or "").splitlines() if k.strip()]
    if base and len(keys) >= 2:
        return [f"{base}/{k.lstrip('/')}" for k in keys]

    # Fallback: guess siblings from first URL (slide_01.jpg → slide_02…)
    if first_url and "slide_" in first_url:
        m = re.search(r"(.*slide_)(\d+)(\.[a-zA-Z0-9]+)$", first_url)
        if m:
            prefix, num, ext = m.group(1), int(m.group(2)), m.group(3)
            guessed = [f"{prefix}{i:02d}{ext}" for i in range(1, 11)]
            # Keep at least the first known URL
            if guessed[0] != first_url:
                guessed[0] = first_url
            return guessed[:6]
    if first_url:
        return [first_url]
    return []


def _day_has_off_queue(con: Any, day_key: str) -> bool:
    """День с внеочередной каруселью не сдвигаем: слоты этого дня остаются."""
    if con is None:
        return False
    rows = con.execute(
        "SELECT last_api_response FROM upload_queue "
        "WHERE reel_id LIKE 'C-%' AND status='planned' "
        "AND scheduled_at LIKE ?",
        (f"{day_key}%",),
    ).fetchall()
    for row in rows:
        raw = str(row[0] or "")
        if '"off_queue": true' in raw or '"off_queue":true' in raw:
            return True
    return False


def _day_carousel_count(con: Any, day_key: str) -> int:
    return int(
        con.execute(
            "SELECT COUNT(*) FROM upload_queue "
            "WHERE reel_id LIKE 'C-%' "
            "AND status IN ('planned','posted','publishing') "
            "AND scheduled_at LIKE ?",
            (f"{day_key}%",),
        ).fetchone()[0]
    )


def _bump_planned_carousel(con: Any, day_key: str, tz: ZoneInfo) -> bool:
    """Move the latest planned carousel on day_key to the next free day.

    Gives brand-new article carousels priority for the soonest window.
    """
    row = con.execute(
        "SELECT reel_id, scheduled_at FROM upload_queue "
        "WHERE reel_id LIKE 'C-%' AND status='planned' "
        "AND scheduled_at LIKE ? "
        "ORDER BY scheduled_at DESC LIMIT 1",
        (f"{day_key}%",),
    ).fetchone()
    if not row:
        return False
    reel_id, old_at = row[0], row[1]
    # Find next free day after day_key
    try:
        base = datetime.fromisoformat(day_key).date()
    except ValueError:
        base = datetime.now(tz=tz).date()
    per_day = max(1, _env_int("CAROUSEL_MAX_PER_DAY", 1))
    windows = _carousel_windows()
    for offset in range(1, 30):
        day = base + timedelta(days=offset)
        dk = day.isoformat()
        if _day_carousel_count(con, dk) >= per_day:
            continue
        hh, mm = windows[0]
        jitter = random.randint(0, max(0, _env_int("CAROUSEL_JITTER_MIN", 25)))
        new_at = datetime(day.year, day.month, day.day, hh, mm, tzinfo=tz) + timedelta(
            minutes=jitter
        )
        con.execute(
            "UPDATE upload_queue SET scheduled_at=? WHERE reel_id=? AND scheduled_at=?",
            (new_at.isoformat(timespec="seconds"), reel_id, old_at),
        )
        con.commit()
        logger.info(
            f"[carousel] bumped backlog {reel_id}: {old_at} → {new_at.isoformat(timespec='seconds')}"
        )
        return True
    return False


def _carousel_windows() -> list[tuple[int, int]]:
    windows_raw = _env("CAROUSEL_WINDOWS", "11:30,16:40")
    windows: list[tuple[int, int]] = []
    for part in windows_raw.split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        hh, mm = part.split(":", 1)
        try:
            windows.append((int(hh), int(mm)))
        except ValueError:
            continue
    if not windows:
        windows = [(11, 30), (16, 40)]
    return sorted(windows)


def _pick_schedule_slot(
    tz: ZoneInfo, *, con: Any = None, priority: bool = True
) -> str:
    """Next free carousel slot: max 1/day across CAROUSEL_WINDOWS (MSK).

    Tries windows in chronological order. With priority=True (default for
    fresh Notion sync), bumps a backlog planned item if today/soon is full
    so the new article carousel can ship in the next window.
    """
    windows = _carousel_windows()
    now = datetime.now(tz=tz)
    per_day = max(1, _env_int("CAROUSEL_MAX_PER_DAY", 1))
    jitter_max = _env_int("CAROUSEL_JITTER_MIN", 25)

    for day_offset in range(0, 21):
        day = (now + timedelta(days=day_offset)).date()
        day_key = day.isoformat()
        day_count = _day_carousel_count(con, day_key) if con is not None else 0
        if _day_has_off_queue(con, day_key):
            continue
        if day_count >= per_day:
            if priority and con is not None and _bump_planned_carousel(con, day_key, tz):
                day_count = _day_carousel_count(con, day_key)
            if day_count >= per_day:
                # Posted already fills the day — cannot bump; try next day
                continue
        for hh, mm in windows:
            jitter = random.randint(0, max(0, jitter_max))
            slot = datetime(
                day.year, day.month, day.day, hh, mm, tzinfo=tz
            ) + timedelta(minutes=jitter)
            if slot <= now + timedelta(minutes=15):
                continue
            return slot.isoformat(timespec="seconds")
    return (now + timedelta(hours=2)).isoformat(timespec="seconds")


def sync_ready_carousels(*, db_path: str, tz: ZoneInfo) -> int:
    """Import Notion C-* rows with status «Готов к публикации» into queue."""
    if not _env_bool("CAROUSEL_AUTOPOST", True):
        return 0

    cfg = load_notion_report_config()
    if cfg is None:
        logger.warning("[carousel] Notion not configured — skip sync")
        return 0

    from uploader.notion_report import (
        _get_database_property_type,
        _resolve_data_source_id,
    )

    notion = Client(auth=cfg.token)
    status_ready = cfg.status_uploaded  # «Готов к публикации»
    logger.info(
        f"[carousel] sync Notion db={cfg.database_id} status={status_ready!r}"
    )

    try:
        ds_id = _resolve_data_source_id(notion, cfg.database_id)
        status_type = _get_database_property_type(
            notion, cfg.database_id, cfg.status_prop
        )
        title_type = _get_database_property_type(
            notion, cfg.database_id, cfg.title_prop
        )

        def _status_filter() -> dict[str, Any]:
            if status_type == "select":
                return {
                    "property": cfg.status_prop,
                    "select": {"equals": status_ready},
                }
            return {
                "property": cfg.status_prop,
                "status": {"equals": status_ready},
            }

        def _title_filter() -> dict[str, Any]:
            key = "title" if title_type in {"", "title"} else "rich_text"
            if title_type == "rich_text":
                key = "rich_text"
            return {
                "property": cfg.title_prop,
                key: {"starts_with": "C-"},
            }

        res = notion.data_sources.query(
            data_source_id=ds_id,
            filter={"and": [_status_filter(), _title_filter()]},
            page_size=50,
        )
    except Exception as exc:
        logger.error(f"[carousel] Notion query failed: {exc}")
        return 0

    pages = res.get("results") or []
    # Newest Notion rows first so today's article wins the next window
    pages = sorted(
        pages,
        key=lambda p: str(p.get("created_time") or ""),
        reverse=True,
    )
    con = connect(db_path)
    used = list_planned_reel_ids(con, include_posted=True, platform="carousel")
    synced = 0

    for page in pages:
        page_id = str(page.get("id") or "").strip()
        props = page.get("properties") or {}
        carousel_id = _plain_text(props.get(cfg.title_prop) or {})
        if not carousel_id.startswith("C-"):
            continue
        if carousel_id in used or is_posted_on_platform(
            con, reel_id=carousel_id, platform="carousel"
        ):
            continue

        caption = _plain_text(props.get(cfg.caption_prop) or {})
        title = _plain_text(props.get(cfg.title_text_prop) or {})
        r2_keys = _plain_text(props.get(cfg.r2_key_prop) or {})
        first_url = _plain_text(props.get(cfg.r2_url_prop) or {})
        last_api = _plain_text(props.get(cfg.last_api_response_prop) or {})
        theme_field = _plain_text(props.get("Тема видео") or {})
        article_url = _article_url_from_meta(last_api, theme_field)
        if not article_url:
            article_url = _lookup_article_url(carousel_id)
        if not article_url:
            slug = _slug_from_carousel_id(carousel_id)
            if slug:
                article_url = f"https://jayshambo.com/blog/{slug}"
        caption = build_carousel_caption(
            body=caption,
            title=title or carousel_id,
            article_url=article_url,
        )
        slides = _parse_slides_from_notion(
            last_api=last_api, r2_keys=r2_keys, first_url=first_url
        )
        if len(slides) < 2:
            logger.warning(
                f"[carousel] skip {carousel_id}: need ≥2 slide URLs "
                f"(got {len(slides)})"
            )
            continue

        scheduled_at = _pick_schedule_slot(tz, con=con)
        base = _env("R2_PUBLIC_BASE_URL").rstrip("/")
        upsert_item(
            con,
            reel_id=carousel_id,
            scheduled_at=scheduled_at,
            video_path="",
            r2_key=r2_keys
            or "\n".join(
                s.replace(base + "/", "") if base else s for s in slides
            ),
            video_url=json.dumps(slides, ensure_ascii=False),
            caption=caption or carousel_id,
            status="planned",
            source="notion",
            source_id=page_id,
            platform="carousel",
        )
        synced += 1
        logger.success(
            f"[carousel] queued {carousel_id} at {scheduled_at} "
            f"slides={len(slides)}"
        )

    if synced:
        logger.success(f"[carousel] synced {synced} ready carousels")
    else:
        logger.info("[carousel] no new ready carousels to queue")
    return synced


def _slide_urls_from_item(item: UploadItem) -> list[str]:
    raw = (item.video_url or "").strip()
    if raw.startswith("["):
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [str(u).strip() for u in data if str(u).strip()]
        except Exception:
            pass
    if raw.startswith("http"):
        return [u.strip() for u in raw.split(",") if u.strip().startswith("http")]
    return _parse_slides_from_notion(
        last_api=item.last_api_response or "",
        r2_keys=item.r2_key or "",
        first_url=raw if raw.startswith("http") else "",
    )


def publish_due_carousel(*, db_path: str, tz: ZoneInfo) -> bool:
    """Publish one due carousel to IG + Threads + Facebook. Returns True if posted."""
    if not _env_bool("CAROUSEL_AUTOPOST", True):
        return False

    con = connect(db_path)
    now = datetime.now(tz=tz).isoformat(timespec="seconds")
    due = next_due(con, now_iso=now, platform="carousel")
    if due is None:
        return False

    if is_posted_on_platform(con, reel_id=due.reel_id, platform="carousel"):
        record_attempt(
            con,
            reel_id=due.reel_id,
            scheduled_at=due.scheduled_at,
            status="skipped",
            last_error="carousel already posted",
        )
        logger.warning(f"[carousel] skip duplicate {due.reel_id}")
        return False

    slides = _slide_urls_from_item(due)
    if len(slides) < 2:
        record_attempt(
            con,
            reel_id=due.reel_id,
            scheduled_at=due.scheduled_at,
            status="skipped",
            last_error=f"Need ≥2 slides, got {len(slides)}",
        )
        logger.error(f"[carousel] skip {due.reel_id}: bad slides")
        return False

    meta_idx = carousel_meta_index()
    # Enrich caption with blog CTA if missing
    article_url = ""
    m = re.search(r"(https?://jayshambo\.com/blog/\S+)", due.caption or "")
    if m:
        article_url = m.group(1).rstrip(".,)")
    else:
        article_url = _article_url_from_meta(due.last_api_response or "")
        if not article_url:
            article_url = _lookup_article_url(due.reel_id)
        if not article_url:
            slug = _slug_from_carousel_id(due.reel_id)
            article_url = f"https://jayshambo.com/blog/{slug}" if slug else ""
    caption = build_carousel_caption(
        body=due.caption or "",
        title=due.reel_id,
        article_url=article_url,
    )
    if contains_competitor_brand(caption) or contains_competitor_brand(due.reel_id):
        caption = strip_competitor_brands(caption)
        logger.warning(
            f"[carousel] competitor brand in {due.reel_id} — caption sanitized"
        )
    if contains_competitor_brand(caption) or contains_competitor_brand(due.reel_id):
        record_attempt(
            con,
            reel_id=due.reel_id,
            scheduled_at=due.scheduled_at,
            status="skipped",
            last_error="competitor brand in caption/id — publish blocked",
        )
        logger.error(
            f"[carousel] skip {due.reel_id}: competitor brand still present"
        )
        return False
    notion_cfg = load_notion_report_config()

    logger.info(
        f"[carousel] publishing {due.reel_id} slides={len(slides)} "
        f"→ META_{meta_idx} IG + Threads + FB caption_len={len(caption)}"
    )

    if notion_cfg is not None:
        try:
            upsert_report_page(
                cfg=notion_cfg,
                reel_id=due.reel_id,
                scheduled_at_iso=due.scheduled_at,
                caption=caption,
                r2_key=due.r2_key,
                r2_url=slides[0],
                status_name=notion_cfg.status_publishing,
                source_page_id=due.source_id if due.source == "notion" else "",
                platform="Instagram",
            )
        except Exception:
            logger.exception(f"[carousel] Notion publishing state failed for {due.reel_id}")

    ig_media_id = ""
    ig_container_id = ""
    threads_post_id = ""
    fb_post_id = ""
    errors: list[str] = []

    # Instagram — only META_N (default 2 = @grishkoff_travel)
    try:
        cfg = load_carousel_config(meta_idx)
        ig_container_id, ig_media_id = publish_carousel(
            cfg=cfg, image_urls=slides, caption=caption
        )
    except Exception as exc:
        errors.append(f"IG: {exc}")
        logger.exception(f"[carousel] IG failed for {due.reel_id}")

    # Threads — same META_N if PUBLISH_THREADS
    if _env_bool("CAROUSEL_PUBLISH_THREADS", True):
        targets = [
            t
            for t in load_meta_targets()
            if t.index == meta_idx and t.publish_threads
        ]
        if targets:
            try:
                th = publish_threads_carousel(
                    target=targets[0], image_urls=slides, caption=caption
                )
                threads_post_id = th.post_id
            except Exception as exc:
                errors.append(f"Threads: {exc}")
                logger.exception(f"[carousel] Threads failed for {due.reel_id}")
        else:
            logger.warning(
                f"[carousel] META_{meta_idx} Threads off — skip Threads"
            )

    if _env_bool("CAROUSEL_PUBLISH_FB", True):
        try:
            fb_results = publish_all_fb_albums(
                image_urls=slides,
                caption=caption,
                meta_index=carousel_fb_meta_index(),
            )
            if fb_results:
                fb_post_id = fb_results[0].post_id
                logger.info(
                    "[carousel] FB album ok: "
                    + ", ".join(f"{r.account}:{r.post_id}" for r in fb_results)
                )
            else:
                logger.warning("[carousel] FB skipped (no META_*_PUBLISH_FB targets)")
        except Exception as exc:
            errors.append(f"FB: {exc}")
            logger.exception(f"[carousel] FB album failed for {due.reel_id}")

    pin_ids: list[str] = []
    if _env_bool("CAROUSEL_PUBLISH_PINTEREST", True) and _env_bool("UPLOAD_PINTEREST", False):
        try:
            # Production image pins when PINTEREST_ACCESS_TOKEN is set;
            # otherwise falls back to Cloud Run Trial inside publisher.
            from uploader.pinterest_publisher import publish_carousel_to_pinterest

            article_link = ""
            for line in (caption or "").splitlines():
                line = line.strip()
                if line.startswith("https://jayshambo.com"):
                    article_link = line
                    break
            pin_results = publish_carousel_to_pinterest(
                slide_urls=slides,
                caption=caption,
                carousel_id=due.reel_id,
                link=article_link or _env("PINTEREST_DEFAULT_LINK", "https://jayshambo.com"),
                max_slides=int(_env("PINTEREST_CAROUSEL_MAX_SLIDES", "5") or "5"),
            )
            pin_ids = [p.pin_id for p in pin_results]
            logger.success(
                f"[carousel] Pinterest pins={len(pin_ids)} ids={','.join(pin_ids[:3])}…"
            )
        except Exception as exc:
            errors.append(f"Pinterest: {exc}")
            logger.exception(f"[carousel] Pinterest failed for {due.reel_id}")

    if not ig_media_id and not threads_post_id and not fb_post_id:
        record_attempt(
            con,
            reel_id=due.reel_id,
            scheduled_at=due.scheduled_at,
            status="planned",
            last_error="; ".join(errors)[:4000],
        )
        if notion_cfg is not None:
            try:
                upsert_report_page(
                    cfg=notion_cfg,
                    reel_id=due.reel_id,
                    scheduled_at_iso=due.scheduled_at,
                    caption=caption,
                    status_name=notion_cfg.status_error,
                    error_text="; ".join(errors)[:1800],
                    source_page_id=due.source_id if due.source == "notion" else "",
                    platform="Instagram",
                )
            except Exception:
                logger.exception("[carousel] Notion error update failed")
        return False

    permalink = (
        f"https://www.instagram.com/p/{ig_media_id}/" if ig_media_id else ""
    )
    api_blob = json.dumps(
        {
            "ig_media_id": ig_media_id,
            "ig_container_id": ig_container_id,
            "threads_post_id": threads_post_id,
            "fb_post_id": fb_post_id,
            "errors": errors,
        },
        ensure_ascii=False,
    )
    record_attempt(
        con,
        reel_id=due.reel_id,
        scheduled_at=due.scheduled_at,
        ig_container_id=ig_container_id,
        ig_media_id=ig_media_id,
        status="posted",
        last_api_response=api_blob,
        last_error="; ".join(errors) if errors else "",
    )

    if notion_cfg is not None:
        try:
            upsert_report_page(
                cfg=notion_cfg,
                reel_id=due.reel_id,
                scheduled_at_iso=due.scheduled_at,
                caption=caption,
                r2_key=due.r2_key,
                r2_url=slides[0],
                post_url=permalink,
                post_id=ig_media_id or threads_post_id or fb_post_id,
                container_id=ig_container_id,
                last_api_response=api_blob[:1900],
                status_name=notion_cfg.status_posted,
                error_text="; ".join(errors) if errors else "",
                source_page_id=due.source_id if due.source == "notion" else "",
                platform="Instagram",
            )
        except Exception:
            logger.exception(f"[carousel] Notion posted update failed for {due.reel_id}")

    logger.success(
        f"[carousel] posted {due.reel_id} ig={ig_media_id or '-'} "
        f"threads={threads_post_id or '-'} fb={fb_post_id or '-'} "
        f"pinterest={','.join(pin_ids[:3]) if pin_ids else '-'} "
        f"permalink={permalink or '-'}"
    )
    return True


def carousel_tick(*, db_path: str, tz_name: str = "Asia/Makassar") -> None:
    """Periodic: sync Notion → queue, then publish one due carousel if any."""
    if not _env_bool("CAROUSEL_AUTOPOST", True):
        return
    tz = ZoneInfo(tz_name)
    try:
        sync_ready_carousels(db_path=db_path, tz=tz)
    except Exception:
        logger.exception("[carousel] sync tick failed")
    try:
        publish_due_carousel(db_path=db_path, tz=tz)
    except Exception:
        logger.exception("[carousel] publish tick failed")


def requeue_carousel(
    *,
    db_path: str,
    carousel_id: str,
    slides: list[str],
    caption: str,
    article_url: str = "",
    title: str = "",
    source_id: str = "",
    publish_now: bool = False,
    tz_name: str = "Asia/Makassar",
) -> str:
    """
  Put carousel back in upload queue (e.g. after fixing slides in R2).

  Instagram does not update published posts — use publish_now=True for a new post.
  """
    if len(slides) < 2:
        raise ValueError(f"Need ≥2 slides, got {len(slides)}")
    tz = ZoneInfo(tz_name)
    con = connect(db_path)
    if publish_now:
        scheduled_at = datetime.now(tz=tz).isoformat(timespec="seconds")
    else:
        scheduled_at = _pick_schedule_slot(tz, con=con, priority=True)

    base = _env("R2_PUBLIC_BASE_URL").rstrip("/")
    r2_keys = "\n".join(
        s.replace(base + "/", "") if base and s.startswith(base) else s
        for s in slides
    )
    body = build_carousel_caption(
        body=caption,
        title=title or carousel_id,
        article_url=article_url,
    )
    meta = {
        "kind": "carousel",
        "article_url": article_url,
        "slides": [{"url": u} for u in slides],
        "republish": True,
    }
    upsert_item(
        con,
        reel_id=carousel_id,
        scheduled_at=scheduled_at,
        video_path="",
        r2_key=r2_keys,
        video_url=json.dumps(slides, ensure_ascii=False),
        caption=body,
        status="planned",
        source="notion",
        source_id=source_id,
        platform="carousel",
    )
    logger.success(
        f"[carousel] requeued {carousel_id} at {scheduled_at} slides={len(slides)}"
    )
    return scheduled_at
