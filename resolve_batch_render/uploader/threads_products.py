"""Jay Shambo product cards and avatar gate for Threads modules."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from loguru import logger

_DEFAULT_PATH = Path(__file__).resolve().parent / "data" / "threads_products.json"


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def products_config_path() -> Path:
    raw = _env("THREADS_PRODUCTS_PATH")
    return Path(raw) if raw else _DEFAULT_PATH


@lru_cache(maxsize=4)
def load_products_config(path: str | None = None) -> dict[str, Any]:
    cfg_path = Path(path) if path else products_config_path()
    with cfg_path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid products config: {cfg_path}")
    return data


def reload_products_config() -> dict[str, Any]:
    load_products_config.cache_clear()
    return load_products_config()


def avatar_source() -> dict[str, str]:
    """Resolve avatar path/id from env; never invent a filesystem path."""
    cfg = load_products_config()
    avatar = cfg.get("avatar") if isinstance(cfg.get("avatar"), dict) else {}
    path_key = str(avatar.get("env_path_key") or "THREADS_AVATAR_PATH")
    id_key = str(avatar.get("env_id_key") or "THREADS_AVATAR_ID")
    path = _env(path_key)
    avatar_id = _env(id_key)
    notion_page_id = str(avatar.get("notion_page_id") or "")
    return {
        "path": path,
        "id": avatar_id,
        "notion_page_id": notion_page_id,
        "resolved": path or avatar_id,
    }


def avatar_available() -> bool:
    src = avatar_source()
    if src["id"]:
        return True
    path = src["path"]
    if not path:
        return False
    return Path(path).expanduser().is_file()


def require_avatar_for_autopublish() -> None:
    """Stop new root-post generation when avatar source is missing."""
    cfg = load_products_config()
    avatar = cfg.get("avatar") if isinstance(cfg.get("avatar"), dict) else {}
    required = bool(avatar.get("required_for_autopublish", True))
    if not required:
        return
    if avatar_available():
        return
    src = avatar_source()
    msg = (
        "THREADS avatar unavailable: set THREADS_AVATAR_PATH or THREADS_AVATAR_ID. "
        f"notion_page_id={src.get('notion_page_id') or 'n/a'}. "
        "Do not invent a path; halt new autopublish drafts and notify operator."
    )
    logger.error(f"[threads-products] {msg}")
    raise RuntimeError(msg)


def active_products(*, include_unavailable: bool = False) -> list[dict[str, Any]]:
    cfg = load_products_config()
    products = cfg.get("products") or []
    out: list[dict[str, Any]] = []
    for item in products:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "").strip().lower()
        if status == "unavailable" and not include_unavailable:
            continue
        out.append(item)
    return sorted(out, key=lambda p: int(p.get("priority") or 99))


def product_by_id(product_id: str) -> dict[str, Any] | None:
    want = (product_id or "").strip()
    for item in active_products(include_unavailable=True):
        if str(item.get("id") or "") == want:
            return item
    return None


def product_url(product_id: str, *, fallback: str = "") -> str:
    item = product_by_id(product_id)
    if not item:
        return fallback
    return str(item.get("url") or fallback).strip()


def approved_urls() -> set[str]:
    urls: set[str] = set()
    for item in active_products(include_unavailable=True):
        url = str(item.get("url") or "").strip()
        if url:
            urls.add(url.rstrip("/"))
            urls.add(url)
    catalog = product_url("catalog")
    if catalog:
        urls.add(catalog.rstrip("/"))
        urls.add(catalog)
    # Always allow Lead Hunt bot link in replies when interest is shown.
    lead = product_url("lead_hunbot", fallback="https://t.me/Lead_Hunbot")
    if lead:
        urls.add(lead.rstrip("/"))
        urls.add(lead)
    return urls


def banned_route_labels() -> list[str]:
    cfg = load_products_config()
    labels: list[str] = []
    for item in cfg.get("banned_routes") or []:
        if not isinstance(item, dict):
            continue
        for label in item.get("labels") or []:
            text = str(label).strip()
            if text:
                labels.append(text)
    return labels


def products_prompt_block() -> str:
    """Compact operator-facing product card dump for LLM context."""
    lines: list[str] = ["АКТУАЛЬНЫЕ КАРТОЧКИ ПРОДУКТОВ:"]
    for item in active_products(include_unavailable=True):
        status = item.get("status") or "unknown"
        formats = ", ".join(item.get("formats") or []) or "n/a"
        price = item.get("price")
        price_s = "не задана оператором" if price in (None, "") else str(price)
        notes = "; ".join(str(n) for n in (item.get("notes") or [])[:4])
        lines.append(
            f"- id={item.get('id')} | {item.get('name')} | status={status} | "
            f"formats={formats} | price={price_s} | url={item.get('url')}"
        )
        if notes:
            lines.append(f"  notes: {notes}")
    banned = banned_route_labels()
    if banned:
        lines.append(
            "ЗАПРЕЩЁННЫЕ МАРШРУТЫ (не продвигать): " + ", ".join(banned)
        )
    lines.append(
        "Статусы: unavailable=не продвигать; announcement=без обещания брони; "
        "interest_collection=приглашать оставить интерес; booking_open=подтверждённые условия."
    )
    return "\n".join(lines)


def flagship_product_ids_for_day() -> list[str]:
    """Seasonal push: Bali NYE/retreats first, India next, Kailas rarer."""
    preferred = [
        "bali_premium_ocean",
        "bali_sacred",
        "bali_weekend",
        "india_private_8march_2027",
        "kailas_lhasa_2027",
    ]
    have = {str(p.get("id")) for p in active_products()}
    return [pid for pid in preferred if pid in have]
