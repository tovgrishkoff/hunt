"""Auto-replies under our own Threads posts.

Jay Shambo commentator module: common prompt + commentator prompt.
Does not reply under other people's posts by default.
"""

from __future__ import annotations

import json
import os
import random
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from loguru import logger

from uploader.meta_accounts import MetaPublishTarget, threads_targets
from uploader.threads_products import approved_urls
from uploader.threads_prompts import commentator_system_prompt, strip_punct_dashes
from uploader.threads_publisher import ThreadsPublishError, publish_threads_reply


_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E0-\U0001F1FF"
    "]+",
    flags=re.UNICODE,
)
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)

SCHEMA = """
CREATE TABLE IF NOT EXISTS threads_replies_seen (
    comment_id   TEXT PRIMARY KEY,
    post_id      TEXT NOT NULL,
    author       TEXT NOT NULL DEFAULT '',
    text         TEXT NOT NULL DEFAULT '',
    decision     TEXT NOT NULL DEFAULT '',
    skip_reason  TEXT NOT NULL DEFAULT '',
    reply_text   TEXT NOT NULL DEFAULT '',
    reply_id     TEXT NOT NULL DEFAULT '',
    replied_at   TEXT NOT NULL DEFAULT '',
    error        TEXT NOT NULL DEFAULT '',
    seen_at      TEXT NOT NULL,
    published_at TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_threads_replies_decision
    ON threads_replies_seen(decision);
"""

def _system_prompt() -> str:
    return commentator_system_prompt(include_products=True)


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name).lower()
    if not raw:
        return default
    return raw not in {"0", "false", "no", "off"}


def is_low_effort(text: str, min_letters: int) -> bool:
    """True when the comment is an emoji or a one-word reaction."""
    cleaned = _EMOJI_RE.sub("", text or "")
    letters = re.sub(r"[^\w]", "", cleaned, flags=re.UNICODE)
    return len(letters) < int(min_letters)


def has_question(text: str) -> bool:
    return "?" in (text or "") or "？" in (text or "")


def clean_reply(
    text: str,
    *,
    max_chars: int = 480,
    allow_approved_links: bool = True,
) -> str:
    """Keep a single public reply. Strip markdown; keep only approved URLs."""
    body = (text or "").strip()
    body = body.replace("```json", "").replace("```", "").strip()
    approved = approved_urls() if allow_approved_links else set()

    def _keep_or_drop(match: re.Match[str]) -> str:
        url = match.group(0).rstrip(").,;")
        if url in approved or url.rstrip("/") in {u.rstrip("/") for u in approved}:
            return url
        return ""

    body = _URL_RE.sub(_keep_or_drop, body)
    body = strip_punct_dashes(body)
    body = re.sub(r"\s{2,}", " ", body).strip(" \n\t\"'")
    if len(body) > max_chars:
        body = body[: max_chars - 1].rstrip(" ,.;") + "…"
    return body


def answered_parent_ids(
    replies: list[dict[str, Any]],
    *,
    username: str,
) -> set[str]:
    """Parent ids we already answered from this account."""
    me = (username or "").strip().lower()
    answered: set[str] = set()
    if not me:
        return answered
    for item in replies:
        author = str(item.get("username") or "").strip().lower()
        if author != me:
            continue
        parent = item.get("replied_to") or {}
        parent_id = ""
        if isinstance(parent, dict):
            parent_id = str(parent.get("id") or "").strip()
        if parent_id:
            answered.add(parent_id)
    return answered


def extract_json_object(raw: str) -> str:
    """Pull a JSON object out of a Claude reply, including fenced blocks."""
    text = (raw or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", text)
    if fenced:
        return fenced.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return text


def parse_decision(raw: str) -> dict[str, Any]:
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("AI JSON is not an object")
    reply = bool(data.get("reply"))
    response = clean_reply(str(data.get("response") or ""))
    reason = str(data.get("reason") or "").strip()[:240]
    if reply and not response:
        reply = False
        response = ""
        reason = (reason + " | empty response").strip(" |")
    # Questions are optional now; clarifying question only when useful.
    # Non-approved links were already stripped; leftover foreign URLs invalidate.
    leftover = [
        u
        for u in _URL_RE.findall(response)
        if u.rstrip("/") not in {a.rstrip("/") for a in approved_urls()}
    ]
    if reply and leftover:
        reply = False
        response = ""
        reason = (reason + " | unapproved link").strip(" |")
    banned = ("госайкунд", "gosaikunda")
    if reply and any(b in response.lower() for b in banned):
        reply = False
        response = ""
        reason = (reason + " | banned route").strip(" |")
    return {"reply": reply, "response": response, "reason": reason}


@dataclass(frozen=True)
class ReplySettings:
    db_path: str
    lookback_hours: int
    max_posts: int
    max_per_tick: int
    max_per_post: int
    max_per_day: int
    min_letters: int
    dry_run: bool
    meta_index: int
    tz_name: str
    enabled: bool


def settings_from_env(*, tz_name: str, dry_run: bool | None = None) -> ReplySettings:
    flag = _env_bool("THREADS_REPLIES_DRY_RUN", False)
    if dry_run is not None:
        flag = dry_run
    return ReplySettings(
        db_path=_env("THREADS_REPLIES_DB", "output/threads_replies.sqlite3"),
        lookback_hours=max(1, _env_int("THREADS_REPLIES_LOOKBACK_HOURS", 72)),
        max_posts=max(1, _env_int("THREADS_REPLIES_MAX_POSTS", 12)),
        max_per_tick=max(1, _env_int("THREADS_REPLIES_MAX_PER_TICK", 2)),
        max_per_post=max(1, _env_int("THREADS_REPLIES_MAX_PER_POST", 1)),
        max_per_day=max(1, _env_int("THREADS_REPLIES_MAX_PER_DAY", 8)),
        min_letters=max(1, _env_int("THREADS_REPLIES_MIN_LETTERS", 8)),
        dry_run=flag,
        meta_index=_env_int("THREADS_REPLIES_META_INDEX", 2),
        tz_name=tz_name or "Europe/Moscow",
        enabled=_env_bool("THREADS_REPLIES_ENABLED", True),
    )


def connect(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    con = sqlite3.connect(db_path, timeout=30.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    return con


def already_seen(con: sqlite3.Connection, comment_id: str) -> bool:
    """Skip comments we already answered or deliberately ignored.

    Publish and AI errors stay retryable on the next tick.
    """
    row = con.execute(
        "SELECT decision FROM threads_replies_seen WHERE comment_id=?",
        (comment_id,),
    ).fetchone()
    if row is None:
        return False
    return str(row[0]) in {"reply", "skip"}


def replies_today(con: sqlite3.Connection, tz_name: str) -> int:
    tz = ZoneInfo(tz_name)
    start = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    row = con.execute(
        """
        SELECT COUNT(*) FROM threads_replies_seen
        WHERE decision='reply' AND replied_at>=?
        """,
        (start.isoformat(timespec="seconds"),),
    ).fetchone()
    return int(row[0] if row else 0)


def record_seen(
    con: sqlite3.Connection,
    *,
    comment_id: str,
    post_id: str,
    author: str,
    text: str,
    decision: str,
    skip_reason: str = "",
    reply_text: str = "",
    reply_id: str = "",
    replied_at: str = "",
    error: str = "",
    published_at: str = "",
) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    con.execute(
        """
        INSERT INTO threads_replies_seen (
            comment_id, post_id, author, text, decision, skip_reason,
            reply_text, reply_id, replied_at, error, seen_at, published_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(comment_id) DO UPDATE SET
            decision=excluded.decision,
            skip_reason=excluded.skip_reason,
            reply_text=excluded.reply_text,
            reply_id=excluded.reply_id,
            replied_at=excluded.replied_at,
            error=excluded.error,
            seen_at=excluded.seen_at
        """,
        (
            comment_id,
            post_id,
            author,
            text[:1000],
            decision,
            skip_reason[:240],
            reply_text[:500],
            reply_id,
            replied_at,
            error[:500],
            now,
            published_at,
        ),
    )
    con.commit()


def _api_get(client: httpx.Client, url: str, token: str, **params: str) -> dict[str, Any]:
    response = client.get(url, params={**params, "access_token": token})
    if response.status_code >= 400:
        raise ThreadsPublishError(
            f"Threads GET {url} failed ({response.status_code}): {response.text[:300]}"
        )
    data = response.json()
    if not isinstance(data, dict):
        raise ThreadsPublishError(f"Threads GET {url} returned non-object")
    return data


def _threads_me(client: httpx.Client, base: str, token: str) -> str:
    data = _api_get(client, f"{base}/me", token, fields="id,username")
    return str(data.get("username") or "").strip()


def _list_posts(
    client: httpx.Client,
    base: str,
    user_id: str,
    token: str,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    data = _api_get(
        client,
        f"{base}/{user_id}/threads",
        token,
        fields="id,text,timestamp,permalink",
        limit=str(limit),
    )
    rows = data.get("data") or []
    return [row for row in rows if isinstance(row, dict) and row.get("id")]


def _list_replies(
    client: httpx.Client,
    base: str,
    post_id: str,
    token: str,
) -> list[dict[str, Any]]:
    fields = "id,text,username,timestamp,has_replies,is_reply,replied_to"
    data = _api_get(
        client,
        f"{base}/{post_id}/replies",
        token,
        fields=fields,
    )
    rows = [row for row in (data.get("data") or []) if isinstance(row, dict)]
    nested_budget = 5
    for row in list(rows):
        if nested_budget <= 0 or not row.get("has_replies"):
            continue
        nested_budget -= 1
        time.sleep(random.uniform(0.6, 1.4))
        try:
            convo = _api_get(
                client,
                f"{base}/{row['id']}/conversation",
                token,
                fields=fields,
            )
        except ThreadsPublishError as exc:
            logger.warning(
                f"[threads-replies] conversation failed reply={row.get('id')}: {exc}"
            )
            continue
        for child in convo.get("data") or []:
            if isinstance(child, dict) and child.get("id"):
                rows.append(child)
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for row in rows:
        comment_id = str(row.get("id") or "")
        if not comment_id or comment_id in seen:
            continue
        seen.add(comment_id)
        unique.append(row)
    return unique


def _within_lookback(timestamp: str, *, hours: int, now: datetime) -> bool:
    if not timestamp:
        return False
    try:
        published = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return False
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    return published >= now - timedelta(hours=hours)


def _select_target(meta_index: int) -> MetaPublishTarget | None:
    targets = [t for t in threads_targets() if t.index == meta_index] or threads_targets()
    return targets[0] if targets else None


def _draft_reply(
    *,
    comment_text: str,
    author: str,
    post_text: str,
) -> dict[str, Any]:
    from anthropic import Anthropic

    api_key = _env("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    model = _env(
        "THREADS_REPLIES_CLAUDE_MODEL",
        _env("CLAUDE_MODEL", "claude-sonnet-4-5-20250929"),
    )
    user_msg = (
        f"Пост:\n{(post_text or '')[:700]}\n\n"
        f"Комментарий @{author}:\n{comment_text}\n\n"
        "Ответь голосом Григория по сути этого комментария. "
        "Уточняющий вопрос только если он реально помогает. "
        "Ссылку ставь только при запросе поездки или явной релевантности "
        "и только из утверждённых URL карточек продуктов."
    )
    client = Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=400,
        system=_system_prompt(),
        messages=[{"role": "user", "content": user_msg}],
    )
    parts = [block.text for block in message.content if getattr(block, "type", "") == "text"]
    raw = "\n".join(parts).strip()
    if not raw:
        raise RuntimeError("Claude returned empty content")
    logger.info(f"[threads-replies] llm=claude model={model}")
    return parse_decision(extract_json_object(raw))


def run_once(cfg: ReplySettings) -> dict[str, int]:
    """Scan recent posts and reply to a few unanswered comments."""
    stats = {
        "posts": 0,
        "comments": 0,
        "replied": 0,
        "skipped": 0,
        "errors": 0,
    }
    if not cfg.enabled:
        logger.info("[threads-replies] disabled (THREADS_REPLIES_ENABLED=0)")
        return stats

    target = _select_target(cfg.meta_index)
    if target is None:
        logger.warning("[threads-replies] no Threads publish target")
        return stats

    token = (target.threads_token or target.page_token or "").strip()
    user_id = (target.threads_user_id or "").strip()
    if not token or not user_id:
        logger.warning(f"[threads-replies] account={target.label} missing token")
        return stats

    api_ver = _env("THREADS_API_VERSION", "v1.0")
    base = f"https://graph.threads.net/{api_ver}"
    now = datetime.now(timezone.utc)
    con = connect(cfg.db_path)
    try:
        sent_today = replies_today(con, cfg.tz_name)
        if sent_today >= cfg.max_per_day:
            logger.info(
                f"[threads-replies] daily cap reached {sent_today}/{cfg.max_per_day}"
            )
            return stats

        with httpx.Client(timeout=40.0) as client:
            username = _threads_me(client, base, token)
            posts = _list_posts(
                client, base, user_id, token, limit=cfg.max_posts
            )
            stats["posts"] = len(posts)
            logger.info(
                f"[threads-replies] account=@{username} posts={len(posts)} "
                f"dry_run={cfg.dry_run} today={sent_today}/{cfg.max_per_day}"
            )
            room = min(cfg.max_per_tick, cfg.max_per_day - sent_today)
            for post in posts:
                if room <= 0:
                    break
                post_id = str(post.get("id") or "")
                post_text = str(post.get("text") or "")
                time.sleep(random.uniform(0.8, 1.8))
                try:
                    replies = _list_replies(client, base, post_id, token)
                except ThreadsPublishError as exc:
                    logger.warning(
                        f"[threads-replies] account=@{username} post={post_id} "
                        f"list failed: {exc}"
                    )
                    stats["errors"] += 1
                    continue
                answered = answered_parent_ids(replies, username=username)
                fresh = [
                    item
                    for item in replies
                    if _within_lookback(
                        str(item.get("timestamp") or ""),
                        hours=cfg.lookback_hours,
                        now=now,
                    )
                ]
                fresh.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)
                posted_here = 0
                for item in fresh:
                    if room <= 0 or posted_here >= cfg.max_per_post:
                        break
                    comment_id = str(item.get("id") or "")
                    author = str(item.get("username") or "")
                    text = str(item.get("text") or "").strip()
                    published_at = str(item.get("timestamp") or "")
                    stats["comments"] += 1
                    if not comment_id or already_seen(con, comment_id):
                        continue
                    if author.lower() == username.lower():
                        record_seen(
                            con,
                            comment_id=comment_id,
                            post_id=post_id,
                            author=author,
                            text=text,
                            decision="skip",
                            skip_reason="self",
                            published_at=published_at,
                        )
                        stats["skipped"] += 1
                        continue
                    if comment_id in answered:
                        record_seen(
                            con,
                            comment_id=comment_id,
                            post_id=post_id,
                            author=author,
                            text=text,
                            decision="skip",
                            skip_reason="already_replied",
                            published_at=published_at,
                        )
                        stats["skipped"] += 1
                        continue
                    if is_low_effort(text, cfg.min_letters):
                        record_seen(
                            con,
                            comment_id=comment_id,
                            post_id=post_id,
                            author=author,
                            text=text,
                            decision="skip",
                            skip_reason="low_effort",
                            published_at=published_at,
                        )
                        stats["skipped"] += 1
                        continue
                    try:
                        decision = _draft_reply(
                            comment_text=text,
                            author=author,
                            post_text=post_text,
                        )
                    except Exception as exc:
                        logger.exception(
                            f"[threads-replies] account=@{username} "
                            f"ai failed comment={comment_id}"
                        )
                        record_seen(
                            con,
                            comment_id=comment_id,
                            post_id=post_id,
                            author=author,
                            text=text,
                            decision="error",
                            skip_reason="ai_error",
                            error=str(exc),
                            published_at=published_at,
                        )
                        stats["errors"] += 1
                        continue
                    reply_text = str(decision.get("response") or "")
                    if not decision.get("reply") or not reply_text:
                        record_seen(
                            con,
                            comment_id=comment_id,
                            post_id=post_id,
                            author=author,
                            text=text,
                            decision="skip",
                            skip_reason=str(decision.get("reason") or "ai_skip"),
                            published_at=published_at,
                        )
                        stats["skipped"] += 1
                        continue
                    if cfg.dry_run:
                        logger.info(
                            f"[threads-replies][DRY] account=@{username} "
                            f"author=@{author} comment={text[:80]!r} "
                            f"reply={reply_text[:160]!r}"
                        )
                        stats["replied"] += 1
                        room -= 1
                        posted_here += 1
                        continue
                    try:
                        time.sleep(random.uniform(40.0, 95.0))
                        published = publish_threads_reply(
                            target=target,
                            reply_to_id=comment_id,
                            text=reply_text,
                        )
                    except ThreadsPublishError as exc:
                        logger.error(
                            f"[threads-replies] account=@{username} "
                            f"publish failed comment={comment_id}: {exc}"
                        )
                        record_seen(
                            con,
                            comment_id=comment_id,
                            post_id=post_id,
                            author=author,
                            text=text,
                            decision="error",
                            skip_reason="publish_error",
                            reply_text=reply_text,
                            error=str(exc),
                            published_at=published_at,
                        )
                        stats["errors"] += 1
                        continue
                    replied_at = datetime.now(ZoneInfo(cfg.tz_name)).isoformat(
                        timespec="seconds"
                    )
                    record_seen(
                        con,
                        comment_id=comment_id,
                        post_id=post_id,
                        author=author,
                        text=text,
                        decision="reply",
                        reply_text=reply_text,
                        reply_id=published.post_id,
                        replied_at=replied_at,
                        published_at=published_at,
                    )
                    logger.success(
                        f"[threads-replies] account=@{username} author=@{author} "
                        f"action=reply reply_id={published.post_id}"
                    )
                    stats["replied"] += 1
                    room -= 1
                    posted_here += 1
    finally:
        con.close()
    return stats


def run_loop(cfg: ReplySettings, *, interval_sec: int) -> None:
    interval = max(60, int(interval_sec))
    logger.info(
        f"[threads-replies] loop started interval={interval}s dry_run={cfg.dry_run}"
    )
    while True:
        try:
            stats = run_once(cfg)
            logger.info(f"[threads-replies] tick {stats}")
        except Exception:
            logger.exception("[threads-replies] tick failed")
        time.sleep(interval + random.uniform(5.0, 25.0))
