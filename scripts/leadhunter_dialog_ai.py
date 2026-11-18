"""AI-диалог для outreach: живые ответы + прогрев к Lead Hunter или Jay Shambo."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("leadhunter_dialog_ai")

OPT_OUT_RE = re.compile(
    r"(стоп|stop|отпиш|не пиши|не пишите|не интересу|не надо|хватит|"
    r"unsubscribe|leave me|spam|спам)",
    re.IGNORECASE,
)

INTEREST_RE = re.compile(
    r"(интересн|как работ|сколько сто|цена|тариф|подключ|хочу|"
    r"расскаж|покажи|ссылк|бот|lead.?hunt|настро|сайт|программ|даты|"
    r"бронир|запис)",
    re.IGNORECASE,
)

DEFAULT_TOURISM_NICHE_KEYS = (
    "туризм",
    "ретрит",
    "йога",
    "travel",
    "путеше",
    "экскур",
    "палом",
    "кайлас",
    "kailas",
)

DEFAULT_TOURISM_TEXT_KEYS = (
    "экскурси",
    "ретрит",
    "йог",
    "путешеств",
    "поездка",
    "поездке",
    "отпуск",
    "тур в",
    "тур на",
    "тур по",
    "туры",
    "тура ",
    "туров",
    "туроператор",
    "паломнич",
    "кайлас",
    "kailas",
    "тибет",
    "лхаса",
    "манасаровар",
    "холи",
    "варанаси",
    "гимала",
    "медитац",
    "сакральн",
    "путь к себе",
    "travel",
    "trip",
    "retreat",
    "jay shambo",
    "jayshambo",
)

DEFAULT_EXCLUDE_NICHE_KEYS = (
    "недвижимост",
    "байк",
    "авто",
    "транспорт",
    "маникюр",
    "брови",
    "ресниц",
    "волос",
    "косметолог",
    "макияж",
    "фотограф",
    "видеограф",
    "playstation",
    "кальян",
    "обмен валют",
)

# Tone of voice = Threads / Narrative (@grishkoff_travel): как сообщение другу, не скрипт.
VOICE_CANON = """
ГОЛОС (как в Threads / Narrative):
- Пиши от первого лица, по-мужски, спокойно и конкретно.
- Как друг в личке, не менеджер, не FAQ-бот, не слайд.
- Смешивай длину фраз: одна короткая ударная ок, весь текст рублеными лозунгами — нет.
- Можно один лёгкий вопрос в конце (да/нет, A/B, «что чаще…»).
- Без канцелярита и нейроштампов: «оба варианта рабочие», «живая тема», «если коротко»,
  «критерий», «разберём», «без общих слов», «а что думаете», «в современном мире»,
  «важно отметить», «давайте разберёмся», «не просто… а…».
- Без эмодзи-спама. Без префиксов ролей.
"""

PROMPT_LEADHUNTER = """Ты пишешь в Telegram личку. Не бот и не менеджер.
Цель: помочь по теме запроса и мягко прогреть к Lead Hunter
({offer_url} / @{bot_username}) — бот ловит живые заявки из Telegram-чатов по нишам.

""" + VOICE_CANON + """
Правила диалога:
1. 1–3 предложения по-русски. Сначала по делу на последнее сообщение.
2. Не здоровайся повторно, если уже писал в этом диалоге.
3. Первое наше сообщение было коротким (контекст + вопрос). Дальше раскрывай диалог
   от их ответа: уточни деталь, дай короткий полезный совет по теме. Не лей шаблон.
4. Прогрев поэтапно:
   - 1-й ответ после их реплики: только по их ответу, оффер НЕ питчи;
   - середина: мягко про мониторинг чатов / откуда клиенты;
   - когда уместно: предложи Lead Hunter и дай ссылку {offer_url}.
5. Ссылку — не чаще одного раза, пока сам не попросит.
6. Не выдумывай тарифы и гарантии.
7. Отказ/стоп — коротко извинись и стоп.
8. Ответ = только текст одного сообщения.
"""

PROMPT_JAYSHAMBO = """Ты пишешь в Telegram личку. Не бот и не менеджер.
Собеседник ищет тур / ретрит / путешествие / экскурсии.
Цель: помочь по запросу и мягко прогреть к турам Jay Shambo: {offer_url}
(сайт: {site_url}).

""" + VOICE_CANON + """
Правила диалога:
1. 1–3 предложения по-русски. Сначала по делу: даты, формат, Бали/Индия/Кайлас.
2. Не здоровайся повторно, если уже писал в этом диалоге.
3. Первое наше сообщение было коротким (контекст + вопрос). Дальше раскрывай диалог
   от их ответа: уточни деталь по поездке/ретриту. Не лей шаблон.
4. Прогрев поэтапно:
   - 1-й ответ после их реплики: только по их ответу, сайт НЕ пихай;
   - середина: мягко про живые программы Jay Shambo под такой запрос;
   - когда уместно: дай ссылку {offer_url} и предложи глянуть программу.
5. Не смешивай с Lead Hunter / ботом заявок — этому человеку нужен тур/ретрит.
6. Не обещай «2 места» и выдуманные скидки. По Кайласу: пермиты нестабильны, группа в лист ожидания.
7. Отказ/стоп — коротко извинись и стоп.
8. Ответ = только текст одного сообщения.
"""


def dialog_cfg(cfg: Dict[str, Any]) -> Dict[str, Any]:
    return dict(cfg.get("dialog") or {})


def offers_cfg(cfg: Dict[str, Any]) -> Dict[str, Any]:
    return dict(cfg.get("offers") or {})


def is_opt_out(text: str) -> bool:
    return bool(OPT_OUT_RE.search(text or ""))


def looks_interested(text: str) -> bool:
    return bool(INTEREST_RE.search(text or ""))


def _norm_list(values: Any) -> List[str]:
    if not values:
        return []
    if isinstance(values, str):
        return [values.lower()]
    return [str(v).lower() for v in values]


def _lead_blob(lead: Dict[str, Any]) -> str:
    niches = " ".join(_norm_list(lead.get("niches")))
    text = str(lead.get("message_text") or "").lower()
    chat = str(lead.get("chat_title") or "").lower()
    return f"{niches}\n{text}\n{chat}"


def is_search_lead(lead: Dict[str, Any]) -> bool:
    mt = str(lead.get("message_type") or "").upper()
    if "ПОИСК" in mt or "СПРОС" in mt:
        return True
    # Untyped but clearly looking for something.
    text = str(lead.get("message_text") or "").lower()
    return bool(
        re.search(
            r"\b("
            r"ищу|ищем|подскажите|кто знает|нужен|нужна|нужно|"
            r"хочу|хотим|looking for|i need|need |want to"
            r")\b",
            text,
        )
    )


def is_tourism_seeker(cfg: Dict[str, Any], lead: Dict[str, Any]) -> bool:
    """Туристический спрос: ищет тур/ретрит/экскурсии, не услугу/недвижимость."""
    dcfg = dialog_cfg(cfg)
    if not bool(dcfg.get("jayshambo_for_tourism_search", True)):
        return False
    if not is_search_lead(lead):
        return False

    niches = _norm_list(lead.get("niches"))
    exclude = tuple(
        _norm_list(dcfg.get("exclude_from_tourism_niches")) or DEFAULT_EXCLUDE_NICHE_KEYS
    )
    if any(any(ex in n for ex in exclude) for n in niches):
        # Niche is clearly non-tourism service/realty.
        # Still allow if explicit tourism niche also present.
        niche_keys = tuple(
            _norm_list(dcfg.get("tourism_niche_keywords")) or DEFAULT_TOURISM_NICHE_KEYS
        )
        if not any(any(k in n for k in niche_keys) for n in niches):
            return False

    niche_keys = tuple(
        _norm_list(dcfg.get("tourism_niche_keywords")) or DEFAULT_TOURISM_NICHE_KEYS
    )
    text_keys = tuple(
        _norm_list(dcfg.get("tourism_text_keywords")) or DEFAULT_TOURISM_TEXT_KEYS
    )
    blob = _lead_blob(lead)
    if any(any(k in n for k in niche_keys) for n in niches):
        return True
    return any(k in blob for k in text_keys)


def pick_jayshambo_url(cfg: Dict[str, Any], lead: Dict[str, Any]) -> str:
    js = (offers_cfg(cfg).get("jayshambo") or {})
    tours = dict(js.get("tours") or {})
    default = str(
        js.get("default_url")
        or js.get("site_url")
        or "https://jayshambo.com"
    )
    blob = _lead_blob(lead)

    rules = [
        (
            ("кайлас", "kailas", "тибет", "лхаса", "кора", "манасаровар"),
            "kailas",
        ),
        (
            ("инди", "холи", "варанаси", "гимала"),
            "india",
        ),
        (
            ("выходн", "3 дня", "каяк"),
            "weekend",
        ),
        (
            ("путь к себе", "бали", "ретрит", "новый год", "медитац", "йог"),
            "put_k_sebe",
        ),
    ]
    for keys, tour_id in rules:
        if any(k in blob for k in keys) and tours.get(tour_id):
            return str(tours[tour_id])
    return default


def resolve_offer(cfg: Dict[str, Any], lead: Dict[str, Any]) -> Dict[str, str]:
    """Return offer track for this lead."""
    if is_tourism_seeker(cfg, lead):
        js = offers_cfg(cfg).get("jayshambo") or {}
        url = pick_jayshambo_url(cfg, lead)
        return {
            "track": "jayshambo",
            "url": url,
            "site_url": str(js.get("site_url") or "https://jayshambo.com"),
            "label": "Jay Shambo",
        }
    return {
        "track": "leadhunter",
        "url": str(cfg.get("bot_url") or "https://t.me/Lead_Hunbot"),
        "site_url": str(cfg.get("bot_url") or "https://t.me/Lead_Hunbot"),
        "label": "Lead Hunter",
    }


def clean_ai_text(text: str) -> str:
    if not text:
        return ""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    drop_prefixes = (
        "я:",
        "ты:",
        "ассистент:",
        "assistant:",
        "бот:",
        "ответ:",
        "собеседник:",
        "пользователь:",
    )
    out: List[str] = []
    for line in lines:
        low = line.lower()
        stripped = line
        for p in drop_prefixes:
            if low.startswith(p):
                stripped = line[len(p) :].strip()
                break
        if stripped:
            out.append(stripped)
    body = "\n".join(out).strip()
    return body.replace("—", "-").replace("–", "-")


def build_system_prompt(cfg: Dict[str, Any], offer: Dict[str, str]) -> str:
    dcfg = dialog_cfg(cfg)
    if offer["track"] == "jayshambo":
        template = str(dcfg.get("system_prompt_jayshambo") or PROMPT_JAYSHAMBO)
    else:
        template = str(
            dcfg.get("system_prompt_leadhunter")
            or dcfg.get("system_prompt")
            or PROMPT_LEADHUNTER
        )
    return template.format(
        offer_url=offer["url"],
        site_url=offer.get("site_url") or offer["url"],
        bot_url=str(cfg.get("bot_url") or "https://t.me/Lead_Hunbot"),
        bot_username=str(cfg.get("bot_username") or "Lead_Hunbot").lstrip("@"),
    )


def _stage_hint(
    *,
    offer: Dict[str, str],
    inbound_count: int,
    our_replies: int,
    offer_link_sent: bool,
    min_inbound_before_link: int,
    allow_link_now: bool,
    latest_inbound: str,
) -> str:
    label = offer["label"]
    url = offer["url"]
    if offer_link_sent:
        return (
            f"Ссылка на {label} уже была. Не пихай повторно; "
            "ответь по делу, ссылку повтори только если просят."
        )
    if allow_link_now or (
        inbound_count >= min_inbound_before_link and looks_interested(latest_inbound)
    ):
        return (
            f"Сейчас нужно мягко предложить {label} и ОБЯЗАТЕЛЬНО один раз вставить "
            f"ссылку {url} прямо в сообщение."
        )
    if inbound_count >= min_inbound_before_link:
        if offer["track"] == "jayshambo":
            return (
                "Можно аккуратно подвести к живым программам Jay Shambo, "
                "но ссылку ещё не обязательно."
            )
        return (
            "Можно аккуратно подвести к автоматизации заявок из чатов, "
            "но ссылку ещё не обязательно."
        )
    return (
        f"Рано питчить {label} (входящих={inbound_count}, наших ответов={our_replies}). "
        "Сначала по теме запроса, один уточняющий вопрос."
    )


def text_contains_offer_link(text: str, offer: Dict[str, str], cfg: Dict[str, Any]) -> bool:
    low = (text or "").lower()
    url = offer["url"].lower()
    site = str(offer.get("site_url") or "").lower()
    if url and url in low:
        return True
    if site and site in low:
        return True
    if offer["track"] == "jayshambo":
        return "jayshambo.com" in low or "jay shambo" in low
    bot_user = str(cfg.get("bot_username") or "").lstrip("@").lower()
    return bool(
        (bot_user and bot_user in low)
        or ("lead hunter" in low)
        or ("t.me/lead_hunbot" in low)
    )


def strip_offer_links(text: str, offer: Dict[str, str], cfg: Dict[str, Any]) -> str:
    out = re.sub(r"https?://\S+", "", text, flags=re.IGNORECASE)
    if offer["track"] == "jayshambo":
        out = re.sub(r"jay\s*shambo", "", out, flags=re.IGNORECASE)
    else:
        bot_user = str(cfg.get("bot_username") or "Lead_Hunbot").lstrip("@")
        out = re.sub(rf"@?{re.escape(bot_user)}", "", out, flags=re.IGNORECASE)
        out = re.sub(r"Lead\s*Hunter", "", out, flags=re.IGNORECASE)
    return re.sub(r"\n{3,}", "\n\n", out).strip(" -\n")


def fallback_soft_pitch(cfg: Dict[str, Any], lead: Optional[Dict[str, Any]] = None) -> str:
    offer = resolve_offer(cfg, lead or {})
    if offer["track"] == "jayshambo":
        return (
            "Если актуально, гляньте живые программы Jay Shambo под такой запрос: "
            f"{offer['url']}\n"
            "Могу подсказать, на что смотреть в описании."
        )
    return (
        "Кстати, если такие запросы ловите часто, можно не сидеть вручную во всех чатах.\n"
        f"Lead Hunter: {offer['url']}\n"
        "Если зайдёт — коротко подскажу с чего начать."
    )


def build_messages(
    cfg: Dict[str, Any],
    *,
    lead: Dict[str, Any],
    history: List[Dict[str, str]],
    inbound_count: int,
    our_replies: int,
    offer_link_sent: bool,
    offer: Dict[str, str],
) -> List[Dict[str, str]]:
    dcfg = dialog_cfg(cfg)
    min_before = int(dcfg.get("min_inbound_before_bot_link") or 2)
    force_after = int(dcfg.get("force_bot_link_after_inbound") or 4)
    latest = ""
    for msg in reversed(history):
        if msg.get("role") == "user":
            latest = str(msg.get("content") or "")
            break
    allow_link = (not offer_link_sent) and (
        inbound_count >= force_after
        or (inbound_count >= min_before and looks_interested(latest))
    )

    topic = (lead.get("message_text") or "")[:240]
    niches = lead.get("niches") or []
    msg_type = lead.get("message_type") or ""
    chat = lead.get("chat_title") or ""
    name = lead.get("sender_name") or lead.get("sender_username") or ""

    context = (
        f"Карточка лида: имя={name}; тип={msg_type}; ниши={niches}; чат={chat}.\n"
        f"Оригинальный пост/запрос: {topic}\n"
        f"Оффер-трек: {offer['track']} ({offer['label']}) url={offer['url']}.\n"
        f"Статус прогрева: inbound={inbound_count}, our_replies={our_replies}, "
        f"offer_link_sent={offer_link_sent}.\n"
        f"Подсказка этапа: {_stage_hint(offer=offer, inbound_count=inbound_count, our_replies=our_replies, offer_link_sent=offer_link_sent, min_inbound_before_link=min_before, allow_link_now=allow_link, latest_inbound=latest)}"
    )

    messages: List[Dict[str, str]] = [
        {"role": "system", "content": build_system_prompt(cfg, offer)},
        {"role": "system", "content": context},
    ]
    hist_limit = int(dcfg.get("history_limit") or 16)
    messages.extend(history[-hist_limit:])
    return messages


def _load_llm_env() -> None:
    """Подтянуть ключи из PIAR и resolve_batch_render (Claude для Threads)."""
    try:
        from dotenv import load_dotenv
    except Exception:
        return
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env", override=False)
    load_dotenv(Path("/home/tovgrishkoff/resolve_batch_render/.env"), override=False)


def _split_system_messages(
    messages: List[Dict[str, str]],
) -> Tuple[str, List[Dict[str, str]]]:
    system_parts: List[str] = []
    chat: List[Dict[str, str]] = []
    for msg in messages:
        role = str(msg.get("role") or "")
        content = str(msg.get("content") or "")
        if role == "system":
            if content.strip():
                system_parts.append(content.strip())
            continue
        if role not in {"user", "assistant"}:
            continue
        # Anthropic: не принимает пустые content
        if not content.strip():
            continue
        chat.append({"role": role, "content": content})
    # Anthropic требует начинать с user
    while chat and chat[0]["role"] != "user":
        chat.pop(0)
    return "\n\n".join(system_parts).strip(), chat


async def _complete_claude(
    *,
    messages: List[Dict[str, str]],
    model: str,
    max_tokens: int,
    temperature: float,
    api_key: str,
) -> str:
    from anthropic import AsyncAnthropic

    system, chat = _split_system_messages(messages)
    if not chat:
        chat = [{"role": "user", "content": "Напиши короткий ответ по контексту выше."}]
    client = AsyncAnthropic(api_key=api_key)
    # anthropic>=0.40: temperature убран из messages.create — тон держим промптом.
    _ = temperature
    kwargs: Dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": chat,
    }
    if system:
        kwargs["system"] = system
    resp = await client.messages.create(**kwargs)
    parts = [
        getattr(b, "text", "")
        for b in (resp.content or [])
        if getattr(b, "type", None) == "text"
    ]
    return "\n".join(p for p in parts if p).strip()


async def _complete_openai(
    *,
    messages: List[Dict[str, str]],
    model: str,
    max_tokens: int,
    temperature: float,
    api_key: str,
) -> str:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key)
    resp = await client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=0.9,
    )
    return (resp.choices[0].message.content or "").strip()


async def generate_reply(
    cfg: Dict[str, Any],
    *,
    lead: Dict[str, Any],
    history: List[Dict[str, str]],
    inbound_count: int,
    our_replies: int,
    bot_link_sent: bool = False,
    offer_link_sent: Optional[bool] = None,
) -> Tuple[str, Dict[str, Any]]:
    """Return (text, meta). Claude first (Narrative/Threads voice), OpenAI fallback."""
    _load_llm_env()
    dcfg = dialog_cfg(cfg)
    offer = resolve_offer(cfg, lead)
    link_sent = bool(offer_link_sent) if offer_link_sent is not None else bool(bot_link_sent)

    provider = str(dcfg.get("provider") or os.getenv("OUTREACH_LLM") or "claude").lower()
    max_tokens = int(dcfg.get("max_tokens") or 220)
    temperature = float(dcfg.get("temperature") or 0.75)
    max_len = int(dcfg.get("max_length") or 420)

    messages = build_messages(
        cfg,
        lead=lead,
        history=history,
        inbound_count=inbound_count,
        our_replies=our_replies,
        offer_link_sent=link_sent,
        offer=offer,
    )

    raw = ""
    model_used = ""
    errors: List[str] = []

    want_claude = provider in {"claude", "anthropic", "auto"}
    want_openai = provider in {"openai", "gpt", "auto"} or True  # fallback always allowed

    if want_claude:
        claude_key = (
            os.getenv("ANTHROPIC_API_KEY")
            or str(dcfg.get("anthropic_api_key") or "")
        ).strip()
        claude_model = str(
            dcfg.get("model")
            or os.getenv("OUTREACH_CLAUDE_MODEL")
            or os.getenv("CLAUDE_MODEL")
            or "claude-sonnet-4-5-20250929"
        )
        if claude_key:
            try:
                raw = await _complete_claude(
                    messages=messages,
                    model=claude_model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    api_key=claude_key,
                )
                model_used = claude_model
            except Exception as e:
                errors.append(f"claude:{e}")
                logger.warning("Claude dialog failed → fallback: %s", e)
                raw = ""
        else:
            errors.append("claude:ANTHROPIC_API_KEY missing")

    if not raw and want_openai:
        openai_key = (
            os.getenv("OPENAI_API_KEY") or str(dcfg.get("openai_api_key") or "")
        ).strip()
        openai_model = str(
            dcfg.get("openai_model")
            or os.getenv("OUTREACH_OPENAI_MODEL")
            or "gpt-4o-mini"
        )
        # If primary provider was openai, prefer dialog.model as openai model.
        if provider in {"openai", "gpt"}:
            openai_model = str(dcfg.get("model") or openai_model)
        if not openai_key:
            raise RuntimeError(
                "No LLM reply: "
                + ("; ".join(errors) if errors else "missing API keys")
            )
        try:
            raw = await _complete_openai(
                messages=messages,
                model=openai_model,
                max_tokens=max_tokens,
                temperature=temperature,
                api_key=openai_key,
            )
            model_used = openai_model
        except Exception as e:
            errors.append(f"openai:{e}")
            raise RuntimeError("; ".join(errors)) from e

    if not raw:
        raise RuntimeError(
            "empty LLM reply (" + ("; ".join(errors) if errors else "unknown") + ")"
        )

    text = clean_ai_text(raw)
    if len(text) > max_len:
        text = text[: max_len - 1].rstrip() + "…"

    contains_link = text_contains_offer_link(text, offer, cfg)
    min_before = int(dcfg.get("min_inbound_before_bot_link") or 2)
    force_after = int(dcfg.get("force_bot_link_after_inbound") or 4)
    latest_user = ""
    for msg in reversed(history):
        if msg.get("role") == "user":
            latest_user = str(msg.get("content") or "")
            break
    should_link = (not link_sent) and (
        inbound_count >= force_after
        or (inbound_count >= min_before and looks_interested(latest_user))
    )

    if contains_link and not link_sent and inbound_count < min_before:
        text = strip_offer_links(text, offer, cfg)
        if not text:
            text = (
                "Понял. Подскажите даты и куда больше тянет — сориентирую точнее."
                if offer["track"] == "jayshambo"
                else "Понял. А какой город или ниша сейчас важнее? Могу порекомендовать, где таких обычно находят."
            )
        contains_link = False

    if should_link and not contains_link:
        if offer["track"] == "jayshambo":
            text = (
                f"{text.rstrip()}\n\n"
                f"Если актуально, вот программа Jay Shambo под такой запрос: {offer['url']}"
            )
        else:
            text = (
                f"{text.rstrip()}\n\n"
                f"Если такие заявки нужны регулярно, удобно ловить их через Lead Hunter: {offer['url']}"
            )
        contains_link = True

    if not text:
        raise RuntimeError("empty AI reply")

    meta = {
        "model": model_used,
        "provider": "claude" if "claude" in model_used else "openai",
        "contains_bot_link": contains_link,  # backward-compat for outreach
        "contains_offer_link": contains_link,
        "offer_track": offer["track"],
        "offer_url": offer["url"],
        "inbound_count": inbound_count,
        "our_replies": our_replies,
    }
    return text, meta
