"""Voice policy through the real chat lifecycle, without speakers or a display."""

import os
import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import Mock, patch

from mira.gui import MiraApp
from mira.learning import LearningStore
from mira.preferences import PreferenceStore
from mira.storage import ConversationStore, MemoryStore, load_json
from mira.studio import DesktopStudio


class InlineThread:
    def __init__(self, *, target, **_kwargs):
        self.target = target

    def start(self):
        self.target()


class VoiceAutoTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.tcl = tk.Tcl()
        boolean = lambda value: tk.BooleanVar(master=self.tcl, value=value)
        string = lambda value: tk.StringVar(master=self.tcl, value=value)
        chats = ConversationStore(root / "conversations.json")
        chat = chats.new()
        self.app = SimpleNamespace(
            path=root, settings_path=root / "settings.json", chats=chats,
            active_chat_id=chat["id"], learning=LearningStore(root / "learning.json"),
            preferences=PreferenceStore(root / "preferences.json"),
            memories=MemoryStore(root / "memories.json"),
            agent=SimpleNamespace(respond=Mock(return_value="Mình nghe bạn rồi.")),
            name_var=string("Mira"), model_var=string("qwen3:4b"),
            voice_auto_var=boolean(False), fast_var=boolean(True), deep_var=boolean(False),
            playful_var=boolean(True), web_var=boolean(False), game_react_var=boolean(False),
            title_var=string("Cuộc trò chuyện"), status_var=string("Sẵn sàng"),
            cloud_consent=False, last_local_model="qwen3:4b", cloud_phone_url="",
            persona_note="Xưng em–anh", avatar_style="violet", avatar_custom=False,
            avatar_state="idle", phone_server=None, telegram_bot=None, workspace=None,
            attachment_data=None, attachment_name=None, starters=None,
            busy=False, closed=False, desktop_enabled=False, device_enabled=False,
            desktop_hid_for_action=False, pending_game_event=None, stream_chat_id=None,
            stream_text="", input=Mock(), retry_button=Mock(), send_button=Mock(),
            listen_button=Mock(), speaker=Mock(),
            _confirm_cloud=Mock(return_value=True), _add_message=Mock(),
            _refresh_chat_list=Mock(), _clear_image=Mock(), _show_pending=Mock(),
            _remove_pending=Mock(), _approve_edit=Mock(),
        )
        # Pump timers are skipped; worker completion still executes on this test's
        # main thread, using the production complete() callback and stores.
        self.app.after = lambda delay, callback, *args: callback(*args) if delay == 0 else None
        for method in ("_save_settings", "_set_voice_auto", "_speak", "_voice_done", "_listen_last"):
            setattr(self.app, method, MethodType(getattr(MiraApp, method), self.app))

    def submit(self):
        with patch("mira.gui.threading.Thread", InlineThread):
            MiraApp._submit(self.app, "Chào Mira!")

    def test_dictated_reply_stays_silent_when_auto_read_is_off(self):
        # This legacy flag previously overrode the user's setting.
        self.app.voice_input_used = True
        self.submit()
        self.app.speaker.speak.assert_not_called()
        self.assertEqual(self.app.chats.get(self.app.active_chat_id)["messages"][-1]["role"],
                         "assistant")

    def test_enabled_auto_read_reads_a_successful_reply(self):
        self.app._set_voice_auto(True)
        self.submit()
        self.assertEqual(self.app.speaker.speak.call_args.args[0], "Mình nghe bạn rồi.")

    def test_muting_an_in_flight_reply_prevents_later_playback(self):
        self.app._set_voice_auto(True)
        def respond(*_args, **_kwargs):
            self.assertTrue(self.app.busy)
            self.app._set_voice_auto(False)
            return "Câu trả lời đến sau khi tắt giọng."
        self.app.agent.respond.side_effect = respond
        self.submit()
        self.app.speaker.speak.assert_not_called()
        self.assertFalse(load_json(self.app.settings_path, {})["voice_auto"])

    def test_failed_or_closed_reply_does_not_start_speech(self):
        self.app._set_voice_auto(True)
        self.app.agent.respond.side_effect = RuntimeError("offline")
        self.submit()
        self.app.speaker.speak.assert_not_called()
        self.app.agent.respond.side_effect = lambda *_a, **_k: setattr(self.app, "closed", True) or "Bye"
        self.submit()
        self.app.speaker.speak.assert_not_called()

    def test_reply_for_another_chat_does_not_start_speech(self):
        self.app._set_voice_auto(True)
        other_chat = self.app.chats.new()["id"]
        self.app.agent.respond.side_effect = lambda *_a, **_k: setattr(self.app, "active_chat_id", other_chat) or "Hi"
        self.submit()
        self.app.speaker.speak.assert_not_called()

    def test_disabling_stops_playback_and_persists_without_changing_persona(self):
        self.app._set_voice_auto(True)
        self.app._speak("Mira đang đọc.")
        self.app.speaker.stop.reset_mock()
        self.app._set_voice_auto(False)
        self.app.speaker.stop.assert_called_once()
        self.assertEqual(self.app.avatar_state, "idle")
        self.app.listen_button.configure.assert_called_with(text="🔊 Nghe")
        settings = load_json(self.app.settings_path, {})
        self.assertIs(settings["voice_auto"], False)
        self.assertEqual(settings["persona_note"], "Xưng em–anh")
        restored = tk.BooleanVar(master=self.tcl, value=settings.get("voice_auto") is True)
        self.assertFalse(restored.get())

    def test_muting_while_streaming_preserves_busy_status_and_animation(self):
        self.app.busy = True
        self.app.avatar_state = "speaking"
        self.app.status_var.set("Mira đang tạo câu trả lời…")
        self.app._set_voice_auto(False)
        self.assertEqual(self.app.avatar_state, "speaking")
        self.assertEqual(self.app.status_var.get(), "Mira đang tạo câu trả lời…")
        self.app.speaker.stop.assert_called_once()

    def test_bad_voice_setting_does_not_mutate_or_save(self):
        for value in (None, "false", "true", 0, 1, [], {}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.app._set_voice_auto(value)
        self.app.speaker.stop.assert_not_called()
        self.assertFalse(self.app.settings_path.exists())

    def test_failed_save_still_mutes_the_current_session(self):
        self.app.voice_auto_var.set(True)
        self.app._save_settings = Mock(side_effect=OSError("disk full"))
        with self.assertRaises(OSError):
            self.app._set_voice_auto(False)
        self.assertFalse(self.app.voice_auto_var.get())
        self.app.speaker.stop.assert_called_once()

    def test_manual_listen_remains_available_with_auto_read_off(self):
        self.app.chats.append(self.app.active_chat_id, "assistant", "Đọc một lần theo yêu cầu.")
        self.app._listen_last()
        self.assertEqual(self.app.speaker.speak.call_args.args[0], "Đọc một lần theo yêu cầu.")
        self.assertFalse(self.app.voice_auto_var.get())

    def test_studio_voice_switch_is_validated_and_allowed_during_a_reply(self):
        bridge = DesktopStudio(self.app)
        self.addCleanup(bridge.stop)
        self.app.busy = True
        self.app.voice_auto_var.set(True)
        self.assertEqual(bridge.handle("voice_auto", {"enabled": False}),
                         {"ok": True, "enabled": False})
        with self.assertRaises(ValueError):
            bridge.handle("voice_auto", {"enabled": "false"})
        self.assertFalse(load_json(self.app.settings_path, {})["voice_auto"])

    def test_studio_dictation_does_not_enable_auto_read(self):
        bridge = DesktopStudio(self.app)
        self.addCleanup(bridge.stop)
        with patch("mira.speech.start_windows_dictation") as dictate:
            bridge.handle("dictation", {})
        dictate.assert_called_once()
        self.assertFalse(self.app.voice_auto_var.get())
        self.submit()
        self.app.speaker.speak.assert_not_called()

    def test_classic_dictation_does_not_enable_auto_read(self):
        self.app.after = lambda _delay, callback, *args: callback(*args)
        with patch("mira.gui.start_windows_dictation") as dictate:
            MiraApp._start_dictation(self.app)
        dictate.assert_called_once()
        self.assertFalse(self.app.voice_auto_var.get())

    @unittest.skipUnless(sys.platform == "win32" or os.environ.get("DISPLAY"),
                         "A desktop display is required to restart a real Tk app.")
    def test_restarting_the_real_app_keeps_auto_read_off(self):
        with patch.dict(os.environ, {"MIRA_DATA_DIR": self.directory.name}):
            app = MiraApp(studio=True)
            try:
                app._set_voice_auto(True)
                app._set_voice_auto(False)
            finally:
                app._close()
            restarted = MiraApp(studio=True)
            try:
                self.assertFalse(restarted.voice_auto_var.get())
            finally:
                restarted._close()


if __name__ == "__main__":
    unittest.main()
