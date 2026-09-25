"""Previously taught PC game actions still require local approval."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mira.agent import Agent
from mira.lessons import LessonStore, validate_steps


class LessonTests(unittest.TestCase):
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
