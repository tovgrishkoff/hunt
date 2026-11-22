#!/usr/bin/env python3
"""Add admin/priority usernames as Telegram contacts on all working accounts.

So story feed includes @grishkoff and activity can view/like his stories
even when there was no prior dialog. Priority list is grishkoff-only.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import sys
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from loguru import logger
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.contacts import AddContactRequest

load_dotenv(ROOT / ".env")

DEFAULT_PRIORITY = ["grishkoff"]


def _load_priority() -> List[str]:
    niche_path = ROOT / "config" / "niches" / "bali.json"
    try:
        data = json.loads(niche_path.read_text(encoding="utf-8"))
        act = data.get("activity") or {}
        users = act.get("story_view_priority_usernames") or DEFAULT_PRIORITY
        return [str(u).strip().lstrip("@").lower() for u in users if u]
    except Exception:
        return list(DEFAULT_PRIORITY)


def _parse_proxy(proxy: str):
    if not proxy:
        return None
    u = urlparse(proxy)
    if not u.hostname or not u.port:
        return None
    scheme = (u.scheme or "http").lower()
    if scheme.startswith("socks"):
        import socks

        return (socks.SOCKS5, u.hostname, int(u.port), True, u.username, u.password)
    return {
        "proxy_type": "http",
        "addr": u.hostname,
        "port": int(u.port),
        "username": u.username,
        "password": u.password,
    }


def _load_accounts() -> List[Dict[str, Any]]:
    path = ROOT / "accounts_config.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    out: List[Dict[str, Any]] = []
    for a in rows:
        name = a.get("session_name")
        if not name or not a.get("string_session") or not a.get("proxy"):
            continue
        if not a.get("api_id") or not a.get("api_hash"):
            continue
        out.append(a)
    return out


async def seed_one(acc: Dict[str, Any], priority: List[str]) -> Dict[str, Any]:
    session = acc["session_name"]
    proxy = _parse_proxy(acc.get("proxy") or "")
    client = TelegramClient(
        StringSession(acc["string_session"]),
        int(acc["api_id"]),
        acc["api_hash"],
        proxy=proxy,
    )
    result = {"session": session, "ok": [], "skip": [], "fail": []}
    try:
        await asyncio.wait_for(client.connect(), timeout=40)
        if not await client.is_user_authorized():
            result["fail"].append("not_authorized")
            return result
        me = await client.get_me()
        my_username = (getattr(me, "username", None) or "").lower()
        for uname in priority:
            if uname == my_username:
                result["skip"].append(uname)
                continue
            try:
                entity = await client.get_entity(uname)
                await client(
                    AddContactRequest(
                        id=await client.get_input_entity(entity),
                        first_name=(getattr(entity, "first_name", None) or uname)[:64],
                        last_name=(getattr(entity, "last_name", None) or "")[:64],
                        phone="",
                        add_phone_privacy_exception=False,
                    )
                )
                result["ok"].append(uname)
                logger.info("{}: added @{}", session, uname)
            except Exception as e:
                result["fail"].append(f"{uname}:{type(e).__name__}")
                logger.warning("{}: @{} -> {}", session, uname, e)
            await asyncio.sleep(random.uniform(1.5, 3.5))
    except Exception as e:
        result["fail"].append(f"connect:{type(e).__name__}")
        logger.error("{}: {}", session, e)
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass
    return result


async def main() -> int:
    priority = _load_priority()
    accounts = _load_accounts()
    only = os.getenv("ONLY_SESSION", "").strip()
    if only:
        accounts = [a for a in accounts if a.get("session_name") == only]
    logger.info(
        "Seeding priority contacts {} on {} accounts",
        priority,
        len(accounts),
    )
    summary = {"accounts": 0, "ok": 0, "fail": 0}
    for i, acc in enumerate(accounts):
        summary["accounts"] += 1
        res = await seed_one(acc, priority)
        if res["ok"]:
            summary["ok"] += 1
        if res["fail"]:
            summary["fail"] += 1
        if i + 1 < len(accounts):
            await asyncio.sleep(random.uniform(4.5, 9.5))
    logger.info("Done: {}", summary)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
