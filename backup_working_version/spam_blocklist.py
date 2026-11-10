"""Persistent spam blocklist fed by the Telegram «Отметить как спам» button.

Stored under data/ so bali-bot and bali-user-monitor share the same file via mount.
Matching is by normalized text hash (sender-independent) so near-identical posts
from new accounts are also blocked from lead search.
"""

from __future__ import annotations

import hashlib
import html
import json
import logging
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_DEFAULT_PATHS = (
    Path("data/user_spam_blocklist.json"),
    Path("/app/data/user_spam_blocklist.json"),
    Path("user_spam_blocklist.json"),
)

_LEAD_TEXT_RE = re.compile(
    r"📄\s*(?:<b>)?Сообщение:?\s*(?:</b>)?\s*\n(?P<body>.*?)(?:\n\s*\n|\n👤|\n💬|\n🔗|\n🔑|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_SENDER_RE = re.compile(
    r"👤\s*(?P<name>[^\n(@]+?)(?:\s*\(@(?P<username>[a-zA-Z0-9_]+)\))?\s*(?:\n|$)",
    re.UNICODE,
)


def _resolve_path(path: Optional[Path] = None) -> Path:
    if path is not None:
        return path
    for candidate in _DEFAULT_PATHS:
        if candidate.parent.exists():
            return candidate
    return _DEFAULT_PATHS[0]


def normalize_spam_text(text: str) -> str:
    """Normalize lead text for stable hashing across tiny typo/spacing changes."""
    if not text:
        return ""
    cleaned = html.unescape(text)
    cleaned = cleaned.replace("\ufeff", " ")
    cleaned = cleaned.lower()
    # Common spam typos / obfuscation around housing offers
    cleaned = (
        cleaned.replace("жалье", "жилье")
        .replace("жальё", "жильё")
        .replace("придоставля", "предоставля")
        .replace("предоставляеться", "предоставляется")
    )
    cleaned = re.sub(r"https?://\S+|t\.me/\S+", " ", cleaned)
    cleaned = re.sub(r"[^\w\sа-яё]+", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def text_fingerprint(text: str) -> str:
    normalized = normalize_spam_text(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def extract_lead_text_from_notification(notification: str) -> Optional[str]:
    """Pull the original lead body from a bot notification message."""
    if not notification:
        return None
    text = html.unescape(notification)
    match = _LEAD_TEXT_RE.search(text)
    if not match:
        return None
    body = match.group("body").strip()
    return body or None


def extract_sender_from_notification(notification: str) -> Dict[str, str]:
    if not notification:
        return {}
    match = _SENDER_RE.search(html.unescape(notification))
    if not match:
        return {}
    out: Dict[str, str] = {}
    name = (match.group("name") or "").strip()
    username = (match.group("username") or "").strip()
    if name:
        out["sender_name"] = name
    if username:
        out["sender_username"] = username.lstrip("@").lower()
    return out


def _empty_store() -> Dict[str, Any]:
    return {
        "version": 1,
        "updated_at": None,
        "entries": [],  # list of dicts
        "text_hashes": [],  # denormalized for fast membership
        "sender_usernames": [],
        "sender_names": [],
    }


def load_blocklist(path: Optional[Path] = None) -> Dict[str, Any]:
    store_path = _resolve_path(path)
    try:
        with store_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return _empty_store()
        data.setdefault("entries", [])
        data.setdefault("text_hashes", [])
        data.setdefault("sender_usernames", [])
        data.setdefault("sender_names", [])
        return data
    except FileNotFoundError:
        return _empty_store()
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to load spam blocklist %s: %s", store_path, exc)
        return _empty_store()


def save_blocklist(data: Dict[str, Any], path: Optional[Path] = None) -> Path:
    store_path = _resolve_path(path)
    store_path.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.utcnow().isoformat() + "Z"
    tmp = store_path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    tmp.replace(store_path)
    return store_path


def add_spam_entry(
    *,
    message_text: str,
    message_id: Optional[str] = None,
    marked_by: Optional[str] = None,
    sender_username: Optional[str] = None,
    sender_name: Optional[str] = None,
    path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Persist a user-marked spam lead so future identical texts are filtered."""
    fingerprint = text_fingerprint(message_text)
    if not fingerprint or not normalize_spam_text(message_text):
        return {"ok": False, "reason": "empty_text"}

    with _LOCK:
        data = load_blocklist(path)
        entry = {
            "text_hash": fingerprint,
            "message_id": message_id,
            "marked_by": str(marked_by) if marked_by is not None else None,
            "sender_username": (sender_username or "").strip().lstrip("@").lower() or None,
            "sender_name": (sender_name or "").strip() or None,
            "sample": normalize_spam_text(message_text)[:240],
            "created_at": datetime.utcnow().isoformat() + "Z",
        }

        hashes: List[str] = list(data.get("text_hashes") or [])
        if fingerprint not in hashes:
            hashes.append(fingerprint)
        data["text_hashes"] = hashes

        entries: List[Dict[str, Any]] = list(data.get("entries") or [])
        # de-dupe by hash
        entries = [e for e in entries if e.get("text_hash") != fingerprint]
        entries.append(entry)
        # keep last 2000
        data["entries"] = entries[-2000:]

        if entry["sender_username"]:
            users = set(data.get("sender_usernames") or [])
            users.add(entry["sender_username"])
            data["sender_usernames"] = sorted(users)
        if entry["sender_name"]:
            names = set(data.get("sender_names") or [])
            names.add(entry["sender_name"].lower())
            data["sender_names"] = sorted(names)

        saved = save_blocklist(data, path)
        logger.warning(
            "Spam blocklist +1 hash=%s by=%s file=%s",
            fingerprint[:12],
            marked_by,
            saved,
        )
        return {"ok": True, "text_hash": fingerprint, "path": str(saved)}


def is_text_blocked(message_text: str, path: Optional[Path] = None) -> bool:
    fingerprint = text_fingerprint(message_text)
    if not fingerprint:
        return False
    data = load_blocklist(path)
    return fingerprint in set(data.get("text_hashes") or [])


def is_sender_blocked(
    *,
    sender_username: Optional[str] = None,
    sender_name: Optional[str] = None,
    path: Optional[Path] = None,
) -> Optional[str]:
    data = load_blocklist(path)
    if sender_username:
        uname = sender_username.strip().lstrip("@").lower()
        if uname and uname in set(data.get("sender_usernames") or []):
            return f"blocklist_username=@{uname}"
    if sender_name:
        name = sender_name.strip().lower()
        if name and name in set(data.get("sender_names") or []):
            return f"blocklist_name={name}"
    return None
