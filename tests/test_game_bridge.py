"""Game state stays local and never turns into arbitrary desktop commands."""

import json
import urllib.error
import urllib.request
import unittest
from unittest.mock import patch

from mira.agent import Agent
from mira.game_bridge import GameBridge, GameBridgeError
from mira.speech import start_windows_dictation


class GameBridgeTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.bridge = GameBridge(self.events.append)
        self.addCleanup(self.bridge.stop)
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def call(self, path, payload=None, key=None):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.bridge.port}{path}",
            data=json.dumps(payload).encode() if payload is not None else None,
            method="POST" if payload is not None else "GET",
            headers={"X-Mira-Game-Key": key or self.bridge.token,
                     "Content-Type": "application/json"})
        with self.opener.open(request, timeout=2) as response:
            return json.load(response)

    def register(self):
        return self.call("/register", {"game": "Cờ mẫu", "actions": [{
            "name": "place", "description": "Đặt O vào ô trống", "options": ["1", "2"]}]})

    def event(self):
        return self.call("/event", {"game": "Cờ mẫu", "context": "Lượt Mira đi O",
                                    "state": "ô 1 và 2 trống", "available": {"place": ["1"]}})

    def test_auth_validation_approval_and_one_time_delivery(self):
        with self.assertRaises(urllib.error.HTTPError) as denied:
            self.call("/register", {"game": "Cờ mẫu", "actions": []}, key="wrong")
        self.assertEqual(denied.exception.code, 401)
        self.register()
        with self.assertRaises(urllib.error.HTTPError) as invalid:
            self.call("/event", {"game": "Cờ mẫu", "context": "nhắc", "state": "x",
                                 "available": {"shell": ["delete everything"]}})
        self.assertEqual(invalid.exception.code, 400)
        event_id = self.event()["id"]
        self.assertEqual(self.events[-1]["id"], event_id)
        self.assertIn("place", self.bridge.tool_for(event_id)["function"]["description"])
        self.assertIn("không nằm", self.bridge.choose(event_id, "place", "2", lambda *_: True))
        self.assertEqual(self.call("/action?id=" + event_id)["status"], "waiting")
        asked = []
        self.assertIn("Đã được duyệt", self.bridge.choose(event_id, "place", "1",
                    lambda description: asked.append(description) or True))
        self.assertIn("Lựa chọn: 1", asked[0])
        self.assertEqual(self.call("/action?id=" + event_id)["action"], {"name": "place", "choice": "1"})
        self.assertEqual(self.call("/action?id=" + event_id)["status"], "delivered")
        self.assertIn("đã cũ", self.bridge.choose(event_id, "place", "1", lambda *_: True))

    def test_denial_and_old_events_cannot_be_replayed(self):
        self.register()
        event_id = self.event()["id"]
        self.assertIn("từ chối", self.bridge.choose(event_id, "place", "1", lambda *_: False))
        self.assertEqual(self.call("/action?id=" + event_id)["status"], "denied")
        self.bridge.last_event_at -= 1
        next_id = self.event()["id"]
        self.assertEqual(self.call("/action?id=" + event_id)["status"], "expired")
        self.assertEqual(self.call("/action?id=" + next_id)["status"], "waiting")

    def test_model_cannot_use_game_tool_without_current_event_and_user_approval(self):
        self.register()
        self.event()
        event = self.bridge.snapshot()

        class ChoosingModel:
            def __init__(self):
                self.count = 0

            def chat(self, model, messages, tools, **_):
                self.count += 1
                if self.count == 1:
                    assert [t["function"]["name"] for t in tools] == ["choose_game_action"]
                    return {"message": {"content": "", "tool_calls": [{"function": {
                        "name": "choose_game_action", "arguments": {"name": "place", "choice": "1"}}}]}}
                return {"message": {"content": "Mình đã chọn ô 1."}}

        agent = Agent(ChoosingModel())
        answer = agent.respond("Đến lượt Mira", [], "qwen3:4b", "Mira", "", object(),
                               lambda *_: False, web_enabled=True, desktop=object(),
                               status_reader=lambda: "private", game_bridge=self.bridge, game_event=event,
                               approve_game_action=lambda *_: False)
        self.assertIn("ô 1", answer)
        self.assertEqual(self.bridge.poll_action(event["id"])["status"], "denied")
        # An ordinary chat cannot access the game tool even while the connector is on.
        class TextModel:
            def chat(self, model, messages, tools, **_):
                assert all(t["function"]["name"] != "choose_game_action" for t in tools)
                return {"message": {"content": "Chào bạn."}}

        self.assertEqual(Agent(TextModel()).respond("Chào", [], "qwen3:4b", "Mira", "", None,
                                                   lambda *_: False), "Chào bạn.")


class VoiceInputTests(unittest.TestCase):
    def test_windows_voice_typing_uses_the_focused_input_and_releases_hotkeys(self):
        calls = []

        class FakeUser32:
            def keybd_event(self, key, scan, flags, extra):
                calls.append((key, flags))

        with patch('mira.speech.sys.platform', 'win32'), patch('mira.speech.ctypes.windll', create=True) as windll:
            windll.user32 = FakeUser32()
            start_windows_dictation()
        self.assertEqual(calls, [(0x5B, 0), (0x48, 0), (0x48, 2), (0x5B, 2)])


if __name__ == "__main__":
    unittest.main()
