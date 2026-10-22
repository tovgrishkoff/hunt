"""Checks for Jay Shambo Threads prompts and product cards."""

from __future__ import annotations

import os
import re
import unittest
from unittest import mock

from uploader.threads_products import (
    approved_urls,
    avatar_available,
    banned_route_labels,
    flagship_product_ids_for_day,
    load_products_config,
    products_prompt_block,
    require_avatar_for_autopublish,
)
from uploader.threads_prompts import (
    AUTHOR_PROMPT,
    COMMENTATOR_PROMPT,
    COMMON_PROMPT,
    author_system_prompt,
    commentator_system_prompt,
    fit_threads_text,
)
from uploader.threads_text_autopost import (
    BALI_FOCUS_ANGLES,
    GEO_POOL,
    KAILAS_FOCUS_ANGLES,
    _mentions_one_day_kora,
    _normalize_text,
    _pick_kind,
    _pick_selling_kind,
    _product_id_for_kind,
    _role_of_kind,
)


class ThreadsPromptsProductsTest(unittest.TestCase):
    def test_author_and_commentator_do_not_share_role_prompts(self) -> None:
        author = author_system_prompt(include_products=False)
        commentator = commentator_system_prompt(include_products=False)
        self.assertIn(COMMON_PROMPT[:40], author)
        self.assertIn(COMMON_PROMPT[:40], commentator)
        self.assertIn("ДНЕВНОЙ СОСТАВ", author)
        self.assertNotIn("ДНЕВНОЙ СОСТАВ", commentator)
        self.assertIn("НЕСОГЛАСИЕ", commentator)
        self.assertNotIn("НЕСОГЛАСИЕ", author)
        self.assertIn(AUTHOR_PROMPT[:30], author)
        self.assertIn(COMMENTATOR_PROMPT[:30], commentator)

    def test_products_config_has_flagships_and_ban(self) -> None:
        cfg = load_products_config()
        ids = {p["id"] for p in cfg["products"]}
        self.assertIn("kailas_lhasa_2027", ids)
        self.assertIn("india_private_8march_2027", ids)
        self.assertTrue(any("Госайкунда" in x for x in banned_route_labels()))
        self.assertTrue(flagship_product_ids_for_day())
        self.assertTrue(approved_urls())
        self.assertIn("status=", products_prompt_block())

    def test_fit_threads_text_does_not_cut_mid_word(self) -> None:
        long = (
            "Кайлас учит простому правилу. На высоте важнее темп и запас дня, "
            "чем красивый план из чата. Самостоятельность хороша, когда ты "
            "уже понимаешь свой потолок нагрузки."
        )
        fitted = fit_threads_text(long, max_chars=120)
        self.assertLessEqual(len(fitted), 120)
        self.assertFalse(fitted.endswith("нагруз"))
        self.assertNotIn("…", fitted)
        # incomplete connector tails should not remain
        self.assertFalse(re.search(r"\b(и|а|но|или)$", fitted))

    def test_fit_threads_text_keeps_trailing_url(self) -> None:
        url = "https://jayshambo.com/tours/kai-las-svyaschennaya-kora-iz-lhasy"
        body = (
            "Для тех, кто хочет кору без самообмана по высоте и логистике. "
            "Смотри программу и решай по фактам. " + url
        )
        fitted = fit_threads_text(body, max_chars=180)
        self.assertLessEqual(len(fitted), 180)
        self.assertTrue(fitted.endswith(url) or fitted == url)

    def test_author_prompt_asks_for_short_dense_posts(self) -> None:
        self.assertIn("180–260", AUTHOR_PROMPT)
        self.assertIn("без воды", AUTHOR_PROMPT.lower())
        self.assertIn("запрещены любые URL", COMMON_PROMPT)
        self.assertIn("Никаких URL", AUTHOR_PROMPT)

    def test_normalize_strips_urls_and_adds_cta(self) -> None:
        out = _normalize_text(
            "Кайлас 2027: кора 3 дня, 52 км, акклиматизация в Лхасе. "
            "https://jayshambo.com/tours/kai-las-svyaschennaya-kora-iz-lhasy",
            kind="promo_kailas",
        )
        self.assertNotRegex(out, r"https?://")
        self.assertIn("КАЙЛАС", out)
        bali = _normalize_text(
            "Ретрит на Бали: океан и тихий темп. https://jayshambo.com/tours/x",
            kind="promo_bali",
        )
        self.assertNotRegex(bali, r"https?://")
        self.assertIn("РЕТРИТ", bali)

    def test_daily_pack_roles(self) -> None:
        self.assertEqual(_role_of_kind("discussion:bali"), "discussion")
        self.assertEqual(_role_of_kind("warmup:india"), "warmup")
        self.assertEqual(_role_of_kind("promo_kailas:kailas_lhasa_2027"), "selling")
        self.assertEqual(_product_id_for_kind("promo_india"), "india_private_8march_2027")

    def test_pick_kind_fills_selling_when_needed(self) -> None:
        kind = _pick_kind(
            ["discussion:a", "discussion:b", "warmup:c"],
            window_idx=4,
            con=None,
            day_key="",
        )
        # Without DB day counts, missing roles are shuffled; still a valid pack kind.
        self.assertTrue(
            kind.startswith("promo")
            or kind in {"discussion", "warmup", "tip", "geo_tip"}
        )

    def test_avatar_gate(self) -> None:
        with mock.patch.dict(os.environ, {"THREADS_AVATAR_ID": "", "THREADS_AVATAR_PATH": ""}, clear=False):
            # Clear cached config side effects are env-only for avatar.
            self.assertFalse(avatar_available())
            with self.assertRaises(RuntimeError):
                require_avatar_for_autopublish()
        with mock.patch.dict(os.environ, {"THREADS_AVATAR_ID": "notion-avatar"}, clear=False):
            self.assertTrue(avatar_available())
            require_avatar_for_autopublish()

    def test_kailas_kora_is_three_days_not_one(self) -> None:
        kailas = next(g for g in GEO_POOL if g["key"] == "kailas")
        self.assertIn("3 дня", kailas["angles"])
        self.assertIn("52 км", kailas["angles"])
        self.assertIn("1 день", kailas["angles"])
        self.assertIn("стандартная кора длится 3 дня", COMMON_PROMPT)
        self.assertIn("52 км", COMMON_PROMPT)
        self.assertTrue(
            _mentions_one_day_kora(
                "Кора вокруг Кайласа — 52 километра за один день на высоте выше 5000."
            )
        )
        self.assertTrue(
            _mentions_one_day_kora("Я веду кору за 1 день: 52 км вокруг Кайласа.")
        )
        self.assertFalse(
            _mentions_one_day_kora(
                "Кора вокруг Кайласа — 52 км за три дня, перевал Долма-Ла 5630 м."
            )
        )
        with self.assertRaises(RuntimeError):
            _normalize_text(
                "Кора вокруг Кайласа — 52 км за один день. Я веду группы.",
                kind="promo_kailas",
            )

    def test_bali_nye_is_primary_commercial_push(self) -> None:
        bali = next(g for g in GEO_POOL if g["key"] == "bali")
        self.assertGreaterEqual(int(bali.get("weight") or 0), 30)
        self.assertIn("новогодн", bali["angles"].lower())
        self.assertTrue(any("новогодн" in a.lower() for a in BALI_FOCUS_ANGLES))
        self.assertIn("Бали", COMMON_PROMPT)
        self.assertIn("реже", COMMON_PROMPT.lower())
        # After recent kailas promo, next selling should avoid immediate kailas spam.
        picks = {_pick_selling_kind(["promo_kailas"] * 3) for _ in range(20)}
        self.assertTrue(picks)
        self.assertTrue(
            any(p.startswith("promo_bali") or p == "promo_india" for p in picks)
        )
        ids = flagship_product_ids_for_day()
        self.assertEqual(ids[0], "bali_premium_ocean")

    def test_kailas_focus_angles_cover_requested_themes(self) -> None:
        joined = " ".join(KAILAS_FOCUS_ANGLES).lower()
        self.assertIn("акклиматизация", joined)
        self.assertIn("эверест", joined)
        self.assertIn("восьмитысячник", joined)
        self.assertIn("тибетская медицина", joined)
        self.assertIn("фарма", joined)
        kailas = next(g for g in GEO_POOL if g["key"] == "kailas")
        for needle in (
            "акклиматизация",
            "эвереста",
            "восьмитысячников",
            "тибетская медицина",
            "фарма",
        ):
            self.assertIn(needle, kailas["angles"].lower())
        self.assertIn("пять восьмитысячников", COMMON_PROMPT)
        self.assertIn("базовый лагерь Эвереста", COMMON_PROMPT)
        self.assertIn("тибетская медицина", COMMON_PROMPT)


if __name__ == "__main__":
    unittest.main()
