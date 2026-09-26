"""Permission and data-boundary checks for live lookup and desktop actions."""

from __future__ import annotations

import ctypes
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from mira.agent import Agent
from mira.desktop import DesktopController, _INPUT, capture_primary_screen
from mira.device import SYSTEM_POWER_STATUS, battery_status
from mira.web_search import search_web


class SearchTests(unittest.TestCase):
    def test_html_results_keep_source_url_and_snippet(self):
        page = (b'<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Fguide">'
                b'Official <b>guide</b></a><a class="result__snippet">Read the <b>guide</b>.</a>')
        with patch("mira.web_search._read", return_value=page):
            result = search_web("guide")
        self.assertIn("https://example.org/guide", result)
        self.assertIn("Read the guide.", result)
        self.assertIn("chưa đọc toàn bài", result)

    def test_search_fallback_is_labelled_wikipedia_only(self):
        def reply(url):
            if "duckduckgo.com" in url:
                raise OSError("Rate limited")
            return json.dumps({"query": {"search": [{"title": "Mira", "snippet": "Ví <b>dụ</b>"}]}}).encode()

        with patch("mira.web_search._read", side_effect=reply):
            result = search_web("Mira")
        self.assertIn("Chỉ tìm được Wikipedia", result)
        self.assertIn("https://vi.wikipedia.org/wiki/Mira", result)
        self.assertIn("Ví dụ", result)
        with self.assertRaises(ValueError):
            search_web(" " * 200)


class AgentPermissionTests(unittest.TestCase):
    def test_pc_battery_question_requires_permission_and_skips_ai_when_allowed(self):
        class NoNetwork:
            def chat(self, *args, **kwargs):
                raise AssertionError("Câu hỏi pin không cần gọi mô hình")

        agent = Agent(NoNetwork())
        no_access = agent.respond("Laptop của anh đang sạc không?", [], "qwen3:4b", "Mira", "",
                                  None, lambda *_: False)
        self.assertIn("chưa được cấp quyền", no_access.lower())
        reply = agent.respond("Laptop của anh đang sạc không?", [], "qwen3:4b", "Mira", "",
                              None, lambda *_: False, status_reader=lambda: "Pin laptop: 70%. Đang cắm sạc.")
        self.assertIn("70%", reply)

    def test_phone_workspace_offers_no_write_tool(self):
        class ToolModel:
            calls = 0
            def chat(self, model, messages, tools):
                self.calls += 1
                if self.calls == 1:
                    self.tool_names = [tool["function"]["name"] for tool in tools]
                    return {"message": {"tool_calls": [{"function": {"name": "propose_write_file",
                        "arguments": {"path": "note.txt", "content": "leak", "reason": "test"}}}]}}
                self.tool_result = next(message["content"] for message in messages if message["role"] == "tool")
                return {"message": {"content": "Không sửa."}}

        from mira.workspace import Workspace
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            model = ToolModel()
            Agent(model).respond("Sửa file", [], "qwen3:4b", "Mira", "", Workspace(Path(tmp), Path(tmp)),
                                 lambda *_: True, workspace_read_only=True)
            self.assertNotIn("propose_write_file", model.tool_names)
            self.assertIn("chưa được cấp quyền", model.tool_result)
            self.assertFalse((Path(tmp) / "note.txt").exists())

    def test_time_question_is_local_and_does_not_contact_model(self):
        class NoNetwork:
            def chat(self, *args, **kwargs):
                self.fail("Không cần gọi Ollama để đọc giờ")

        reply = Agent(NoNetwork()).respond("Mấy giờ rồi?", [], "qwen3:4b", "Mira", "", None,
                                          lambda *_: False)
        self.assertIn("Giờ trên máy tính:", reply)

    def test_unauthorized_tool_call_never_runs_on_phone_or_without_permission(self):
        class UntrustedModel:
            def __init__(self):
                self.calls = 0

            def chat(self, model, messages, tools):
                self.calls += 1
                if self.calls == 1:
                    self.assertEqual(tools, [])
                    return {"message": {"tool_calls": [
                        {"function": {"name": "click_screen", "arguments": {"x": 1, "y": 2}}},
                        {"function": {"name": "search_web", "arguments": {"query": "private"}}},
                    ]}}
                self.results = [m["content"] for m in messages if m["role"] == "tool"]
                return {"message": {"content": "Đã hiểu."}}

        model = UntrustedModel()
        model.assertEqual = self.assertEqual
        Agent(model).respond("Xin chào", [], "qwen3:4b", "Mira", "", None, lambda *_: False)
        self.assertIn("chưa được cấp quyền", model.results[0])
        self.assertIn("chưa được cấp quyền", model.results[1])

    def test_search_and_desktop_action_need_explicit_runtime_approval(self):
        class FakeDesktop:
            def __init__(self):
                self.actions = []

            def describe(self, name, args):
                return f"{name}: {args}"

            def execute(self, name, args):
                self.actions.append(name)
                return "Đã nhấp chuột và cần ảnh mới." if name == "click_screen" else "Đã thao tác."

        class ToolModel:
            calls = 0

            def chat(self, model, messages, tools):
                self.calls += 1
                if self.calls == 1:
                    self.assertIn("search_web", [t["function"]["name"] for t in tools])
                    return {"message": {"tool_calls": [
                        {"function": {"name": "search_web", "arguments": {"query": "example"}}},
                        {"function": {"name": "click_screen", "arguments": {"x": 20, "y": 40}}},
                        {"function": {"name": "click_screen", "arguments": {"x": 30, "y": 50}}},
                        {"function": {"name": "type_text", "arguments": {"text": "Hi"}}},
                    ]}}
                self.results = [m["content"] for m in messages if m["role"] == "tool"]
                return {"message": {"content": "Xong."}}

        desktop = FakeDesktop()
        model = ToolModel()
        model.assertIn = self.assertIn
        approvals = []
        with patch("mira.agent.search_web", return_value="URL: https://example.org"):
            Agent(model).respond("Làm việc này", [], "qwen3:4b", "Mira", "", None,
                                 lambda *_: False, image=b"image", web_enabled=True,
                                 desktop=desktop, approve_action=lambda desc: approvals.append(desc) or True)
        self.assertEqual(desktop.actions, ["click_screen", "type_text"])
        self.assertEqual(len(approvals), 2)
        self.assertIn("Ảnh màn hình đã cũ", model.results[2])

        desktop.actions.clear()
        result = Agent._call_tool("click_screen", {"x": 20, "y": 40}, None, lambda *_: False,
                                  desktop=desktop, approve_action=lambda _: True)
        self.assertIn("đính kèm", result)
        self.assertEqual(desktop.actions, [])

    def test_explicit_web_command_works_without_model_tool_support(self):
        class NoModel:
            def chat(self, *args, **kwargs):
                raise AssertionError("Lệnh /web không cần chạy Ollama")

        with patch("mira.agent.search_web", return_value="URL: https://example.org") as search:
            result = Agent(NoModel()).respond("/web cách học Python", [], "qwen3:4b", "Mira", "",
                                              None, lambda *_: False, web_enabled=True)
        self.assertIn("example.org", result)
        search.assert_called_once_with("cách học Python")


class CaptureTests(unittest.TestCase):
    def test_windows_power_status_uses_ac_line_without_guessing_unknown(self):
        class Kernel:
            def GetSystemPowerStatus(self, output):
                status = ctypes.cast(output, ctypes.POINTER(SYSTEM_POWER_STATUS)).contents
                status.ACLineStatus = 1
                status.BatteryFlag = 8
                status.BatteryLifePercent = 64
                return True

        with patch("mira.device.sys.platform", "win32"), patch("mira.device.ctypes.windll", create=True) as api:
            api.kernel32 = Kernel()
            self.assertIn("Pin laptop: 64%. Đang sạc pin, có cắm nguồn.", battery_status())
            def unknown(output):
                ctypes.cast(output, ctypes.POINTER(SYSTEM_POWER_STATUS)).contents.BatteryFlag = 255
                return True
            api.kernel32.GetSystemPowerStatus = unknown
            unknown_status = battery_status().casefold()
            self.assertRegex(unknown_status, r"chưa xác định|không xác định")
            self.assertNotIn("pin laptop: 64%", unknown_status)

    def test_screenshot_bytes_are_read_then_temporary_file_is_removed(self):
        paths = []

        def fake_run(command, **options):
            path = Path(options["env"]["MIRA_CAPTURE_PATH"])
            paths.append(path)
            path.write_bytes(b"\x89PNG\r\n\x1a\nfake-pixels")
            return type("Result", (), {"returncode": 0})()

        with patch("mira.desktop.sys.platform", "win32"), patch("mira.desktop.subprocess.run", side_effect=fake_run):
            self.assertTrue(capture_primary_screen().startswith(b"\x89PNG"))
        self.assertFalse(paths[0].exists())
        self.assertFalse(paths[0].parent.exists())

    def test_desktop_action_validates_inputs_before_approval(self):
        controller = DesktopController()
        if os.name == "nt":
            self.assertEqual(ctypes.sizeof(_INPUT), 40)
        with self.assertRaises(ValueError):
            controller.describe("type_text", {"text": ""})
        with self.assertRaises(ValueError):
            controller.describe("open_app", {"app": "powershell"})


if __name__ == "__main__":
    unittest.main()
