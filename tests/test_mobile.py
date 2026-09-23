"""Phone pairing, scoped chat and durable reminder regressions."""

from __future__ import annotations

import json
import tempfile
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from mira.mobile_server import PhoneServer
from mira.preferences import PreferenceStore
from mira.reminders import ReminderStore, draft_reminder
from mira.storage import MemoryStore


class ReminderTests(unittest.TestCase):
    def test_reminder_persists_fires_once_and_exports_calendar_alarm(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "reminders.json"
            store = ReminderStore(path)
            tz = timezone(timedelta(hours=7))
            future = (datetime.now(tz) + timedelta(minutes=20)).replace(second=0, microsecond=0)
            item = store.create("Gặp bạn, nhé; test", future.strftime("%Y-%m-%dT%H:%M"), 5, 420)
            self.assertEqual(ReminderStore(path).list()[0]["id"], item["id"])
            self.assertEqual(store.due(future - timedelta(minutes=6)), [])
            self.assertEqual(store.due(future - timedelta(minutes=4))[0]["id"], item["id"])
            self.assertEqual(ReminderStore(path).due(future), [])
            calendar = store.calendar_file(item["id"]).decode("utf-8")
            self.assertIn("BEGIN:VALARM\r\nTRIGGER:-PT5M", calendar)
            self.assertIn("SUMMARY:Gặp bạn\\, nhé\\; test", calendar)
            self.assertIn("DTSTART:" + future.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ"), calendar)
            store.delete(item["id"])
            self.assertEqual(ReminderStore(path).list(), [])

    def test_invalid_or_past_schedule_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ReminderStore(Path(folder) / "reminders.json")
            for when, offset in (("2020-01-01T10:00", 420), ("tomorrow", 420),
                                 ("2030-01-01T10:00", 2_000)):
                with self.subTest(when=when, offset=offset), self.assertRaises(ValueError):
                    store.create("Việc", when, 0, offset)

    def test_ai_draft_is_editable_and_never_saves(self):
        future = (datetime.now(timezone(timedelta(hours=7))) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")

        class FakeClient:
            def chat(self, model, messages, tools, fast=True):
                self.messages = messages
                return {"message": {"content": json.dumps({"title": "Mua sách", "when": future,
                                                           "lead_minutes": 15})}}

        client = FakeClient()
        result = draft_reminder(client, "qwen3:4b", "Nhắc tôi mai mua sách", 420)
        self.assertEqual(result["title"], "Mua sách")
        self.assertEqual(result["when"], future)
        self.assertIn("Thời gian hiện tại", client.messages[0]["content"])


class PhoneSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)

        class FakeClient:
            def chat(self, model, messages, tools, fast=True):
                when = (datetime.now(timezone(timedelta(hours=7))) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
                return {"message": {"content": json.dumps({"title": "Gọi điện", "when": when,
                                                           "lead_minutes": 0})}}

        class FakeAgent:
            client = FakeClient()
            calls = []

            def respond(self, text, history, model, name, memories, workspace, approve, **kwargs):
                self.calls.append((text, history, workspace, kwargs))
                return "Mira chào bạn."

        self.agent = FakeAgent()
        self.server = PhoneServer(root, self.agent, ReminderStore(root / "reminders.json"),
                                  MemoryStore(root / "memories.json"),
                                  PreferenceStore(root / "preferences.json"), port=0,
                                  model="qwen3:4b", name="Mira", cloud_consent=False,
                                  fast=True, persona="standard", persona_note="")
        self.server.start()
        self.addCleanup(self.server.stop)
        self.base = f"http://127.0.0.1:{self.server.port}"
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def api(self, path, payload=None, *, identity="owner@example.com", cookie=None, csrf=None,
            origin=None):
        headers = {}
        if identity is not None:
            headers["Tailscale-User-Login"] = identity
        if cookie:
            headers["Cookie"] = cookie
        if csrf:
            headers["X-Mira-CSRF"] = csrf
        if origin:
            headers["Origin"] = origin
        data = json.dumps(payload).encode() if payload is not None else None
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.base + path, data=data, headers=headers)
        try:
            response = self.opener.open(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read()
            body = raw if path.endswith(".ics") else json.loads(raw) if path != "/" else raw
            return response.status, body, response.headers

    def test_identity_pairing_csrf_and_scoped_phone_chat(self):
        self.assertEqual(self.api("/api/state", identity=None)[0], 403)
        self.assertEqual(self.api("/api/state")[0], 401)
        self.assertEqual(self.api("/api/pair", {"code": "wrong"})[0], 429)
        code = self.server.new_pairing_code()
        status, _, headers = self.api("/api/pair", {"code": code})
        self.assertEqual(status, 200)
        cookie = headers.get("Set-Cookie").split(";", 1)[0]
        self.assertIn("Secure", headers.get("Set-Cookie"))
        self.assertEqual(self.api("/api/pair", {"code": code})[0], 429)
        self.assertEqual(self.api("/api/state", cookie=cookie, identity="other@example.com")[0], 401)
        status, state, _ = self.api("/api/state", cookie=cookie)
        self.assertEqual(status, 200)
        csrf = state["csrf"]
        self.assertEqual(self.api("/api/chat", {"text": "Xin chào"}, cookie=cookie)[0], 403)
        self.assertEqual(self.api("/api/chat", {"text": "Xin chào"}, cookie=cookie, csrf=csrf,
                                  origin="https://evil.example")[0], 403)
        status, body, _ = self.api("/api/chat", {"text": "Xin chào"}, cookie=cookie, csrf=csrf)
        self.assertEqual((status, body["answer"]), (200, "Mira chào bạn."))
        self.assertIsNone(self.agent.calls[0][2])
        self.assertEqual(self.api("/api/state", cookie=cookie)[1]["messages"][0]["content"], "Xin chào")

        self.server.update_config(model="gemma4:31b-cloud", cloud_consent=False)
        self.assertEqual(self.api("/api/chat", {"text": "Tiếp"}, cookie=cookie, csrf=csrf)[0], 409)
        self.assertEqual(len(self.agent.calls), 1)
        self.server.update_config(cloud_consent=True)
        self.assertEqual(self.api("/api/chat", {"text": "Tiếp"}, cookie=cookie, csrf=csrf)[0], 200)

    def test_phone_must_confirm_reminder_before_creating_and_can_download_ics(self):
        _, _, headers = self.api("/api/pair", {"code": self.server.new_pairing_code()})
        cookie = headers.get("Set-Cookie").split(";", 1)[0]
        csrf = self.api("/api/state", cookie=cookie)[1]["csrf"]
        status, draft, _ = self.api("/api/reminders/draft",
                                    {"text": "Nhắc tôi ngày mai gọi điện", "offset_minutes": 420},
                                    cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200)
        self.assertEqual(self.api("/api/state", cookie=cookie)[1]["reminders"], [])
        status, body, _ = self.api("/api/reminders", {**draft, "offset_minutes": 420},
                                   cookie=cookie, csrf=csrf)
        self.assertEqual(status, 201)
        reminder_id = body["reminder"]["id"]
        status, calendar, _ = self.api(f"/api/reminders/{reminder_id}.ics", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertIn(b"BEGIN:VCALENDAR", calendar)
        self.assertEqual(self.api("/api/reminders/delete", {"id": reminder_id},
                                  cookie=cookie, csrf=csrf)[0], 200)
        self.assertEqual(self.api("/api/state", cookie=cookie)[1]["reminders"], [])
