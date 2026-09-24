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
                        app.geometry("900x520")
                        app.update()
                        self.assertTrue(app.input.winfo_ismapped())
                        self.assertTrue(app.send_button.winfo_ismapped())
                        self.assertTrue(app.avatar.winfo_ismapped())
                        self.assertTrue(app.phone_button.winfo_ismapped())
                        self.assertTrue(app.feed_canvas.winfo_ismapped())
                        self.assertTrue(app.starters.winfo_ismapped())
                        self.assertGreater(app.feed_canvas.winfo_height(), 100)
                        self.assertFalse(app.side_panel.winfo_ismapped())
                        self.assertGreater(app.input.winfo_height(), 30)
                        self.assertLessEqual(app.input.winfo_rooty() + app.input.winfo_height(),
                                             app.winfo_rooty() + app.winfo_height())
                        self.assertIn("Gửi", app.send_button.cget("text"))
                        self.assertTrue(app.copy_button.winfo_ismapped())
                        app.chats.append(app.active_chat_id, "assistant", "Câu trả lời thử")
                        app._render_chat()
                        app.update()
                        self.assertEqual(len(app._message_labels), 1)
                        self.assertEqual(app._message_labels[0].cget("text"), "Câu trả lời thử")
                        app.stream_text = "Mira đang trả lời"
                        app._show_pending("Mira")
                        app.stream_text = "Đã thêm chữ"
                        app._show_pending("Mira")
                        self.assertEqual(app._pending_label.cget("text"), "Đã thêm chữ")
                        app._remove_pending()
                        app._copy_last_answer()
                        self.assertEqual(app.clipboard_get(), "Câu trả lời thử")
                        app.geometry("1600x900")
                        app.update()
                        self.assertTrue(app.side_panel.winfo_ismapped())
                        self.assertLessEqual(app.desk.winfo_width(), 900)
                        app._model_lab_dialog()
                        app.update()
                        self.assertTrue(any(child.title() == "Mô hình mạnh & tốc độ"
                                            for child in app.winfo_children()
                                            if isinstance(child, tk.Toplevel)))
                        app._cloud_dialog()
                        app.update()
                        self.assertTrue(any(child.title() == "AI cloud cho máy yếu"
                                            for child in app.winfo_children()
                                            if isinstance(child, tk.Toplevel)))
                        app._mobile_dialog()
                        app.update()
                        self.assertTrue(any(child.title() == "Điện thoại & truy cập từ xa"
                                            for child in app.winfo_children()
                                            if isinstance(child, tk.Toplevel)))
                        app._telegram_dialog()
                        app.update()
                        self.assertTrue(any(child.title() == "Mira qua Telegram"
                                            for child in app.winfo_children()
                                            if isinstance(child, tk.Toplevel)))
                    finally:
                        app._close()
        except tk.TclError as exc:
            if "display" in str(exc).lower() or "screen" in str(exc).lower():
                self.skipTest("Môi trường không có màn hình Tkinter: " + str(exc))
            raise

    def test_cloud_send_needs_consent_before_saving_or_sending_text(self):
        if tk is None:
            self.skipTest("Tkinter chưa có trong môi trường CI.")
        try:
            from mira.gui import MiraApp
            with tempfile.TemporaryDirectory() as folder:
                with patch.dict(os.environ, {"MIRA_DATA_DIR": folder}):
                    app = MiraApp()
                    try:
                        app.model_var.set("gemma4:cloud")
                        app.input.insert("1.0", "Chuyện riêng tư")
                        with patch("mira.gui.messagebox.askyesno", return_value=False) as confirm:
                            app._send()
                        self.assertEqual(confirm.call_count, 1)
                        self.assertFalse(app.cloud_consent)
                        self.assertEqual(app.input.get("1.0", "end").strip(), "Chuyện riêng tư")
                        self.assertEqual(app.chats.get(app.active_chat_id)["messages"], [])
                        self.assertFalse(app.busy)
                    finally:
                        app._close()
        except tk.TclError as exc:
            if "display" in str(exc).lower() or "screen" in str(exc).lower():
                self.skipTest("Môi trường không có màn hình Tkinter: " + str(exc))
            raise


if __name__ == "__main__":
    unittest.main()
