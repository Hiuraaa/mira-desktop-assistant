"""Telegram private pairing, confirmation, delivery, and cloud permission."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from mira.preferences import PreferenceStore
from mira.reminders import ReminderStore
from mira.storage import MemoryStore
from mira.telegram_bot import TelegramBot, TelegramError


class TelegramTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)

        class FakeAPI:
            def __init__(self):
                self.sent = []

            def call(self, method, payload):
                self.sent.append((method, payload))
                if method == "getMe":
                    return {"id": 42}
                if method == "getWebhookInfo":
                    return {"url": ""}
                if method == "getUpdates":
                    return []
                return True

        class FakeAgent:
            def __init__(self):
                self.calls = []

            def respond(self, text, history, model, name, memories, workspace, approve, **kwargs):
                self.calls.append((text, workspace))
                return "Mira chào bạn."

        self.api = FakeAPI()
        self.agent = FakeAgent()
        self.store = ReminderStore(root / "reminders.json")
        self.bot = TelegramBot(root, "", self.agent, self.store,
                               MemoryStore(root / "memories.json"),
                               PreferenceStore(root / "preferences.json"),
                               model="qwen3:4b", name="Mira", cloud_consent=False,
                               fast=True, persona="standard", persona_note="", api=self.api)
        self.bot._bot_id = 42

    def msg(self, text, user=12, chat=12, kind="private"):
        return {"message": {"from": {"id": user}, "chat": {"id": chat, "type": kind},
                            "text": text}}

    def pair(self):
        code = self.bot.new_pairing_code()
        self.bot._handle(self.msg("/start " + code))
        self.assertEqual(self.bot.binding["chat_id"], 12)
        self.bot._handle(self.msg("/muigio +7"))

    def test_private_one_time_pairing_and_scope(self):
        self.bot._handle(self.msg("/start " + self.bot.new_pairing_code(), kind="group"))
        self.assertEqual(self.bot.binding, {})
        self.pair()
        self.bot._handle(self.msg("xin chào", user=19, chat=19))
        self.assertEqual(self.agent.calls, [])
        self.bot._handle(self.msg("xin chào"))
        self.assertEqual(self.agent.calls, [("xin chào", None)])
        self.assertTrue(any("Mira chào bạn" in p.get("text", "")
                            for _, p in self.api.sent))
        self.bot.unpair()
        self.assertEqual(self.bot.chat.list(), [])
        self.bot._handle(self.msg("xin chào"))
        self.assertEqual(len(self.agent.calls), 1)

    def test_exact_schedule_needs_button_and_notifies_phone_once(self):
        self.pair()
        stamp = (datetime.now(timezone(timedelta(hours=7))) + timedelta(minutes=15))
        stamp = stamp.replace(second=0, microsecond=0)
        command = "/nhac " + stamp.strftime("%Y-%m-%d %H:%M") + " | Gọi mẹ"
        self.bot._handle(self.msg(command))
        self.assertEqual(self.store.list(), [])
        draft_message = self.api.sent[-1][1]
        save_data = draft_message["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
        self.bot._handle({"callback_query": {"id": "1", "from": {"id": 99},
                                            "message": {"chat": {"id": 99, "type": "private"}},
                                            "data": save_data}})
        self.assertEqual(self.store.list(), [])
        approve = {"callback_query": {"id": "2", "from": {"id": 12},
                                      "message": {"chat": {"id": 12, "type": "private"}},
                                      "data": save_data}}
        self.bot._handle(approve)
        self.assertEqual(self.store.list()[0]["title"], "Gọi mẹ")
        self.bot._handle(approve)
        self.assertEqual(len(self.store.list()), 1)
        self.assertEqual(self.agent.calls, [])  # Exact dates work without AI credits.
        self.assertEqual(self.store.due(stamp + timedelta(minutes=1))[0]["title"], "Gọi mẹ")
        self.bot._notify_due(stamp + timedelta(minutes=1))
        self.assertEqual(self.store.pending_telegram(stamp + timedelta(minutes=1)), [])
        self.assertEqual(sum("🔔" in p.get("text", "") for _, p in self.api.sent), 1)

    def test_cloud_consent_required_for_chat_and_ai_draft_but_not_exact_date(self):
        self.pair()
        self.bot.update_config(model="gemma4:31b-cloud", cloud_consent=False)
        self.bot._handle(self.msg("xin chào"))
        self.assertEqual(self.agent.calls, [])
        self.assertIn("cho phép Ollama Cloud", self.api.sent[-1][1]["text"])
        stamp = (datetime.now(timezone(timedelta(hours=7))) + timedelta(days=1))
        self.bot._handle(self.msg("/nhac " + stamp.strftime("%Y-%m-%d %H:%M") + " | Gọi mẹ"))
        self.assertIn("reply_markup", self.api.sent[-1][1])

    def test_failed_telegram_delivery_remains_due_for_retry(self):
        self.pair()
        start = datetime.now(timezone(timedelta(hours=7))) + timedelta(minutes=5)
        reminder = self.store.create("Lấy thuốc", start.strftime("%Y-%m-%dT%H:%M"), 5, 420)
        original = self.api.call

        def fail_message(method, payload):
            if method == "sendMessage":
                raise TelegramError("Tạm lỗi")
            return original(method, payload)

        self.api.call = fail_message
        with self.assertRaises(TelegramError):
            self.bot._notify_due(start)
        self.assertEqual(self.store.pending_telegram(start)[0]["id"], reminder["id"])
        self.api.call = original
        self.bot._notify_due(start)
        self.assertEqual(self.store.pending_telegram(start), [])


if __name__ == "__main__":
    unittest.main()
