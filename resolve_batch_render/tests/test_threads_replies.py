"""Pure checks for Threads comment auto-replies."""

from __future__ import annotations

import unittest

from uploader.threads_replies import (
    answered_parent_ids,
    clean_reply,
    discussion_wants_program_link,
    ensure_program_link,
    extract_json_object,
    has_question,
    is_low_effort,
    parse_decision,
    program_url_for_context,
)
from uploader.threads_prompts import strip_punct_dashes


class ThreadsReplyRulesTest(unittest.TestCase):
    def test_emoji_only_is_low_effort(self) -> None:
        self.assertTrue(is_low_effort("🔥🔥 класс", 8))

    def test_real_comment_is_kept(self) -> None:
        self.assertFalse(is_low_effort("Когда лучше ехать на Бали с детьми?", 8))

    def test_own_reply_marks_parent_answered(self) -> None:
        replies = [
            {
                "id": "c1",
                "username": "guest",
                "replied_to": {"id": "post"},
            },
            {
                "id": "r1",
                "username": "grishkoff_travel",
                "replied_to": {"id": "c1"},
            },
        ]
        self.assertEqual(
            answered_parent_ids(replies, username="grishkoff_travel"),
            {"c1"},
        )

    def test_reply_without_question_is_allowed(self) -> None:
        decision = parse_decision(
            '{"reply": true, "response": "Север тише, особенно если ехать не в пик.", '
            '"reason": "experience"}'
        )
        self.assertTrue(decision["reply"])
        self.assertIn("Север", decision["response"])
        self.assertFalse(has_question(decision["response"]))

    def test_extracts_fenced_json(self) -> None:
        raw = '```json\n{"reply": false, "response": "", "reason": "skip"}\n```'
        self.assertIn('"reply": false', extract_json_object(raw))

    def test_reply_keeps_approved_link_and_strips_foreign(self) -> None:
        decision = parse_decision(
            '{"reply": true, "response": "Если смотрите программу, вот страница '
            'https://jayshambo.com/tours/kai-las-svyaschennaya-kora-iz-lhasy '
            'и ещё https://booking.com/x", "reason": "tour_request"}'
        )
        self.assertTrue(decision["reply"])
        self.assertIn("jayshambo.com", decision["response"])
        self.assertNotIn("booking.com", decision["response"])

    def test_banned_gosaikunda_is_skipped(self) -> None:
        decision = parse_decision(
            '{"reply": true, "response": "Лучше через Госайкунду.", "reason": "other"}'
        )
        self.assertFalse(decision["reply"])

    def test_strip_punct_dashes_keeps_year_range(self) -> None:
        self.assertEqual(strip_punct_dashes("сезон 2026–2027"), "сезон 2026-2027")
        self.assertNotIn("—", strip_punct_dashes("Свобода — без показухи"))

    def test_clean_reply_strips_dashes(self) -> None:
        body = clean_reply("Комфорт — не про люкс.")
        self.assertNotIn("—", body)

    def test_program_url_for_kailas_discussion(self) -> None:
        url = program_url_for_context(
            "Кора 3 дня, 52 км, акклиматизация в Лхасе.",
            "Сколько стоит и когда даты?",
        )
        self.assertIn("kai-las", url)
        self.assertTrue(
            discussion_wants_program_link(
                "Сколько стоит программа?", reason="question"
            )
        )
        linked = ensure_program_link("Вот программа и условия.", url)
        self.assertIn(url, linked)
        self.assertEqual(
            ensure_program_link(f"Уже есть {url}", url),
            f"Уже есть {url}",
        )

    def test_leadhunt_link_only_on_service_interest(self) -> None:
        post = "Выбираешь ниши в Telegram — бот шлёт заявки на услугу."
        url = program_url_for_context(post, "А как подключить бота для лидов?")
        self.assertIn("Lead_Hunbot", url)
        self.assertTrue(
            discussion_wants_program_link(
                "Хочу такого бота для поиска клиентов",
                reason="question",
                post_text=post,
            )
        )
        # Generic villa chat without service interest should not force Lead Hunt.
        self.assertFalse(
            discussion_wants_program_link(
                "Красивая вилла",
                reason="experience",
                post_text="Цены на жильё в Чангу",
            )
        )


if __name__ == "__main__":
    unittest.main()
