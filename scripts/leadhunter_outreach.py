#!/usr/bin/env python3
"""Lead Hunter → безопасные ЛС (прогрев 1/день).

Команды:
  python3 scripts/leadhunter_outreach.py ingest
  python3 scripts/leadhunter_outreach.py plan [--limit N]
  python3 scripts/leadhunter_outreach.py send [--live] [--limit N]
  python3 scripts/leadhunter_outreach.py followup [--live] [--limit N]
  python3 scripts/leadhunter_outreach.py status

Первый контакт: человеческий ответ на запрос, без ссылки на бота.
После ответа человека: AI-диалог (followup) — живые ответы и мягкий прогрев к Lead Hunter.

Базовые правила:
  - получатели: monitoring и/или manual @username
  - не писать повторно тем, кому уже писали (окно months)
  - пропускать давно не заходивших
  - паузы с полом min_delay_floor_sec
  - только в рабочие часы timezone
  - {имя} в тексте
  - PeerFlood/ban: пауза только этого writer → join+сторис; живые продолжают
  - глобальный halt только если не осталось живых writers; авто-снятие через N часов
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import random
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    PeerFloodError,
    UserPrivacyRestrictedError,
    UserBannedInChannelError,
    InputUserDeactivatedError,
    UsernameNotOccupiedError,
    UsernameInvalidError,
)
from telethon.sessions import StringSession
from telethon.tl.types import (
    User,
    UserStatusOffline,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CFG = PROJECT_ROOT / "config" / "leadhunter_outreach.json"
load_dotenv(PROJECT_ROOT / ".env")

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from leadhunter_dialog_ai import (  # noqa: E402
    dialog_cfg,
    fallback_soft_pitch,
    generate_reply,
    is_opt_out,
    resolve_offer,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("leadhunter_outreach")

TERMINAL_DIALOG_STAGES = {"won", "opt_out", "closed", "privacy", "dead_peer", "error_stop"}
ACTIVE_DIALOG_STAGES = {
    None,
    "first_touch",
    "dialog",
    "soft_offer",
    "followup_sent",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _tzinfo(cfg: Dict[str, Any]) -> timezone:
    # Asia/Makassar = UTC+8 fixed; keep stdlib-only.
    name = str(cfg.get("timezone") or "Asia/Makassar")
    if name in {"Asia/Makassar", "Asia/Singapore", "Asia/Hong_Kong"}:
        return timezone(timedelta(hours=8))
    if name in {"Asia/Kolkata", "Asia/Calcutta"}:
        return timezone(timedelta(hours=5, minutes=30))
    return timezone(timedelta(hours=8))


def _rules(cfg: Dict[str, Any]) -> Dict[str, Any]:
    return cfg.get("rules") or {}


def _within_work_hours(cfg: Dict[str, Any], when: Optional[datetime] = None) -> bool:
    rules = _rules(cfg)
    wh = rules.get("work_hours") or {}
    if not wh.get("enabled", True):
        return True
    when = when or _now()
    local = when.astimezone(_tzinfo(cfg))
    start = int(wh.get("start_hour", 9))
    end = int(wh.get("end_hour", 21))
    return start <= local.hour < end


def _clamp_delay_sec(cfg: Dict[str, Any], lo: float, hi: float) -> Tuple[float, float]:
    rules = _rules(cfg)
    floor = float(rules.get("min_delay_floor_sec", 15))
    # Prefer rules defaults if limits missing/too aggressive.
    default_lo = float(rules.get("default_delay_min_sec", 60))
    default_hi = float(rules.get("default_delay_max_sec", 120))
    lo = float(lo if lo is not None else default_lo)
    hi = float(hi if hi is not None else default_hi)
    lo = max(floor, lo)
    hi = max(lo, hi)
    return lo, hi


def _contacted_recently(state: Dict[str, Any], ckey: str, months: float) -> bool:
    row = (state.get("contacted") or {}).get(ckey)
    if not row:
        return False
    at = _parse_ts(row.get("at") if isinstance(row, dict) else None)
    if not at:
        return True
    return (_now() - at) <= timedelta(days=float(months) * 30.4375)


def _prune_contacted(state: Dict[str, Any], months: float) -> None:
    contacted = state.get("contacted") or {}
    keep = {}
    ttl = timedelta(days=float(months) * 30.4375)
    for k, v in contacted.items():
        at = _parse_ts(v.get("at") if isinstance(v, dict) else None)
        if at and (_now() - at) <= ttl:
            keep[k] = v
        elif not at:
            keep[k] = v
    state["contacted"] = keep


def _load_manual_recipients(cfg: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for u in (cfg.get("recipients") or {}).get("manual_usernames") or []:
        s = str(u).strip().lstrip("@").lower()
        if s:
            out.append(s)
    path = cfg.get("manual_recipients_path")
    if path and Path(path).exists():
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            out.append(line.lstrip("@").lower())
    # unique preserve order
    seen = set()
    uniq = []
    for u in out:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq


def _is_complaint_result(result: str) -> bool:
    return result in {"peer_flood", "banned", "floodwait", "floodwait_stop"}


def _recovery(cfg: Dict[str, Any]) -> Dict[str, Any]:
    return cfg.get("recovery") or {}


def _auto_resume_hours(cfg: Dict[str, Any]) -> float:
    return float(_recovery(cfg).get("auto_resume_hours") or 6)


def _peer_flood_pause_hours(cfg: Dict[str, Any]) -> float:
    return float((cfg.get("limits") or {}).get("pause_hours_on_peer_flood") or 6)


def _maybe_auto_resume_halt(cfg: Dict[str, Any], state: Dict[str, Any]) -> bool:
    """Снять send_halted после auto_resume_hours, чтобы живые writers снова слали."""
    halted = state.get("send_halted")
    if not halted:
        return False
    hours = _auto_resume_hours(cfg)
    at = _parse_ts(halted.get("at") if isinstance(halted, dict) else None)
    if at is None or (_now() - at) >= timedelta(hours=hours):
        logger.warning(
            "AUTO-RESUME: clearing send_halted after %.1fh (was=%s)",
            hours,
            halted,
        )
        state.pop("send_halted", None)
        state["consecutive_complaints"] = 0
        state["last_auto_resume_at"] = _now().isoformat()
        return True
    return False


def _bali_accounts_config_paths(cfg: Dict[str, Any]) -> List[Path]:
    raw = _recovery(cfg).get("bali_accounts_config_path") or str(
        PROJECT_ROOT / "bali_accounts_config.json"
    )
    root = Path(raw)
    paths = [root, root.parent / "config" / "bali_accounts_config.json"]
    # unique preserve order
    out: List[Path] = []
    for p in paths:
        if p not in out:
            out.append(p)
    return out


def _restart_account_manager() -> None:
    try:
        subprocess.run(
            ["docker-compose", "restart", "account-manager"],
            cwd=str(PROJECT_ROOT),
            timeout=90,
            check=False,
            capture_output=True,
            text=True,
        )
        logger.info("account-manager restart requested after demote→join")
    except Exception as e:
        logger.warning("account-manager restart failed: %s", e)


def _demote_writer_to_join(
    cfg: Dict[str, Any],
    state: Dict[str, Any],
    session: str,
    reason: str,
) -> None:
    """Пауза writer + перевод в join_accounts (сторис/вступления), без инициации ЛС."""
    hours = _peer_flood_pause_hours(cfg)
    _pause_account(state, session, hours, reason)
    until = _now() + timedelta(hours=hours)
    state.setdefault("demoted_to_join", {})[session] = {
        "at": _now().isoformat(),
        "until": until.isoformat(),
        "reason": reason,
        "mode": "join_stories",
    }
    if not bool(_recovery(cfg).get("demote_to_join_on_complaint", True)):
        return

    changed = False
    for path in _bali_accounts_config_paths(cfg):
        if not path.exists():
            continue
        try:
            data = _load_json(path)
        except Exception as e:
            logger.warning("demote: cannot read %s: %s", path, e)
            continue
        joins = [s for s in (data.get("join_accounts") or []) if s]
        if session not in joins:
            joins.append(session)
            data["join_accounts"] = joins
            changed = True
        excl = [s for s in (data.get("excluded_accounts") or []) if s]
        if session not in excl:
            excl.append(session)
            data["excluded_accounts"] = excl
            changed = True
        # Marketer читает только allowed_accounts — убрать оттуда на всякий.
        allowed = [s for s in (data.get("allowed_accounts") or []) if s and s != session]
        if allowed != list(data.get("allowed_accounts") or []):
            data["allowed_accounts"] = allowed
            changed = True
        if changed:
            _save_json(path, data)
            logger.warning(
                "Demoted %s → join+stories in %s (%s, pause %.1fh)",
                session,
                path,
                reason,
                hours,
            )
    if changed and bool(_recovery(cfg).get("restart_account_manager_on_demote", True)):
        _restart_account_manager()


def _healthy_writers(cfg: Dict[str, Any], state: Dict[str, Any]) -> List[str]:
    accounts = load_accounts(cfg)
    out: List[str] = []
    for session in cfg.get("writers") or []:
        if session not in accounts:
            continue
        if _is_account_paused(state, session):
            continue
        if not accounts[session].get("string_session") or not accounts[session].get("proxy"):
            continue
        out.append(session)
    return out


def _note_send_result(
    state: Dict[str, Any],
    cfg: Dict[str, Any],
    result: str,
    writer: Optional[str] = None,
) -> bool:
    """Обновить streak жалоб. True = остановить текущий run (не обязательно навсегда)."""
    if result in {"sent", "dry_run", "privacy", "dead_peer", "peer_is_bot", "waiting_reply"}:
        state["consecutive_complaints"] = 0
        return False

    if not _is_complaint_result(result):
        return bool(state.get("send_halted"))

    if writer:
        _demote_writer_to_join(cfg, state, writer, result)

    state["consecutive_complaints"] = int(state.get("consecutive_complaints") or 0) + 1
    healthy = _healthy_writers(cfg, state)
    if healthy:
        logger.warning(
            "Complaint %s on %s — demoted to join/stories; healthy writers continue: %s",
            result,
            writer or "?",
            ", ".join(healthy),
        )
        # Не жжём остальных: мягко выходим из текущего run, без вечного halt.
        return True

    hours = _auto_resume_hours(cfg)
    state["send_halted"] = {
        "at": _now().isoformat(),
        "reason": f"no healthy writers left after {result}",
        "last_result": result,
        "auto_resume_hours": hours,
        "last_writer": writer,
    }
    logger.error(
        "MAILING HALTED: no healthy writers (last=%s). Auto-resume in %.1fh",
        result,
        hours,
    )
    return True


def _user_inactive_too_long(entity: Any, days: int) -> bool:
    """True if Telegram last-seen clearly older than N days."""
    if days <= 0 or not isinstance(entity, User):
        return False
    status = getattr(entity, "status", None)
    if isinstance(status, UserStatusOffline):
        was = getattr(status, "was_online", None)
        if was is None:
            return False
        if was.tzinfo is None:
            was = was.replace(tzinfo=timezone.utc)
        return (_now() - was) > timedelta(days=days)
    return False



def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _parse_ts(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


def _day_key(ts: Optional[datetime] = None) -> str:
    ts = ts or _now()
    # Asia/Makassar operational day
    local = ts.astimezone(timezone(timedelta(hours=8)))
    return local.strftime("%Y-%m-%d")


def _parse_http_proxy(proxy_url: str) -> Tuple[Any, ...]:
    import socks

    u = urlparse(proxy_url)
    if not u.hostname or not u.port:
        raise ValueError(f"bad proxy: {proxy_url}")
    return (
        socks.HTTP,
        u.hostname,
        int(u.port),
        True,
        u.username,
        u.password,
    )


def load_cfg(path: Path = DEFAULT_CFG) -> Dict[str, Any]:
    return _load_json(path)


def load_state(cfg: Dict[str, Any]) -> Dict[str, Any]:
    path = Path(cfg["state_path"])
    if not path.exists():
        return {
            "ingested_ids": {},
            "queue": [],
            "sent": {},
            "contacted": {},
            "paused_accounts": {},
            "daily": {},
            "stats": {},
        }
    return _load_json(path)


def save_state(cfg: Dict[str, Any], state: Dict[str, Any]) -> None:
    _save_json(Path(cfg["state_path"]), state)


def load_accounts(cfg: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    rows = _load_json(Path(cfg["accounts_config_path"]))
    if isinstance(rows, dict):
        rows = rows.get("accounts") or []
    return {a["session_name"]: a for a in rows if a.get("session_name")}


def _snip(text: str, limit: int = 140) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    if len(t) <= limit:
        return t
    return t[: limit - 1].rstrip() + "…"




_PLACE_LOCATIVE = {
    "сесех": "Сесехе",
    "ченгу": "Ченгу",
    "чангу": "Чангу",
    "кута": "Куте",
    "убуд": "Убуде",
    "будук": "Будуке",
    "переренан": "Переренане",
    "сеими": "Сеими",
    "бо пхут": "Бо Пхуте",
}


def _place_locative(raw: str) -> str:
    key = re.sub(r"\s+", " ", raw.strip().lower())
    return _PLACE_LOCATIVE.get(key, raw.strip().title())

def _first_name(sender_name: Optional[str]) -> str:
    if not sender_name:
        return ""
    # drop emoji-heavy prefixes roughly
    clean = re.sub(r"[^\w\s\-а-яА-ЯёЁ]+", " ", sender_name, flags=re.UNICODE)
    parts = [p for p in clean.split() if p]
    return parts[0] if parts else ""


def _is_offer(lead: Dict[str, Any]) -> bool:
    msg_type = (lead.get("message_type") or "").upper()
    if msg_type == "ПРЕДЛОЖЕНИЕ":
        return True
    if msg_type == "ПОИСК":
        return False
    text = (lead.get("message_text") or "").lower()
    offer_markers = (
        "сдам",
        "сдаётся",
        "сдается",
        "продаю",
        "цена:",
        "млн/мес",
        "$/мес",
        "за сутки",
        "в наличии",
        "предлагаю",
        "услуги",
        "прайс",
    )
    search_markers = (
        "ищу",
        "ищем",
        "нужен",
        "нужна",
        "нужно",
        "подскажите",
        "кто знает",
        "looking for",
        "need ",
        "арендовать",
        "сниму",
    )
    if any(m in text for m in offer_markers) and not any(m in text for m in search_markers):
        return True
    return False


def _topic_from_lead(lead: Dict[str, Any]) -> str:
    """Short human topic, not a pasted ad block."""
    raw = (lead.get("message_text") or "").strip()
    text = re.sub(r"[🏡🌴📍💵💰🔥✅•|]+", " ", raw)
    text = re.sub(r"\s+", " ", text).strip(" .,-")
    low = text.lower()

    # Pattern-based compact topics for common intents.
    if re.search(r"ищу\s+сосед", low):
        place = ""
        m = re.search(r"(сесех|ченгу|чангу|кута|убуд|будук|переренан|сеими)", low)
        if m:
            place = f" в {_place_locative(m.group(1))}"
        return f"соседку на виллу{place}"
    if re.search(r"(сдам|сдаётся|сдается|таунхаус|вилл[аыу]|квартир)", low) and _is_offer(lead):
        place = ""
        m = re.search(r"(сесех|ченгу|чангу|кута|убуд|будук|переренан|сеими|бо\s*пхут)", low)
        if m:
            place = f" в {_place_locative(m.group(1))}"
        kind = "жильё"
        if "таунхаус" in low:
            kind = "таунхаус"
        elif "вилл" in low:
            kind = "виллу"
        elif "квартир" in low:
            kind = "квартиру"
        return f"{kind}{place} в аренду"
    if re.search(r"банковск\w*\s+счет|открыть\s+счет", low):
        return "как открыть банковский счёт по турвизе"
    if re.search(r"байк|scooter|nmax|xmax", low):
        return "аренду байка"
    if re.search(r"экскур|тур(а|ы|истов)?", low) and "виз" not in low:
        return "экскурсии / локальные туры"

    niches = [str(n).strip() for n in (lead.get("niches") or []) if str(n).strip()]
    # Take a short verb phrase if present.
    m = re.search(
        r"((?:ищу|ищем|нужен|нужна|нужно|подскажите|looking for)[^.!?]{0,60})",
        text,
        flags=re.I,
    )
    if m:
        return _snip(m.group(1).strip(" ,;-"), 70)
    first = re.split(r"[.!?\n]", text)[0].strip()
    first = _snip(first, 60)
    if niches and first:
        return _snip(f"{niches[0].lower()}: {first}", 70)
    return _snip(first or (niches[0] if niches else "ваш запрос"), 70)


def _questions_for_lead(lead: Dict[str, Any]) -> Tuple[str, str]:
    niches = " ".join(str(n).lower() for n in (lead.get("niches") or []))
    text = (lead.get("message_text") or "").lower()
    blob = f"{niches} {text}"
    if re.search(r"банковск|счет|счёт|тур\s*виз", blob):
        return ("в каком городе сейчас", "нужен счет для себя или ещё для кого-то")
    if any(k in blob for k in ("жил", "вилл", "квартир", "аренда", "rent", "сосед", "таунхаус")):
        if _is_offer(lead):
            return ("на долгий срок или short stay", "какой портрет жильца вам важнее")
        return ("на какой срок", "какой бюджет примерно")
    if any(k in blob for k in ("байк", "мото", "scooter", "nmax", "xmax")):
        return ("на сколько дней или месяцев", "какой бюджет в сутки")
    if any(k in blob for k in ("работ", "вакан", "job", "ищу человека")):
        return ("какой формат занятости", "какая ставка или бюджет")
    if any(k in blob for k in ("экскур", "ретрит")):
        return ("какие даты", "один или компанией")
    if _is_offer(lead):
        return ("кому нужен отклик в первую очередь", "что для вас важнее: скорость или точность")
    return ("что важнее всего сейчас", "в какие сроки нужно решение")


def _format_copy(template: str, cfg: Dict[str, Any], lead: Dict[str, Any]) -> str:
    name = _first_name(lead.get("sender_name"))
    # Avoid awkward "Привет, IV!" from brand/agency names
    if name and (len(name) <= 2 or name.isupper() or name.lower() in {"iv", "vj", "ok", "hi"}):
        name = ""
    name_part = f", {name}" if name else ""
    chat = lead.get("chat_title") or ""
    chat_part = f" в «{chat}»" if chat else ""
    q1, q2 = _questions_for_lead(lead)
    values = {
        "name_part": name_part,
        "chat_part": chat_part,
        "topic": _topic_from_lead(lead),
        "snippet": _snip(str(lead.get("message_text") or ""), 90),
        "q1": q1,
        "q2": q2,
        "bot_url": cfg.get("bot_url") or "https://t.me/Lead_Hunbot",
        "niches": ", ".join(lead.get("niches") or []) or "ваша тема",
        "имя": name,
        "name": name,
    }
    body = str(template)
    # Support literal {имя} without breaking str.format.
    body = body.replace("{имя}", "{имя_placeholder}")
    values["имя_placeholder"] = name
    body = body.format(**values)
    return body.replace("—", " - ").replace("–", "-")


def _first_touch_stage(lead: Dict[str, Any]) -> str:
    return "first_touch_offer" if _is_offer(lead) else "first_touch_search"


def render_dm(
    cfg: Dict[str, Any],
    lead: Dict[str, Any],
    variant_id: Optional[str] = None,
    *,
    stage: str = "first_touch",
) -> Tuple[str, str]:
    copy_cfg = cfg.get("copy") or {}
    if stage == "first_touch":
        stage = _first_touch_stage(lead)
    variants = copy_cfg.get(stage) or copy_cfg.get("first_touch") or copy_cfg.get("variants") or []
    if not variants:
        raise RuntimeError(f"no copy.{stage} in config")
    if variant_id:
        variant = next((v for v in variants if v.get("id") == variant_id), variants[0])
    else:
        variant = random.choice(variants)
    body = _format_copy(str(variant["text"]), cfg, lead)
    # First touch must not pitch the bot link.
    if stage.startswith("first_touch"):
        bot_url = str(cfg.get("bot_url") or "")
        bot_user = str(cfg.get("bot_username") or "")
        low = body.lower()
        if bot_url and bot_url.lower() in low:
            raise RuntimeError("first_touch copy contains bot_url")
        if bot_user and bot_user.lower() in low:
            raise RuntimeError("first_touch copy contains bot username")
        if "lead hunter" in low or "leadhunter" in low:
            raise RuntimeError("first_touch copy must not pitch Lead Hunter")
    return str(variant.get("id") or "unknown"), body


def _lead_contact_key(lead: Dict[str, Any]) -> Optional[str]:
    sid = lead.get("sender_id")
    if sid:
        return f"id:{int(sid)}"
    uname = (lead.get("sender_username") or "").strip().lstrip("@").lower()
    if uname:
        return f"user:{uname}"
    return None


def _is_account_paused(state: Dict[str, Any], session: str) -> Optional[str]:
    row = (state.get("paused_accounts") or {}).get(session)
    if not row:
        return None
    until = _parse_ts(row.get("until") if isinstance(row, dict) else None)
    if until and until > _now():
        return str(row.get("reason") or "paused")
    return None


def _daily_count(state: Dict[str, Any], session: str) -> int:
    day = _day_key()
    return int((((state.get("daily") or {}).get(day) or {}).get(session) or 0))


def _bump_daily(state: Dict[str, Any], session: str) -> None:
    day = _day_key()
    daily = state.setdefault("daily", {})
    bucket = daily.setdefault(day, {})
    bucket[session] = int(bucket.get(session) or 0) + 1


def _pause_account(state: Dict[str, Any], session: str, hours: float, reason: str) -> None:
    until = _now() + timedelta(hours=hours)
    state.setdefault("paused_accounts", {})[session] = {
        "until": until.isoformat(),
        "reason": reason,
        "at": _now().isoformat(),
    }


def lead_passes_filters(cfg: Dict[str, Any], lead: Dict[str, Any]) -> Tuple[bool, str]:
    filters = cfg.get("filters") or {}
    if lead.get("manual"):
        if not (lead.get("sender_username") or lead.get("sender_id")):
            return False, "no_contact"
        return True, "ok"
    text = (lead.get("message_text") or "").strip()
    if len(text) < int(filters.get("min_text_chars") or 25):
        return False, "text_too_short"
    if len(text) > int(filters.get("max_text_chars") or 500):
        return False, "text_too_long"

    uname = (lead.get("sender_username") or "").strip().lstrip("@").lower()
    for bad in filters.get("deny_username_substrings") or []:
        if uname and bad.lower() in uname:
            return False, f"denied_username:{bad}"

    if filters.get("require_username_or_id", True):
        if not uname and not lead.get("sender_id"):
            return False, "no_contact"

    if filters.get("require_enriched"):
        # Prefer typed/niche rows, but username-only monitor payloads are contactable.
        if not (
            lead.get("message_type")
            or lead.get("niches")
            or lead.get("sender_id")
            or lead.get("sender_username")
        ):
            return False, "not_enriched"

    allowed_types = [t.upper() for t in (filters.get("allowed_message_types") or [])]
    msg_type = (lead.get("message_type") or "").upper()
    # Old payloads have no message_type — allow them but prefer typed later in scoring
    if allowed_types and msg_type and msg_type not in allowed_types:
        return False, f"type:{msg_type}"

    created = _parse_ts(lead.get("created_at"))
    if not created:
        return False, "no_ts"
    limits = cfg.get("limits") or {}
    age = _now() - created
    if age < timedelta(minutes=float(limits.get("min_lead_age_minutes") or 5)):
        return False, "too_fresh"
    if age > timedelta(hours=float(limits.get("max_lead_age_hours") or 36)):
        return False, "too_old"
    return True, "ok"


def score_lead(lead: Dict[str, Any]) -> float:
    score = 0.0
    msg_type = (lead.get("message_type") or "").upper()
    if msg_type == "ПОИСК":
        score += 3.0
    elif msg_type == "ПРЕДЛОЖЕНИЕ":
        score += 2.5
    if lead.get("sender_username"):
        # Strong boost: username resolve is safer than raw sender_id.
        score += 3.0
    if lead.get("sender_id"):
        score += 1.0
    if lead.get("niches"):
        score += min(2.0, 0.4 * len(lead["niches"]))
    # Thin payloads have no message_type — nudge seekers above rental spam.
    if not msg_type:
        text_l = (lead.get("message_text") or "").lower()
        seek_kw = (
            "ищу",
            "ищем",
            "looking for",
            "need ",
            "нужен",
            "нужна",
            "нужно",
            "сниму",
            "снимем",
            "хочу аренд",
            "кто знает",
            "подскажите",
        )
        offer_kw = (
            "сдам",
            "сдаём",
            "for rent",
            "в наличии",
            "available",
            "прокат",
            "we also provide",
        )
        if any(k in text_l for k in seek_kw):
            score += 2.0
        if any(k in text_l for k in offer_kw):
            score -= 1.5
    # fresher is better within window
    created = _parse_ts(lead.get("created_at"))
    if created:
        hours = max(0.1, (_now() - created).total_seconds() / 3600.0)
        score += max(0.0, 2.0 - hours / 12.0)
    return score


def cmd_ingest(cfg: Dict[str, Any], state: Dict[str, Any]) -> int:
    months = float((_rules(cfg).get("do_not_rewrite_months") or 6))
    _prune_contacted(state, months)

    sources = set(((cfg.get("recipients") or {}).get("sources")) or ["monitoring"])
    entries: Dict[str, Any] = {}
    if "monitoring" in sources:
        path = Path(cfg["lead_payloads_path"])
        data = _load_json(path)
        entries.update(data.get("entries") or {})

    # Manual usernames become lightweight leads if not already queued/contacted.
    if "manual" in sources:
        for uname in _load_manual_recipients(cfg):
            lead_id = f"manual:{uname}"
            if lead_id in entries:
                continue
            entries[lead_id] = {
                "message_text": f"Ручной контакт @{uname}",
                "sender_username": uname,
                "sender_name": uname,
                "message_type": "ПОИСК",
                "niches": ["manual"],
                "created_at": _now().isoformat().replace("+00:00", "Z"),
                "manual": True,
            }

    ingested = state.setdefault("ingested_ids", {})
    contacted = state.get("contacted") or {}
    queue = state.setdefault("queue", [])
    queued_ids = {q.get("lead_id") for q in queue}

    added = 0
    skipped: Dict[str, int] = {}

    def bump(reason: str) -> None:
        skipped[reason] = skipped.get(reason, 0) + 1

    for lead_id, raw in entries.items():
        if lead_id in ingested or lead_id in queued_ids:
            bump("already")
            continue
        lead = dict(raw)
        lead["lead_id"] = lead_id
        ok, reason = lead_passes_filters(cfg, lead)
        if not ok:
            # too_fresh: do not consume id, retry on next ingest
            if reason != "too_fresh":
                ingested[lead_id] = {"at": _now().isoformat(), "skip": reason}
            bump(reason)
            continue
        ckey = _lead_contact_key(lead)
        months = float((_rules(cfg).get("do_not_rewrite_months") or 6))
        if ckey and _contacted_recently(state, ckey, months):
            ingested[lead_id] = {"at": _now().isoformat(), "skip": "already_contacted"}
            bump("already_contacted")
            continue
        item = {
            "lead_id": lead_id,
            "status": "new",
            "score": score_lead(lead),
            "lead": lead,
            "queued_at": _now().isoformat(),
        }
        queue.append(item)
        ingested[lead_id] = {"at": _now().isoformat(), "queued": True}
        added += 1

    queue.sort(key=lambda x: float(x.get("score") or 0), reverse=True)
    state["queue"] = queue
    save_state(cfg, state)
    logger.info("ingest: added=%s queue=%s skips=%s", added, len(queue), skipped)
    return 0


def _writer_day_cap(cfg: Dict[str, Any], session: str) -> int:
    """Per-account DM cap; falls back to global max_dm_per_day_per_account."""
    limits = cfg.get("limits") or {}
    default_cap = int(limits.get("max_dm_per_day_per_account") or 3)
    per_account = limits.get("per_account_max_dm") or {}
    if isinstance(per_account, dict) and session in per_account:
        try:
            return max(0, int(per_account[session]))
        except (TypeError, ValueError):
            return default_cap
    return default_cap


def plan_batch(cfg: Dict[str, Any], state: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
    accounts = load_accounts(cfg)
    limits = cfg.get("limits") or {}
    run_cap = min(limit, int(limits.get("max_dm_per_run") or 5))
    planned: List[Dict[str, Any]] = []
    writer_load: Dict[str, int] = {}

    for item in list(state.get("queue") or []):
        if len(planned) >= run_cap:
            break
        if item.get("status") not in {"new", "planned"}:
            continue
        lead = item.get("lead") or {}
        ok, reason = lead_passes_filters(cfg, lead)
        if not ok:
            item["status"] = "skipped"
            item["skip_reason"] = reason
            continue
        ckey = _lead_contact_key(lead)
        if not ckey:
            item["status"] = "skipped"
            item["skip_reason"] = "no_contact"
            continue
        months = float((_rules(cfg).get("do_not_rewrite_months") or 6))
        if ckey and _contacted_recently(state, ckey, months):
            item["status"] = "skipped"
            item["skip_reason"] = "already_contacted"
            continue

        # choose writer with remaining daily room including this plan
        chosen = None
        for session in sorted(
            cfg.get("writers") or [],
            key=lambda s: _daily_count(state, s) + writer_load.get(s, 0),
        ):
            if session not in accounts:
                continue
            if _is_account_paused(state, session):
                continue
            day_cap = _writer_day_cap(cfg, session)
            used = _daily_count(state, session) + writer_load.get(session, 0)
            if used >= day_cap:
                continue
            if not accounts[session].get("string_session") or not accounts[session].get("proxy"):
                continue
            chosen = session
            break
        if not chosen:
            break

        variant_id, text = render_dm(cfg, lead)
        plan = {
            "lead_id": item["lead_id"],
            "writer": chosen,
            "contact_key": ckey,
            "variant_id": variant_id,
            "text": text,
            "lead": lead,
        }
        item["status"] = "planned"
        item["writer"] = chosen
        item["variant_id"] = variant_id
        item["planned_at"] = _now().isoformat()
        writer_load[chosen] = writer_load.get(chosen, 0) + 1
        planned.append(plan)

    save_state(cfg, state)
    return planned


def cmd_plan(cfg: Dict[str, Any], state: Dict[str, Any], limit: int) -> int:
    cmd_ingest(cfg, state)
    state = load_state(cfg)
    planned = plan_batch(cfg, state, limit=limit)
    logger.info("plan: %s message(s)", len(planned))
    for i, row in enumerate(planned, 1):
        lead = row["lead"]
        print(f"\n=== {i}. writer={row['writer']} lead={row['lead_id'][:10]}… ===")
        print(
            f"to=@{lead.get('sender_username') or '-'} id={lead.get('sender_id')} "
            f"type={lead.get('message_type')} niches={lead.get('niches')}"
        )
        print(f"chat={lead.get('chat_title')}")
        print(f"orig={_snip(str(lead.get('message_text') or ''), 180)}")
        print("--- DM ---")
        print(row["text"])
    return 0


def _client(acc: Dict[str, Any]) -> TelegramClient:
    return TelegramClient(
        StringSession(acc["string_session"]),
        int(acc["api_id"]),
        acc["api_hash"],
        proxy=_parse_http_proxy(acc["proxy"]),
    )


async def _resolve_peer(
    client: TelegramClient,
    lead: Dict[str, Any],
    contact_key: Optional[str] = None,
):
    # Prefer username first: raw sender_id often isn't in the local entity cache
    # and repeated get_entity(id) is a common PeerFlood trigger.
    uname = (lead.get("sender_username") or "").strip().lstrip("@")
    key = (contact_key or "").strip()
    if not uname and key.startswith("user:"):
        uname = key.split(":", 1)[1].strip().lstrip("@")
    if uname:
        try:
            return await client.get_entity(uname)
        except Exception as e:
            logger.warning("resolve by username failed: %s", e)

    if lead.get("sender_id"):
        try:
            return await client.get_entity(int(lead["sender_id"]))
        except Exception as e:
            logger.warning("resolve by id failed: %s", e)

    if key.startswith("user:"):
        try:
            return await client.get_entity(key.split(":", 1)[1])
        except Exception as e:
            logger.warning("resolve contact_key username failed: %s", e)
    if key.startswith("id:"):
        try:
            uid = int(key.split(":", 1)[1])
            return await client.get_entity(uid)
        except Exception as e:
            logger.warning("resolve contact_key id failed: %s", e)

    # Last resort: find open private dialog by user id.
    target_id = None
    if lead.get("sender_id"):
        target_id = int(lead["sender_id"])
    elif key.startswith("id:"):
        try:
            target_id = int(key.split(":", 1)[1])
        except ValueError:
            target_id = None
    if target_id:
        async for dialog in client.iter_dialogs(limit=80):
            entity = dialog.entity
            if isinstance(entity, User) and int(entity.id) == target_id:
                return entity
    raise RuntimeError("no resolvable peer")


def _msg_dt(msg: Any) -> datetime:
    msg_date = msg.date
    if msg_date.tzinfo is None:
        return msg_date.replace(tzinfo=timezone.utc)
    return msg_date


async def _load_private_history(
    client: TelegramClient, entity: Any, *, limit: int = 24
) -> Tuple[List[Dict[str, str]], List[Any]]:
    """Newest-last chat history for GPT + raw messages newest-first from Telethon."""
    raw: List[Any] = []
    async for msg in client.iter_messages(entity, limit=limit):
        raw.append(msg)
    chronological = list(reversed(raw))
    history: List[Dict[str, str]] = []
    for msg in chronological:
        text = (msg.message or "").strip()
        if not text:
            continue
        role = "assistant" if bool(getattr(msg, "out", False)) else "user"
        history.append({"role": role, "content": text})
    return history, raw


def _latest_inbound(raw_msgs: List[Any]) -> Optional[Any]:
    for msg in raw_msgs:
        if bool(getattr(msg, "out", False)):
            continue
        if (msg.message or "").strip():
            return msg
    return None


def _has_unanswered_inbound(raw_msgs: List[Any], since: Optional[datetime]) -> Optional[Any]:
    """Return newest inbound text message that is newer than our last outbound (and since)."""
    newest_in: Optional[Any] = None
    for msg in raw_msgs:
        text = (msg.message or "").strip()
        if not text:
            continue
        if bool(getattr(msg, "out", False)):
            # Our message on top means we already answered later traffic.
            if newest_in is None:
                return None
            break
        if newest_in is None:
            newest_in = msg
    if newest_in is None:
        return None
    if since and _msg_dt(newest_in) < since - timedelta(seconds=3):
        return None
    return newest_in


async def _send_one(
    cfg: Dict[str, Any],
    state: Dict[str, Any],
    accounts: Dict[str, Dict[str, Any]],
    plan: Dict[str, Any],
    live: bool,
) -> str:
    writer = plan["writer"]
    lead = plan["lead"]
    lead_id = plan["lead_id"]
    text = plan["text"]

    if not live:
        logger.info("DRY-RUN would send via %s to %s", writer, plan.get("contact_key"))
        return "dry_run"

    acc = accounts[writer]
    client = _client(acc)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            _pause_account(state, writer, 24, "not authorized")
            return "not_authorized"
        entity = await _resolve_peer(client, lead)
        if isinstance(entity, User) and getattr(entity, "bot", False):
            return "peer_is_bot"

        # Refresh name from Telegram entity for {имя}
        if isinstance(entity, User) and getattr(entity, "first_name", None):
            lead["sender_name"] = entity.first_name
            # re-render with live name if template used placeholders
            try:
                _, text = render_dm(cfg, lead, variant_id=plan.get("variant_id"))
            except Exception:
                pass

        inactive_days = int((_rules(cfg).get("skip_inactive_days") or 30))
        if _user_inactive_too_long(entity, inactive_days):
            for item in state.get("queue") or []:
                if item.get("lead_id") == lead_id:
                    item["status"] = "skipped"
                    item["skip_reason"] = "inactive"
                    break
            logger.info("skip inactive >%sd: %s", inactive_days, plan.get("contact_key"))
            return "inactive"

        # human-ish pause before send
        await asyncio.sleep(random.uniform(2.3, 6.8))
        await client.send_message(entity, text)

        state.setdefault("sent", {})[lead_id] = {
            "at": _now().isoformat(),
            "writer": writer,
            "contact_key": plan["contact_key"],
            "variant_id": plan.get("variant_id"),
            "stage": "first_touch",
            "text": text,
            "lead": {
                "sender_id": lead.get("sender_id"),
                "sender_username": lead.get("sender_username"),
                "sender_name": lead.get("sender_name"),
                "message_text": lead.get("message_text"),
                "chat_title": lead.get("chat_title"),
                "niches": lead.get("niches"),
                "message_type": lead.get("message_type"),
            },
        }
        state.setdefault("contacted", {})[plan["contact_key"]] = {
            "at": _now().isoformat(),
            "lead_id": lead_id,
            "writer": writer,
        }
        _bump_daily(state, writer)

        # mark queue item
        for item in state.get("queue") or []:
            if item.get("lead_id") == lead_id:
                item["status"] = "sent"
                item["sent_at"] = _now().isoformat()
                break
        return "sent"
    except FloodWaitError as e:
        # pause+demote сделает _note_send_result наверху
        _pause_account(state, writer, max(1.0, float(e.seconds) / 3600.0) + 1.0, f"FloodWait {e.seconds}s")
        if (cfg.get("limits") or {}).get("stop_on_floodwait", True):
            raise
        return "floodwait"
    except PeerFloodError:
        for item in state.get("queue") or []:
            if item.get("lead_id") == lead_id and item.get("status") == "planned":
                item["status"] = "new"
                item.pop("writer", None)
                item["peer_flood_release_at"] = _now().isoformat()
                break
        return "peer_flood"
    except UserPrivacyRestrictedError:
        state.setdefault("contacted", {})[plan["contact_key"]] = {
            "at": _now().isoformat(),
            "lead_id": lead_id,
            "writer": writer,
            "result": "privacy",
        }
        for item in state.get("queue") or []:
            if item.get("lead_id") == lead_id:
                item["status"] = "privacy"
                break
        return "privacy"
    except (UsernameNotOccupiedError, UsernameInvalidError, InputUserDeactivatedError) as e:
        for item in state.get("queue") or []:
            if item.get("lead_id") == lead_id:
                item["status"] = "dead_peer"
                item["error"] = str(e)
                break
        return "dead_peer"
    except UserBannedInChannelError as e:
        return "banned"
    except (ConnectionError, OSError, asyncio.TimeoutError) as e:
        # Dead proxy / network — do not burn the lead; pause writer briefly.
        logger.warning("proxy/network fail writer=%s lead=%s: %s", writer, lead_id, e)
        _pause_account(state, writer, 3.0, f"proxy/network: {type(e).__name__}")
        for item in state.get("queue") or []:
            if item.get("lead_id") == lead_id:
                item["status"] = "new"
                item.pop("writer", None)
                item["error"] = str(e)
                item["retry_after_proxy"] = _now().isoformat()
                break
        return "proxy_error"
    except Exception as e:
        err_l = str(e).lower()
        if "proxy" in err_l or "connection to telegram failed" in err_l:
            logger.warning("proxy/network fail writer=%s lead=%s: %s", writer, lead_id, e)
            _pause_account(state, writer, 3.0, f"proxy/network: {type(e).__name__}")
            for item in state.get("queue") or []:
                if item.get("lead_id") == lead_id:
                    item["status"] = "new"
                    item.pop("writer", None)
                    item["error"] = str(e)
                    item["retry_after_proxy"] = _now().isoformat()
                    break
            return "proxy_error"
        logger.exception("send failed writer=%s lead=%s: %s", writer, lead_id, e)
        for item in state.get("queue") or []:
            if item.get("lead_id") == lead_id:
                item["status"] = "error"
                item["error"] = str(e)
                break
        return "error"
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


async def cmd_send_async(cfg: Dict[str, Any], state: Dict[str, Any], limit: int, live: bool) -> int:
    if live and not cfg.get("send_enabled"):
        logger.error("Refusing live send: send_enabled=false in config")
        return 2
    if _maybe_auto_resume_halt(cfg, state):
        save_state(cfg, state)
    if state.get("send_halted"):
        halted = state.get("send_halted") or {}
        at = _parse_ts(halted.get("at") if isinstance(halted, dict) else None)
        hours = float(
            (halted.get("auto_resume_hours") if isinstance(halted, dict) else None)
            or _auto_resume_hours(cfg)
        )
        left = ""
        if at is not None:
            remain = timedelta(hours=hours) - (_now() - at)
            left = f", resume_in≈{max(0, int(remain.total_seconds() // 60))}m"
        logger.error("Refusing send: mailing halted (%s)%s", halted, left)
        return 3
    if not _within_work_hours(cfg):
        local = _now().astimezone(_tzinfo(cfg))
        logger.info("Outside work hours (%s). Skip send.", local.strftime("%Y-%m-%d %H:%M %Z"))
        return 0
    if not _healthy_writers(cfg, state):
        logger.error("No healthy writers available; skip send")
        return 0

    cmd_ingest(cfg, state)
    state = load_state(cfg)
    # re-apply resume after reload
    if _maybe_auto_resume_halt(cfg, state):
        save_state(cfg, state)
    planned = plan_batch(cfg, state, limit=limit)
    if not planned:
        logger.info("nothing to send")
        return 0

    accounts = load_accounts(cfg)
    limits = cfg.get("limits") or {}
    results: Dict[str, int] = {}
    lo, hi = _clamp_delay_sec(
        cfg,
        limits.get("min_delay_between_dm_sec"),
        limits.get("max_delay_between_dm_sec"),
    )

    for i, plan in enumerate(planned):
        if state.get("send_halted"):
            results["halted"] = results.get("halted", 0) + 1
            break
        writer = str(plan.get("writer") or "")
        if writer and _is_account_paused(state, writer):
            results["writer_paused"] = results.get("writer_paused", 0) + 1
            continue
        if i > 0 and live:
            delay = random.uniform(lo, hi)
            logger.info("sleep %.1fs before next DM", delay)
            await asyncio.sleep(delay)
        try:
            result = await _send_one(cfg, state, accounts, plan, live=live)
        except FloodWaitError:
            results["floodwait_stop"] = results.get("floodwait_stop", 0) + 1
            # demote already done inside _send_one path via raise after _demote;
            # still record streak / possible halt-if-none
            _note_send_result(state, cfg, "floodwait_stop", writer=writer or None)
            save_state(cfg, state)
            break
        results[result] = results.get(result, 0) + 1
        if _note_send_result(state, cfg, result, writer=writer or None):
            results["soft_stop"] = results.get("soft_stop", 0) + 1
            save_state(cfg, state)
            break
        save_state(cfg, state)

    logger.info("send done live=%s results=%s", live, results)
    return 0


async def cmd_followup_async(
    cfg: Dict[str, Any], state: Dict[str, Any], limit: int, live: bool
) -> int:
    """Continue DM dialog after first_touch: AI replies + soft warm-up to Lead Hunter."""
    if live and not cfg.get("send_enabled"):
        logger.error("Refusing live followup: send_enabled=false in config")
        return 2
    if not _within_work_hours(cfg):
        local = _now().astimezone(_tzinfo(cfg))
        logger.info("Outside work hours (%s). Skip followup.", local.strftime("%Y-%m-%d %H:%M %Z"))
        return 0

    dcfg = dialog_cfg(cfg)
    ai_enabled = bool(dcfg.get("enabled", True))
    max_ai = int(dcfg.get("max_ai_replies_per_dialog") or 8)
    run_cap = min(limit, int(dcfg.get("max_dialogs_per_run") or limit or 6))

    accounts = load_accounts(cfg)
    sent = state.setdefault("sent", {})
    candidates: List[Tuple[str, Dict[str, Any]]] = []
    for lead_id, row in sent.items():
        stage = row.get("stage")
        if stage in TERMINAL_DIALOG_STAGES:
            continue
        if stage not in ACTIVE_DIALOG_STAGES:
            continue
        if row.get("followup_skipped") in {"privacy", "missing_writer_account", "dead_peer"}:
            continue
        if not row.get("writer") or not row.get("lead"):
            continue
        if _is_account_paused(state, str(row["writer"])):
            continue
        if int(row.get("dialog_replies") or 0) >= max_ai:
            row["stage"] = "closed"
            row["closed_reason"] = "max_ai_replies"
            continue
        candidates.append((lead_id, row))

    candidates.sort(
        key=lambda x: str(x[1].get("last_inbound_at") or x[1].get("at") or ""),
        reverse=True,
    )
    candidates = candidates[: max(1, run_cap)]
    if not candidates:
        logger.info("followup/dialog: nothing pending")
        save_state(cfg, state)
        return 0

    results: Dict[str, int] = {}
    processed = 0
    for i, (lead_id, row) in enumerate(candidates):
        writer = str(row["writer"])
        lead = dict(row.get("lead") or {})
        if writer not in accounts:
            row["followup_skipped"] = "missing_writer_account"
            results["missing_account"] = results.get("missing_account", 0) + 1
            continue

        if not live:
            logger.info(
                "DRY-RUN dialog check writer=%s contact=%s stage=%s ai=%s",
                writer,
                row.get("contact_key"),
                row.get("stage"),
                ai_enabled,
            )
            results["dry_run"] = results.get("dry_run", 0) + 1
            continue

        if processed > 0:
            await asyncio.sleep(random.uniform(45.5, 120.7))

        client = _client(accounts[writer])
        try:
            await client.connect()
            if not await client.is_user_authorized():
                _pause_account(state, writer, 24, "not authorized")
                results["not_authorized"] = results.get("not_authorized", 0) + 1
                continue

            entity = await _resolve_peer(client, lead, row.get("contact_key"))
            history, raw_msgs = await _load_private_history(client, entity, limit=24)
            first_touch_at = _parse_ts(row.get("at"))
            inbound = _has_unanswered_inbound(raw_msgs, since=first_touch_at)
            if inbound is None:
                results["waiting_reply"] = results.get("waiting_reply", 0) + 1
                continue

            inbound_text = (inbound.message or "").strip()
            inbound_id = int(getattr(inbound, "id", 0) or 0)
            if inbound_id and inbound_id == int(row.get("last_answered_inbound_id") or 0):
                results["waiting_reply"] = results.get("waiting_reply", 0) + 1
                continue

            row["last_inbound_at"] = _msg_dt(inbound).isoformat()
            row["last_inbound_id"] = inbound_id
            row["last_inbound_text"] = inbound_text[:500]

            if is_opt_out(inbound_text):
                bye = "Ок, понял, больше не пишу. Хорошего дня."
                await asyncio.sleep(random.uniform(2.5, 6.2))
                await client.send_message(entity, bye)
                row["stage"] = "opt_out"
                row["opt_out_at"] = _now().isoformat()
                row["last_answered_inbound_id"] = inbound_id
                row["dialog_replies"] = int(row.get("dialog_replies") or 0) + 1
                results["opt_out"] = results.get("opt_out", 0) + 1
                processed += 1
                logger.info("opt-out writer=%s lead=%s", writer, lead_id[:12])
                continue

            inbound_count = sum(1 for m in history if m.get("role") == "user")
            our_replies = int(row.get("dialog_replies") or 0)
            offer = resolve_offer(cfg, lead)
            row["offer_track"] = offer["track"]
            offer_link_sent = bool(row.get("offer_link_sent") or row.get("bot_link_sent")) or (
                str(row.get("stage")) in {"soft_offer", "followup_sent"}
            )

            text = ""
            meta: Dict[str, Any] = {}
            if ai_enabled:
                try:
                    text, meta = await generate_reply(
                        cfg,
                        lead=lead,
                        history=history,
                        inbound_count=inbound_count,
                        our_replies=our_replies,
                        bot_link_sent=offer_link_sent,
                        offer_link_sent=offer_link_sent,
                    )
                except Exception as e:
                    logger.exception("AI reply failed lead=%s: %s", lead_id[:12], e)
                    results["ai_error"] = results.get("ai_error", 0) + 1
                    if inbound_count >= int(dcfg.get("min_inbound_before_bot_link") or 2):
                        text = fallback_soft_pitch(cfg, lead)
                        meta = {
                            "contains_bot_link": True,
                            "contains_offer_link": True,
                            "offer_track": offer["track"],
                            "fallback": True,
                        }
                    else:
                        text = (
                            "Понял вас. Подскажите ещё одну деталь по запросу — "
                            "сориентирую точнее."
                        )
                        meta = {
                            "contains_bot_link": False,
                            "contains_offer_link": False,
                            "offer_track": offer["track"],
                            "fallback": True,
                        }
            else:
                if offer["track"] == "jayshambo":
                    text = fallback_soft_pitch(cfg, lead)
                    meta = {
                        "contains_bot_link": True,
                        "contains_offer_link": True,
                        "offer_track": "jayshambo",
                        "template": True,
                    }
                else:
                    _, text = render_dm(cfg, lead, stage="followup_after_reply")
                    meta = {
                        "contains_bot_link": True,
                        "contains_offer_link": True,
                        "offer_track": "leadhunter",
                        "template": True,
                    }

            await asyncio.sleep(random.uniform(2.5, 7.2))
            await client.send_message(entity, text)

            our_replies += 1
            row["dialog_replies"] = our_replies
            row["last_outbound_at"] = _now().isoformat()
            row["last_outbound_text"] = text
            row["last_answered_inbound_id"] = inbound_id
            row["last_ai_meta"] = meta
            if not row.get("followup_sent_at"):
                row["followup_sent_at"] = _now().isoformat()

            if meta.get("contains_offer_link") or meta.get("contains_bot_link"):
                row["offer_link_sent"] = True
                row["bot_link_sent"] = True
                row["bot_link_sent_at"] = _now().isoformat()
                row["offer_url"] = meta.get("offer_url") or offer["url"]
                row["stage"] = "soft_offer"
                results[f"soft_offer_{offer['track']}"] = (
                    results.get(f"soft_offer_{offer['track']}", 0) + 1
                )
            else:
                row["stage"] = "dialog"
                results[f"dialog_{offer['track']}"] = (
                    results.get(f"dialog_{offer['track']}", 0) + 1
                )

            processed += 1
            logger.info(
                "dialog reply writer=%s lead=%s stage=%s track=%s link=%s",
                writer,
                lead_id[:12],
                row.get("stage"),
                offer["track"],
                bool(meta.get("contains_offer_link") or meta.get("contains_bot_link")),
            )
        except PeerFloodError:
            _note_send_result(state, cfg, "peer_flood", writer=writer)
            results["peer_flood"] = results.get("peer_flood", 0) + 1
            # не жжём остальных диалогов в этом же run
            break
        except UserPrivacyRestrictedError:
            row["followup_skipped"] = "privacy"
            row["stage"] = "privacy"
            results["privacy"] = results.get("privacy", 0) + 1
        except Exception as e:
            logger.exception("dialog failed lead=%s: %s", lead_id, e)
            row["followup_error"] = str(e)
            results["error"] = results.get("error", 0) + 1
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass
            save_state(cfg, state)

    logger.info("followup/dialog done live=%s results=%s", live, results)
    return 0



def cmd_status(cfg: Dict[str, Any], state: Dict[str, Any]) -> int:
    queue = state.get("queue") or []
    by_status: Dict[str, int] = {}
    for item in queue:
        st = str(item.get("status") or "?")
        by_status[st] = by_status.get(st, 0) + 1
    print("send_enabled:", cfg.get("send_enabled"))
    print("send_halted:", state.get("send_halted"))
    print("consecutive_complaints:", state.get("consecutive_complaints") or 0)
    print("recovery:", _recovery(cfg))
    print("demoted_to_join:", state.get("demoted_to_join") or {})
    print("healthy_writers:", _healthy_writers(cfg, state))
    print("last_auto_resume_at:", state.get("last_auto_resume_at"))
    print("day:", _day_key())
    print("work_hours_ok:", _within_work_hours(cfg))
    print("rules:", _rules(cfg))
    print("queue_by_status:", by_status)
    sent = state.get("sent") or {}
    print("sent_total:", len(sent))
    print("dialog_enabled:", bool((cfg.get("dialog") or {}).get("enabled", True)))
    stage_counts: Dict[str, int] = {}
    for v in sent.values():
        stg = str(v.get("stage") or "first_touch")
        stage_counts[stg] = stage_counts.get(stg, 0) + 1
    print("dialog_stages:", stage_counts)
    print(
        "followup_sent:",
        sum(1 for v in sent.values() if v.get("followup_sent_at")),
    )
    print(
        "bot_link_sent:",
        sum(1 for v in sent.values() if v.get("bot_link_sent") or v.get("offer_link_sent")),
    )
    offer_tracks: Dict[str, int] = {}
    for v in sent.values():
        tr = str(v.get("offer_track") or "?")
        offer_tracks[tr] = offer_tracks.get(tr, 0) + 1
    print("offer_tracks:", offer_tracks)
    print(
        "active_dialog_candidates:",
        sum(
            1
            for v in sent.values()
            if v.get("stage") in ACTIVE_DIALOG_STAGES
            and v.get("writer")
            and v.get("lead")
            and not _is_account_paused(state, str(v.get("writer")))
        ),
    )
    print("contacted_total:", len(state.get("contacted") or {}))
    print("daily:", (state.get("daily") or {}).get(_day_key()) or {})
    print("paused:", state.get("paused_accounts") or {})
    writers = cfg.get("writers") or []
    accounts = load_accounts(cfg)
    for w in writers:
        acc = accounts.get(w)
        print(
            f"writer {w}: session={'yes' if acc and acc.get('string_session') else 'no'} "
            f"proxy={'yes' if acc and acc.get('proxy') else 'no'} "
            f"today={_daily_count(state, w)} "
            f"pause={_is_account_paused(state, w) or '-'}"
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Lead Hunter DM outreach")
    parser.add_argument(
        "command",
        choices=("ingest", "plan", "send", "followup", "status"),
    )
    parser.add_argument("--config", default=str(DEFAULT_CFG))
    parser.add_argument("--limit", type=int, default=2)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Really send (also requires send_enabled=true)",
    )
    args = parser.parse_args()

    cfg = load_cfg(Path(args.config))
    state = load_state(cfg)

    if args.command == "ingest":
        return cmd_ingest(cfg, state)
    if args.command == "plan":
        return cmd_plan(cfg, state, limit=args.limit)
    if args.command == "status":
        return cmd_status(cfg, state)
    if args.command == "send":
        return asyncio.run(cmd_send_async(cfg, state, limit=args.limit, live=args.live))
    if args.command == "followup":
        return asyncio.run(
            cmd_followup_async(cfg, state, limit=args.limit, live=args.live)
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
