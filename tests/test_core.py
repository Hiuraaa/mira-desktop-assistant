from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mira.agent import Agent, OllamaClient
from mira.storage import ConversationStore, MemoryStore, save_json
from mira.workspace import Workspace, WorkspaceError


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
        import io

        class FakeOpener:
            def open(self, request, timeout):
                self.url = request.full_url
                return io.BytesIO(b'{"models": [{"name": "qwen3:4b"}]}')

        client = OllamaClient()
        client.opener = FakeOpener()
        self.assertEqual(client.list_models(), ["qwen3:4b"])
        self.assertEqual(client.opener.url, "http://127.0.0.1:11434/api/tags")


if __name__ == "__main__":
    unittest.main()
