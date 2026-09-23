"""Regression checks for Mira's chat-first update."""

from __future__ import annotations

import os
import tempfile
import unittest

try:
    import tkinter as tk
except ImportError:
    tk = None
from pathlib import Path
from unittest.mock import patch

from mira.storage import ConversationStore, MemoryStore, save_json


class ConversationTests(unittest.TestCase):
    def test_import_old_chat_and_keep_its_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            legacy = root / "conversation.json"
            save_json(legacy, [{"role": "user", "content": "Chào Mira"},
                               {"role": "assistant", "content": "Chào bạn"}])
            path = root / "conversations.json"
            first = ConversationStore(path, legacy)
            self.assertEqual(first.messages(first.list()[0]["id"])[0]["content"], "Chào Mira")
            self.assertTrue(path.exists())
            second = ConversationStore(path, legacy)
            self.assertEqual(first.list()[0]["id"], second.list()[0]["id"])

    def test_multiple_conversations_and_rename(self):
        with tempfile.TemporaryDirectory() as folder:
            chats = ConversationStore(Path(folder) / "conversations.json")
            a, b = chats.create(), chats.create()
            chats.append(a, "user", "Hỏi về Python")
            chats.append(b, "user", "Hỏi về phim")
            chats.rename(a, "Lập trình")
            reopened = ConversationStore(chats.path)
            self.assertEqual(reopened.get(a)["title"], "Lập trình")
            self.assertEqual(reopened.messages(b)[0]["content"], "Hỏi về phim")
            reopened.delete(a)
            self.assertIsNone(ConversationStore(chats.path).get(a))

    def test_memory_can_be_corrected(self):
        with tempfile.TemporaryDirectory() as folder:
            memory = MemoryStore(Path(folder) / "memories.json")
            item = memory.add("Trả lời bằng tiếng Anh")
            memory.update(item["id"], "Trả lời bằng tiếng Việt")
            self.assertIn("tiếng Việt", MemoryStore(memory.path).prompt())


class VisibleComposerTests(unittest.TestCase):
    def test_chat_input_and_send_button_fit_in_window(self):
        if tk is None:
            self.skipTest("Tkinter chưa có trong môi trường CI.")
        try:
            from mira.gui import MiraApp
            with tempfile.TemporaryDirectory() as folder:
                with patch.dict(os.environ, {"MIRA_DATA_DIR": folder}):
                    app = MiraApp()
                    try:
                        app.geometry("900x600")
                        app.update()
                        self.assertTrue(app.input.winfo_ismapped())
                        self.assertTrue(app.send_button.winfo_ismapped())
                        self.assertGreater(app.input.winfo_height(), 30)
                        self.assertLessEqual(app.input.winfo_rooty() + app.input.winfo_height(),
                                             app.winfo_rooty() + app.winfo_height())
                        self.assertIn("Gửi", app.send_button.cget("text"))
                    finally:
                        app._close()
        except tk.TclError as exc:
            self.skipTest("Môi trường không có màn hình Tkinter: " + str(exc))


if __name__ == "__main__":
    unittest.main()
