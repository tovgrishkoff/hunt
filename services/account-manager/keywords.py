"""
Генерация ключевых слов для поиска групп из "нишевых" сообщений.

Идея: мы уже храним все сообщения в `config/messages/<niche>/messages.json`,
и у каждого сообщения есть `source_file` (например, messages_bike_rental.txt).
По этим текстам можно автоматически собрать релевантные запросы для SearchRequest.
"""

import re
from collections import Counter
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


_RU_STOPWORDS = {
    # служебные
    "и",
    "в",
    "во",
    "на",
    "по",
    "из",
    "к",
    "ко",
    "с",
    "со",
    "у",
    "за",
    "от",
    "до",
    "для",
    "про",
    "или",
    "а",
    "но",
    "что",
    "это",
    "как",
    "где",
    "когда",
    "ли",
    "то",
    # типовые "объявленческие"
    "ищу",
    "нужен",
    "нужна",
    "нужны",
    "нужно",
    "кто",
    "может",
    "помочь",
    "подскажите",
    "посоветуйте",
    "знает",
    "есть",
    "взять",
    "вариант",
    "компания",
    "проверенную",
    "проверенная",
    "проверенный",
    "аккуратно",
    "чисто",
    "удаленно",
    "личные",
    "сообщения",
    "личку",
    "лс",
    "в",
    "лс",
    # гео/общие, добавляем отдельно контролируемо
    "бали",
}

_EN_STOPWORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "to",
    "for",
    "in",
    "on",
    "at",
    "of",
    "with",
    "need",
    "looking",
    "searching",
    "bali",
}

_TOKEN_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁ0-9]+", re.UNICODE)


class SearchKeywordsConfig:
    """Настройки генерации search keywords (без dataclasses для importlib)."""

    def __init__(
        self,
        max_queries_total: int = 80,
        max_queries_per_source: int = 6,
        max_unigrams_per_source: int = 6,
        max_bigrams_per_source: int = 3,
    ) -> None:
        self.max_queries_total = max_queries_total
        self.max_queries_per_source = max_queries_per_source
        self.max_unigrams_per_source = max_unigrams_per_source
        self.max_bigrams_per_source = max_bigrams_per_source


def _normalize_token(token: str) -> str:
    token = token.lower().replace("ё", "е").strip()
    return token


def _tokenize(text: str) -> List[str]:
    return [_normalize_token(t) for t in _TOKEN_RE.findall(text or "")]


def _is_good_term(token: str) -> bool:
    if not token or token.isdigit():
        return False
    if len(token) < 3:
        return False
    if token in _RU_STOPWORDS or token in _EN_STOPWORDS:
        return False
    return True


def _extract_terms(texts: Sequence[str], cfg: SearchKeywordsConfig) -> Tuple[List[str], List[str]]:
    """
    Возвращает (bigrams, unigrams) — самые частые термы.
    """
    uni: Counter[str] = Counter()
    bi: Counter[str] = Counter()

    for text in texts:
        tokens_all = _tokenize(text)
        tokens = [t for t in tokens_all if _is_good_term(t)]

        uni.update(tokens)

        # биграммы на основе "хороших" токенов
        for a, b in zip(tokens, tokens[1:]):
            phrase = f"{a} {b}"
            # отрезаем слишком длинные биграммы по токенам — полезнее короткие
            if len(a) <= 16 and len(b) <= 16:
                bi[phrase] += 1

    bigrams = [p for p, _ in bi.most_common(cfg.max_bigrams_per_source)]

    # не повторяем униграммы, которые уже входят в выбранные биграммы
    used_tokens = set()
    for p in bigrams:
        used_tokens.update(p.split())

    unigrams = [
        t
        for t, _ in uni.most_common(cfg.max_unigrams_per_source * 2)
        if t not in used_tokens
    ][: cfg.max_unigrams_per_source]

    return bigrams, unigrams


def _build_queries_for_terms(terms: Sequence[str]) -> List[str]:
    """
    Превращает термы в поисковые запросы.

    Практика: Telegram Search лучше работает с "квотацией" не всегда стабильно,
    поэтому используем простые строки.
    """
    queries: List[str] = []
    for t in terms:
        t = (t or "").strip()
        if not t:
            continue
        # Базовый запрос + привязка к Бали для снижения мусора.
        queries.append(f"{t} bali")
        queries.append(f"{t} бали")
    return queries


def _dedupe_keep_order(items: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for x in items:
        x = (x or "").strip()
        if not x or x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def build_search_keywords_from_messages(
    messages: Sequence[object],
    cfg: Optional[SearchKeywordsConfig] = None,
    restrict_to_source_files: Optional[Sequence[str]] = None,
) -> List[str]:
    """
    Собирает поисковые запросы из списка сообщений.

    Поддерживаемые форматы элементов:
    - dict: {"text": "...", "source_file": "..."}
    - str: "..."
    """
    cfg = cfg or SearchKeywordsConfig()
    restrict = {s for s in (restrict_to_source_files or []) if s}

    texts_by_source: Dict[str, List[str]] = {}

    for item in messages:
        if isinstance(item, dict):
            text = item.get("text") or ""
            source = item.get("source_file") or "unknown"
        else:
            text = str(item or "")
            source = "unknown"

        if restrict and source not in restrict:
            continue

        text = text.strip()
        if not text:
            continue

        texts_by_source.setdefault(source, []).append(text)

    all_queries: List[str] = []

    for source, texts in sorted(texts_by_source.items(), key=lambda kv: kv[0]):
        bigrams, unigrams = _extract_terms(texts, cfg)
        terms: List[str] = []
        terms.extend(bigrams)
        terms.extend(unigrams)

        queries = _build_queries_for_terms(terms)
        queries = _dedupe_keep_order(queries)[: cfg.max_queries_per_source]
        all_queries.extend(queries)

    # Общие “гео” запросы, которые хорошо находят чаты/комьюнити
    geo_queries = [
        "bali chat",
        "бали чат",
        "bali community",
        "русские бали",
        "bali expat",
        "bali expats",
        "чангу чат",
        "ubud chat",
        "canggu chat",
    ]

    merged = _dedupe_keep_order([*all_queries, *geo_queries])
    return merged[: cfg.max_queries_total]

