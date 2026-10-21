#!/usr/bin/env python3
"""One-shot live Threads root post for operator review."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from loguru import logger

from uploader.db import connect, record_attempt, upsert_item
from uploader.meta_accounts import load_meta_targets
from uploader.threads_products import require_avatar_for_autopublish
from uploader.threads_publisher import publish_threads_text
from uploader.threads_text_autopost import (
    _recent_captions,
    generate_threads_text,
    threads_text_meta_index,
)


def _resolve_db_path() -> str:
    raw = os.environ.get("DB_PATH") or "output/queue.db"
    candidates = [
        Path(raw),
        Path("/app/output/queue.db"),
        Path("/home/tovgrishkoff/resolve_batch_render/output/queue.db"),
        Path("/home/tovgrishkoff/.cache/resolve_batch_render/output/queue.db"),
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    return str(candidates[0])


def main() -> None:
    require_avatar_for_autopublish()
    tz = ZoneInfo("Europe/Moscow")
    db_path = _resolve_db_path()
    logger.info(f"db_path={db_path}")
    con = connect(db_path)
    history = _recent_captions(con, limit=20)

    kind = os.environ.get("LIVE_TEST_KIND", "discussion").strip() or "discussion"
    geo = {
        "key": "kailas",
        "label": "Кайлас / Тибет",
        "angles": (
            "самостоятельная организация vs готовый маршрут, высота, "
            "подготовка 2027 без продажи 2026"
        ),
    }

    logger.info(f"generating kind={kind}")
    text = generate_threads_text(kind=kind, avoid_openings=history, geo=geo)
    print("--- TEXT ---")
    print(text)
    print("-------------")
    print(f"chars={len(text)}")

    idx = threads_text_meta_index()
    targets = [t for t in load_meta_targets() if t.index == idx and t.publish_threads]
    if not targets:
        raise SystemExit(f"No Threads target for META_{idx}")
    target = targets[0]
    logger.info(f"publishing account={target.label} user={target.threads_user_id}")

    result = publish_threads_text(target=target, text=text)
    logger.success(f"post_id={result.post_id} container={result.container_id}")

    permalink = ""
    token = (target.threads_token or target.page_token or "").strip()
    api_ver = os.environ.get("THREADS_API_VERSION", "v1.0").strip() or "v1.0"
    base = f"https://graph.threads.net/{api_ver}"
    with httpx.Client(timeout=40.0) as client:
        response = client.get(
            f"{base}/{result.post_id}",
            params={
                "fields": "id,permalink,text,timestamp,username",
                "access_token": token,
            },
        )
        print(f"permalink_http={response.status_code}")
        data = response.json()
        print("post_meta=" + json.dumps(data, ensure_ascii=False)[:1000])
        permalink = str(data.get("permalink") or "").strip()

    if not permalink:
        permalink = "https://www.threads.net/@grishkoff_travel"

    now = datetime.now(tz=tz).isoformat(timespec="seconds")
    post_local_id = f"TT-LIVE-{uuid.uuid4().hex[:8].upper()}"
    upsert_item(
        con,
        reel_id=post_local_id,
        scheduled_at=now,
        video_path="",
        caption=text,
        status="posted",
        source="threads_text_live_test",
        source_id=f"{kind}:kailas:live_test",
        platform="threads_text",
    )
    record_attempt(
        con,
        reel_id=post_local_id,
        scheduled_at=now,
        status="posted",
        ig_media_id=result.post_id,
        last_api_response=json.dumps(
            {
                "threads_post_id": result.post_id,
                "permalink": permalink,
                "kind": kind,
                "live_test": True,
            },
            ensure_ascii=False,
        ),
        last_error="",
    )

    out = {
        "local_id": post_local_id,
        "threads_post_id": result.post_id,
        "permalink": permalink,
        "account": "@grishkoff_travel",
        "kind": kind,
        "text": text,
    }
    for path in (
        Path("/tmp/threads_live_test.json"),
        Path("/app/output/threads_live_test.json"),
        Path("/home/tovgrishkoff/resolve_batch_render/output/threads_live_test.json"),
    ):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            logger.warning(f"could not write {path}: {exc}")

    print("=== DONE ===")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
