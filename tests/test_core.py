from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mira.agent import Agent
from mira.storage import MemoryStore
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


class MemoryTests(unittest.TestCase):
    def test_teach_and_forget_survive_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "memories.json"
            store = MemoryStore(file)
            item = store.add("Thích trả lời ngắn gọn")
            self.assertIn("ngắn gọn", MemoryStore(file).prompt())
            store.forget(item["id"])
            self.assertEqual(MemoryStore(file).items, [])


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


if __name__ == "__main__":
    unittest.main()
