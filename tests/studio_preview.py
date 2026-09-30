"""Real desktop bridge with synthetic data and an offline test agent for UI QA."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import mira.gui
import mira.speech
from mira.gui import MiraApp
from mira.storage import save_json
from mira.studio import DesktopStudio


class SilentTestSpeaker:
    """Record playback requests without generating audio or invoking PowerShell."""
    def __init__(self, path):
        self.path = path
        self.calls = []
        self.active = False
        self.dictations = 0
        self.record()

    def available(self):
        return True

    def record(self):
        save_json(self.path, {"calls": self.calls, "active": self.active,
                              "dictations": self.dictations})

    def stop(self):
        self.active = False
        self.record()

    def speak(self, text, _finished):
        self.calls.append(text)
        self.active = True
        self.record()

    def dictate(self):
        self.dictations += 1
        self.record()


class OfflineAgent:
    client = None

    def __init__(self):
        self.client = self

    def list_models(self):
        return ["qwen3:4b", "qwen3-vl:4b"]

    def respond(self, text, _history, _model, _name, memories, *_args, on_token=None, **_kwargs):
        if text == "Kiểm tra giọng đọc khi đang chờ.":
            if on_token:
                on_token("Mình đang chờ…")
            release = Path(os.environ["MIRA_DATA_DIR"]) / "release-voice-test"
            deadline = time.monotonic() + 15
            while not release.exists():
                if time.monotonic() >= deadline:
                    raise RuntimeError("The voice test did not release its pending reply.")
                time.sleep(.025)
        if "Cobalt" in text and "18h" in memories:
            answer = "Theo nguồn Dự án Cobalt, robot dùng Python và cần sạc lúc 18h."
        elif text.startswith("Tôi thích"):
            answer = "Mình ghi nhận rồi. Bạn có thể duyệt điều này trong **Bộ nhớ** nhé."
        else:
            answer = ("Mình sẽ chia việc thành những bước ngắn, dễ bắt đầu.\n\n"
                      "1. Chọn một việc quan trọng cho hôm nay.\n2. Dành 15 phút bắt đầu việc đó.\n"
                      "3. Ghi lại điều còn vướng để mình cùng xử lý.\n\nBạn đang muốn ưu tiên điều gì?")
        if on_token:
            for offset in range(0,len(answer),14):
                on_token(answer[offset:offset+14])
                time.sleep(.025)
        return answer


def main():
    app = MiraApp(studio=True)
    app.agent = OfflineAgent()
    app.speaker = SilentTestSpeaker(app.path / "test-audio.json")
    mira.speech.start_windows_dictation = app.speaker.dictate
    mira.gui.start_windows_dictation = app.speaker.dictate
    app.memories.add("Tôi thích câu trả lời ngắn gọn, dễ bắt đầu.")
    app.memories.add("Tôi đang học Python và làm trợ lý Mira.")
    app.learning.add_source("Dự án Cobalt", "Cobalt dùng Python để điều khiển robot. Pin robot cần sạc lúc 18h.")
    app.learning.study(busy=False, force=True)
    app.studio = DesktopStudio(app)
    app.withdraw()
    app.studio.server.start()
    app.after(40, app.studio._pump)
    app.after(180_000, app._close)
    print(json.dumps({"url":app.studio.server.url}),flush=True)
    app.mainloop()


if __name__ == "__main__":
    main()
