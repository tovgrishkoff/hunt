#!/usr/bin/env python3
"""Pull Threads insights and summarize what performs for views / engagement."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import httpx


def avg(xs: list[float]) -> float:
    return round(sum(xs) / len(xs), 1) if xs else 0.0


def main() -> None:
    token = (os.environ.get("META_2_THREADS_TOKEN") or "").strip()
    uid = (os.environ.get("META_2_THREADS_USER_ID") or "").strip()
    api = (os.environ.get("THREADS_API_VERSION") or "v1.0").strip() or "v1.0"
    if not token or not uid:
        raise SystemExit("META_2_THREADS_TOKEN / META_2_THREADS_USER_ID required")

    base = f"https://graph.threads.net/{api}"
    client = httpx.Client(timeout=40)
    since = int(datetime(2026, 9, 20, tzinfo=timezone.utc).timestamp())
    until = int(datetime(2026, 10, 22, tzinfo=timezone.utc).timestamp())

    print("=== USER INSIGHTS ===")
    for metrics in (
        "views,likes,replies,reposts,quotes,followers_count",
        "clicks",
    ):
        r = client.get(
            f"{base}/{uid}/threads_insights",
            params={
                "metric": metrics,
                "since": since,
                "until": until,
                "access_token": token,
            },
        )
        print(metrics, r.status_code)
        print(r.text[:3000])
        print("---")

    db = Path("output/upload_queue.sqlite3")
    if not db.exists():
        db = Path("/app/output/upload_queue.sqlite3")
    con = sqlite3.connect(str(db))
    rows = con.execute(
        """
        SELECT reel_id, source_id, scheduled_at, caption, ig_media_id, status
        FROM upload_queue
        WHERE platform='threads_text'
          AND status IN ('posted','deleted')
          AND ig_media_id != ''
          AND scheduled_at >= '2026-09-20'
        ORDER BY scheduled_at DESC
        """
    ).fetchall()
    print("media_rows", len(rows))

    results: list[dict] = []
    errors = 0
    for reel_id, source_id, scheduled_at, caption, mid, status in rows:
        r = client.get(
            f"{base}/{mid}/insights",
            params={
                "metric": "views,likes,replies,reposts,quotes,shares",
                "access_token": token,
            },
        )
        metrics: dict = {}
        if r.status_code == 200:
            for item in r.json().get("data", []):
                vals = item.get("values") or []
                metrics[item.get("name")] = vals[0].get("value") if vals else None
        else:
            errors += 1
            metrics["error"] = f"{r.status_code}:{r.text[:160]}"
        cap = caption or ""
        low = cap.lower()
        sid = source_id or ""
        results.append(
            {
                "reel_id": reel_id,
                "source_id": sid,
                "scheduled_at": scheduled_at,
                "status": status,
                "len": len(cap),
                "has_url": bool(re.search(r"https?://", cap)),
                "has_question": "?" in cap,
                "topic": (
                    "kailas"
                    if (
                        "кайлас" in low
                        or "кор" in low
                        or "тибет" in low
                        or "kailas" in sid
                    )
                    else "bali"
                    if ("бали" in low or "bali" in sid)
                    else "india"
                    if ("инди" in low or "гоа" in low or "india" in sid)
                    else "other"
                ),
                "opening": re.split(r"[.!\n]", cap.strip())[0][:90]
                if cap.strip()
                else "",
                **metrics,
            }
        )
        time.sleep(0.12)

    ok = [x for x in results if isinstance(x.get("views"), (int, float))]
    ok.sort(key=lambda x: x.get("views") or 0, reverse=True)
    print("fetched", len(results), "ok", len(ok), "errors", errors)

    print("\nTOP 15 by views")
    for x in ok[:15]:
        print(
            json.dumps(
                {
                    k: x.get(k)
                    for k in (
                        "scheduled_at",
                        "source_id",
                        "topic",
                        "views",
                        "likes",
                        "replies",
                        "reposts",
                        "quotes",
                        "shares",
                        "len",
                        "has_url",
                        "has_question",
                        "opening",
                    )
                },
                ensure_ascii=False,
            )
        )

    print("\nBOTTOM 10 by views")
    for x in ok[-10:]:
        print(
            json.dumps(
                {
                    k: x.get(k)
                    for k in (
                        "scheduled_at",
                        "source_id",
                        "topic",
                        "views",
                        "likes",
                        "replies",
                        "len",
                        "has_url",
                        "has_question",
                        "opening",
                    )
                },
                ensure_ascii=False,
            )
        )

    print("\n=== AGG by topic ===")
    by: dict[str, list] = defaultdict(list)
    for x in ok:
        by[x["topic"]].append(x)
    for t, xs in sorted(by.items(), key=lambda kv: -avg([i["views"] for i in kv[1]])):
        print(
            t,
            "n=",
            len(xs),
            "avg_views=",
            avg([i["views"] for i in xs]),
            "med_views=",
            sorted(i["views"] for i in xs)[len(xs) // 2],
            "avg_likes=",
            avg([i.get("likes") or 0 for i in xs]),
            "avg_replies=",
            avg([i.get("replies") or 0 for i in xs]),
            "url%",
            round(100 * sum(1 for i in xs if i["has_url"]) / len(xs), 1),
            "q%",
            round(100 * sum(1 for i in xs if i["has_question"]) / len(xs), 1),
            "avg_len=",
            avg([i["len"] for i in xs]),
        )

    print("\n=== AGG by kind ===")
    byk: dict[str, list] = defaultdict(list)
    for x in ok:
        sid = x["source_id"]
        if sid.startswith("promo"):
            pref = "promo"
        elif sid.startswith("discussion"):
            pref = "discussion"
        elif sid.startswith("story"):
            pref = "story"
        elif sid.startswith(("tip", "geo_tip", "warmup", "relocation", "news")):
            pref = "warmup/tip"
        else:
            pref = sid[:24] or "empty"
        byk[pref].append(x)
    for t, xs in sorted(byk.items(), key=lambda kv: -avg([i["views"] for i in kv[1]])):
        print(
            t,
            "n=",
            len(xs),
            "avg_views=",
            avg([i["views"] for i in xs]),
            "avg_likes=",
            avg([i.get("likes") or 0 for i in xs]),
            "avg_replies=",
            avg([i.get("replies") or 0 for i in xs]),
            "url%",
            round(100 * sum(1 for i in xs if i["has_url"]) / len(xs), 1),
        )

    print("\n=== URL vs no URL ===")
    for label, pred in (("with_url", True), ("no_url", False)):
        xs = [i for i in ok if i["has_url"] is pred]
        print(
            label,
            "n=",
            len(xs),
            "avg_views=",
            avg([i["views"] for i in xs]),
            "avg_likes=",
            avg([i.get("likes") or 0 for i in xs]),
            "avg_replies=",
            avg([i.get("replies") or 0 for i in xs]),
        )

    print("\n=== Question vs no ===")
    for label, pred in (("with_q", True), ("no_q", False)):
        xs = [i for i in ok if i["has_question"] is pred]
        print(
            label,
            "n=",
            len(xs),
            "avg_views=",
            avg([i["views"] for i in xs]),
            "avg_replies=",
            avg([i.get("replies") or 0 for i in xs]),
        )

    print("\n=== Length buckets ===")
    for lo, hi, name in (
        (0, 180, "<=180"),
        (181, 260, "181-260"),
        (261, 400, "261-400"),
        (401, 9999, "400+"),
    ):
        xs = [i for i in ok if lo <= i["len"] <= hi]
        if not xs:
            continue
        print(
            name,
            "n=",
            len(xs),
            "avg_views=",
            avg([i["views"] for i in xs]),
            "avg_replies=",
            avg([i.get("replies") or 0 for i in xs]),
        )

    print("\n=== By hour ===")
    byh: dict[str, list] = defaultdict(list)
    for x in ok:
        m = re.search(r"T(\d{2}):", x["scheduled_at"] or "")
        if m:
            byh[m.group(1)].append(x)
    for h, xs in sorted(byh.items()):
        print(h, "n=", len(xs), "avg_views=", avg([i["views"] for i in xs]))

    out = Path("output/threads_insights_analysis.json")
    out.write_text(
        json.dumps({"results": results, "ok_count": len(ok)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("wrote", out)


if __name__ == "__main__":
    main()
