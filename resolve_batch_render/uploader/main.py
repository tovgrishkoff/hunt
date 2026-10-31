from __future__ import annotations

import argparse
import os
import time as _time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from loguru import logger

from uploader.catalog import build_reel_assets
from uploader.db import (
    UploadItem,
    connect,
    list_for_date,
    list_planned_reel_ids,
    items_with_status,
    mark_status,
    next_due,
    record_attempt,
    set_caption,
    set_r2_key_and_url,
    set_source_id,
    set_video_path,
    upsert_item,
)
from uploader.scheduler import fixed_times, parse_times, parse_window, sample_times
from uploader.tg_alert import alert_autopost_fail


def _stories_gap_wait_sec(con, tz: ZoneInfo) -> float:
    """Seconds until a new Telegram story is allowed after the last posted one."""
    gap_h = float(_env("TG_STORIES_MIN_GAP_HOURS", "48") or "48")
    row = con.execute(
        """
        SELECT scheduled_at FROM upload_queue
        WHERE platform='telegram_story' AND status='posted'
        ORDER BY scheduled_at DESC
        LIMIT 1
        """
    ).fetchone()
    if not row or not row[0]:
        return 0.0
    try:
        last = datetime.fromisoformat(str(row[0]))
    except ValueError:
        return 0.0
    if last.tzinfo is None:
        last = last.replace(tzinfo=tz)
    ready_at = last.astimezone(tz) + timedelta(hours=gap_h)
    return max(0.0, (ready_at - datetime.now(tz=tz)).total_seconds())


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _env_bool(name: str, default: bool = True) -> bool:
    raw = _env(name)
    if not raw:
        return default
    return raw.lower() not in {"0", "false", "no", "off"}


def _cli_bool(*, flag_on: bool, flag_off: bool, env_name: str, default: bool) -> bool:
    if flag_on:
        return True
    if flag_off:
        return False
    return _env_bool(env_name, default)


def _today_str(tz: ZoneInfo) -> str:
    return datetime.now(tz=tz).date().isoformat()


def _safe_delete_local_video(video_path: str) -> None:
    """
    Delete a local file only if it is under LOCAL_MEDIA_ROOT (or cwd).

    This reduces the risk of deleting arbitrary paths due to bad queue data.
    """
    p = Path(video_path).expanduser()
    try:
        p = p.resolve()
    except Exception:
        p = Path(os.path.abspath(str(p)))

    root_raw = (os.environ.get("LOCAL_MEDIA_ROOT") or "").strip()
    root = Path(root_raw).expanduser().resolve() if root_raw else Path.cwd().resolve()

    try:
        p.relative_to(root)
    except Exception:
        raise ValueError(f"Refusing to delete outside LOCAL_MEDIA_ROOT: {p} (root={root})")

    if _queue_still_needs_file(str(p)):
        logger.info(f"Keep local video, another platform still queued: {p.name}")
        return

    if p.exists() and p.is_file():
        p.unlink()


def _queue_still_needs_file(video_path: str) -> bool:
    """True when a not-yet-posted row still points at this file."""
    from uploader.db import connect

    db_path = (os.environ.get("UPLOAD_DB_PATH") or "output/upload_queue.sqlite3").strip()
    try:
        target = Path(video_path).expanduser().resolve()
    except Exception:
        target = Path(video_path)
    try:
        con = connect(db_path)
    except Exception:
        return False
    try:
        rows = con.execute(
            "SELECT video_path FROM upload_queue "
            "WHERE status IN ('planned', 'publishing', 'hold')"
        ).fetchall()
    finally:
        con.close()
    raw = str(video_path)
    for (stored,) in rows:
        if not stored:
            continue
        if stored == raw:
            return True
        try:
            if Path(stored).expanduser().resolve() == target:
                return True
        except Exception:
            continue
    return False


def _find_video_by_reel_id(reels_dir: Path, reel_id: str) -> Path | None:
    rid = (reel_id or "").strip()
    if not rid or not reels_dir.is_dir():
        return None
    base = reels_dir / rid
    for ext in (".mp4", ".mov", ".m4v"):
        p = Path(str(base) + ext)
        if p.is_file():
            return p.resolve()
    rid_lower = rid.lower()
    exact: list[Path] = []
    prefixed: list[Path] = []
    for p in sorted(reels_dir.iterdir()):
        if not p.is_file() or not p.name.lower().endswith((".mp4", ".mov", ".m4v")):
            continue
        if p.stem.lower() == rid_lower:
            exact.append(p)
        elif p.name.lower().startswith(rid_lower):
            prefixed.append(p)
    if exact:
        return exact[0].resolve()
    if prefixed:
        return prefixed[0].resolve()
    return None


def _resolve_video_path(video_path: str, *, reel_id: str) -> Path:
    """Resolve a usable local path for a queued item.

    Some environments stored absolute paths under a different root
    (e.g. /home/.../.cache/resolve_batch_render/...) than the current runtime.
    This function tries a few safe fallbacks before failing.
    """
    raw = (video_path or "").strip()
    if not raw:
        raise FileNotFoundError("empty video_path in queue")

    p = Path(raw).expanduser()
    if p.is_file():
        return p.resolve()

    # 1) Map ".../resolve_batch_render/<suffix>" onto current project root.
    parts: list[str]
    try:
        parts = list(p.resolve().parts)
    except Exception:
        parts = list(p.parts)
    if "resolve_batch_render" in parts:
        idx = parts.index("resolve_batch_render")
        suffix = Path(*parts[idx + 1 :])
        project_root = Path(__file__).resolve().parent.parent
        mapped = (project_root / suffix).resolve()
        if mapped.is_file():
            return mapped

    # 2) Try same filename inside configured reels dirs.
    candidates: list[Path] = []
    for env_key in ("READY_DIR", "UPLOAD_REELS_DIR", "REELS_DIR"):
        v = (os.environ.get(env_key) or "").strip()
        if v:
            candidates.append(Path(v).expanduser())
    candidates.append(Path(__file__).resolve().parent.parent / "output" / "reels")

    filename = p.name
    for d in candidates:
        try:
            direct = (d / filename).expanduser().resolve()
            if direct.is_file():
                return direct
        except Exception:
            continue

    # 3) Try by reel_id inside those dirs.
    for d in candidates:
        try:
            found = _find_video_by_reel_id(d.expanduser().resolve(), reel_id)
            if found is not None:
                return found
        except Exception:
            continue

    # 4) Hotel media-kit originals (survive LOCAL_DELETE_AFTER_POST on output/reels).
    #    AVANA__DINER → media_kit_downloads/video/AVANA/diner.mov
    try:
        from uploader.media_kit_catalog import parse_hotel_prefix

        hotel, original_name = parse_hotel_prefix(reel_id)
        if not hotel:
            hotel, original_name = parse_hotel_prefix(filename)
        if hotel and original_name:
            project_root = Path(__file__).resolve().parent.parent
            mk_dir = project_root / "media_kit_downloads" / "video" / hotel.upper()
            # try exact original name, then case-insensitive / stem match
            for cand in (
                mk_dir / original_name,
                mk_dir / Path(original_name).name,
            ):
                if cand.is_file():
                    return cand.resolve()
            if mk_dir.is_dir():
                stem = Path(original_name).stem.lower()
                for p in mk_dir.iterdir():
                    if p.is_file() and p.stem.lower() == stem:
                        return p.resolve()
    except Exception:
        pass

    # 5) Already-transcoded Stories MP4 cache
    try:
        project_root = Path(__file__).resolve().parent.parent
        ready = project_root / "output" / "stories_ready" / f"{reel_id}.mp4"
        if ready.is_file():
            return ready.resolve()
    except Exception:
        pass

    tried = ", ".join([str(c) for c in candidates] + ["media_kit_downloads", "stories_ready"])
    raise FileNotFoundError(f"{raw} (tried: {tried})")


def _hold_interrupted_publishes(con, *, platform: str) -> None:
    """A killed publish stays 'publishing'. Do not open another container for it."""
    for item in items_with_status(con, status="publishing", platform=platform):
        if (item.ig_media_id or "").strip():
            record_attempt(
                con,
                reel_id=item.reel_id,
                scheduled_at=item.scheduled_at,
                status="posted",
                last_error="",
            )
            logger.info(f"[IG] {item.reel_id} already has media id, marked posted")
            continue
        record_attempt(
            con,
            reel_id=item.reel_id,
            scheduled_at=item.scheduled_at,
            status="hold",
            last_error="publish interrupted, not repeating the same reel",
        )
        logger.warning(
            f"[IG] {item.reel_id} publish was interrupted, held so it is not posted again"
        )


def _release_held_media(con, *, platform: str) -> None:
    """Move hold rows back to planned once the QuickTime file is finished."""
    from uploader.media_file import incomplete_reason

    for item in items_with_status(con, status="hold", platform=platform):
        err = item.last_error or ""
        if not (err.startswith("media not ready:") or err.startswith("file missing:")):
            continue
        try:
            path = _resolve_video_path(item.video_path, reel_id=item.reel_id)
        except FileNotFoundError:
            continue
        reason = incomplete_reason(path)
        if reason:
            continue
        set_r2_key_and_url(
            con,
            reel_id=item.reel_id,
            scheduled_at=item.scheduled_at,
            r2_key="",
            video_url="",
        )
        record_attempt(
            con,
            reel_id=item.reel_id,
            scheduled_at=item.scheduled_at,
            status="planned",
            last_error="",
        )
        logger.info(f"[media] {item.reel_id} finished, returned to planned")


def _park_until_ready(con, due: UploadItem) -> tuple[str, Path | None]:
    """Decide whether a due row can be published.

    Returns:
        ("ready", path) — local file has a moov atom.
        ("remote", None) — local file is gone, but a public URL is already stored.
        ("parked", None) — row set to hold; caller should take the next item.
    """
    from uploader.media_file import incomplete_reason

    try:
        path = _resolve_video_path(due.video_path, reel_id=due.reel_id)
    except FileNotFoundError as exc:
        if (due.video_url or "").strip():
            return "remote", None
        record_attempt(
            con,
            reel_id=due.reel_id,
            scheduled_at=due.scheduled_at,
            status="hold",
            last_error=f"file missing: {exc}",
        )
        logger.warning(f"[media] hold {due.reel_id}: file missing")
        return "parked", None

    if str(path) != (due.video_path or "").strip():
        set_video_path(
            con,
            reel_id=due.reel_id,
            scheduled_at=due.scheduled_at,
            video_path=str(path),
        )
    reason = incomplete_reason(path)
    if reason:
        set_r2_key_and_url(
            con,
            reel_id=due.reel_id,
            scheduled_at=due.scheduled_at,
            r2_key="",
            video_url="",
        )
        record_attempt(
            con,
            reel_id=due.reel_id,
            scheduled_at=due.scheduled_at,
            status="hold",
            last_error=f"media not ready: {reason}",
        )
        logger.warning(f"[media] hold {due.reel_id}: {reason}")
        return "parked", None
    return "ready", path


def _is_placeholder_ig_caption(caption: str, reel_id: str) -> bool:
    """True if queue caption is only reel id / plan-dir stub — replace from texts CSV."""
    t = (caption or "").strip()
    rid = (reel_id or "").strip()
    if not t:
        return True
    if rid and (t == rid or t.startswith(rid + "\n") or t.startswith(rid + " ")):
        return len(t) < 400
    return False


def _instagram_caption_for_publish(con, item: UploadItem) -> str:
    """Prefer texts CSV / R###→T### caption; keep explicit Notion caption when set."""
    from uploader.caption_resolve import resolve_publish_caption

    src = (item.source or "").strip().lower()
    cap_stored = (item.caption or "").strip()
    if src == "notion" and cap_stored and not _is_placeholder_ig_caption(item.caption, item.reel_id):
        return cap_stored

    resolved = resolve_publish_caption(item.reel_id, item.caption)
    if resolved != (item.caption or "").strip():
        set_caption(con, reel_id=item.reel_id, scheduled_at=item.scheduled_at, caption=resolved)
    return resolved


def cmd_plan(ns: argparse.Namespace) -> int:
    tz = ZoneInfo(ns.tz)
    window = parse_window(ns.window)
    db_path = ns.db_path
    con = connect(db_path)

    assets = build_reel_assets(
        plan_csv=ns.plan,
        texts_csv=ns.texts,
        reels_dir=ns.reels_dir,
        caption_suffix=ns.caption_suffix,
    )
    if not assets:
        logger.error("No reel assets found. Check reels_dir/plan/texts.")
        return 2

    day = date.fromisoformat(ns.day) if ns.day else datetime.now(tz=tz).date()
    times = sample_times(day=day, window=window, tz=tz, count=ns.count, seed=ns.seed)

    # Pick first N assets not already planned for this date.
    already = {it.reel_id for it in list_for_date(con, yyyy_mm_dd=day.isoformat())}
    remaining = [a for a in assets if a.reel_id not in already]
    if len(remaining) < ns.count:
        logger.warning(
            f"Not enough unused reels: need={ns.count}, available={len(remaining)}. Will reuse."
        )
        remaining = assets

    chosen = remaining[: ns.count]
    for dt, a in zip(times, chosen):
        upsert_item(
            con,
            reel_id=a.reel_id,
            scheduled_at=dt.isoformat(timespec="seconds"),
            video_path=a.video_path,
            r2_key="",
            video_url="",
            caption=a.caption,
            status="planned",
            source="local",
            source_id="",
        )
        logger.info(f"Planned {a.reel_id} @ {dt.isoformat(timespec='minutes')}  {a.video_path}")
    logger.info(f"DB: {db_path}")
    return 0


def cmd_plan_slots(ns: argparse.Namespace) -> int:
    """Plan reels at fixed times (e.g. morning/noon/evening)."""
    tz = ZoneInfo(ns.tz)
    db_path = ns.db_path
    con = connect(db_path)

    assets = build_reel_assets(
        plan_csv=ns.plan,
        texts_csv=ns.texts,
        reels_dir=ns.reels_dir,
        caption_suffix=ns.caption_suffix,
    )
    if not assets:
        logger.error("No reel assets found. Check reels_dir/plan/texts.")
        return 2

    day = date.fromisoformat(ns.day) if ns.day else datetime.now(tz=tz).date()
    times = parse_times(ns.times)
    if not times:
        raise SystemExit("No --times provided (example: 09:00,13:00,19:00)")
    dts = fixed_times(day=day, tz=tz, times=times)

    already = {it.reel_id for it in list_for_date(con, yyyy_mm_dd=day.isoformat())}
    remaining = [a for a in assets if a.reel_id not in already]
    if len(remaining) < len(dts):
        logger.warning(
            f"Not enough unused reels: need={len(dts)}, available={len(remaining)}. Will reuse."
        )
        remaining = assets

    chosen = remaining[: len(dts)]
    for dt, a in zip(dts, chosen):
        upsert_item(
            con,
            reel_id=a.reel_id,
            scheduled_at=dt.isoformat(timespec="seconds"),
            video_path=a.video_path,
            caption=a.caption,
            status="planned",
            source="local",
            source_id="",
        )
        logger.info(f"Planned {a.reel_id} @ {dt.isoformat(timespec='minutes')}  {a.video_path}")
    logger.info(f"DB: {db_path}")
    return 0


def _iter_reels_dir(reels_dir: str) -> list[tuple[str, str]]:
    """Return [(reel_id, abs_video_path)] sorted by reel_id."""
    root = Path(reels_dir).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        return []
    files: list[Path] = []
    for ext in (".mp4", ".mov", ".m4v"):
        files.extend(sorted(root.glob(f"*{ext}")))
        files.extend(sorted(root.glob(f"*{ext.upper()}")))
    out: list[tuple[str, str]] = []
    for p in files:
        if not p.is_file():
            continue
        rid = p.stem.strip()
        if not rid:
            continue
        out.append((rid, str(p.resolve())))
    # dedupe by reel_id keeping first
    uniq: dict[str, str] = {}
    for rid, path in out:
        uniq.setdefault(rid, path)
    return sorted(uniq.items(), key=lambda x: x[0])


def cmd_plan_dir_slots(ns: argparse.Namespace) -> int:
    """Plan fixed times from files in a directory (no CSV required)."""
    tz = ZoneInfo(ns.tz)
    db_path = ns.db_path
    con = connect(db_path)

    day = date.fromisoformat(ns.day) if ns.day else datetime.now(tz=tz).date()
    times = parse_times(ns.times)
    if not times:
        raise SystemExit("No --times provided (example: 09:00,13:00,19:00)")
    dts = fixed_times(day=day, tz=tz, times=times)

    reels = _iter_reels_dir(ns.reels_dir)
    if not reels:
        logger.error(f"No videos found in reels_dir={ns.reels_dir!r}")
        return 2

    already = {it.reel_id for it in list_for_date(con, yyyy_mm_dd=day.isoformat())}
    remaining = [(rid, p) for rid, p in reels if rid not in already]
    if len(remaining) < len(dts):
        logger.warning(
            f"Not enough unused reels: need={len(dts)}, available={len(remaining)}. Will reuse."
        )
        remaining = reels

    suffix = (ns.caption_suffix or "").strip()
    chosen = remaining[: len(dts)]
    for dt, (rid, vpath) in zip(dts, chosen):
        caption = (rid + ("\n\n" + suffix if suffix else "")).strip()
        upsert_item(
            con,
            reel_id=rid,
            scheduled_at=dt.isoformat(timespec="seconds"),
            video_path=vpath,
            caption=caption,
            status="planned",
            source="local",
            source_id="",
        )
        logger.info(f"Planned {rid} @ {dt.isoformat(timespec='minutes')}  {vpath}")
    logger.info(f"DB: {db_path}")
    return 0


def cmd_plan_dir_week(ns: argparse.Namespace) -> int:
    """Plan fixed times for multiple days from reels dir (no CSV)."""
    tz = ZoneInfo(ns.tz)
    db_path = ns.db_path
    con = connect(db_path)

    platform = (getattr(ns, "platform", None) or "instagram").strip().lower()
    if platform not in {"instagram", "youtube"}:
        raise SystemExit(f"Bad --platform={platform!r}, expected instagram|youtube")

    start_day = date.fromisoformat(ns.start_day) if ns.start_day else datetime.now(tz=tz).date()
    days = max(1, int(ns.days))
    times = parse_times(ns.times)
    if not times:
        raise SystemExit("No --times provided (example: 09:00,13:00,19:00)")

    reels = _iter_reels_dir(ns.reels_dir)
    if not reels:
        logger.error(f"No videos found in reels_dir={ns.reels_dir!r}")
        return 2

    already = list_planned_reel_ids(con, platform=platform)
    remaining = [(rid, p) for rid, p in reels if rid not in already]
    total_needed = days * len(times)
    allow_reuse = bool(getattr(ns, "allow_reuse", False))
    if not remaining:
        if allow_reuse:
            logger.warning(
                f"No fresh reels (all {len(reels)} are already used). "
                f"Cycling existing reels for {total_needed} slots (--allow-reuse)."
            )
            remaining = list(reels)
        else:
            logger.error(
                f"No fresh reels (all {len(reels)} are already used in queue). "
                "Add new videos to --reels-dir or pass --allow-reuse to cycle."
            )
            return 2
    elif len(remaining) < total_needed:
        if allow_reuse:
            logger.warning(
                f"Not enough unused reels for full range: need={total_needed}, "
                f"available={len(remaining)}. Will reuse after exhausting (--allow-reuse)."
            )
        else:
            logger.warning(
                f"Not enough unused reels for full range: need={total_needed}, "
                f"available={len(remaining)}. Strict mode: planning only what's available."
            )

    suffix = (ns.caption_suffix or "").strip()
    idx = 0
    planned = 0
    stop_all = False

    for d_off in range(days):
        if stop_all:
            break
        day = start_day + timedelta(days=d_off)
        dts = fixed_times(day=day, tz=tz, times=times)
        day_items = list_for_date(con, yyyy_mm_dd=day.isoformat(), platform=platform)
        used_slots = {it.scheduled_at for it in day_items if (it.scheduled_at or "").strip()}
        for dt in dts:
            slot_iso = dt.isoformat(timespec="seconds")
            if slot_iso in used_slots:
                logger.info(f"Skip slot already planned ({platform}): {slot_iso}")
                continue
            if idx >= len(remaining):
                if allow_reuse:
                    remaining = [(rid, p) for rid, p in reels if rid not in already] or list(reels)
                    idx = 0
                else:
                    logger.warning(
                        f"Strict mode: out of fresh reels at slot {slot_iso}; stopping early."
                    )
                    stop_all = True
                    break
            rid, vpath = remaining[idx]
            idx += 1
            already.add(rid)
            caption = (rid + ("\n\n" + suffix if suffix else "")).strip()
            if not ns.dry_run:
                upsert_item(
                    con,
                    reel_id=rid,
                    scheduled_at=slot_iso,
                    video_path=vpath,
                    caption=caption,
                    status="planned",
                    source="local",
                    source_id="",
                    platform=platform,
                )
            logger.info(f"Planned [{platform}] {rid} @ {dt.isoformat(timespec='minutes')}  {vpath}")
            planned += 1

    logger.info(f"Planned items: {planned} (platform={platform}, days={days}, slots_per_day={len(times)})")
    logger.info(f"DB: {db_path}")
    return 0


def cmd_next_due_summary(ns: argparse.Namespace) -> int:
    """Print next planned slot per platform as machine-readable lines.

    Format: PLATFORM\\tISO_DATETIME\\tREEL_ID\\tMINUTES_UNTIL
    If no upcoming row: PLATFORM\\tNONE\\t-\\t-
    """
    tz = ZoneInfo(ns.tz)
    con = connect(ns.db_path)
    now = datetime.now(tz=tz)
    for plat in ("instagram", "youtube", "pinterest"):
        row = con.execute(
            """
            SELECT reel_id, scheduled_at
              FROM upload_queue
             WHERE platform=? AND status='planned'
             ORDER BY scheduled_at ASC LIMIT 1
            """,
            (plat,),
        ).fetchone()
        if not row:
            print(f"{plat}\tNONE\t-\t-")
            continue
        sched_iso = str(row["scheduled_at"])
        try:
            dt = datetime.fromisoformat(sched_iso)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=tz)
            delta_min = int((dt - now).total_seconds() // 60)
        except Exception:
            delta_min = 0
        print(f"{plat}\t{sched_iso}\t{row['reel_id']}\t{delta_min}")
    return 0


def cmd_plan_mirror(ns: argparse.Namespace) -> int:
    """Mirror planned slots from one platform to another at different times.

    For each `planned` row of --from platform, find the corresponding row(s) on
    --to platform on the same date and at given --times (in order). Existing
    --to rows for that (reel_id, scheduled_at) are upserted.
    """
    from collections import defaultdict

    tz = ZoneInfo(ns.tz)
    con = connect(ns.db_path)
    src = (ns.from_platform or "").strip().lower()
    dst = (ns.to_platform or "").strip().lower()
    if src == dst or src not in {"instagram", "youtube"} or dst not in {"instagram", "youtube"}:
        raise SystemExit("--from and --to must be one of instagram|youtube and different")

    times = parse_times(ns.times)
    if not times:
        raise SystemExit("No --times provided (example: 11:00,16:00,22:00)")

    rows = con.execute(
        """
        SELECT reel_id, scheduled_at, video_path, caption
          FROM upload_queue
         WHERE platform=? AND status='planned'
         ORDER BY scheduled_at ASC, reel_id ASC
        """,
        (src,),
    ).fetchall()
    if not rows:
        logger.warning(f"No planned rows for platform={src!r}; nothing to mirror.")
        return 1

    by_date: dict[str, list] = defaultdict(list)
    for r in rows:
        d_str = str(r["scheduled_at"])[:10]
        by_date[d_str].append(r)

    dst_used = list_planned_reel_ids(con, platform=dst)
    planned = 0
    skipped = 0
    for d_str in sorted(by_date.keys()):
        try:
            day = date.fromisoformat(d_str)
        except ValueError:
            continue
        if ns.from_day and day < date.fromisoformat(ns.from_day):
            continue
        dts = fixed_times(day=day, tz=tz, times=times)
        day_rows = by_date[d_str]
        for i, dt in enumerate(dts):
            if i >= len(day_rows):
                break
            src_row = day_rows[i]
            rid = str(src_row["reel_id"])
            if rid in dst_used:
                logger.info(f"Skip mirror: {rid} already on {dst}")
                skipped += 1
                continue
            slot_iso = dt.isoformat(timespec="seconds")
            if not ns.dry_run:
                upsert_item(
                    con,
                    reel_id=rid,
                    scheduled_at=slot_iso,
                    video_path=str(src_row["video_path"]),
                    caption=str(src_row["caption"]),
                    status="planned",
                    source="local",
                    source_id="",
                    platform=dst,
                )
                dst_used.add(rid)
            logger.info(f"Mirrored [{dst}] {rid} @ {dt.isoformat(timespec='minutes')}")
            planned += 1

    logger.success(
        f"plan-mirror {src}->{dst}: planned={planned} skipped={skipped} (dry_run={bool(ns.dry_run)})"
    )
    return 0


def cmd_today(ns: argparse.Namespace) -> int:
    tz = ZoneInfo(ns.tz)
    con = connect(ns.db_path)
    d = ns.day or _today_str(tz)
    items = list_for_date(con, yyyy_mm_dd=d)
    if not items:
        print(f"No items planned for {d}. Run: plan")
        return 1
    for it in items:
        print(f"{it.scheduled_at}  {it.reel_id}  status={it.status}")
        print(f"video: {it.video_path}")
        print("caption:")
        print(it.caption)
        print("---")
    return 0


def cmd_daily_report(ns: argparse.Namespace) -> int:
    tz = ZoneInfo(ns.tz)
    con = connect(ns.db_path)
    day = ns.day or _today_str(tz)
    items = list_for_date(con, yyyy_mm_dd=day)

    planned = [it for it in items if it.status == "planned"]
    posted = [it for it in items if it.status == "posted"]
    other = [it for it in items if it.status not in {"planned", "posted"}]

    ig_items = [it for it in items if (it.platform or "instagram") == "instagram"]
    yt_items = [it for it in items if (it.platform or "instagram") == "youtube"]

    print(f"Daily report: {day} (tz={ns.tz})")
    print(f"total={len(items)} planned={len(planned)} posted={len(posted)} other={len(other)}")
    print(
        f"  by platform: instagram total={len(ig_items)} "
        f"posted={sum(1 for it in ig_items if it.status == 'posted')} | "
        f"youtube total={len(yt_items)} "
        f"posted={sum(1 for it in yt_items if it.status == 'posted')}"
    )
    print("---")

    for it in items:
        ig_url = f"https://www.instagram.com/reel/{it.ig_media_id}/" if it.ig_media_id else ""
        yt_url = it.yt_video_url or ""
        err = (it.last_error or "").strip()
        plat = (it.platform or "instagram").upper()
        print(f"{it.scheduled_at}  [{plat}]  {it.reel_id}  status={it.status}  attempts={it.attempts}")
        if ig_url:
            print(f"IG: {ig_url}")
        if yt_url:
            print(f"YT: {yt_url}")
        if err:
            print(f"ERR: {err}")
        print(f"video: {it.video_path}")
        print("---")
    return 0


def cmd_tick(ns: argparse.Namespace) -> int:
    tz = ZoneInfo(ns.tz)
    con = connect(ns.db_path)
    logger.info("Tick started. Press Ctrl+C to stop.")
    while True:
        now = datetime.now(tz=tz).isoformat(timespec="seconds")
        due = next_due(con, now_iso=now)
        if due is not None:
            logger.warning(
                f"NOW: post (Trial) {due.reel_id} scheduled_at={due.scheduled_at}\n"
                f"video={due.video_path}\n"
                f"caption:\n{due.caption}\n"
                "After posting in Instagram, run: mark-posted --reel-id "
                f"{due.reel_id}"
            )
            # avoid spamming; sleep longer after alert
            _time.sleep(max(10, int(ns.interval_sec)))
        else:
            _time.sleep(max(5, int(ns.interval_sec)))


def cmd_mark_posted(ns: argparse.Namespace) -> int:
    con = connect(ns.db_path)
    n = mark_status(con, reel_id=ns.reel_id, status="posted")
    if n <= 0:
        print(f"Not found: {ns.reel_id}")
        return 1
    print(f"OK: marked posted: {ns.reel_id} (rows={n})")
    return 0


def _publish_ig_fb_fanout(
    *,
    video_url: str,
    caption: str,
    max_attempts: int = 5,
) -> tuple[str, str]:
    """
    Post to all META IG accounts (+ FB pages / Threads if enabled).
    Returns primary (container_id, media_id) for queue/Notion.
    """
    from uploader.facebook_publisher import publish_all_fb_pages
    from uploader.instagram_publisher import publish_all_ig_accounts
    from uploader.threads_publisher import publish_all_threads

    ig_results = publish_all_ig_accounts(
        video_url=video_url,
        caption=caption,
        max_attempts=max_attempts,
    )
    if not ig_results:
        raise RuntimeError(
            "No Instagram publish targets (META_*_PUBLISH_IG=false or tokens missing)"
        )
    _label, container_id, media_id = ig_results[0]
    if len(ig_results) > 1:
        logger.info(
            "[IG] fanout ok: "
            + ", ".join(f"{a}:{mid}" for a, _c, mid in ig_results)
        )
    try:
        fb_results = publish_all_fb_pages(video_url=video_url, caption=caption)
        if fb_results:
            logger.info(
                "[FB] fanout ok: "
                + ", ".join(f"{r.account}:{r.video_id}" for r in fb_results)
            )
    except Exception:
        logger.exception("[FB] fanout failed (IG already posted)")
    # Reels → Threads duplicates the same video on another feed (looks like double-post).
    # Carousels keep their own CAROUSEL_PUBLISH_THREADS path.
    reels_threads = (_env("REELS_PUBLISH_THREADS", "0") or "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not reels_threads:
        logger.info("[Threads] skipped for reels (REELS_PUBLISH_THREADS=0)")
    else:
        try:
            th_results = publish_all_threads(video_url=video_url, caption=caption)
            if th_results:
                logger.info(
                    "[Threads] fanout ok: "
                    + ", ".join(f"{r.account}:{r.post_id}" for r in th_results)
                )
            else:
                logger.info("[Threads] skipped (no META_N_PUBLISH_THREADS targets)")
        except Exception:
            logger.exception("[Threads] fanout failed (IG already posted)")
    return container_id, media_id


def cmd_crosspost(ns: argparse.Namespace) -> int:
    """
    Publish the same video to Instagram + YouTube and write platform-specific columns in Notion.
    """
    from uploader.instagram_publisher import ensure_video_url
    from uploader.notion_report import load_notion_report_config, upsert_report_page
    from uploader.r2_storage import (
        build_object_key,
        delete_by_key,
        delete_keys,
        load_r2_config,
        public_url_exists,
        upload_file_public,
    )
    from uploader.youtube_publisher import publish_youtube_short

    tz = ZoneInfo(ns.tz)
    con = connect(ns.db_path)
    notion_cfg = load_notion_report_config()

    # Resolve a single item.
    day = ns.day or _today_str(tz)
    items = list_for_date(con, yyyy_mm_dd=day)
    item = None
    for it in items:
        if it.reel_id == ns.reel_id:
            item = it
            break
    if item is None:
        raise SystemExit(f"Not found in queue for {day}: {ns.reel_id}")

    video_path = item.video_path
    if not video_path:
        raise SystemExit("Item has empty video_path")

    ig_caption = _instagram_caption_for_publish(con, item)

    # 1) Instagram publish via R2
    r2 = load_r2_config()
    key = item.r2_key or build_object_key(cfg=r2, reel_id=item.reel_id, video_path=video_path)
    video_url = item.video_url
    if not video_url or not public_url_exists(video_url):
        video_url = upload_file_public(cfg=r2, key=key, file_path=video_path)
        set_r2_key_and_url(
            con,
            reel_id=item.reel_id,
            scheduled_at=item.scheduled_at,
            r2_key=key,
            video_url=video_url,
        )

    if notion_cfg is not None:
        upsert_report_page(
            cfg=notion_cfg,
            reel_id=item.reel_id,
            scheduled_at_iso=item.scheduled_at,
            caption=ig_caption,
            tags_text="",
            privacy="",
            r2_key=key,
            r2_url=video_url,
            status_name=notion_cfg.status_publishing,
            error_text="",
            attempts=1,
            source_page_id=item.source_id if item.source == "notion" else "",
            platform="Instagram",
        )
    container_id, media_id = _publish_ig_fb_fanout(
        video_url=video_url, caption=ig_caption, max_attempts=5
    )
    ig_url = f"https://www.instagram.com/reel/{media_id}/"

    record_attempt(
        con,
        reel_id=item.reel_id,
        scheduled_at=item.scheduled_at,
        ig_container_id=container_id,
        ig_media_id=media_id,
        status="posted",
        last_api_response=f'{{"container_id":"{container_id}","media_id":"{media_id}"}}',
        last_error="",
    )

    if notion_cfg is not None:
        upsert_report_page(
            cfg=notion_cfg,
            reel_id=item.reel_id,
            scheduled_at_iso=item.scheduled_at,
            caption=ig_caption,
            title="",
            tags_text="",
            privacy="",
            r2_key=key,
            r2_url=video_url,
            post_id=media_id,
            post_url=ig_url,
            container_id=container_id,
            attempts=1,
            last_api_response=f'{{"container_id":"{container_id}","media_id":"{media_id}"}}',
            status_name=notion_cfg.status_posted,
            error_text="",
            source_page_id=item.source_id if item.source == "notion" else "",
            platform="Instagram",
        )

    if ns.r2_delete_after_post:
        delete_by_key(cfg=r2, key=key)

    # 2) YouTube publish with auto metadata
    yt = publish_youtube_short(video_path=Path(video_path), privacy_status=ns.yt_privacy)
    yt_tags = ", ".join(yt.tags)
    yt_hashtags = " ".join(yt.hashtags)

    if notion_cfg is not None:
        upsert_report_page(
            cfg=notion_cfg,
            reel_id=item.reel_id,
            scheduled_at_iso=item.scheduled_at,
            caption=yt.description,
            title=yt.title,
            tags_text=(yt_hashtags or yt_tags).strip(),
            privacy=ns.yt_privacy,
            r2_key="",
            r2_url="",
            post_id=yt.video_id,
            post_url=yt.video_url,
            container_id="",
            attempts=1,
            last_api_response=f'{{"video_id":"{yt.video_id}"}}',
            status_name=notion_cfg.status_posted,
            error_text="",
            source_page_id="",
            platform="YouTube Shorts",
        )

    print(f"OK crossposted {item.reel_id}\nIG: {ig_url}\nYT: {yt.video_url}")
    return 0


def cmd_sync_notion(ns: argparse.Namespace) -> int:
    from uploader.notion_sync import sync_ready_posts

    tz = ZoneInfo(ns.tz)
    sync_ready_posts(db_path=ns.db_path, tz=tz)
    return 0


def cmd_rebuild_texts(ns: argparse.Namespace) -> int:
    from uploader.schedule_crosspost import filter_reels_from_dir
    from uploader.text_assign import assign_fresh_text_ids, rebuild_post_texts

    reels_dir = Path(ns.reels_dir).expanduser().resolve()
    texts_path = Path(ns.texts).expanduser().resolve()
    post_dir = Path(ns.post_texts_dir).expanduser().resolve()
    min_num = int(ns.min_reel_num) if ns.min_reel_num else None
    reels = filter_reels_from_dir(reels_dir, min_num=min_num)
    from uploader.db import connect, is_posted_on_platform

    con = connect(ns.db_path)
    reel_ids = [
        r
        for r, _ in reels
        if not is_posted_on_platform(con, reel_id=r, platform="instagram")
    ]
    if not reel_ids:
        logger.info("All reels already posted on IG; nothing to rebuild.")
        return 0
    mapping = assign_fresh_text_ids(reel_ids, texts_csv=texts_path, db_path=ns.db_path)
    rebuild_post_texts(
        mapping,
        texts_csv=texts_path,
        post_texts_dir=post_dir,
        caption_suffix=ns.caption_suffix or _env("CAPTION_SUFFIX"),
    )
    # Persist mapping for ingest/resolve
    out = Path(ns.output_root).expanduser() / "reels_plan_auto_ingest.csv"
    lines = ["reel_id;text_id;source\n"]
    for rid, tid in sorted(mapping.items()):
        lines.append(f"{rid};{tid};fresh_assign\n")
    out.write_text("".join(lines), encoding="utf-8")
    logger.success(f"Wrote {out}")
    return 0


def cmd_sync_notion_schedule(ns: argparse.Namespace) -> int:
    from uploader.notion_schedule_sync import sync_notion_from_queue

    audio_dir = Path(_env("AUDIO_DIR", "output/audio")).expanduser()
    raw_min = (getattr(ns, "min_reel_num", None) or "").strip()
    min_num = int(raw_min) if raw_min.isdigit() else None
    prefixes_raw = (getattr(ns, "reel_prefixes", None) or "").strip()
    prefixes = [p.strip() for p in prefixes_raw.split(",") if p.strip()] if prefixes_raw else None
    sync_notion_from_queue(
        db_path=ns.db_path,
        texts_csv=Path(_env("UPLOAD_TEXTS_CSV", "texts_kailas.csv")).expanduser(),
        post_texts_dir=Path(ns.post_texts_dir).expanduser(),
        audio_dir=audio_dir,
        yt_preview=bool(ns.yt_preview),
        status_name=ns.notion_status or _env("INGEST_NOTION_STATUS", "Готов к публикации"),
        reel_id_min=min_num,
        reel_prefixes=prefixes,
    )
    return 0


def _maybe_watch_reels(*, tz_name: str) -> None:
    interval = int(_env("AUTOPOST_WATCH_INTERVAL_SEC", "0") or "0")
    if interval <= 0:
        return
    if not hasattr(_maybe_watch_reels, "_last_ts"):
        _maybe_watch_reels._last_ts = 0.0  # type: ignore[attr-defined]
    now_ts = _time.time()
    if now_ts - _maybe_watch_reels._last_ts < interval:  # type: ignore[attr-defined]
        return
    _maybe_watch_reels._last_ts = now_ts  # type: ignore[attr-defined]
    from uploader.watch_reels import process_new_reels_once

    try:
        process_new_reels_once(
            tz_name=tz_name,
            reels_dir=_env("READY_DIR", "output/reels"),
            texts_csv=_env("UPLOAD_TEXTS_CSV", "texts_kailas.csv"),
            post_texts_dir=_env("INGEST_POST_TEXTS_DIR", "output/post_texts"),
            output_root="output",
            db_path=_env("UPLOAD_DB_PATH", "output/upload_queue.sqlite3"),
        )
    except Exception:
        logger.exception("[watch] ingest/schedule tick failed")


def _maybe_carousel_tick(*, tz_name: str, db_path: str) -> None:
    """Sync Notion C-* ready carousels and publish due ones (META_2 IG + Threads)."""
    if not _env("CAROUSEL_AUTOPOST", "1") or _env("CAROUSEL_AUTOPOST", "1").lower() in {
        "0",
        "false",
        "no",
        "off",
    }:
        return
    interval = int(_env("CAROUSEL_TICK_INTERVAL_SEC", "120") or "120")
    if interval <= 0:
        return
    if not hasattr(_maybe_carousel_tick, "_last_ts"):
        _maybe_carousel_tick._last_ts = 0.0  # type: ignore[attr-defined]
    now_ts = _time.time()
    if now_ts - _maybe_carousel_tick._last_ts < interval:  # type: ignore[attr-defined]
        return
    _maybe_carousel_tick._last_ts = now_ts  # type: ignore[attr-defined]
    from uploader.carousel_autopost import carousel_tick

    try:
        carousel_tick(db_path=db_path, tz_name=tz_name)
    except Exception:
        logger.exception("[carousel] tick failed")


def cmd_watch_reels(ns: argparse.Namespace) -> int:
    from uploader.watch_reels import process_new_reels_once

    return process_new_reels_once(
        tz_name=ns.tz,
        reels_dir=ns.reels_dir,
        texts_csv=ns.texts,
        post_texts_dir=ns.post_texts_dir,
        output_root=ns.output_root,
        db_path=ns.db_path,
        dry_run=bool(getattr(ns, "dry_run", False)),
    )


def cmd_sync_carousels(ns: argparse.Namespace) -> int:
    from uploader.carousel_autopost import sync_ready_carousels

    tz = ZoneInfo(ns.tz)
    n = sync_ready_carousels(db_path=ns.db_path, tz=tz)
    print(f"Synced carousels: {n}")
    return 0


def cmd_publish_carousel_due(ns: argparse.Namespace) -> int:
    from uploader.carousel_autopost import publish_due_carousel

    tz = ZoneInfo(ns.tz)
    ok = publish_due_carousel(db_path=ns.db_path, tz=tz)
    print("Published" if ok else "Nothing due / failed")
    return 0 if ok else 1


def cmd_republish_carousel(ns: argparse.Namespace) -> int:
    import json
    from pathlib import Path

    from uploader.carousel_autopost import publish_due_carousel, requeue_carousel

    export_path = Path(ns.export_json)
    items = json.loads(export_path.read_text(encoding="utf-8"))
    item = next((i for i in items if i.get("carousel_id") == ns.carousel_id), None)
    if not item:
        item = items[0] if len(items) == 1 else None
    if not item:
        print(f"Carousel {ns.carousel_id!r} not found in {export_path}")
        return 1
    carousel_id = str(item.get("carousel_id") or ns.carousel_id)
    slides = [s["url"] for s in (item.get("r2_slides") or []) if s.get("url")]
    manifest_dir = Path(str(item.get("carousel_output_dir") or ""))
    if not manifest_dir.is_absolute():
        manifest_dir = Path("/home/tovgrishkoff/content_engine") / manifest_dir
    caption = ""
    cap_path = manifest_dir / "caption.txt"
    if cap_path.is_file():
        caption = cap_path.read_text(encoding="utf-8")
    elif (manifest_dir / "manifest.json").is_file():
        data = json.loads((manifest_dir / "manifest.json").read_text(encoding="utf-8"))
        caption = str(data.get("caption") or "")
    scheduled = requeue_carousel(
        db_path=ns.db_path,
        carousel_id=carousel_id,
        slides=slides,
        caption=caption,
        article_url=str(item.get("article_url") or ""),
        title=str(item.get("title") or carousel_id),
        source_id=str(item.get("notion_page_id") or ""),
        publish_now=ns.publish_now,
        tz_name=ns.tz,
    )
    print(f"Requeued {carousel_id} at {scheduled}")
    if ns.publish_now:
        tz = ZoneInfo(ns.tz)
        ok = publish_due_carousel(db_path=ns.db_path, tz=tz)
        print("Published to IG" if ok else "Publish failed or nothing due")
        return 0 if ok else 1
    return 0


def cmd_schedule_crosspost(ns: argparse.Namespace) -> int:
    from uploader.schedule_crosspost import (
        delete_planned_for_reels,
        filter_reels_from_dir,
        schedule_crosspost_batch,
    )

    tz = ZoneInfo(ns.tz)
    reels_dir = Path(ns.reels_dir).expanduser().resolve()
    post_dir = Path(ns.post_texts_dir).expanduser().resolve()
    start_day = date.fromisoformat(ns.start_day) if ns.start_day else datetime.now(tz=tz).date()

    min_num = int(ns.min_reel_num) if ns.min_reel_num else None
    reels = filter_reels_from_dir(reels_dir, min_num=min_num)
    if ns.reel_id and ns.reel_id.upper() != "ALL":
        want = {x.strip().upper() for x in ns.reel_id.split(",")}
        reels = [(r, p) for r, p in reels if r in want]
    if not reels:
        logger.error("No reels to schedule.")
        return 2

    reel_ids = [r for r, _ in reels]
    con = connect(ns.db_path)
    clear = bool(ns.clear_planned) and not bool(getattr(ns, "no_clear_planned", False))
    if clear:
        n = delete_planned_for_reels(con, reel_ids)
        logger.info(f"Cleared {n} planned row(s) for {len(reel_ids)} reel(s)")

    random_slots = _cli_bool(
        flag_on=bool(getattr(ns, "random_slots", False)),
        flag_off=bool(getattr(ns, "no_random_slots", False)),
        env_name="UPLOAD_RANDOM_SLOTS",
        default=False,
    )
    schedule_crosspost_batch(
        db_path=ns.db_path,
        reels=reels,
        post_texts_dir=post_dir,
        tz=tz,
        start_day=start_day,
        ig_times_spec=ns.ig_times,
        yt_times_spec=ns.yt_times,
        pinterest_times_spec=getattr(ns, "pinterest_times", "") or "",
        dry_run=bool(ns.dry_run),
        random_slots=random_slots,
    )
    return 0


def cmd_autopost_pinterest(ns: argparse.Namespace) -> int:
    """Auto-publish Pinterest-platform queue items as video pins."""
    pin_on = (os.environ.get("UPLOAD_PINTEREST") or "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not pin_on:
        logger.warning(
            "Autopost [pinterest] refused: UPLOAD_PINTEREST=0 "
            "(no API yet). Set UPLOAD_PINTEREST=1 + tokens to enable."
        )
        return 1

    from uploader.notion_report import load_notion_report_config, upsert_report_page
    from uploader.pinterest_publisher import publish_with_retries

    tz = ZoneInfo(ns.tz)
    con = connect(ns.db_path)
    notion_cfg = load_notion_report_config()
    local_delete = bool(int((os.environ.get("LOCAL_DELETE_AFTER_POST") or "0").strip() or "0"))
    max_attempts = max(1, int(getattr(ns, "max_attempts", 3) or 3))

    logger.info("Autopost [pinterest] started. Press Ctrl+C to stop.")
    while True:
        now = datetime.now(tz=tz).isoformat(timespec="seconds")
        _release_held_media(con, platform="pinterest")
        due = next_due(con, now_iso=now, platform="pinterest")
        if due is None:
            _time.sleep(max(5, int(ns.interval_sec)))
            continue

        try:
            gate, ready_path = _park_until_ready(con, due)
            if gate == "parked":
                alert_autopost_fail(
                    platform="Pinterest",
                    reel_id=due.reel_id,
                    scheduled_at=due.scheduled_at,
                    error=due.last_error or "file missing",
                )
                continue
            if gate == "ready" and ready_path is not None:
                due = UploadItem(**{**due.__dict__, "video_path": str(ready_path)})
            due = _attach_feed_mp4(con, due)

            caption = _instagram_caption_for_publish(con, due)

            if notion_cfg is not None:
                try:
                    upsert_report_page(
                        cfg=notion_cfg,
                        reel_id=due.reel_id,
                        scheduled_at_iso=due.scheduled_at,
                        caption=caption,
                        status_name=notion_cfg.status_publishing,
                        error_text="",
                        attempts=1,
                        source_page_id=due.source_id if due.source == "notion" else "",
                        platform="Pinterest",
                    )
                except Exception:
                    logger.exception(f"Notion report failed (Pinterest publishing) for {due.reel_id}")

            pin = publish_with_retries(
                video_path=Path(due.video_path),
                caption=caption,
                reel_id=due.reel_id,
                max_attempts=max_attempts,
            )

            record_attempt(
                con,
                reel_id=due.reel_id,
                scheduled_at=due.scheduled_at,
                yt_video_id=pin.pin_id,
                yt_video_url=pin.pin_url,
                status="posted",
                last_api_response=f'{{"pin_id":"{pin.pin_id}"}}',
                last_error="",
            )

            if notion_cfg is not None:
                try:
                    upsert_report_page(
                        cfg=notion_cfg,
                        reel_id=due.reel_id,
                        scheduled_at_iso=due.scheduled_at,
                        caption=pin.description,
                        title=pin.title,
                        tags_text="",
                        post_id=pin.pin_id,
                        post_url=pin.pin_url,
                        attempts=1,
                        last_api_response=f'{{"pin_id":"{pin.pin_id}"}}',
                        status_name=notion_cfg.status_posted,
                        error_text="",
                        source_page_id=due.source_id if due.source == "notion" else "",
                        platform="Pinterest",
                    )
                except Exception:
                    logger.exception(f"Notion report failed (Pinterest posted) for {due.reel_id}")

            if local_delete:
                try:
                    _safe_delete_local_video(due.video_path)
                except Exception:
                    logger.exception(f"Local delete failed for {due.reel_id}")

        except Exception as e:
            if isinstance(e, FileNotFoundError):
                record_attempt(
                    con,
                    reel_id=due.reel_id,
                    scheduled_at=due.scheduled_at,
                    status="hold",
                    last_error=f"file missing: {e}",
                )
                logger.error(
                    f"Hold missing video for Pinterest {due.reel_id} "
                    f"scheduled_at={due.scheduled_at}: {e}"
                )
                alert_autopost_fail(
                    platform="Pinterest",
                    reel_id=due.reel_id,
                    scheduled_at=due.scheduled_at,
                    error=f"file missing: {e}",
                )
                continue
            logger.exception(
                f"Pinterest autopost failed for {due.reel_id} scheduled_at={due.scheduled_at}"
            )
            alert_autopost_fail(
                platform="Pinterest",
                reel_id=due.reel_id,
                scheduled_at=due.scheduled_at,
                error=f"{type(e).__name__}: {e}",
            )
            if notion_cfg is not None:
                try:
                    upsert_report_page(
                        cfg=notion_cfg,
                        reel_id=due.reel_id,
                        scheduled_at_iso=due.scheduled_at,
                        caption=due.caption,
                        status_name=notion_cfg.status_error,
                        error_text=f"{type(e).__name__}: {e}"[:500],
                        source_page_id=due.source_id if due.source == "notion" else "",
                        platform="Pinterest",
                    )
                except Exception:
                    pass
            _time.sleep(max(10, int(ns.interval_sec)))


def cmd_pinterest_boards(ns: argparse.Namespace) -> int:
    """List Pinterest boards (use id for PINTEREST_BOARD_ID in .env)."""
    from uploader.pinterest_publisher import PinterestPublishError, list_boards, load_pinterest_config

    try:
        cfg = load_pinterest_config()
        logger.info(f"Pinterest API: {cfg.api_base}")
        boards = list_boards()
    except PinterestPublishError as e:
        logger.error(f"{e}")
        return 1
    if not boards:
        logger.warning("No boards returned. Check token scopes (boards:read) and sandbox URL.")
        return 2
    for b in boards:
        print(f"{b['id']}\t{b['name']}")
    logger.success(f"Found {len(boards)} board(s). Set PINTEREST_BOARD_ID to one of the ids above.")
    return 0


def cmd_pinterest_oauth_url(ns: argparse.Namespace) -> int:
    """Print Pinterest OAuth URL (request pins:write — not in Trial test-token UI)."""
    from uploader.pinterest_oauth import build_authorize_url, load_oauth_settings

    client_id, _, redirect_uri = load_oauth_settings()
    scopes = (getattr(ns, "scopes", None) or "").strip() or None
    url = build_authorize_url(
        client_id=client_id,
        redirect_uri=redirect_uri,
        scopes=scopes or "boards:read,boards:write,pins:read,pins:write,user_accounts:read",
    )
    print(url)
    logger.info(
        "1) Add this exact redirect URI in Pinterest app → URI перенаправления:\n"
        f"   {redirect_uri}\n"
        "2) Open the URL above in a browser, approve access.\n"
        "3) Copy ?code=... from the redirect URL.\n"
        "4) Run: python -m uploader.main pinterest-oauth-token --code YOUR_CODE"
    )
    return 0


def cmd_pinterest_oauth_token(ns: argparse.Namespace) -> int:
    """Exchange OAuth code for access_token (+ refresh_token)."""
    from uploader.pinterest_oauth import exchange_code_for_tokens, load_oauth_settings, save_tokens_json

    code = (getattr(ns, "code", None) or "").strip()
    if not code:
        logger.error("Pass --code from the redirect URL (?code=...)")
        return 2
    client_id, client_secret, redirect_uri = load_oauth_settings()
    payload = exchange_code_for_tokens(
        client_id=client_id,
        client_secret=client_secret,
        code=code,
        redirect_uri=redirect_uri,
    )
    out_path = getattr(ns, "token_file", None) or _env(
        "PINTEREST_TOKEN_FILE", "output/pinterest_oauth.json"
    )
    save_tokens_json(out_path, payload)
    access = str(payload.get("access_token") or "")
    refresh = str(payload.get("refresh_token") or "")
    scope = str(payload.get("scope") or "")
    print(f"PINTEREST_ACCESS_TOKEN={access}")
    if refresh:
        print(f"PINTEREST_REFRESH_TOKEN={refresh}")
    print(f"# scopes: {scope}")
    logger.success(
        "Paste PINTEREST_ACCESS_TOKEN into .env, restart pinterest-autopost. "
        "Keep PINTEREST_REFRESH_TOKEN for future auto-refresh."
    )
    return 0


def cmd_pinterest_oauth(ns: argparse.Namespace) -> int:
    """Interactive Pinterest OAuth (local redirect server or manual paste)."""
    from uploader.pinterest_oauth import run_oauth_interactive, run_oauth_manual

    token_file = getattr(ns, "token_file", None) or _env(
        "PINTEREST_TOKEN_FILE", "output/pinterest_oauth.json"
    )
    scopes = (getattr(ns, "scopes", None) or "").strip() or None
    use_manual = bool(getattr(ns, "manual", False))

    try:
        if use_manual:
            run_oauth_manual(token_file=token_file, scopes=scopes or "")
        else:
            port = int(getattr(ns, "port", None) or _env("PINTEREST_OAUTH_PORT", "8765") or "8765")
            bind_addr = (getattr(ns, "bind", None) or _env("PINTEREST_OAUTH_BIND", "127.0.0.1")).strip()
            run_oauth_interactive(
                port=port,
                bind_addr=bind_addr,
                token_file=token_file,
                scopes=scopes or "",
            )
    except KeyboardInterrupt:
        logger.warning("Pinterest OAuth cancelled")
        return 130
    except Exception as e:
        logger.exception(f"Pinterest OAuth failed: {e}")
        return 1

    logger.success(
        "Paste PINTEREST_ACCESS_TOKEN into .env, restart pinterest-autopost. "
        "Then run: python -m uploader.main pinterest-status"
    )
    return 0


def cmd_pinterest_refresh(ns: argparse.Namespace) -> int:
    """Refresh expired PINTEREST_ACCESS_TOKEN via refresh_token; sync .env + token file."""
    from uploader.pinterest_oauth import ensure_fresh_access_token

    token_file = getattr(ns, "token_file", None) or _env(
        "PINTEREST_TOKEN_FILE", "output/pinterest_oauth.json"
    )
    env_path = getattr(ns, "env_file", None) or _env("PINTEREST_ENV_FILE", ".env")
    force = bool(getattr(ns, "force", False))
    try:
        payload = ensure_fresh_access_token(
            token_file=token_file,
            env_path=env_path,
            force=force,
        )
    except Exception as e:
        logger.exception(f"Pinterest token refresh failed: {e}")
        return 1
    access = str(payload.get("access_token") or "")
    print(f"PINTEREST_ACCESS_TOKEN={access}")
    if payload.get("refresh_token"):
        print("PINTEREST_REFRESH_TOKEN=(updated in .env / token file)")
    print(f"# expires_in={payload.get('expires_in')} saved_at={payload.get('saved_at')}")
    logger.success("Restart pinterest-autopost to pick up the new token from .env")
    return 0


def cmd_pinterest_status(ns: argparse.Namespace) -> int:
    """Show Pinterest API integration status (for demo / debugging)."""
    from uploader.pinterest_oauth import (
        _resolve_api_base,
        ensure_fresh_access_token,
        fetch_user_account,
        load_oauth_settings,
    )
    from uploader.pinterest_publisher import PinterestPublishError, list_boards, load_pinterest_config

    print("\n=== Pinterest integration (Jay-Shambo APP) ===\n")
    try:
        client_id, _, redirect_uri = load_oauth_settings()
        print(f"App ID:        {client_id}")
        print(f"Redirect URI:  {redirect_uri}")
    except ValueError as e:
        print(f"App config:    missing ({e})")
        return 2

    try:
        ensure_fresh_access_token(force=bool(getattr(ns, "refresh", False)))
    except Exception as e:
        logger.warning(f"token refresh: {e}")

    token = _env("PINTEREST_ACCESS_TOKEN")
    board_id = _env("PINTEREST_BOARD_ID")
    api_base = _resolve_api_base()
    print(f"API base:      {api_base}")
    print(f"Access token:  {'set' if token else 'NOT SET — run pinterest-oauth'}")
    print(f"Target board:  {board_id or 'NOT SET'}")

    if not token:
        print("\nNext: ./scripts/pinterest_oauth.sh oauth")
        return 2

    try:
        account = fetch_user_account(access_token=token, api_base=api_base)
        username = str(account.get("username") or "").strip()
        account_type = str(account.get("account_type") or "").strip()
        print(f"\nConnected as:  @{username or '?'} ({account_type or 'account'})")
    except Exception as e:
        logger.warning(f"user_account call failed: {e}")

    try:
        boards = list_boards()
        print(f"\nBoards via API ({len(boards)}):")
        for b in boards[:10]:
            marker = "  ← target" if board_id and b["id"] == board_id else ""
            print(f"  {b['id']}\t{b['name']}{marker}")
        if len(boards) > 10:
            print(f"  ... and {len(boards) - 10} more")
    except PinterestPublishError as e:
        logger.warning(f"list boards failed: {e}")
    except ValueError as e:
        logger.warning(f"boards skipped: {e}")

    try:
        cfg = load_pinterest_config()
        print(
            f"\nAutopost ready: board={cfg.board_id} "
            f"link={cfg.default_link or '(none)'} sandbox={cfg.api_base.endswith('sandbox.pinterest.com')}"
        )
    except ValueError as e:
        print(f"\nAutopost:      not configured ({e})")

    print("\nDemo checklist: OAuth done → boards listed → pinterest-autopost container running")
    return 0


def cmd_ingest_reels(ns: argparse.Namespace) -> int:
    from uploader.ingest_reels import ingest_new_reels

    reel_ids: list[str] | None = None
    raw = (getattr(ns, "reel_id", None) or "").strip()
    if raw and raw.upper() != "ALL":
        reel_ids = [x.strip() for x in raw.split(",") if x.strip()]

    return ingest_new_reels(
        reels_dir=ns.reels_dir,
        texts_csv=ns.texts,
        plan=getattr(ns, "plan", "") or "",
        plan_glob=getattr(ns, "plan_glob", "") or "",
        post_texts_dir=ns.post_texts_dir,
        output_root=ns.output_root,
        tz_name=ns.tz,
        reel_ids=reel_ids,
        force=bool(getattr(ns, "force", False)),
        dry_run=bool(getattr(ns, "dry_run", False)),
        yt_preview=_cli_bool(
            flag_on=bool(ns.yt_preview),
            flag_off=bool(getattr(ns, "no_yt_preview", False)),
            env_name="INGEST_YT_PREVIEW",
            default=False,
        ),
        notion_prefill=_cli_bool(
            flag_on=bool(ns.notion_prefill),
            flag_off=bool(getattr(ns, "no_notion_prefill", False)),
            env_name="INGEST_NOTION_PREFILL",
            default=True,
        ),
        auto_plan_ig=_cli_bool(
            flag_on=bool(ns.auto_plan_ig),
            flag_off=bool(getattr(ns, "no_auto_plan_ig", False)),
            env_name="INGEST_AUTO_PLAN_IG",
            default=False,
        ),
        auto_plan_yt=_cli_bool(
            flag_on=bool(ns.auto_plan_yt),
            flag_off=bool(getattr(ns, "no_auto_plan_yt", False)),
            env_name="INGEST_AUTO_PLAN_YT",
            default=False,
        ),
        ig_times=getattr(ns, "ig_times", "") or "",
        yt_times=getattr(ns, "yt_times", "") or "",
        plan_day=getattr(ns, "plan_day", "") or "",
        notion_status=getattr(ns, "notion_status", "") or "",
    )


def cmd_upload_r2(ns: argparse.Namespace) -> int:
    from uploader.notion_report import load_notion_report_config, upsert_report_page
    from uploader.r2_storage import build_object_key, load_r2_config, upload_file_public

    tz = ZoneInfo(ns.tz)
    con = connect(ns.db_path)
    day = ns.day or _today_str(tz)
    items = list_for_date(con, yyyy_mm_dd=day)
    if not items:
        print(f"No items planned for {day}.")
        return 1

    cfg = load_r2_config()
    notion_cfg = load_notion_report_config()
    updated = 0
    for it in items:
        if it.status != "planned":
            continue
        if it.video_url:
            continue
        if not it.video_path:
            continue
        key = build_object_key(cfg=cfg, reel_id=it.reel_id, video_path=it.video_path)
        url = upload_file_public(cfg=cfg, key=key, file_path=it.video_path)
        set_r2_key_and_url(con, reel_id=it.reel_id, scheduled_at=it.scheduled_at, r2_key=key, video_url=url)
        if notion_cfg is not None:
            try:
                page_id, _page_url = upsert_report_page(
                    cfg=notion_cfg,
                    reel_id=it.reel_id,
                    scheduled_at_iso=it.scheduled_at,
                    caption=it.caption,
                    r2_key=key,
                    r2_url=url,
                    status_name=notion_cfg.status_uploaded,
                    error_text="",
                    source_page_id=it.source_id if it.source == "notion" else "",
                    platform="Instagram",
                )
                if it.source != "notion" and not it.source_id and page_id:
                    set_source_id(
                        con,
                        reel_id=it.reel_id,
                        scheduled_at=it.scheduled_at,
                        source="notion",
                        source_id=page_id,
                    )
            except Exception:
                logger.exception(f"Notion report failed (upload-r2) for {it.reel_id}")
        updated += 1
    logger.success(f"R2: updated video_url for items: {updated}")
    return 0


def _attach_feed_mp4(con, due: UploadItem) -> UploadItem:
    """Swap a planned row onto the H.264 1080x1920 file used by IG, YouTube and Pinterest."""
    from uploader.publish_media import ensure_feed_mp4

    src = Path(due.video_path)
    ready = ensure_feed_mp4(src, reel_id=due.reel_id)
    if ready.resolve() == src.resolve():
        return due
    set_video_path(
        con,
        reel_id=due.reel_id,
        scheduled_at=due.scheduled_at,
        video_path=str(ready),
    )
    if (due.video_url or "").strip() or (due.r2_key or "").strip():
        set_r2_key_and_url(
            con,
            reel_id=due.reel_id,
            scheduled_at=due.scheduled_at,
            r2_key="",
            video_url="",
        )
    logger.info(f"[media] {due.reel_id} publish file {ready.name}")
    return UploadItem(
        **{**due.__dict__, "video_path": str(ready), "video_url": "", "r2_key": ""}
    )


def cmd_autopost(ns: argparse.Namespace) -> int:
    from uploader.instagram_publisher import ensure_video_url, load_instagram_configs
    from uploader.notion_report import load_notion_report_config, upsert_report_page
    from uploader.r2_storage import (
        build_object_key,
        delete_by_key,
        delete_keys,
        load_r2_config,
        public_url_size,
        upload_file_public,
    )

    tz = ZoneInfo(ns.tz)
    con = connect(ns.db_path)
    cfgs = load_instagram_configs()
    notion_cfg = load_notion_report_config()
    if not cfgs:
        logger.error(
            "Autopost [instagram] IDLE — no IG targets. "
            "Refresh META_1/2_PAGE_TOKEN, set META_*_PUBLISH_IG=true, recreate container."
        )
    else:
        logger.info(
            "Autopost [instagram] started accounts="
            + ",".join(c.account_label for c in cfgs)
            + ". Press Ctrl+C to stop."
        )
    while True:
        _maybe_watch_reels(tz_name=ns.tz)
        _maybe_carousel_tick(tz_name=ns.tz, db_path=ns.db_path)
        if not cfgs:
            # Re-read env each idle tick in case tokens were hot-fixed without recreate
            # (compose mounts .env at start — still need recreate; keep quiet sleep).
            _time.sleep(max(30, int(ns.interval_sec)))
            continue
        now = datetime.now(tz=tz).isoformat(timespec="seconds")
        _hold_interrupted_publishes(con, platform="instagram")
        _release_held_media(con, platform="instagram")
        due = next_due(con, now_iso=now, platform="instagram")
        if due is None:
            _time.sleep(max(5, int(ns.interval_sec)))
            continue

        ig_caption = ""
        try:
            gate, ready_path = _park_until_ready(con, due)
            if gate == "parked":
                continue
            if gate == "ready" and ready_path is not None:
                due = UploadItem(**{**due.__dict__, "video_path": str(ready_path)})
                due = _attach_feed_mp4(con, due)
                ready_path = Path(due.video_path)
                remote = public_url_size(due.video_url) if due.video_url else None
                local_size = ready_path.stat().st_size
                if remote is not None and remote != local_size:
                    logger.warning(
                        f"[media] {due.reel_id} public file {remote}B "
                        f"!= local {local_size}B, uploading the finished file"
                    )
                    set_r2_key_and_url(
                        con,
                        reel_id=due.reel_id,
                        scheduled_at=due.scheduled_at,
                        r2_key="",
                        video_url="",
                    )
                    due = UploadItem(**{**due.__dict__, "video_url": "", "r2_key": ""})

            ig_caption = _instagram_caption_for_publish(con, due)
            video_url = due.video_url
            if not video_url and due.video_path and ns.r2_autoupload:
                r2 = load_r2_config()
                key = build_object_key(cfg=r2, reel_id=due.reel_id, video_path=due.video_path)
                video_url = upload_file_public(cfg=r2, key=key, file_path=due.video_path)
                set_r2_key_and_url(
                    con,
                    reel_id=due.reel_id,
                    scheduled_at=due.scheduled_at,
                    r2_key=key,
                    video_url=video_url,
                )
                if notion_cfg is not None:
                    try:
                        page_id, _page_url = upsert_report_page(
                            cfg=notion_cfg,
                            reel_id=due.reel_id,
                            scheduled_at_iso=due.scheduled_at,
                            caption=ig_caption,
                            r2_key=key,
                            r2_url=video_url,
                            status_name=notion_cfg.status_uploaded,
                            error_text="",
                            source_page_id=due.source_id if due.source == "notion" else "",
                            platform="Instagram",
                        )
                    except Exception:
                        logger.exception(f"Notion report failed (r2 autoupload) for {due.reel_id}")
                    else:
                        if due.source != "notion" and not due.source_id and page_id:
                            set_source_id(
                                con,
                                reel_id=due.reel_id,
                                scheduled_at=due.scheduled_at,
                                source="notion",
                                source_id=page_id,
                            )
            # Enter "publishing" state in Notion (re-entry-safe).
            if notion_cfg is not None:
                try:
                    page_id, _page_url = upsert_report_page(
                        cfg=notion_cfg,
                        reel_id=due.reel_id,
                        scheduled_at_iso=due.scheduled_at,
                        caption=ig_caption,
                        r2_key=due.r2_key,
                        r2_url=video_url,
                        status_name=notion_cfg.status_publishing,
                        error_text="",  # clear
                        attempts=1,  # increment in upsert
                        source_page_id=due.source_id if due.source == "notion" else "",
                        platform="Instagram",
                    )
                    if due.source != "notion" and not due.source_id and page_id:
                        set_source_id(
                            con,
                            reel_id=due.reel_id,
                            scheduled_at=due.scheduled_at,
                            source="notion",
                            source_id=page_id,
                        )
                except Exception:
                    logger.exception(f"Notion report failed (publishing) for {due.reel_id}")
            video_url = ensure_video_url(due.video_path, explicit_url=video_url)
            # Claim the row before Graph create. A restart must not open a second container.
            record_attempt(
                con,
                reel_id=due.reel_id,
                scheduled_at=due.scheduled_at,
                status="publishing",
                last_error="",
            )
            container_id, media_id = _publish_ig_fb_fanout(
                video_url=video_url,
                caption=ig_caption,
                max_attempts=max(1, int(ns.max_attempts)),
            )
            ig_url = f"https://www.instagram.com/reel/{media_id}/"
            record_attempt(
                con,
                reel_id=due.reel_id,
                scheduled_at=due.scheduled_at,
                ig_container_id=container_id,
                ig_media_id=media_id,
                status="posted",
                last_api_response=f'{{"container_id":"{container_id}","media_id":"{media_id}"}}',
                last_error="",
            )
            if notion_cfg is not None:
                try:
                    page_id, _page_url = upsert_report_page(
                        cfg=notion_cfg,
                        reel_id=due.reel_id,
                        scheduled_at_iso=due.scheduled_at,
                        caption=ig_caption,
                        r2_key=due.r2_key,
                        r2_url=video_url,
                        post_id=media_id,
                        post_url=ig_url,
                        container_id=container_id,
                        attempts=1,
                        last_api_response=f'{{"container_id":"{container_id}","media_id":"{media_id}"}}',
                        status_name=notion_cfg.status_posted,
                        error_text="",
                        source_page_id=due.source_id if due.source == "notion" else "",
                        platform="Instagram",
                    )
                    if due.source != "notion" and not due.source_id and page_id:
                        set_source_id(
                            con,
                            reel_id=due.reel_id,
                            scheduled_at=due.scheduled_at,
                            source="notion",
                            source_id=page_id,
                        )
                except Exception:
                    logger.exception(f"Notion report failed (posted) for {due.reel_id}")

            if ns.r2_delete_after_post and due.r2_key:
                try:
                    r2 = load_r2_config()
                    delete_keys(cfg=r2, keys=due.r2_key)
                except Exception:
                    logger.exception(f"R2 delete failed for {due.reel_id} key={due.r2_key}")
        except Exception as e:
            if isinstance(e, FileNotFoundError):
                record_attempt(
                    con,
                    reel_id=due.reel_id,
                    scheduled_at=due.scheduled_at,
                    status="hold",
                    last_error=f"file missing: {e}",
                )
                logger.error(
                    f"Hold missing video for {due.reel_id} scheduled_at={due.scheduled_at}: {e}"
                )
                continue
            err_text = f"{type(e).__name__}: {e}"
            is_auth = (
                "Auth failed" in err_text
                or "code\":190" in err_text
                or "Session has expired" in err_text
                or "Error validating access token" in err_text
                or "No Instagram publish targets" in err_text
            )
            if is_auth:
                # Hold item; stop CRM spam until tokens refreshed.
                record_attempt(
                    con,
                    reel_id=due.reel_id,
                    scheduled_at=due.scheduled_at,
                    status="planned",
                    last_error=err_text,
                )
                logger.error(
                    f"IG auth/config hold for {due.reel_id}: {err_text}. "
                    "Idle until META_*_PAGE_TOKEN refreshed."
                )
                alert_autopost_fail(
                    platform="Instagram",
                    reel_id=due.reel_id,
                    scheduled_at=due.scheduled_at,
                    error=err_text + " — IG paused; refresh Page tokens",
                )
                # Long sleep so we don't hammer CRM / Graph every interval.
                _time.sleep(3600)
                continue
            media_reject = any(
                code in err_text
                for code in ("2207082", "2207026", "2207052", "2207009")
            )
            record_attempt(
                con,
                reel_id=due.reel_id,
                scheduled_at=due.scheduled_at,
                status="hold" if media_reject else "planned",
                last_error=(
                    f"ig media reject: {err_text}" if media_reject else err_text
                ),
            )
            if notion_cfg is not None:
                try:
                    page_id, _page_url = upsert_report_page(
                        cfg=notion_cfg,
                        reel_id=due.reel_id,
                        scheduled_at_iso=due.scheduled_at,
                        caption=ig_caption,
                        r2_key=due.r2_key,
                        r2_url=due.video_url,
                        container_id=due.ig_container_id,
                        attempts=1,
                        last_api_response=due.last_api_response,
                        status_name=notion_cfg.status_error,
                        error_text=err_text,
                        source_page_id=due.source_id if due.source == "notion" else "",
                        platform="Instagram",
                    )
                    if due.source != "notion" and not due.source_id and page_id:
                        set_source_id(
                            con,
                            reel_id=due.reel_id,
                            scheduled_at=due.scheduled_at,
                            source="notion",
                            source_id=page_id,
                        )
                except Exception:
                    logger.exception(f"Notion report failed (error) for {due.reel_id}")
            logger.exception(f"Autopost failed for {due.reel_id} scheduled_at={due.scheduled_at}")
            alert_autopost_fail(
                platform="Instagram",
                reel_id=due.reel_id,
                scheduled_at=due.scheduled_at,
                error=err_text,
            )
            _time.sleep(max(10, int(ns.interval_sec)))


def cmd_autocrosspost(ns: argparse.Namespace) -> int:
    """Auto-publish due items to Instagram + YouTube (in sequence)."""
    from uploader.instagram_publisher import ensure_video_url, load_instagram_configs
    from uploader.notion_report import load_notion_report_config, upsert_report_page
    from uploader.r2_storage import (
        build_object_key,
        delete_by_key,
        delete_keys,
        load_r2_config,
        upload_file_public,
    )
    from uploader.youtube_publisher import publish_youtube_short

    tz = ZoneInfo(ns.tz)
    con = connect(ns.db_path)
    cfgs = load_instagram_configs()
    notion_cfg = load_notion_report_config()
    logger.info(
        "Auto-crosspost started accounts="
        + ",".join(c.account_label for c in cfgs)
        + ". Press Ctrl+C to stop."
    )

    local_delete = bool(int((os.environ.get("LOCAL_DELETE_AFTER_POST") or "0").strip() or "0"))

    while True:
        now = datetime.now(tz=tz).isoformat(timespec="seconds")
        due = next_due(con, now_iso=now, platform="instagram")
        if due is None:
            _time.sleep(max(5, int(ns.interval_sec)))
            continue

        try:
            resolved_path = _resolve_video_path(due.video_path, reel_id=due.reel_id)
            if str(resolved_path) != (due.video_path or "").strip():
                set_video_path(
                    con,
                    reel_id=due.reel_id,
                    scheduled_at=due.scheduled_at,
                    video_path=str(resolved_path),
                )
                due = UploadItem(**{**due.__dict__, "video_path": str(resolved_path)})

            ig_caption = _instagram_caption_for_publish(con, due)
            # --- Instagram ---
            video_url = due.video_url
            if not video_url and due.video_path and ns.r2_autoupload:
                r2 = load_r2_config()
                key = build_object_key(cfg=r2, reel_id=due.reel_id, video_path=due.video_path)
                video_url = upload_file_public(cfg=r2, key=key, file_path=due.video_path)
                set_r2_key_and_url(
                    con,
                    reel_id=due.reel_id,
                    scheduled_at=due.scheduled_at,
                    r2_key=key,
                    video_url=video_url,
                )
                if notion_cfg is not None:
                    try:
                        page_id, _page_url = upsert_report_page(
                            cfg=notion_cfg,
                            reel_id=due.reel_id,
                            scheduled_at_iso=due.scheduled_at,
                            caption=ig_caption,
                            r2_key=key,
                            r2_url=video_url,
                            status_name=notion_cfg.status_uploaded,
                            error_text="",
                            source_page_id=due.source_id if due.source == "notion" else "",
                            platform="Instagram",
                        )
                    except Exception:
                        logger.exception(f"Notion report failed (r2 autoupload) for {due.reel_id}")
                    else:
                        if due.source != "notion" and not due.source_id and page_id:
                            set_source_id(
                                con,
                                reel_id=due.reel_id,
                                scheduled_at=due.scheduled_at,
                                source="notion",
                                source_id=page_id,
                            )

            # Mark publishing in Notion (IG).
            if notion_cfg is not None:
                try:
                    page_id, _page_url = upsert_report_page(
                        cfg=notion_cfg,
                        reel_id=due.reel_id,
                        scheduled_at_iso=due.scheduled_at,
                        caption=ig_caption,
                        r2_key=due.r2_key,
                        r2_url=video_url,
                        status_name=notion_cfg.status_publishing,
                        error_text="",
                        attempts=1,
                        source_page_id=due.source_id if due.source == "notion" else "",
                        platform="Instagram",
                    )
                    if due.source != "notion" and not due.source_id and page_id:
                        set_source_id(
                            con,
                            reel_id=due.reel_id,
                            scheduled_at=due.scheduled_at,
                            source="notion",
                            source_id=page_id,
                        )
                except Exception:
                    logger.exception(f"Notion report failed (publishing) for {due.reel_id}")

            video_url = ensure_video_url(due.video_path, explicit_url=video_url)
            container_id, media_id = _publish_ig_fb_fanout(
                video_url=video_url,
                caption=ig_caption,
                max_attempts=max(1, int(ns.max_attempts)),
            )
            ig_url = f"https://www.instagram.com/reel/{media_id}/"

            # --- YouTube ---
            yt = publish_youtube_short(
                video_path=Path(due.video_path),
                privacy_status=ns.yt_privacy,
            )

            record_attempt(
                con,
                reel_id=due.reel_id,
                scheduled_at=due.scheduled_at,
                ig_container_id=container_id,
                ig_media_id=media_id,
                yt_video_id=yt.video_id,
                yt_video_url=yt.video_url,
                status="posted",
                last_api_response=f'{{"ig_media_id":"{media_id}","yt_video_id":"{yt.video_id}"}}',
                last_error="",
            )

            if notion_cfg is not None:
                # IG row
                try:
                    upsert_report_page(
                        cfg=notion_cfg,
                        reel_id=due.reel_id,
                        scheduled_at_iso=due.scheduled_at,
                        caption=ig_caption,
                        r2_key=due.r2_key,
                        r2_url=video_url,
                        post_id=media_id,
                        post_url=ig_url,
                        container_id=container_id,
                        attempts=1,
                        last_api_response=f'{{"container_id":"{container_id}","media_id":"{media_id}"}}',
                        status_name=notion_cfg.status_posted,
                        error_text="",
                        source_page_id=due.source_id if due.source == "notion" else "",
                        platform="Instagram",
                    )
                except Exception:
                    logger.exception(f"Notion report failed (IG posted) for {due.reel_id}")

                # YT row
                try:
                    upsert_report_page(
                        cfg=notion_cfg,
                        reel_id=due.reel_id,
                        scheduled_at_iso=due.scheduled_at,
                        caption=yt.description,
                        title=yt.title,
                        tags_text=(" ".join(yt.hashtags) or ", ".join(yt.tags)).strip(),
                        privacy=ns.yt_privacy,
                        r2_key="",
                        r2_url="",
                        post_id=yt.video_id,
                        post_url=yt.video_url,
                        container_id="",
                        attempts=1,
                        last_api_response=f'{{"video_id":"{yt.video_id}"}}',
                        status_name=notion_cfg.status_posted,
                        error_text="",
                        source_page_id="",
                        platform="YouTube Shorts",
                    )
                except Exception:
                    logger.exception(f"Notion report failed (YT posted) for {due.reel_id}")

            if ns.r2_delete_after_post and due.r2_key:
                try:
                    r2 = load_r2_config()
                    delete_keys(cfg=r2, keys=due.r2_key)
                except Exception:
                    logger.exception(f"R2 delete failed for {due.reel_id} key={due.r2_key}")

            if local_delete:
                try:
                    _safe_delete_local_video(due.video_path)
                    logger.success(f"Deleted local video: {due.video_path}")
                except Exception:
                    logger.exception(f"Local delete failed for {due.reel_id} path={due.video_path}")

        except Exception as e:
            if isinstance(e, FileNotFoundError):
                record_attempt(
                    con,
                    reel_id=due.reel_id,
                    scheduled_at=due.scheduled_at,
                    status="skipped",
                    last_error=f"{type(e).__name__}: {e}",
                )
                logger.error(
                    f"Skip missing video for {due.reel_id} scheduled_at={due.scheduled_at}: {e}"
                )
                continue
            record_attempt(
                con,
                reel_id=due.reel_id,
                scheduled_at=due.scheduled_at,
                status="planned",
                last_error=f"{type(e).__name__}: {e}",
            )
            if notion_cfg is not None:
                try:
                    upsert_report_page(
                        cfg=notion_cfg,
                        reel_id=due.reel_id,
                        scheduled_at_iso=due.scheduled_at,
                        caption=ig_caption,
                        r2_key=due.r2_key,
                        r2_url=due.video_url,
                        container_id=due.ig_container_id,
                        attempts=1,
                        last_api_response=due.last_api_response,
                        status_name=notion_cfg.status_error,
                        error_text=f"{type(e).__name__}: {e}",
                        source_page_id=due.source_id if due.source == "notion" else "",
                        platform="Crosspost",
                    )
                except Exception:
                    logger.exception(f"Notion report failed (error) for {due.reel_id}")
            logger.exception(f"Auto-crosspost failed for {due.reel_id} scheduled_at={due.scheduled_at}")
            alert_autopost_fail(
                platform="Crosspost IG+YT",
                reel_id=due.reel_id,
                scheduled_at=due.scheduled_at,
                error=f"{type(e).__name__}: {e}",
            )
            _time.sleep(max(10, int(ns.interval_sec)))


def _process_one_due(*, con, tz: ZoneInfo, ns: argparse.Namespace) -> int:
    from uploader.instagram_publisher import ensure_video_url, load_instagram_configs
    from uploader.notion_report import load_notion_report_config, upsert_report_page
    from uploader.r2_storage import build_object_key, delete_by_key, delete_keys, load_r2_config, upload_file_public

    _cfgs = load_instagram_configs()
    notion_cfg = load_notion_report_config()
    now = datetime.now(tz=tz).isoformat(timespec="seconds")
    due = next_due(con, now_iso=now, platform="instagram")
    if due is None:
        print("No due items right now.")
        return 1

    try:
        resolved_path = _resolve_video_path(due.video_path, reel_id=due.reel_id)
        if str(resolved_path) != (due.video_path or "").strip():
            set_video_path(
                con,
                reel_id=due.reel_id,
                scheduled_at=due.scheduled_at,
                video_path=str(resolved_path),
            )
            due = UploadItem(**{**due.__dict__, "video_path": str(resolved_path)})
    except FileNotFoundError as e:
        record_attempt(
            con,
            reel_id=due.reel_id,
            scheduled_at=due.scheduled_at,
            status="skipped",
            last_error=f"{type(e).__name__}: {e}",
        )
        print(f"Skip missing video: {due.reel_id} ({e})")
        return 2

    ig_caption = _instagram_caption_for_publish(con, due)

    video_url = due.video_url
    if not video_url and due.video_path and ns.r2_autoupload:
        r2 = load_r2_config()
        key = build_object_key(cfg=r2, reel_id=due.reel_id, video_path=due.video_path)
        video_url = upload_file_public(cfg=r2, key=key, file_path=due.video_path)
        set_r2_key_and_url(
            con, reel_id=due.reel_id, scheduled_at=due.scheduled_at, r2_key=key, video_url=video_url
        )
        if notion_cfg is not None:
            try:
                page_id, _page_url = upsert_report_page(
                    cfg=notion_cfg,
                    reel_id=due.reel_id,
                    scheduled_at_iso=due.scheduled_at,
                    caption=ig_caption,
                    r2_key=key,
                    r2_url=video_url,
                    status_name=notion_cfg.status_uploaded,
                    error_text="",
                    source_page_id=due.source_id if due.source == "notion" else "",
                    platform="Instagram",
                )
                if due.source != "notion" and not due.source_id and page_id:
                    set_source_id(
                        con,
                        reel_id=due.reel_id,
                        scheduled_at=due.scheduled_at,
                        source="notion",
                        source_id=page_id,
                    )
            except Exception:
                logger.exception(f"Notion report failed (post-once upload) for {due.reel_id}")

    try:
        video_url = ensure_video_url(due.video_path, explicit_url=video_url)
        if notion_cfg is not None:
            try:
                page_id, _page_url = upsert_report_page(
                    cfg=notion_cfg,
                    reel_id=due.reel_id,
                    scheduled_at_iso=due.scheduled_at,
                    caption=ig_caption,
                    r2_key=due.r2_key,
                    r2_url=video_url,
                    status_name=notion_cfg.status_publishing,
                    error_text="",
                    attempts=1,
                    source_page_id=due.source_id if due.source == "notion" else "",
                    platform="Instagram",
                )
                if due.source != "notion" and not due.source_id and page_id:
                    set_source_id(
                        con,
                        reel_id=due.reel_id,
                        scheduled_at=due.scheduled_at,
                        source="notion",
                        source_id=page_id,
                    )
            except Exception:
                logger.exception(f"Notion report failed (post-once publishing) for {due.reel_id}")
        container_id, media_id = _publish_ig_fb_fanout(
            video_url=video_url,
            caption=ig_caption,
            max_attempts=max(1, int(ns.max_attempts)),
        )
        record_attempt(
            con,
            reel_id=due.reel_id,
            scheduled_at=due.scheduled_at,
            ig_container_id=container_id,
            ig_media_id=media_id,
            status="posted",
            last_api_response=f'{{"container_id":"{container_id}","media_id":"{media_id}"}}',
            last_error="",
        )
        if notion_cfg is not None:
            try:
                page_id, _page_url = upsert_report_page(
                    cfg=notion_cfg,
                    reel_id=due.reel_id,
                    scheduled_at_iso=due.scheduled_at,
                    caption=ig_caption,
                    r2_key=due.r2_key,
                    r2_url=video_url,
                    post_id=media_id,
                    post_url=f"https://www.instagram.com/reel/{media_id}/",
                    container_id=container_id,
                    attempts=1,
                    last_api_response=f'{{"container_id":"{container_id}","media_id":"{media_id}"}}',
                    status_name=notion_cfg.status_posted,
                    error_text="",
                    source_page_id=due.source_id if due.source == "notion" else "",
                    platform="Instagram",
                )
                if due.source != "notion" and not due.source_id and page_id:
                    set_source_id(
                        con,
                        reel_id=due.reel_id,
                        scheduled_at=due.scheduled_at,
                        source="notion",
                        source_id=page_id,
                    )
            except Exception:
                logger.exception(f"Notion report failed (post-once posted) for {due.reel_id}")
        if ns.r2_delete_after_post and due.r2_key:
            r2 = load_r2_config()
            delete_keys(cfg=r2, keys=due.r2_key)
        print(f"OK posted: {due.reel_id} media_id={media_id}")
        return 0
    except Exception as e:
        record_attempt(
            con,
            reel_id=due.reel_id,
            scheduled_at=due.scheduled_at,
            status="planned",
            last_error=f"{type(e).__name__}: {e}",
        )
        if notion_cfg is not None:
            try:
                page_id, _page_url = upsert_report_page(
                    cfg=notion_cfg,
                    reel_id=due.reel_id,
                    scheduled_at_iso=due.scheduled_at,
                    caption=ig_caption,
                    r2_key=due.r2_key,
                    r2_url=due.video_url,
                    container_id=due.ig_container_id,
                    attempts=1,
                    last_api_response=due.last_api_response,
                    status_name=notion_cfg.status_error,
                    error_text=f"{type(e).__name__}: {e}",
                    source_page_id=due.source_id if due.source == "notion" else "",
                    platform="Instagram",
                )
                if due.source != "notion" and not due.source_id and page_id:
                    set_source_id(
                        con,
                        reel_id=due.reel_id,
                        scheduled_at=due.scheduled_at,
                        source="notion",
                        source_id=page_id,
                    )
            except Exception:
                logger.exception(f"Notion report failed (post-once error) for {due.reel_id}")
        logger.exception(f"Post failed for {due.reel_id} scheduled_at={due.scheduled_at}")
        alert_autopost_fail(
            platform="Instagram",
            reel_id=due.reel_id,
            scheduled_at=due.scheduled_at,
            error=f"{type(e).__name__}: {e}",
        )
        return 2


def cmd_post_once(ns: argparse.Namespace) -> int:
    tz = ZoneInfo(ns.tz)
    con = connect(ns.db_path)
    return _process_one_due(con=con, tz=tz, ns=ns)


def cmd_youtube_oauth(ns: argparse.Namespace) -> int:
    from uploader.youtube_channels import (
        build_youtube_service,
        get_channel_info,
        load_upload_credentials,
        resolve_channel,
        run_oauth_manual,
        verify_channel_handle,
    )

    profile = resolve_channel(ns.channel)
    if getattr(ns, "manual", False):
        creds = run_oauth_manual(profile=profile)
    else:
        creds = load_upload_credentials(profile=profile, interactive=True)
    print(f"Token saved: {profile.token_path}")
    print(f"  brand_url   : {profile.brand_url}")
    print(f"  queue plat. : {profile.queue_platform}")
    print(f"  Notion plat.: {profile.notion_platform}")
    try:
        me = get_channel_info(build_youtube_service(creds))
        verify_channel_handle(
            profile,
            custom_url=str(me.get("custom_url") or ""),
            title=str(me.get("title") or ""),
        )
        print(f"  channel_id  : {me['id']}")
        print(f"  title       : {me['title']}")
        print(f"  custom_url  : {me.get('custom_url') or '-'}")
    except Exception as e:
        err = str(e)
        if "insufficient" in err.lower() or "403" in err:
            print("  (upload token OK; channel name check skipped)")
        else:
            raise
    return 0


def cmd_youtube_whoami(ns: argparse.Namespace) -> int:
    from uploader.youtube_channels import (
        build_youtube_service,
        get_channel_info,
        load_upload_credentials,
        resolve_channel,
    )

    profile = resolve_channel(ns.channel)
    if not profile.token_path.is_file():
        print(f"No token at {profile.token_path}")
        print(f"Run: ./venv/bin/python -m uploader.main youtube-oauth --channel {profile.key}")
        return 1
    creds = load_upload_credentials(profile=profile, interactive=False)
    print(f"channel profile : {profile.key}")
    print(f"token path      : {profile.token_path}")
    try:
        me = get_channel_info(build_youtube_service(creds))
        print(f"  channel_id    : {me['id']}")
        print(f"  title         : {me['title']}")
        print(f"  custom_url    : {me.get('custom_url') or '-'}")
    except Exception as e:
        err = str(e)
        if "insufficient" in err.lower() or "403" in err:
            print(
                "  (token exists; re-run youtube-oauth to refresh scopes "
                "and see channel title)"
            )
            return 0
        raise
    return 0


def cmd_autopost_yt(ns: argparse.Namespace) -> int:
    """Auto-publish YouTube-platform queue items to YouTube Shorts."""
    from uploader.notion_report import load_notion_report_config, upsert_report_page
    from uploader.youtube_channels import resolve_channel
    from uploader.youtube_publisher import publish_youtube_short

    tz = ZoneInfo(ns.tz)
    con = connect(ns.db_path)
    notion_cfg = load_notion_report_config()
    privacy = (ns.yt_privacy or "unlisted").strip()
    local_delete = bool(int((os.environ.get("LOCAL_DELETE_AFTER_POST") or "0").strip() or "0"))
    profile = resolve_channel(getattr(ns, "channel", None))
    platform = profile.queue_platform
    notion_platform = profile.notion_platform

    logger.info(f"Autopost [{platform}] channel={profile.key} started. Press Ctrl+C to stop.")
    while True:
        now = datetime.now(tz=tz).isoformat(timespec="seconds")
        _release_held_media(con, platform=platform)
        due = next_due(con, now_iso=now, platform=platform)
        if due is None:
            _time.sleep(max(5, int(ns.interval_sec)))
            continue

        try:
            gate, ready_path = _park_until_ready(con, due)
            if gate == "parked":
                continue
            if gate == "ready" and ready_path is not None:
                due = UploadItem(**{**due.__dict__, "video_path": str(ready_path)})
                due = _attach_feed_mp4(con, due)

            if notion_cfg is not None:
                try:
                    page_id, _page_url = upsert_report_page(
                        cfg=notion_cfg,
                        reel_id=due.reel_id,
                        scheduled_at_iso=due.scheduled_at,
                        caption=due.caption,
                        status_name=notion_cfg.status_publishing,
                        error_text="",
                        attempts=1,
                        source_page_id=due.source_id if due.source == "notion" else "",
                        platform=notion_platform,
                    )
                    if due.source != "notion" and not due.source_id and page_id:
                        set_source_id(
                            con,
                            reel_id=due.reel_id,
                            scheduled_at=due.scheduled_at,
                            source="notion",
                            source_id=page_id,
                        )
                except Exception:
                    logger.exception(f"Notion report failed (YT publishing) for {due.reel_id}")

            yt_caption = _instagram_caption_for_publish(con, due)
            yt = publish_youtube_short(
                video_path=Path(due.video_path),
                privacy_status=privacy,
                channel=profile.key,
                caption_override=yt_caption,
            )

            record_attempt(
                con,
                reel_id=due.reel_id,
                scheduled_at=due.scheduled_at,
                yt_video_id=yt.video_id,
                yt_video_url=yt.video_url,
                status="posted",
                last_api_response=f'{{"video_id":"{yt.video_id}"}}',
                last_error="",
            )

            if notion_cfg is not None:
                try:
                    upsert_report_page(
                        cfg=notion_cfg,
                        reel_id=due.reel_id,
                        scheduled_at_iso=due.scheduled_at,
                        caption=yt.description,
                        title=yt.title,
                        tags_text=(" ".join(yt.hashtags) or ", ".join(yt.tags)).strip(),
                        privacy=privacy,
                        post_id=yt.video_id,
                        post_url=yt.video_url,
                        attempts=1,
                        last_api_response=f'{{"video_id":"{yt.video_id}"}}',
                        status_name=notion_cfg.status_posted,
                        error_text="",
                        source_page_id="",
                        platform=notion_platform,
                    )
                except Exception:
                    logger.exception(f"Notion report failed (YT posted) for {due.reel_id}")

            if local_delete:
                try:
                    _safe_delete_local_video(due.video_path)
                    logger.success(f"Deleted local video: {due.video_path}")
                except Exception:
                    logger.exception(f"Local delete failed for {due.reel_id} path={due.video_path}")

        except Exception as e:
            if isinstance(e, FileNotFoundError):
                record_attempt(
                    con,
                    reel_id=due.reel_id,
                    scheduled_at=due.scheduled_at,
                    status="skipped",
                    last_error=f"{type(e).__name__}: {e}",
                )
                logger.error(
                    f"Skip missing video for {due.reel_id} scheduled_at={due.scheduled_at}: {e}"
                )
                continue
            record_attempt(
                con,
                reel_id=due.reel_id,
                scheduled_at=due.scheduled_at,
                status="planned",
                last_error=f"{type(e).__name__}: {e}",
            )
            if notion_cfg is not None:
                try:
                    upsert_report_page(
                        cfg=notion_cfg,
                        reel_id=due.reel_id,
                        scheduled_at_iso=due.scheduled_at,
                        caption=due.caption,
                        attempts=1,
                        last_api_response=due.last_api_response,
                        status_name=notion_cfg.status_error,
                        error_text=f"{type(e).__name__}: {e}",
                        source_page_id="",
                        platform="YouTube Shorts",
                    )
                except Exception:
                    logger.exception(f"Notion report failed (YT error) for {due.reel_id}")
            logger.exception(f"YT autopost failed for {due.reel_id} scheduled_at={due.scheduled_at}")
            alert_autopost_fail(
                platform="YouTube Shorts",
                reel_id=due.reel_id,
                scheduled_at=due.scheduled_at,
                error=f"{type(e).__name__}: {e}",
            )
            _time.sleep(max(10, int(ns.interval_sec)))


def cmd_tg_stories_whoami(ns: argparse.Namespace) -> int:
    import asyncio as _aio

    from uploader.telegram_stories_publisher import whoami

    info = _aio.run(whoami())
    print(
        f"Telegram Stories account: id={info['id']} @{info['username']} "
        f"name={info['first_name']!r} phone={info['phone']}"
    )
    return 0


def cmd_autopost_tg_stories(ns: argparse.Namespace) -> int:
    """Publish due telegram_story queue rows as Telegram Stories (every ≥48h)."""
    from uploader.telegram_stories_publisher import publish_story_video_sync

    tz = ZoneInfo(ns.tz)
    con = connect(ns.db_path)
    dry = bool(getattr(ns, "dry_run", False)) or (
        (_env("TG_STORIES_DRY_RUN") or "").lower() in {"1", "true", "yes", "on"}
    )
    logger.info(
        f"Autopost [telegram_story] started dry_run={dry}. Press Ctrl+C to stop."
    )
    while True:
        now = datetime.now(tz=tz).isoformat(timespec="seconds")
        due = next_due(con, now_iso=now, platform="telegram_story")
        if due is None:
            _time.sleep(max(15, int(ns.interval_sec)))
            continue
        wait_sec = _stories_gap_wait_sec(con, tz)
        if wait_sec > 0:
            logger.info(
                f"[tg-stories] pause {wait_sec/3600:.1f}h — "
                f"next story only after {_env('TG_STORIES_MIN_GAP_HOURS', '48')}h"
            )
            _time.sleep(min(wait_sec, 3600))
            continue
        try:
            resolved_path = _resolve_video_path(due.video_path, reel_id=due.reel_id)
            if str(resolved_path) != (due.video_path or "").strip():
                set_video_path(
                    con,
                    reel_id=due.reel_id,
                    scheduled_at=due.scheduled_at,
                    video_path=str(resolved_path),
                )
                due = UploadItem(**{**due.__dict__, "video_path": str(resolved_path)})

            token = publish_story_video_sync(
                video_path=Path(due.video_path),
                caption=due.caption,
                dry_run=dry,
                reel_id=due.reel_id,
            )
            record_attempt(
                con,
                reel_id=due.reel_id,
                scheduled_at=due.scheduled_at,
                status="skipped" if dry else "posted",
                last_api_response=f'{{"story":"{token}"}}',
                last_error="dry-run" if dry else "",
            )
            logger.success(
                f"[tg-stories] {due.reel_id} @ {due.scheduled_at} → {token}"
            )
            _time.sleep(max(5, int(ns.interval_sec)))
        except Exception as e:
            record_attempt(
                con,
                reel_id=due.reel_id,
                scheduled_at=due.scheduled_at,
                status="planned",
                last_error=f"{type(e).__name__}: {e}",
            )
            logger.exception(
                f"[tg-stories] failed {due.reel_id} scheduled_at={due.scheduled_at}"
            )
            alert_autopost_fail(
                platform="Telegram Stories",
                reel_id=due.reel_id,
                scheduled_at=due.scheduled_at,
                error=f"{type(e).__name__}: {e}",
            )
            _time.sleep(max(30, int(ns.interval_sec)))


def cmd_refill_threads_text(ns: argparse.Namespace) -> int:
    from uploader.threads_text_autopost import refill_queue

    n = refill_queue(
        db_path=ns.db_path,
        tz_name=ns.tz,
        count=int(ns.count) if ns.count else None,
    )
    print(f"Added threads TEXT posts: {n}")
    return 0


def cmd_threads_replies_once(ns: argparse.Namespace) -> int:
    from uploader.threads_replies import run_once, settings_from_env

    cfg = settings_from_env(
        tz_name=ns.tz,
        dry_run=True if ns.dry_run else None,
    )
    stats = run_once(cfg)
    logger.info(f"[threads-replies] once {stats}")
    return 0


def cmd_autopost_threads_replies(ns: argparse.Namespace) -> int:
    from uploader.threads_replies import run_loop, settings_from_env

    cfg = settings_from_env(
        tz_name=ns.tz,
        dry_run=True if ns.dry_run else None,
    )
    logger.info(
        "Threads reply bot @grishkoff_travel started. Press Ctrl+C to stop."
    )
    run_loop(cfg, interval_sec=int(ns.interval_sec))
    return 0


def cmd_autopost_threads_text(ns: argparse.Namespace) -> int:
    """Native TEXT Threads @grishkoff_travel — random active windows."""
    from uploader.threads_text_autopost import threads_text_tick

    logger.info(
        "Autopost [threads_text] @grishkoff_travel started. Press Ctrl+C to stop."
    )
    interval = max(30, int(ns.interval_sec))
    while True:
        try:
            threads_text_tick(db_path=ns.db_path, tz_name=ns.tz)
        except Exception:
            logger.exception("[threads-text] tick failed")
        _time.sleep(interval)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="uploader", description="Trial-mode Reels uploader helper (no autopost).")
    p.add_argument("--db-path", default=_env("UPLOAD_DB_PATH", "output/upload_queue.sqlite3"))
    p.add_argument("--tz", default=_env("TZ", "Asia/Makassar"))

    sub = p.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="Plan N reels for a day within a time window.")
    plan.add_argument("--plan", required=True, help="output/reels_plan.csv")
    plan.add_argument("--texts", required=True, help="texts_kailas.csv")
    plan.add_argument("--reels-dir", required=True, help="output/reels/")
    plan.add_argument("--count", type=int, default=int(_env("UPLOAD_COUNT_PER_DAY", "5") or 5))
    plan.add_argument("--window", default=_env("UPLOAD_WINDOW", "19:00-22:30"))
    plan.add_argument("--day", default="", help="YYYY-MM-DD (default: today in tz)")
    plan.add_argument("--seed", type=int, default=None)
    plan.add_argument("--caption-suffix", default=_env("CAPTION_SUFFIX", "\n\nНапиши «КАЙЛАС»"))
    plan.set_defaults(func=cmd_plan)

    slots = sub.add_parser("plan-slots", help="Plan fixed times (e.g. morning/noon/evening).")
    slots.add_argument("--plan", required=True, help="output/reels_plan.csv")
    slots.add_argument("--texts", required=True, help="texts_kailas.csv")
    slots.add_argument("--reels-dir", required=True, help="output/reels/")
    slots.add_argument("--times", default=_env("UPLOAD_TIMES", "09:00,13:00,19:00"))
    slots.add_argument("--day", default="", help="YYYY-MM-DD (default: today in tz)")
    slots.add_argument("--caption-suffix", default=_env("CAPTION_SUFFIX", "\n\nНапиши «КАЙЛАС»"))
    slots.set_defaults(func=cmd_plan_slots)

    slots2 = sub.add_parser("plan-dir-slots", help="Plan fixed times from reels dir (no CSV).")
    slots2.add_argument("--reels-dir", required=True, help="output/reels/")
    slots2.add_argument("--times", default=_env("UPLOAD_TIMES", "09:00,13:00,19:00"))
    slots2.add_argument("--day", default="", help="YYYY-MM-DD (default: today in tz)")
    slots2.add_argument("--caption-suffix", default=_env("CAPTION_SUFFIX", "\n\nНапиши «КАЙЛАС»"))
    slots2.set_defaults(func=cmd_plan_dir_slots)

    week = sub.add_parser("plan-dir-week", help="Plan fixed slots for N days from reels dir.")
    week.add_argument("--reels-dir", required=True, help="output/reels/")
    week.add_argument("--times", default=_env("UPLOAD_TIMES", "09:00,13:00,19:00"))
    week.add_argument("--start-day", default="", help="YYYY-MM-DD (default: today in tz)")
    week.add_argument("--days", type=int, default=7)
    week.add_argument("--caption-suffix", default=_env("CAPTION_SUFFIX", "\n\nНапиши «КАЙЛАС»"))
    week.add_argument("--dry-run", action="store_true", default=False)
    week.add_argument(
        "--platform",
        default=_env("UPLOAD_PLATFORM", "instagram"),
        choices=["instagram", "youtube"],
        help="Target platform for these slots.",
    )
    week.add_argument(
        "--allow-reuse",
        action="store_true",
        default=bool(int(_env("UPLOAD_ALLOW_REUSE", "0") or "0")),
        help="If set, cycle existing reels when fresh ones run out (default: strict).",
    )
    week.set_defaults(func=cmd_plan_dir_week)

    today = sub.add_parser("today", help="Show today's plan with captions.")
    today.add_argument("--day", default="", help="YYYY-MM-DD (default: today in tz)")
    today.set_defaults(func=cmd_today)

    dr = sub.add_parser("daily-report", help="Print a daily report from the queue.")
    dr.add_argument("--day", default="", help="YYYY-MM-DD (default: today in tz)")
    dr.set_defaults(func=cmd_daily_report)

    tick = sub.add_parser("tick", help="Print reminders when items become due.")
    tick.add_argument("--interval-sec", type=int, default=30)
    tick.set_defaults(func=cmd_tick)

    mp = sub.add_parser("mark-posted", help="Mark a reel_id as posted.")
    mp.add_argument("--reel-id", required=True)
    mp.set_defaults(func=cmd_mark_posted)

    cp = sub.add_parser("crosspost", help="Publish same reel to Instagram + YouTube (with Notion rows).")
    cp.add_argument("--reel-id", required=True)
    cp.add_argument("--day", default="", help="YYYY-MM-DD (default: today in tz)")
    cp.add_argument(
        "--yt-privacy",
        default=_env("YOUTUBE_PRIVACY_STATUS", "unlisted") or "unlisted",
        choices=["private", "unlisted", "public"],
    )
    cp.add_argument(
        "--r2-delete-after-post",
        action="store_true",
        default=bool(int(_env("R2_DELETE_AFTER_POST", "0") or "0")),
    )
    cp.set_defaults(func=cmd_crosspost)

    sn = sub.add_parser("sync-notion", help="Import Ready items from Notion database into queue.")
    sn.set_defaults(func=cmd_sync_notion)

    ing = sub.add_parser(
        "ingest-reels",
        help="New files in output/reels: IG captions, optional YT/Notion, queue.",
    )
    ing.add_argument("--reels-dir", default=_env("READY_DIR", "output/reels"))
    ing.add_argument("--texts", default=_env("UPLOAD_TEXTS_CSV", "texts_kailas.csv"))
    ing.add_argument("--plan", default=_env("INGEST_PLAN_CSV", ""), help="Batch plan CSV")
    ing.add_argument(
        "--plan-glob",
        default=_env("INGEST_PLAN_GLOB", "reels_plan*.csv"),
        help="Auto-find plan in output/ when --plan empty",
    )
    ing.add_argument("--post-texts-dir", default=_env("INGEST_POST_TEXTS_DIR", "output/post_texts"))
    ing.add_argument("--output-root", default="output")
    ing.add_argument("--reel-id", default="ALL", help="R411 or R411,R412 or ALL")
    ing.add_argument("--force", action="store_true", help="Re-process even if ingested before")
    ing.add_argument("--dry-run", action="store_true")
    ing.add_argument(
        "--yt-preview",
        action="store_true",
        help="Whisper+OpenAI metadata for Notion YT row (slow)",
    )
    ing.add_argument("--no-yt-preview", action="store_true")
    ing.add_argument("--notion-prefill", action="store_true")
    ing.add_argument("--no-notion-prefill", action="store_true")
    ing.add_argument("--auto-plan-ig", action="store_true")
    ing.add_argument("--no-auto-plan-ig", action="store_true")
    ing.add_argument("--auto-plan-yt", action="store_true")
    ing.add_argument("--no-auto-plan-yt", action="store_true")
    ing.add_argument("--ig-times", default=_env("UPLOAD_TIMES", "09:00,13:00,19:00"))
    ing.add_argument("--yt-times", default=_env("UPLOAD_YT_TIMES", "11:00,16:00,22:00"))
    ing.add_argument("--plan-day", default="", help="YYYY-MM-DD for queue slots")
    ing.add_argument(
        "--notion-status",
        default=_env("INGEST_NOTION_STATUS", "Готов к публикации"),
    )
    ing.set_defaults(func=cmd_ingest_reels)

    sch = sub.add_parser(
        "schedule-crosspost",
        help="3 reels/day: IG + YT on fixed slots, spread across days.",
    )
    sch.add_argument("--reels-dir", default=_env("READY_DIR", "output/reels"))
    sch.add_argument("--post-texts-dir", default=_env("INGEST_POST_TEXTS_DIR", "output/post_texts"))
    sch.add_argument("--start-day", default="", help="YYYY-MM-DD (default: today MSK)")
    sch.add_argument("--ig-times", default=_env("UPLOAD_TIMES", "09:00,13:00,19:00"))
    sch.add_argument("--yt-times", default=_env("UPLOAD_YT_TIMES", "10:00,14:00,20:00"))
    sch.add_argument(
        "--pinterest-times",
        default=_env("UPLOAD_PINTEREST_TIMES", ""),
        help="Pinterest slots (only if UPLOAD_PINTEREST=1 and PINTEREST_* set)",
    )
    sch.add_argument("--min-reel-num", default="411", help="Only R### with num >= this (default 411)")
    sch.add_argument("--reel-id", default="ALL", help="R411 or comma list or ALL")
    sch.add_argument(
        "--clear-planned",
        action="store_true",
        default=True,
        help="Remove existing planned rows for these reels first (default: on)",
    )
    sch.add_argument("--no-clear-planned", action="store_true")
    sch.add_argument("--dry-run", action="store_true")
    sch.add_argument("--random-slots", action="store_true", help="Random time per day (UPLOAD_RANDOM_SLOTS)")
    sch.add_argument("--no-random-slots", action="store_true")
    sch.set_defaults(func=cmd_schedule_crosspost)

    wr = sub.add_parser(
        "watch-reels",
        help="Ingest new videos + schedule only those not yet in queue.",
    )
    wr.add_argument("--reels-dir", default=_env("READY_DIR", "output/reels"))
    wr.add_argument("--texts", default=_env("UPLOAD_TEXTS_CSV", "texts_kailas.csv"))
    wr.add_argument("--post-texts-dir", default=_env("INGEST_POST_TEXTS_DIR", "output/post_texts"))
    wr.add_argument("--output-root", default="output")
    wr.add_argument("--dry-run", action="store_true")
    wr.set_defaults(func=cmd_watch_reels)

    rb = sub.add_parser("rebuild-texts", help="Assign unused texts_kailas + rewrite post_texts/")
    rb.add_argument("--reels-dir", default=_env("READY_DIR", "output/reels"))
    rb.add_argument("--texts", default=_env("UPLOAD_TEXTS_CSV", "texts_kailas.csv"))
    rb.add_argument("--post-texts-dir", default=_env("INGEST_POST_TEXTS_DIR", "output/post_texts"))
    rb.add_argument("--output-root", default="output")
    rb.add_argument("--min-reel-num", default="411")
    rb.add_argument("--caption-suffix", default=_env("CAPTION_SUFFIX", ""))
    rb.set_defaults(func=cmd_rebuild_texts)

    nsync = sub.add_parser("sync-notion-schedule", help="Update Notion rows from queue schedule.")
    nsync.add_argument("--post-texts-dir", default=_env("INGEST_POST_TEXTS_DIR", "output/post_texts"))
    nsync.add_argument(
        "--min-reel-num",
        default="411",
        help="Only R### reels with number >= N. Empty / non-digit = no R### filter.",
    )
    nsync.add_argument(
        "--reel-prefixes",
        default="",
        help="Comma-separated reel_id prefixes, e.g. AVANA__,AZERAI__,CRUISE__,WYNDHAM__",
    )
    nsync.add_argument("--yt-preview", action="store_true", help="Whisper+OpenAI for YT SEO in Notion")
    nsync.add_argument(
        "--notion-status",
        default=_env("INGEST_NOTION_STATUS", "Готов к публикации"),
    )
    nsync.set_defaults(func=cmd_sync_notion_schedule)

    ur2 = sub.add_parser("upload-r2", help="Upload planned local videos to R2 and store video_url.")
    ur2.add_argument("--day", default="", help="YYYY-MM-DD (default: today in tz)")
    ur2.set_defaults(func=cmd_upload_r2)

    ap = sub.add_parser("autopost", help="Auto-publish due queue items to Instagram.")
    ap.add_argument("--interval-sec", type=int, default=int(_env("UPLOAD_AUTPOST_INTERVAL_SEC", "30") or 30))
    ap.add_argument("--max-attempts", type=int, default=int(_env("IG_MAX_ATTEMPTS", "5") or 5))
    ap.add_argument(
        "--r2-autoupload",
        action="store_true",
        default=bool(int(_env("R2_AUTUPLOAD", "0") or "0")),
        help="If video_url is empty but video_path exists, upload to R2 and publish.",
    )
    ap.add_argument(
        "--r2-delete-after-post",
        action="store_true",
        default=bool(int(_env("R2_DELETE_AFTER_POST", "0") or "0")),
        help="After successful publish, delete video object from R2.",
    )
    ap.set_defaults(func=cmd_autopost)

    tta = sub.add_parser(
        "autopost-threads-text",
        help="Native TEXT posts → Threads @grishkoff_travel (discussion/tips/promo).",
    )
    tta.add_argument("--interval-sec", type=int, default=int(_env("THREADS_TEXT_TICK_SEC", "120") or 120))
    tta.set_defaults(func=cmd_autopost_threads_text)

    tr_once = sub.add_parser(
        "threads-replies-once",
        help="Reply once to new comments under our Threads posts.",
    )
    tr_once.add_argument(
        "--dry-run",
        action="store_true",
        help="Draft replies and print them. Do not publish.",
    )
    tr_once.set_defaults(func=cmd_threads_replies_once)

    tr_loop = sub.add_parser(
        "autopost-threads-replies",
        help="Keep replying to comments under @grishkoff_travel posts.",
    )
    tr_loop.add_argument(
        "--interval-sec",
        type=int,
        default=int(_env("THREADS_REPLIES_INTERVAL_SEC", "180") or 180),
    )
    tr_loop.add_argument(
        "--dry-run",
        action="store_true",
        help="Draft replies and print them. Do not publish.",
    )
    tr_loop.set_defaults(func=cmd_autopost_threads_replies)

    ttr = sub.add_parser(
        "refill-threads-text",
        help="Generate and queue native Threads TEXT posts (GPT).",
    )
    ttr.add_argument("--count", type=int, default=0, help="Override batch size (0=env default)")
    ttr.set_defaults(func=cmd_refill_threads_text)

    car = sub.add_parser(
        "sync-carousels",
        help="Sync Notion C-* «Готов к публикации» → queue (platform=carousel).",
    )
    car.set_defaults(func=cmd_sync_carousels)

    carp = sub.add_parser(
        "publish-carousel-due",
        help="Publish one due carousel to META_2 IG + Threads.",
    )
    carp.set_defaults(func=cmd_publish_carousel_due)

    carr = sub.add_parser(
        "republish-carousel",
        help="Re-queue carousel from notion_export.json (e.g. after slide fix).",
    )
    carr.add_argument("--carousel-id", required=True, help="C-slug carousel id")
    carr.add_argument(
        "--export-json",
        required=True,
        help="Path to notion_export.json from content_engine rerender",
    )
    carr.add_argument(
        "--publish-now",
        action="store_true",
        help="Publish immediately to Instagram (new post)",
    )
    carr.set_defaults(func=cmd_republish_carousel)

    acp = sub.add_parser("autocrosspost", help="Auto-publish due queue items to Instagram + YouTube.")
    acp.add_argument("--interval-sec", type=int, default=int(_env("UPLOAD_AUTPOST_INTERVAL_SEC", "30") or 30))
    acp.add_argument("--max-attempts", type=int, default=int(_env("IG_MAX_ATTEMPTS", "5") or 5))
    acp.add_argument(
        "--yt-privacy",
        default=_env("YOUTUBE_PRIVACY_STATUS", "unlisted") or "unlisted",
        choices=["private", "unlisted", "public"],
    )
    acp.add_argument(
        "--r2-autoupload",
        action="store_true",
        default=bool(int(_env("R2_AUTUPLOAD", "0") or "0")),
    )
    acp.add_argument(
        "--r2-delete-after-post",
        action="store_true",
        default=bool(int(_env("R2_DELETE_AFTER_POST", "0") or "0")),
    )
    acp.set_defaults(func=cmd_autocrosspost)

    mir = sub.add_parser("plan-mirror", help="Mirror planned slots from one platform to another.")
    mir.add_argument("--from", dest="from_platform", required=True, choices=["instagram", "youtube"])
    mir.add_argument("--to", dest="to_platform", required=True, choices=["instagram", "youtube"])
    mir.add_argument(
        "--times",
        required=True,
        help="Comma-separated HH:MM list for the target platform (e.g. 11:00,16:00,22:00)",
    )
    mir.add_argument(
        "--from-day",
        default="",
        help="YYYY-MM-DD: ignore source rows before this date (default: include all future)",
    )
    mir.add_argument("--dry-run", action="store_true", default=False)
    mir.set_defaults(func=cmd_plan_mirror)

    nds = sub.add_parser(
        "next-due-summary",
        help="Print one-line per platform with the next planned slot.",
    )
    nds.set_defaults(func=cmd_next_due_summary)

    ytoa = sub.add_parser(
        "youtube-oauth",
        help="One-time OAuth for YouTube upload token (default or --channel 7x7).",
    )
    ytoa.add_argument(
        "--channel",
        default=_env("YOUTUBE_CHANNEL", "default"),
        help="Channel profile: default (Grishkoff) or 7x7",
    )
    ytoa.add_argument(
        "--manual",
        action="store_true",
        help="No SSH tunnel: paste redirect URL from browser after Allow",
    )
    ytoa.set_defaults(func=cmd_youtube_oauth)

    ytwho = sub.add_parser("youtube-whoami", help="Show which YouTube channel the upload token uses.")
    ytwho.add_argument("--channel", default=_env("YOUTUBE_CHANNEL", "default"))
    ytwho.set_defaults(func=cmd_youtube_whoami)

    apy = sub.add_parser("autopost-yt", help="Auto-publish due YouTube items to YouTube Shorts.")
    apy.add_argument("--interval-sec", type=int, default=int(_env("UPLOAD_AUTPOST_INTERVAL_SEC", "30") or 30))
    apy.add_argument(
        "--channel",
        default=_env("YOUTUBE_CHANNEL", "default"),
        help="Channel profile: default or 7x7",
    )
    apy.add_argument(
        "--yt-privacy",
        default=_env("YOUTUBE_PRIVACY_STATUS", "unlisted") or "unlisted",
        choices=["private", "unlisted", "public"],
    )
    apy.set_defaults(func=cmd_autopost_yt)

    aptg = sub.add_parser(
        "autopost-tg-stories",
        help="Auto-publish due telegram_story items as Telegram Stories (@grishkoff).",
    )
    aptg.add_argument(
        "--interval-sec",
        type=int,
        default=int(_env("TG_STORIES_AUTOPOST_INTERVAL_SEC", "60") or 60),
    )
    aptg.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not publish; mark as skipped dry-run",
    )
    aptg.set_defaults(func=cmd_autopost_tg_stories)

    tgwho = sub.add_parser("tg-stories-whoami", help="Print Telegram session identity for Stories.")
    tgwho.set_defaults(func=cmd_tg_stories_whoami)

    appin = sub.add_parser("autopost-pinterest", help="Auto-publish due Pinterest queue items.")
    appin.add_argument("--interval-sec", type=int, default=int(_env("UPLOAD_AUTPOST_INTERVAL_SEC", "30") or 30))
    appin.add_argument("--max-attempts", type=int, default=int(_env("PINTEREST_MAX_ATTEMPTS", "3") or 3))
    appin.set_defaults(func=cmd_autopost_pinterest)

    pinb = sub.add_parser(
        "pinterest-boards",
        help="List boards (copy id → PINTEREST_BOARD_ID). Trial: use sandbox token + api.",
    )
    pinb.set_defaults(func=cmd_pinterest_boards)

    purl = sub.add_parser(
        "pinterest-oauth-url",
        help="Print OAuth URL with pins:write (Trial test-token UI is read-only).",
    )
    purl.add_argument("--scopes", default="", help="Override scopes (comma-separated)")
    purl.set_defaults(func=cmd_pinterest_oauth_url)

    ptok = sub.add_parser(
        "pinterest-oauth-token",
        help="Exchange ?code= from redirect for access_token + refresh_token.",
    )
    ptok.add_argument("--code", required=True, help="Authorization code from redirect URL")
    ptok.add_argument(
        "--token-file",
        default=_env("PINTEREST_TOKEN_FILE", "output/pinterest_oauth.json"),
    )
    ptok.set_defaults(func=cmd_pinterest_oauth_token)

    poauth = sub.add_parser(
        "pinterest-oauth",
        help="Full OAuth flow: browser Allow → redirect → token (for Standard access demo).",
    )
    poauth.add_argument("--scopes", default="", help="Override scopes (comma-separated)")
    poauth.add_argument(
        "--token-file",
        default=_env("PINTEREST_TOKEN_FILE", "output/pinterest_oauth.json"),
    )
    poauth.add_argument(
        "--port",
        type=int,
        default=int(_env("PINTEREST_OAUTH_PORT", "8765") or "8765"),
        help="Local redirect port (must match PINTEREST_REDIRECT_URI)",
    )
    poauth.add_argument(
        "--bind",
        default=_env("PINTEREST_OAUTH_BIND", "127.0.0.1"),
        help="Bind address (0.0.0.0 + ssh -L for remote server)",
    )
    poauth.add_argument(
        "--manual",
        action="store_true",
        help="Paste redirect URL instead of local server (no port forward)",
    )
    poauth.set_defaults(func=cmd_pinterest_oauth)

    pref = sub.add_parser(
        "pinterest-refresh",
        help="Refresh expired access token via PINTEREST_REFRESH_TOKEN; update .env.",
    )
    pref.add_argument(
        "--token-file",
        default=_env("PINTEREST_TOKEN_FILE", "output/pinterest_oauth.json"),
    )
    pref.add_argument("--env-file", default=_env("PINTEREST_ENV_FILE", ".env"))
    pref.add_argument(
        "--force",
        action="store_true",
        help="Refresh even if access token still looks valid",
    )
    pref.set_defaults(func=cmd_pinterest_refresh)

    pstat = sub.add_parser(
        "pinterest-status",
        help="Show connected account, boards, autopost config (demo integration proof).",
    )
    pstat.add_argument(
        "--refresh",
        action="store_true",
        help="Force OAuth access token refresh before status checks",
    )
    pstat.set_defaults(func=cmd_pinterest_status)

    po = sub.add_parser("post-once", help="Publish a single due item and exit (for testing).")
    po.add_argument("--max-attempts", type=int, default=int(_env("IG_MAX_ATTEMPTS", "5") or 5))
    po.add_argument(
        "--r2-autoupload",
        action="store_true",
        default=bool(int(_env("R2_AUTUPLOAD", "0") or "0")),
    )
    po.add_argument(
        "--r2-delete-after-post",
        action="store_true",
        default=bool(int(_env("R2_DELETE_AFTER_POST", "0") or "0")),
    )
    po.set_defaults(func=cmd_post_once)

    return p


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)
    logger.remove()
    try:
        logger.add(
            "app.log",
            rotation="5 MB",
            retention="10 days",
            backtrace=True,
            diagnose=True,
        )
    except (OSError, PermissionError):
        pass
    logger.add(lambda msg: print(msg, end=""), colorize=False)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())

