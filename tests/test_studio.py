"""The private studio should accept VRM, teach bounded actions and require its session."""

from __future__ import annotations

import json
import struct
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from mira.agent import Agent
from mira.desktop import DesktopController
from mira.lessons import LessonStore, validate_steps
from mira.storage import ConversationStore, MemoryStore
from mira.studio_server import StudioServer, check_vrm


def sample_vrm(*, external=False):
    info = {"asset": {"version": "2.0"}, "scenes": [{"nodes": [0]}], "nodes": [{}],
            "extensions": {"VRMC_vrm": {"specVersion": "1.0"}}}
    if external:
        info["images"] = [{"uri": "https://bad.tld/x"}]
    json_bytes = json.dumps(info).encode()
    json_bytes += b" " * (-len(json_bytes) % 4)
    return (b"glTF" + struct.pack("<II", 2, 20 + len(json_bytes)) +
            struct.pack("<I4s", len(json_bytes), b"JSON") + json_bytes)


class VRMTests(unittest.TestCase):
    def test_only_bounded_vrm_glb_with_embedded_resources(self):
        data = sample_vrm()
        self.assertEqual(check_vrm(data)["version"], "1.0")
        with self.assertRaises(ValueError):
            check_vrm(data.replace(b"VRMC_vrm", b"ordinary"))
        with self.assertRaises(ValueError):
            check_vrm(data[:-1])
        with self.assertRaises(ValueError):
            check_vrm(sample_vrm(external=True))

    def test_game_lesson_requires_approval_and_releases_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LessonStore(Path(directory) / "lessons.json")
            moves = [{"kind": "hold", "key": "w", "duration": .3},
                     {"kind": "press", "key": "space", "duration": 0}]
            item = store.add("Đi tới và nhảy", moves)
            class Desktop:
                actions = []
                def _target_title(self):
                    return "Game đã chọn"
                def execute(self, name, args, **kwargs):
                    self.actions.append((name, args))
            desktop = Desktop()
            self.assertIn("từ chối", store.run(item["id"], desktop, lambda _: False))
            self.assertEqual(desktop.actions, [])
            self.assertIn("Đã thực hiện", store.run(item["id"], desktop, lambda _: True))
            self.assertEqual([name for name, _ in desktop.actions], ["hold_key", "press_keys"])
            desktop.actions.clear()
            def stop_while_approving(_):
                store.stop_event.set()
                return True
            self.assertIn("Đã dừng", store.run(item["id"], desktop, stop_while_approving))
            self.assertEqual(desktop.actions, [])
            with self.assertRaises(ValueError):
                validate_steps([{"kind": "hold", "key": "win", "duration": 10}])

    def test_ai_may_suggest_saved_lesson_but_cannot_run_without_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            lessons = LessonStore(Path(directory) / "lessons.json")
            lesson = lessons.add("Nhảy", [{"kind": "press", "key": "space", "duration": 0}])
            class Desktop:
                executed = False
                def _target_title(self):
                    return "Cửa sổ game"
                def execute(self, *_args, **_kwargs):
                    self.executed = True
            desktop = Desktop()
            class Client:
                def __init__(self):
                    self.calls = 0
                def chat(self, _model, _messages, tools, **_kwargs):
                    self.calls += 1
                    if self.calls == 1:
                        assert any(t["function"]["name"] == "run_learned_action" for t in tools)
                        return {"message": {"tool_calls": [{"function": {
                            "name": "run_learned_action", "arguments": {"id": lesson["id"]}}}]}}
                    assert "từ chối" in _messages[-1]["content"]
                    return {"message": {"content": "Bạn đã từ chối."}}
            answer = Agent(Client()).respond("Nhảy đi", [], "demo", "Mira", "", None,
                                             lambda *_: False, desktop=desktop,
                                             approve_action=lambda _: False, lessons=lessons)
            self.assertIn("từ chối", answer)
            self.assertFalse(desktop.executed)


class _Value:
    def __init__(self, value):
        self.value = value
    def get(self):
        return self.value


class StudioHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        owner = type("Owner", (), {})()
        owner.path = root
        owner.closed = False
        owner.busy = False
        owner.lessons = LessonStore(root / "game_lessons.json")
        owner.memories = MemoryStore(root / "memories.json")
        owner.chats = ConversationStore(root / "conversations.json")
        owner.active_chat_id = owner.chats.new()["id"]
        owner.name_var = _Value("Mira")
        owner.model_var = _Value("local:test")
        owner.cloud_consent = False
        owner.desktop_enabled = False
        owner.desktop = DesktopController()
        owner.preferences = type("Prefs", (), {"prompt_for": lambda _self, _text: ""})()
        owner.web_var = _Value(False)
        owner.fast_var = _Value(True)
        owner.playful_var = _Value(False)
        owner.deep_var = _Value(False)
        owner.device_enabled = False
        owner.persona_note = ""
        owner.workspace = None
        owner._approve_edit = lambda *_args: False
        owner.after = lambda _ms, fn: fn()
        owner._refresh_chat_list = lambda: None
        owner._render_chat = lambda: None
        owner._save_settings = lambda: None
        self.owner = owner
        self.server = StudioServer(owner)
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.origin = f"http://127.0.0.1:{self.server.port}"

    def tearDown(self):
        self.server.stop()
        self.temp.cleanup()

    def get(self, path, *, auth=True):
        headers = {"X-Mira-Session": self.server.token} if auth else {}
        try:
            response = self.opener.open(urllib.request.Request(self.origin + path, headers=headers))
            return response.status, response.read(), response.headers
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read(), exc.headers

    def post(self, path, body, *, origin=None, content_type="application/json"):
        if content_type == "application/json":
            body = json.dumps(body).encode()
        headers = {"X-Mira-Session": self.server.token, "Content-Type": content_type,
                   "Origin": origin if origin is not None else self.origin}
        req = urllib.request.Request(self.origin + path, data=body, headers=headers, method="POST")
        try:
            res = self.opener.open(req)
            return res.status, json.load(res)
        except urllib.error.HTTPError as exc:
            return exc.code, json.load(exc)

    def test_local_app_requires_token_and_same_origin(self):
        self.assertEqual(self.get("/")[0], 200)
        self.assertEqual(self.get("/api/state", auth=False)[0], 401)
        status, state, headers = self.get("/api/state")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(state)["name"], "Mira")
        self.assertIn("default-src 'none'", headers["Content-Security-Policy"])
        self.assertEqual(self.post("/api/teach", {"name": "Nhảy", "steps": []},
                                   origin="https://another.site")[0], 403)

    def test_import_model_and_manage_teaching(self):
        data = sample_vrm()
        status, result = self.post("/api/import", data, content_type="model/gltf-binary")
        self.assertEqual((status, result["version"]), (200, "1.0"))
        self.assertEqual(self.get("/api/model")[1], data)
        self.assertEqual(self.get("/api/model", auth=False)[0], 401)
        self.assertEqual(self.post("/api/import", b"broken", content_type="model/gltf-binary")[0], 400)
        self.assertEqual(self.get("/api/model")[1], data)
        status, value = self.post("/api/teach", {"name": "Đi trái", "steps": [
            {"kind": "hold", "key": "a", "duration": .2}]})
        self.assertEqual(status, 200)
        lesson_id = value["lesson"]["id"]
        self.assertEqual(len(json.loads(self.get("/api/state")[1])["lessons"]), 1)
        self.assertEqual(self.post("/api/delete-lesson", {"id": lesson_id})[0], 200)
        self.assertEqual(self.post("/api/new-chat", {})[0], 200)

    def test_streamed_chat_uses_existing_conversation_and_releases_busy(self):
        class Client:
            def chat(self, _model, _messages, _tools, *, on_token=None, **_kwargs):
                if on_token:
                    on_token("Chào bạn")
                return {"message": {"content": "Chào bạn"}}
        self.owner.agent = Agent(Client())
        body = json.dumps({"text": "Mira ơi"}).encode()
        req = urllib.request.Request(self.origin + "/api/chat", data=body,
                 headers={"Content-Type": "application/json", "X-Mira-Session": self.server.token,
                          "Origin": self.origin}, method="POST")
        result = self.opener.open(req).read().decode()
        self.assertIn('"type": "token"', result)
        self.assertIn('"type": "done"', result)
        self.assertEqual([m["role"] for m in self.owner.chats.messages(self.owner.active_chat_id)],
                         ["user", "assistant"])
        self.assertFalse(self.owner.busy)


if __name__ == "__main__":
    unittest.main()
