"""Optional, offline speech using a voice installed in Windows."""

from __future__ import annotations

import base64
import re
import shutil
import subprocess
import sys
import threading
from typing import Callable


def clean_for_speech(text: str) -> str:
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"\[([^]]+)\]\(https?://[^)]+\)", r"\1", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[`*_#>]", "", text)
    return " ".join(text.split())[:800]


def speech_command(text: str) -> list[str]:
    # The text is UTF-8 base64 inside an encoded PowerShell program, never shell code.
    encoded_text = base64.b64encode(text.encode("utf-8")).decode("ascii")
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "try { $s.SetOutputToDefaultAudioDevice(); "
        f"$s.Speak([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded_text}'))) "
        "} finally { $s.Dispose() }"
    )
    return ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand",
            base64.b64encode(script.encode("utf-16-le")).decode("ascii")]


class SpeechPlayer:
    def __init__(self):
        self._lock = threading.Lock()
        self._process: subprocess.Popen | None = None

    @staticmethod
    def available() -> bool:
        return sys.platform == "win32" and shutil.which("powershell.exe") is not None

    def stop(self) -> None:
        with self._lock:
            process, self._process = self._process, None
        if process and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass

    def speak(self, text: str, finished: Callable[[str | None], None]) -> None:
        if not self.available():
            raise RuntimeError("Giọng đọc này cần Windows và PowerShell.")
        spoken = clean_for_speech(text)
        if not spoken:
            raise ValueError("Câu trả lời này không có văn bản để đọc.")
        self.stop()
        process = subprocess.Popen(speech_command(spoken), stdout=subprocess.DEVNULL,
                                   stderr=subprocess.PIPE,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        with self._lock:
            self._process = process

        def wait():
            _, errors = process.communicate()
            with self._lock:
                current = self._process is process
                if current:
                    self._process = None
            if current:
                finished(None if process.returncode == 0 else
                         "Không phát được giọng Windows. Hãy kiểm tra giọng đọc đã cài trong máy.")

        threading.Thread(target=wait, daemon=True).start()
