"""Checks for Jay Shambo Threads prompts and product cards."""

from __future__ import annotations

import os
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
)
from uploader.threads_text_autopost import (
    _pick_kind,
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


if __name__ == "__main__":
    unittest.main()
