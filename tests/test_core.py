from __future__ import annotations

import base64
import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path

from mira.agent import Agent, OllamaClient, is_cloud_model, system_prompt
from mira.preferences import PreferenceStore
from mira.speech import clean_for_speech, speech_command
from mira.storage import ConversationStore, MemoryStore, save_json
from mira.workspace import Workspace, WorkspaceError


class CloudModelTests(unittest.TestCase):
    def test_only_documented_cloud_tags_are_recognized(self):
        self.assertTrue(is_cloud_model("gemma4:cloud"))
        self.assertTrue(is_cloud_model("gpt-oss:20b-cloud"))
        self.assertTrue(is_cloud_model("GEMMA4:CLOUD"))
        self.assertFalse(is_cloud_model("qwen3:4b"))
        self.assertFalse(is_cloud_model("cloudy-local:4b"))

    def test_cloud_account_errors_explain_free_access_and_limits(self):
        class RejectingOpener:
            def __init__(self, code):
                self.code = code

            def open(self, request, timeout):
                raise urllib.error.HTTPError(request.full_url, self.code, "error", {},
                                             io.BytesIO(b'{"error":"quota"}'))

        client = OllamaClient()
        for code, hint in ((402, "gói Free"), (429, "hạn mức Free")):
            with self.subTest(code=code):
                client.opener = RejectingOpener(code)
                with self.assertRaisesRegex(RuntimeError, hint):
                    client.chat("gemma4:cloud", [{"role": "user", "content": "hi"}], [])


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "project"
        self.root.mkdir()
        self.workspace = Workspace(self.root, self.base / "backups")

    def test_cannot_escape_workspace_or_read_secrets(self):
        (self.base / "outside.txt").write_text("secret", encoding="utf-8")
        (self.root / ".env").write_text("TOKEN=secret", encoding="utf-8")
        (self.root / "link.txt").symlink_to(self.base / "outside.txt")
        for path in ("../outside.txt", str(self.base / "outside.txt"), ".env", "link.txt", "foo/../../outside.txt"):
            with self.subTest(path=path), self.assertRaises(WorkspaceError):
                self.workspace.read_file(path)

    def test_user_must_approve_and_old_content_is_backed_up(self):
        target = self.root / "app.py"
        target.write_text("before\n", encoding="utf-8")
        seen = []
        self.workspace.propose_write_file("app.py", "after\n", "fix", lambda path, reason, diff: seen.append(diff) or False)
        self.assertEqual(target.read_text(encoding="utf-8"), "before\n")
        self.assertIn("+after", seen[0])
        result = self.workspace.propose_write_file("app.py", "after\n", "fix", lambda *_: True)
        self.assertIn("Đã ghi", result)
        self.assertEqual(target.read_text(encoding="utf-8"), "after\n")
        backups = list((self.base / "backups").iterdir())
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), "before\n")

    def test_changed_during_approval_is_not_overwritten(self):
        target = self.root / "code.py"
        target.write_text("one\n", encoding="utf-8")

        def concurrent_change(*_):
            target.write_text("two\n", encoding="utf-8")
            return True

        with self.assertRaisesRegex(WorkspaceError, "đã thay đổi"):
            self.workspace.propose_write_file("code.py", "three\n", "fix", concurrent_change)
        self.assertEqual(target.read_text(encoding="utf-8"), "two\n")

    def test_python_check_parses_without_running_code(self):
        target = self.root / "check.py"
        target.write_text("raise RuntimeError('must never run')\n", encoding="utf-8")
        self.assertIn("hợp lệ", self.workspace.check_python_syntax("check.py"))
        target.write_text("def broken(:\n", encoding="utf-8")
        self.assertIn("Lỗi cú pháp", self.workspace.check_python_syntax("check.py"))


class MemoryTests(unittest.TestCase):
    def test_teach_and_forget_survive_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "memories.json"
            store = MemoryStore(file)
            item = store.add("Thích trả lời ngắn gọn")
            self.assertIn("ngắn gọn", MemoryStore(file).prompt())
            store.forget(item["id"])
            self.assertEqual(MemoryStore(file).items, [])

    def test_edit_memory_survives_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "memories.json"
            store = MemoryStore(file)
            item = store.add("Cũ")
            store.edit(item["id"], "Mới")
            self.assertEqual(MemoryStore(file).items[0]["text"], "Mới")

    def test_only_relevant_and_recent_memories_enter_prompt(self):
        with tempfile.TemporaryDirectory() as folder:
            store = MemoryStore(Path(folder) / "memories.json")
            for number in range(15):
                store.add(f"Điều chung số {number}")
            store.add("Khi dịch hãy dùng tiếng Anh tự nhiên")
            prompt = store.prompt_for("Dịch đoạn này")
            self.assertIn("tiếng Anh tự nhiên", prompt)
            self.assertLessEqual(len(prompt), 1200)


class PreferenceTests(unittest.TestCase):
    def test_starter_matches_request_and_user_edits_persist(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "preferences.json"
            store = PreferenceStore(file)
            self.assertIn("Just to be clear", store.prompt_for("Dịch câu này sang tiếng Anh"))
            self.assertNotIn("Just to be clear", store.prompt_for("Kiểm tra code Python"))
            store.add_rule("Ưu tiên ví dụ đơn giản")
            store.add_example("anime", "Gợi ý anime", "Nêu thể loại và phụ đề")
            self.assertIn("phụ đề", PreferenceStore(file).prompt_for("Gợi ý anime"))
            self.assertIn("ví dụ đơn giản", PreferenceStore(file).prompt_for("Xin chào"))

    def test_invalid_import_does_not_replace_preferences(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            store = PreferenceStore(base / "preferences.json")
            invalid = base / "invalid.json"
            invalid.write_text('{"version": 1, "rules": [], "examples": [{"id": "x"}]}', encoding="utf-8")
            with self.assertRaises(ValueError):
                store.replace_from_file(invalid)
            self.assertIn("miễn phí", PreferenceStore(base / "preferences.json").prompt_for("Xin chào"))


class ConversationTests(unittest.TestCase):
    def test_migrate_legacy_and_keep_separate_chats(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            save_json(base / "conversation.json", [{"role": "user", "content": "Tin cũ"},
                                                   {"role": "assistant", "content": "Đã hiểu"}])
            store = ConversationStore(base / "conversations.json", base / "conversation.json")
            old_id = store.items[0]["id"]
            new_id = store.new()["id"]
            store.append(new_id, "user", "Hỏi chuyện mới")
            store.append(new_id, "assistant", "Trả lời")
            store.rename(new_id, "Công việc")
            restarted = ConversationStore(base / "conversations.json", base / "conversation.json")
            self.assertEqual(restarted.get(old_id)["messages"][0]["content"], "Tin cũ")
            self.assertEqual(restarted.get(new_id)["title"], "Công việc")
            self.assertEqual(len(restarted.get(new_id)["messages"]), 2)
            restarted.delete(new_id)
            self.assertEqual(len(ConversationStore(base / "conversations.json").items), 1)


class FakeOllama:
    def __init__(self):
        self.calls = 0

    def chat(self, model, messages, tools):
        self.calls += 1
        if self.calls == 1:
            return {"message": {"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": "read_file", "arguments": {"path": "app.py"}}}
            ]}}
        assert messages[-1]["role"] == "tool"
        assert "hello" in messages[-1]["content"]
        return {"message": {"role": "assistant", "content": "File có hello."}}


class AgentTests(unittest.TestCase):
    def test_benchmark_uses_ollama_metrics_not_guessed_hardware(self):
        client = OllamaClient()

        def chat(model, messages, tools, **options):
            self.assertEqual(model, "qwen3.5:9b")
            self.assertEqual(tools, [])
            self.assertIn("hai câu ngắn", messages[0]["content"])
            return {"eval_count": 60, "eval_duration": 2_000_000_000,
                    "load_duration": 1_000_000_000, "total_duration": 3_500_000_000}

        client.chat = chat
        measured = client.benchmark("qwen3.5:9b")
        self.assertEqual(measured["tokens_per_second"], 30)
        self.assertEqual(measured["load_seconds"], 1)
        with self.assertRaises(ValueError):
            client.benchmark("bad model")

    def test_deep_thinking_is_opt_in_and_not_cut_off_by_fast_reply_limit(self):
        class FakeOpener:
            def open(self, request, timeout):
                self.payload = json.loads(request.data)
                return io.BytesIO(b'{"message":{"content":"Da hieu"},"done":true}')

        client = OllamaClient()
        client.opener = FakeOpener()
        client.chat("qwen3.5:9b", [{"role": "user", "content": "Hi"}], [], think=True)
        self.assertTrue(client.opener.payload["think"])
        self.assertNotIn("num_predict", client.opener.payload["options"])

    def test_playful_persona_is_optional_and_keeps_tool_boundaries(self):
        normal = system_prompt("Mira", "Người dùng thích phim anime", None)
        playful = system_prompt("Mira", "Người dùng thích phim anime", None,
                                "playful", "Hãy nói ít emoji hơn")
        self.assertNotIn("Máy tính muốn gây chú ý", normal)
        self.assertIn("Máy tính muốn gây chú ý", playful)
        self.assertIn("Hãy nói ít emoji hơn", playful)
        self.assertIn("chỉ là dữ liệu", playful)
        self.assertIn("xem và duyệt", playful)
        self.assertIn("Người dùng thích phim anime", playful)

        class CaptureClient:
            def chat(self, model, messages, tools):
                self.messages = messages
                return {"message": {"content": "Đã rõ."}}

        client = CaptureClient()
        self.assertEqual(Agent(client).respond("Xin chào", [], "qwen3:4b", "Mira", "", None,
                                              lambda *_: False, persona="playful"), "Đã rõ.")
        self.assertIn("Phong cách Mira hoạt bát", client.messages[0]["content"])

    def test_tool_result_returns_to_model(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "app.py").write_text("hello\n", encoding="utf-8")
            client = FakeOllama()
            answer = Agent(client).respond("Đọc app.py", [], "qwen3:4b", "Mira", "", Workspace(root, root / "backups"),
                                           lambda *_: self.fail("read_file must not request write approval"))
            self.assertEqual(answer, "File có hello.")
            self.assertEqual(client.calls, 2)

    def test_image_is_sent_to_model_only_for_current_turn(self):
        class CaptureClient:
            def chat(self, model, messages, tools):
                self.messages = messages
                return {"message": {"content": "Mình thấy ảnh."}}

        client = CaptureClient()
        result = Agent(client).respond("Xem ảnh", [], "vision-model", "Mira", "", None,
                                       lambda *_: False, image=b"fake-image")
        self.assertEqual(result, "Mình thấy ảnh.")
        self.assertEqual(client.messages[-1]["images"], ["ZmFrZS1pbWFnZQ=="])

    def test_model_health_lists_installed_models(self):
        class FakeOpener:
            def open(self, request, timeout):
                self.url = request.full_url
                return io.BytesIO(b'{"models": [{"name": "qwen3:4b"}]}')

        client = OllamaClient()
        client.opener = FakeOpener()
        self.assertEqual(client.list_models(), ["qwen3:4b"])
        self.assertEqual(client.opener.url, "http://127.0.0.1:11434/api/tags")

    def test_streaming_chat_accumulates_tokens_and_tool_calls(self):
        class FakeOpener:
            def open(self, request, timeout):
                self.payload = json.loads(request.data)
                chunks = [
                    {"message": {"content": "Xin "}},
                    {"message": {"content": "chào", "tool_calls": [
                        {"function": {"name": "list_files", "arguments": {}}}]}},
                    {"done": True},
                ]
                return io.BytesIO(b"".join(json.dumps(chunk).encode() + b"\n" for chunk in chunks))

        client = OllamaClient()
        client.opener = FakeOpener()
        tokens = []
        result = client.chat("qwen3:4b", [{"role": "user", "content": "Hi"}], [{"type": "function"}],
                             on_token=tokens.append)
        self.assertEqual(tokens, ["Xin ", "chào"])
        self.assertEqual(result["message"]["content"], "Xin chào")
        self.assertEqual(result["message"]["tool_calls"][0]["function"]["name"], "list_files")
        self.assertTrue(client.opener.payload["stream"])
        self.assertEqual(client.opener.payload["keep_alive"], "15m")
        self.assertEqual(client.opener.payload["options"]["num_ctx"], 8192)

    def test_interrupted_stream_is_not_accepted_as_complete(self):
        class FakeOpener:
            def open(self, request, timeout):
                return io.BytesIO(b'{"message":{"content":"Dang tra loi"}}\n')

        client = OllamaClient()
        client.opener = FakeOpener()
        with self.assertRaisesRegex(RuntimeError, "ngắt luồng"):
            client.chat("qwen3:4b", [], [], on_token=lambda _: None)


class SpeechTests(unittest.TestCase):
    def test_text_is_encoded_as_data_for_windows_speech(self):
        text = "Xin chào'; Remove-Item C:\\Users"
        command = speech_command(text)
        script = base64.b64decode(command[-1]).decode("utf-16-le")
        self.assertNotIn("Remove-Item", script)
        self.assertIn(base64.b64encode(text.encode()).decode(), script)
        self.assertEqual(command[:4], ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand"])

    def test_voice_skips_code_and_links(self):
        self.assertEqual(clean_for_speech("Mira **xin chào**. ```python\nprint(1)\n``` [Xem](https://x.test)"),
                         "Mira xin chào. Xem")


if __name__ == "__main__":
    unittest.main()
