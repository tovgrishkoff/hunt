"""Локальный семантический классификатор ниш (ruBERT-tiny2).

Используется как бесплатный fallback, когда OpenAI GPT недоступен
(нет кредитов / circuit breaker / budget cap).
"""

from __future__ import annotations

import logging
import os
import re
from typing import Dict, List, Optional, Tuple

import numpy as np
from sentence_transformers import SentenceTransformer, util

import spam_blocklist

logger = logging.getLogger(__name__)


class SemanticSniper:
    """Семантический поиск ниши по эталонным фразам клиента."""

    def __init__(
        self,
        model_name: str = "cointegrated/rubert-tiny2",
        threshold: float = 0.55,
        fallback_threshold: Optional[float] = None,
    ):
        """
        Args:
            model_name: sentence-transformers модель.
            threshold: мягкий порог (legacy analyze).
            fallback_threshold: порог для автономного fallback без GPT.
        """
        logger.info("🎯 Инициализация AI Снайпера...")
        try:
            self.model = SentenceTransformer(model_name)
            self.threshold = threshold
            self.fallback_threshold = float(
                fallback_threshold
                if fallback_threshold is not None
                else os.getenv("SNIPER_FALLBACK_THRESHOLD", "0.72")
            )
            # Ниже этого score без явного niche-keyword — не лид
            self.lexical_gate_below = float(
                os.getenv("SNIPER_LEXICAL_GATE_BELOW", "0.80")
            )
            self.anchors: Dict[str, List[str]] = {}
            self.anchor_embeddings: Dict[str, np.ndarray] = {}

            # Регулярки для выявления продавцов (Supply) — legacy
            self.seller_patterns = [
                r"предлагаю",
                r"предоставляю",
                r"оказываю",
                r"услуги",
                r"пишите\s+в\s+лс",
                r"за\s+подробностями",
                r"портфолио",
                r"наш\s+канал",
                r"подписывайтесь",
                r"стаж\s+работы",
                r"опыт\s+работы",
                r"кейсы",
                r"свободные\s+окошки",
                r"делаю\s+качественно",
                r"обучаю",
                r"курсы",
                r"запись\s+на",
                r"приглашаю",
                r"могу\s+сделать",
            ]

            # Узкий hard-spam / FX: не трогаем «вакансия/менеджер/bot»
            # (омоглифы вроде USDТ нормализуются перед матчем)
            self.hard_spam_re = re.compile(
                r"(?i)("
                r"\busdt\b|\busdc\b|usd[tт]|usd[cс]|tether|"
                r"тезер|тез[еёe]{1,4}[рr]|обмен\s+валют|"
                r"\b(?:trc|erc|bep)[\s\-]?20\b|\bтр[cсцkк]{1,3}[\s\-]?20\b|"
                r"наличк\w*\s+на\s+руках|купл\w*.{0,40}(?:usd|usdt|usdc|тезер|tether)|"
                r"прод\w*.{0,40}(?:usd|usdt|usdc|тезер|tether)|"
                r"легк\w*\s+заработок|без\s+опыта\s+от\s+\d|"
                r"крипт\w*|сигналы?\s+в\s+тг|"
                r"казино|ставки\s+на\s+спорт|1xbet"
                r")"
            )

            self.intent_re = re.compile(
                r"(?i)("
                r"ищ[уеюём]|нуж(ен|на|ны|но)|требуется|ваканси|"
                r"подскажите|посоветуйте|заказ|"
                r"кто\s+(может|умеет|сделает|снимет|пофоткает|поможет)|"
                r"куплю|продам|сдам|сниму|аренду|looking\s+for|"
                r"\bneed\b|\brent\b|\bbuy\b|\bsell\b|remote|freelance|фриланс|"
                # «хочу» только рядом с услугой/исполнителем, не «хочу погулять»
                r"хоч[уем]+\s+(?:найти|снять|заказать|сделать|чтобы\s+сделали)|"
                r"хоч[уем]+.{0,40}(?:мастер|фотограф|видеограф|риелтор|разработчик|"
                r"программист|смм|smm|seo|визажист|маникюр|косметолог)"
                r")"
            )

            # Прогулки / компания / тусовки — не услуга ниши
            self.social_meetup_re = re.compile(
                r"(?i)("
                r"найд\w*\s+компани|"
                r"ищ\w*\s+компани|"
                r"компани\w*\s+себе|"
                r"погулять|"
                r"встретить\s+закат|"
                r"встречу\s+закат|"
                r"потусить|"
                r"кто\s+составит\s+компани|"
                r"приятн\w*\s+компани|"
                r"покажет\w*\s+(?:мне\s+)?остров"
                r")"
            )

            # Админ-варны / прайс на размещение в ЭТОМ чате — не лид «Реклама TG/INST»
            self.group_ad_policy_re = re.compile(
                r"(?i)("
                r"/dwarn\b|"
                r"реклам\w*\s+в\s+(?:этой\s+|данной\s+)?(?:групп\w*|чат\w*|канал\w*)\s+платн|"
                r"реклам\w*\s+платн\w*.{0,80}(?:групп\w*|чат\w*|канал\w*)|"
                r"(?:в\s+)?(?:групп\w*|чат\w*)\s+реклам\w*\s+платн|"
                r"для\s+заказ\w*\s+реклам\w*.{0,60}(?:пишите|писать|обраща|"
                r"бот|@\w+bot)|"
                r"заказ\w*\s+реклам\w*.{0,40}(?:наш\s+)?бот|"
                r"размещен\w*.{0,40}(?:объявлен|реклам).{0,40}платн|"
                r"платн\w*\s+размещен\w*.{0,40}(?:объявлен|реклам|пост)"
                r")"
            )

            # Лексические якоря: без них borderline semantic score не принимаем
            self.niche_lexicon = {
                "Макияж": r"(?i)макияж|визаж|визажист|makeup|мейкап",
                "Маникюр": r"(?i)маникюр|педикюр|ногт|гель[- ]?лак|шеллак",
                "Реснички": r"(?i)ресниц|lash",
                "Брови": r"(?i)бров",
                "Космеология": r"(?i)косметолог|чистка\s+лица|пилинг|ботокс|филлер",
                "Волосы": r"(?i)парикмахер|стрижк|окрашиван|волос",
                "Фотограф": r"(?i)фотограф|фотосесс|пофотк|съ[её]мк\w*\s+фото|\bфото\b",
                "Видеограф": r"(?i)видеограф|видеосъ[её]м|рилл?с|монтаж\s+видео|оператор",
                "Мобилографы": r"(?i)мобилограф|съ[её]мк\w*\s+на\s+(?:телефон|айфон)",
                "SMM": (
                    r"(?i)\bsmm\b|\bсмм(?:щик\w*)?\b|соцсет|инстаграм|"
                    r"ведение\s+(?:инст|сторис|соц)"
                ),
                "UGC": r"(?i)\bugc\b",
                "SEO": r"(?i)\bseo\b|\bсео\b|продвижен\w*\s+сайт",
                "Продюсирование": r"(?i)продюсер|продюсирован",
                "PR-менеджеры": r"(?i)\bpr\b|пиар|пресс[- ]?релиз",
                # Не голое «реклам» — иначе админ-варн «реклама в группе платная»
                "Реклама TG/INST": (
                    r"(?i)("
                    r"закуп\w*\s+реклам|посев|таргет|"
                    r"реклам\w*.{0,40}(?:телеграм|telegram|инстаграм|instagram|"
                    r"\bтг\b|\binst\b|stories|сторис)|"
                    r"(?:ищ\w*|нуж\w*|купл\w*).{0,40}реклам"
                    r")"
                ),
                "Медиабайеры": r"(?i)медиабайер|mediabuyer|media[- ]?buyer|арбитраж",
                "Тех. специалисты": r"(?i)разработчик|программист|техспец|бот|сайт|no[- ]?code",
                "Заказы по AI": r"(?i)нейросет|chatgpt|midjourney|\bai\b",
                "Удаленная работа": r"(?i)удал[её]нн|remote|freelance|фриланс|ваканси",
                "Туризм": r"(?i)гид|экскурси|\bтур\b|visa\s*run",
                "Транспорт": r"(?i)трансфер|такси|аэропорт|водитель",
                "Аренда авто": r"(?i)аренда\s+авто|прокат\s+авто|машин\w*\s+в\s+аренду|\brent\s+car\b",
                "Аренда байков": r"(?i)байк|скутер|nmax|pcx|мото",
                "Медиа-студия": r"(?i)фотостуд|видеостуд|медиастуд|аренда\s+студи",
                # Только объект жилья — голые «сниму/сдам/продам» ловят барахолку
                "Недвижимость (Спрос)": (
                    r"(?i)квартир|вилл|жиль[её]|апартамент|комнат|"
                    r"(?:сниму|снять|арендую)\s+дом\b"
                ),
                "Недвижимость (Предложение)": (
                    r"(?i)квартир|вилл|жиль[её]|апартамент|комнат|"
                    r"(?:сдам|сдаю|сдается)\s+дом\b"
                ),
                "Продажа недвижимости": (
                    r"(?i)недвижимост|риелтор|пентхаус|квартир|вилл|апартамент|"
                    r"участ(?:ок|ка|ки)|земл[еияю]|"
                    r"(?:куплю|продам|продаю|продается)\s+дом\b"
                ),
            }
            # Для этих ниш lexicon обязателен даже при высоком semantic score
            # (иначе «нужны грузчики» → SMM на 87% без слов ниши)
            self.strict_lexicon_niches = {
                "Недвижимость (Спрос)",
                "Недвижимость (Предложение)",
                "Продажа недвижимости",
                "Реклама TG/INST",
                "SMM",
                "SEO",
                "UGC",
                "Мобилографы",
                "PR-менеджеры",
                "Медиабайеры",
                "Продюсирование",
                "Заказы по AI",
                "Удаленная работа",
                "Тех. специалисты",
            }

            # Грузчики / movers — не digital-ниши
            self.movers_job_re = re.compile(
                r"(?i)("
                r"грузчик\w*|movers?|loaders?|"
                r"(?:погруз|выгруз|разгруз)\w*.{0,40}(?:вещ|мебел|квартир|грузовик)|"
                r"(?:нужны|ищем|требуется).{0,60}(?:на\s+)?переезд"
                r")"
            )

            self._load_anchors()
            logger.info(
                f"✅ AI Снайпер заряжен. Ниш: {len(self.anchor_embeddings)}, "
                f"fallback_threshold={self.fallback_threshold}"
            )
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки AI Снайпера: {e}")
            raise

    def _load_anchors(self) -> None:
        """Эталонные фразы — как пишет клиент/заказчик."""
        self.anchors = {
            "Фотограф": [
                "нужен фотограф",
                "ищу фотографа",
                "кто может пофоткать",
                "нужна фотосессия",
                "ищу человека для фото",
                "свадебный фотограф нужен",
                "красиво пофоткать на свадьбу",
                "кто пофоткает на свадьбу",
            ],
            "Видеограф": [
                "нужен видеограф",
                "кто снимает рилс",
                "ищу оператора на съёмку",
                "монтаж видео нужен",
                "нужно снять ролик",
            ],
            "Недвижимость (Спрос)": [
                "сниму квартиру",
                "сниму виллу",
                "сниму комнату",
                "ищу жилье в аренду",
                "арендую комнату",
                "нужна квартира на месяц",
                "снять виллу",
                "снять квартиру",
                "ищу дом на длительный срок",
                "ищу квартиру для аренды",
                "нужна вилла в аренду",
                "нужно снять жилье",
                "ищу жилье",
            ],
            "Недвижимость (Предложение)": [
                "сдам квартиру",
                "сдаю квартиру",
                "сдаю виллу",
                "сдается комната",
                "сдается квартира",
                "сдается вилла",
                "освободилась вилла",
                "предлагаю жилье",
                "сдача апартаментов",
                "available for rent",
                "сдаю в аренду",
                "сдаю жилье",
            ],
            "Продажа недвижимости": [
                "куплю виллу",
                "куплю квартиру",
                "продам дом",
                "продам виллу",
                "продажа недвижимости",
                "ищу объект на покупку",
            ],
            "Маникюр": [
                "нужен мастер маникюра",
                "ищу где сделать ногти",
                "нужен маникюр",
            ],
            "Волосы": [
                "нужен парикмахер",
                "ищу мастера по волосам",
                "нужна стрижка",
                "покрасить волосы",
            ],
            "Аренда авто": [
                "нужна машина в аренду",
                "арендую авто",
                "ищу тачку на прокат",
                "снять машину",
                "сдаю машину в аренду",
                "прокат авто",
                "rent car",
            ],
            "Реснички": [
                "нужен мастер по ресницам",
                "наращивание ресниц ищу",
            ],
            "Брови": [
                "нужен бровист",
                "коррекция бровей ищу",
            ],
            "Макияж": [
                "нужен визажист",
                "макияж на свадьбу ищу",
            ],
            "Косметология": [
                "нужен косметолог",
                "чистка лица ищу",
            ],
            "Аренда байков": [
                "снять байк",
                "аренда скутера",
                "нужен nmax в аренду",
                "ищу байк",
                "кто сдаёт байк",
            ],
            "Мобилографы": [
                "ищу мобилографа",
                "нужен мобилограф",
                "съёмка на телефон",
                "мобилография для бренда",
            ],
            "SMM": [
                "ищу smm",
                "нужен смм менеджер",
                "ведение инстаграма",
                "ведение соцсетей",
                "нужен сммщик",
                "вести инсту и сторис",
                "ведение сторис на постоянке",
                "человек который ведёт инсту",
            ],
            "UGC": [
                "ищу ugc креатора",
                "нужен ugc",
                "ugc контент на заказ",
            ],
            "SEO": [
                "ищу seo специалиста",
                "нужен сео",
                "продвижение сайта",
                "seo аудит",
            ],
            "Продюсирование": [
                "ищу продюсера",
                "нужен продюсер курса",
                "продюсирование проекта",
            ],
            "PR-менеджеры": [
                "ищу pr менеджера",
                "нужен пиарщик",
                "пресс релиз",
            ],
            "Реклама TG/INST": [
                "закуп рекламы в телеграм",
                "нужна реклама в инстаграм",
                "посевы у блогеров",
                "таргет в инстаграм",
            ],
            "Медиабайеры": [
                "ищу медиабайера",
                "нужен media buyer",
                "арбитраж трафика",
            ],
            "Тех. специалисты": [
                "ищу разработчика",
                "нужен программист",
                "сделать бота",
                "нужен техспециалист",
                "доработать сайт",
                "сделать телеграм-бота под заявки",
                "человек сделать телеграм бота",
            ],
            "Заказы по AI": [
                "заказ по нейросетям",
                "нужен chatgpt специалист",
                "сделать на midjourney",
                "нужна генерация нейросетями",
            ],
            "Удаленная работа": [
                "ищу удалённую работу",
                "remote job",
                "вакансия удалённо",
                "удалённая занятость",
            ],
            "Медиа-студия": [
                "аренда фотостудии",
                "студия для подкаста",
                "снять студию",
            ],
            "Туризм": [
                "нужен гид",
                "ищу экскурсию",
                "организатор туров нужен",
            ],
            "Транспорт": [
                "нужно такси",
                "трансфер в аэропорт",
                "ищу водителя на трансфер",
                "airport transfer",
            ],
        }

        logger.info(f"📝 Векторизация эталонов для {len(self.anchors)} ниш...")
        for niche, phrases in self.anchors.items():
            if not phrases:
                continue
            try:
                self.anchor_embeddings[niche] = self.model.encode(
                    phrases, convert_to_numpy=True
                )
            except Exception as e:
                logger.error(f"❌ Ошибка векторизации для '{niche}': {e}")

        total_phrases = sum(len(p) for p in self.anchors.values())
        logger.info(
            f"✅ Загружено {total_phrases} эталонных фраз "
            f"для {len(self.anchor_embeddings)} ниш"
        )

    def is_seller(self, text: str) -> bool:
        """Legacy: похоже ли на предложение услуг продавца."""
        if not text:
            return False
        text_lower = text.lower()
        for pattern in self.seller_patterns:
            if re.search(pattern, text_lower):
                return True
        return False

    def _rank_niches(self, text: str) -> List[Tuple[float, str]]:
        """Все ниши по убыванию semantic score."""
        msg_embedding = self.model.encode(text, convert_to_numpy=True)
        ranked: List[Tuple[float, str]] = []
        for niche, anchor_embs in self.anchor_embeddings.items():
            scores = util.cos_sim(msg_embedding, anchor_embs)[0]
            if hasattr(scores, "cpu"):
                scores_np = scores.cpu().numpy()
            else:
                scores_np = scores
            ranked.append((float(np.max(scores_np)), niche))
        ranked.sort(reverse=True)
        return ranked

    def _best_niche(
        self, text: str
    ) -> Tuple[Optional[str], float, Optional[str], float]:
        """Возвращает (best, best_score, second, second_score)."""
        ranked = self._rank_niches(text)
        if not ranked:
            return None, 0.0, None, 0.0
        best_score, best_niche = ranked[0]
        if len(ranked) > 1:
            second_score, second_niche = ranked[1]
        else:
            second_score, second_niche = 0.0, None
        return best_niche, best_score, second_niche, second_score

    def _has_niche_lexicon(self, niche: str, text_lower: str) -> bool:
        pattern = self.niche_lexicon.get(niche)
        if not pattern:
            return True
        return bool(re.search(pattern, text_lower))

    def analyze(self, text: str) -> Dict:
        """
        Legacy API: кандидат для GPT (мягкий порог).
        """
        if not text:
            return {"is_lead": False, "niche": None, "score": 0, "reason": "empty_text"}

        text_norm = spam_blocklist.normalize_crypto_homoglyphs(text).lower()
        if self.hard_spam_re.search(text_norm):
            return {"is_lead": False, "niche": None, "score": 0, "reason": "hard_spam"}
        if self.movers_job_re.search(text.lower()):
            return {"is_lead": False, "niche": None, "score": 0, "reason": "movers_job"}

        try:
            best_niche, max_score, _, _ = self._best_niche(text)
            if max_score < self.threshold:
                return {
                    "is_lead": False,
                    "niche": None,
                    "score": round(max_score * 100, 1),
                    "reason": "low_score",
                }
            return {
                "is_lead": True,
                "niche": best_niche,
                "score": round(max_score * 100, 1),
                "reason": "candidate_for_gpt",
            }
        except Exception as e:
            logger.error(f"❌ Ошибка в analyze: {e}")
            return {
                "is_lead": False,
                "niche": None,
                "score": 0,
                "reason": f"error: {str(e)}",
            }

    def classify_fallback(self, text: str) -> Dict:
        """
        Автономная классификация без GPT (резерв при outage/quota).

        Returns:
            dict совместимый с AIClassifier / monitor hybrid result:
            message_type, is_spam, niches, confidence, reason, ...
        """
        empty = {
            "message_type": "ОБЩЕНИЕ",
            "is_spam": False,
            "niches": [],
            "context": "Local sniper fallback",
            "urgency": "не срочно",
            "budget": "",
            "confidence": 0,
            "reason": "sniper: no match",
        }
        if not text or not text.strip():
            empty["reason"] = "sniper: empty"
            return empty

        text_lower = text.lower()
        text_norm = spam_blocklist.normalize_crypto_homoglyphs(text).lower()
        if self.hard_spam_re.search(text_norm):
            empty["reason"] = "sniper: hard_spam"
            return empty

        if self.social_meetup_re.search(text_lower):
            empty["reason"] = "sniper: social_meetup"
            return empty

        if self.group_ad_policy_re.search(text_lower):
            empty["reason"] = "sniper: group_ad_policy"
            return empty

        if self.movers_job_re.search(text_lower):
            empty["reason"] = "sniper: movers_job"
            return empty

        if not self.intent_re.search(text_lower):
            empty["reason"] = "sniper: no intent"
            return empty

        try:
            ranked = self._rank_niches(text)
            if not ranked:
                empty["reason"] = "sniper: no niches"
                return empty

            best_niche, max_score = ranked[0][1], ranked[0][0]
            second_niche = ranked[1][1] if len(ranked) > 1 else None
            second_score = ranked[1][0] if len(ranked) > 1 else 0.0
            score100 = round(max_score * 100, 1)
            if max_score < self.fallback_threshold:
                empty["confidence"] = score100
                empty["reason"] = f"sniper: low_score ({score100})"
                return empty

            # Почти ничья между нишами → слишком шумно для автономного режима
            if second_niche and (max_score - second_score) < 0.03 and max_score < 0.80:
                empty["confidence"] = score100
                empty["reason"] = (
                    f"sniper: ambiguous ({best_niche}/{second_niche} "
                    f"{score100}/{round(second_score * 100, 1)})"
                )
                return empty

            # Borderline / digital / realty: без слов ниши не принимаем.
            # Сканируем top-N: SMM-текст иначе уезжает в PR/SEO без лексикона.
            chosen_niche = None
            chosen_score = 0.0
            for score, niche in ranked[:8]:
                if score < self.fallback_threshold:
                    break
                need_lexicon = (
                    score < self.lexical_gate_below
                    or niche in self.strict_lexicon_niches
                )
                if need_lexicon and not self._has_niche_lexicon(niche, text_lower):
                    continue
                chosen_niche, chosen_score = niche, score
                break

            if not chosen_niche:
                empty["confidence"] = score100
                empty["reason"] = (
                    f"sniper: no lexicon for {best_niche} ({score100})"
                )
                return empty

            best_niche, max_score = chosen_niche, chosen_score
            score100 = round(max_score * 100, 1)

            # Грубая эвристика типа сообщения
            offer_re = re.compile(
                r"(?i)\b(сдам|сдаю|сдается|продам|продаю|предлагаю|услуги|прайс)\b"
            )
            search_re = re.compile(
                r"(?i)\b(ищ[уеюём]|нуж(ен|на|ны|но)|сниму|куплю|требуется|ваканси|"
                r"looking\s+for|need)\b"
            )
            if offer_re.search(text_lower) and not search_re.search(text_lower):
                msg_type = "ПРЕДЛОЖЕНИЕ"
            elif search_re.search(text_lower):
                msg_type = "ПОИСК"
            else:
                msg_type = "ПОИСК"

            logger.info(
                f"🎯 Sniper fallback: niche={best_niche} score={score100} type={msg_type}"
            )
            return {
                "message_type": msg_type,
                "is_spam": False,
                "niches": [best_niche],
                "context": f"Local sniper: {best_niche}",
                "urgency": "не срочно",
                "budget": "",
                "confidence": score100,
                "reason": f"sniper fallback ({score100})",
            }
        except Exception as e:
            logger.error(f"❌ Ошибка sniper fallback: {e}")
            empty["reason"] = f"sniper error: {str(e)[:80]}"
            return empty
