"""Opt-in Windows desktop observation and approved input; no shell from the model."""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


_CAPTURE = r"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bitmap = [System.Drawing.Bitmap]::new($bounds.Width, $bounds.Height)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
try {
    $graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
    $bitmap.Save($env:MIRA_CAPTURE_PATH, [System.Drawing.Imaging.ImageFormat]::Png)
} finally {
    $graphics.Dispose()
    $bitmap.Dispose()
}
"""


def capture_primary_screen() -> bytes:
    """Capture once into a private temporary PNG and remove it immediately."""
    if sys.platform != "win32":
        raise RuntimeError("Chụp màn hình tự động hiện chỉ hỗ trợ Mira trên Windows.")
    with tempfile.TemporaryDirectory(prefix="mira-screen-") as folder:
        target = Path(folder) / "screen.png"
        env = {**os.environ, "MIRA_CAPTURE_PATH": str(target)}
        try:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _CAPTURE],
                env=env, capture_output=True, timeout=15, check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError("Không chụp được màn hình. Hãy thử lại khi máy đã mở khóa.") from exc
        if result.returncode or not target.is_file():
            raise RuntimeError("Không chụp được màn hình chính. Hãy thử lại khi máy đã mở khóa.")
        if target.stat().st_size > 5 * 1024 * 1024:
            raise RuntimeError("Ảnh màn hình quá 5 MiB. Hãy giảm độ phân giải hoặc chụp một ảnh riêng.")
        data = target.read_bytes()
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise RuntimeError("Ảnh màn hình nhận được không hợp lệ.")
        return data


_KEYS = {
    "ctrl": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B,
    "enter": 0x0D, "esc": 0x1B, "tab": 0x09, "backspace": 0x08,
    "delete": 0x2E, "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "home": 0x24, "end": 0x23, "space": 0x20, "f4": 0x73,
    **{letter: ord(letter.upper()) for letter in "abcdefghijklmnopqrstuvwxyz"},
}
_APPS = {"notepad": "notepad.exe", "calculator": "calc.exe", "explorer": "explorer.exe"}


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.c_size_t)]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.c_size_t)]


class _INPUT_DATA(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("data", _INPUT_DATA)]


class DesktopController:
    """Only used by the desktop app after the user enables control this session."""

    def __init__(self):
        self.target_window = 0
        self.screen_size: tuple[int, int] | None = None

    @staticmethod
    def _user32():
        if sys.platform != "win32":
            raise RuntimeError("Điều khiển màn hình chỉ hỗ trợ Windows.")
        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.restype = ctypes.c_void_p
        user32.IsWindow.argtypes = [ctypes.c_void_p]
        user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
        user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
        user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        user32.SendInput.argtypes = [ctypes.c_uint, ctypes.POINTER(_INPUT), ctypes.c_int]
        user32.SendInput.restype = ctypes.c_uint
        return user32

    def describe(self, name: str, args: dict) -> str:
        if name == "click_screen":
            x, y = args.get("x"), args.get("y")
            width, height = self._user32().GetSystemMetrics(0), self._user32().GetSystemMetrics(1)
            if self.screen_size and self.screen_size != (width, height):
                raise ValueError("Ảnh và tọa độ Windows khác tỉ lệ; không thể nhấp chính xác. Hãy chỉnh tỉ lệ màn hình rồi chụp lại.")
            if (type(x) is not int or type(y) is not int or
                    not 0 <= x < width or not 0 <= y < height):
                raise ValueError("Tọa độ phải nằm trong màn hình chính.")
            return f"Nhấp chuột trái tại ({x}, {y}) trên màn hình chính."
        if name == "type_text":
            value = args.get("text")
            if not isinstance(value, str) or not 1 <= len(value) <= 500 or "\x00" in value:
                raise ValueError("Văn bản phải dài từ 1 đến 500 ký tự.")
            title = self._target_title()
            return f"Gõ vào cửa sổ {title}:\n{value}"
        if name == "press_keys":
            value = args.get("keys")
            if not isinstance(value, str):
                raise ValueError("Phím tắt không hợp lệ.")
            parts = value.casefold().replace(" ", "").split("+")
            if (not 1 <= len(parts) <= 4 or len(set(parts)) != len(parts)
                    or any(part not in _KEYS for part in parts)
                    or any(part not in ("ctrl", "shift", "alt", "win") for part in parts[:-1])):
                raise ValueError("Chỉ hỗ trợ tổ hợp phím thông dụng, ví dụ Ctrl+S.")
            title = self._target_title()
            return f"Nhấn {value} trong cửa sổ {title}."
        if name == "open_app":
            app = args.get("app")
            if app not in _APPS:
                raise ValueError("Chỉ mở được: notepad, calculator, explorer.")
            return f"Mở ứng dụng Windows: {app}."
        raise ValueError("Hành động desktop không được hỗ trợ.")

    def _target_title(self) -> str:
        user32 = self._user32()
        if not self.target_window or not user32.IsWindow(self.target_window):
            raise ValueError("Hãy chụp màn hình và cho Mira nhấp vào ô đích trước khi gõ/phím tắt.")
        process = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(self.target_window, ctypes.byref(process))
        if process.value == os.getpid():
            raise ValueError("Không thể gõ vào cửa sổ Mira. Hãy nhấp vào ứng dụng đích trước.")
        title = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(self.target_window, title, len(title))
        if not title.value:
            raise ValueError("Không xác định được cửa sổ đích.")
        return title.value

    @staticmethod
    def _send(inputs: list[_INPUT]) -> None:
        arr = (_INPUT * len(inputs))(*inputs)
        sent = ctypes.windll.user32.SendInput(len(arr), arr, ctypes.sizeof(_INPUT))
        if sent != len(arr):
            raise RuntimeError("Windows không cho phép gửi thao tác này vào cửa sổ đích.")

    def _focus(self) -> None:
        user32 = self._user32()
        self._target_title()
        if not user32.SetForegroundWindow(self.target_window):
            raise RuntimeError("Không đưa được cửa sổ đích lên trước. Hãy nhấp lại vào ô cần thao tác.")
        time.sleep(0.12)
        if user32.GetForegroundWindow() != self.target_window:
            raise RuntimeError("Cửa sổ đích đã thay đổi; không gõ để tránh nhầm chỗ.")

    def execute(self, name: str, args: dict) -> str:
        self.describe(name, args)  # Revalidate before touching the desktop.
        if name == "open_app":
            subprocess.Popen([_APPS[args["app"]]], shell=False)
            self.target_window = 0
            return "Đã yêu cầu mở ứng dụng. Hãy chụp màn hình mới để xem kết quả."
        if name == "click_screen":
            user32 = self._user32()
            x, y = args["x"], args["y"]
            if not user32.SetCursorPos(x, y):
                raise RuntimeError("Không di chuyển được chuột đến tọa độ này.")
            self._send([_INPUT(0, _INPUT_DATA(mi=_MOUSEINPUT(0, 0, 0, 0x0002, 0, 0))),
                        _INPUT(0, _INPUT_DATA(mi=_MOUSEINPUT(0, 0, 0, 0x0004, 0, 0)))])
            time.sleep(0.15)
            self.target_window = user32.GetForegroundWindow()
            return "Đã nhấp chuột; Mira chưa nhìn thấy kết quả. Hãy chụp màn hình lại để kiểm tra."
        self._focus()
        if name == "type_text":
            inputs = []
            encoded = args["text"].encode("utf-16-le")
            for index in range(0, len(encoded), 2):
                unit = int.from_bytes(encoded[index:index + 2], "little")
                inputs.extend((_INPUT(1, _INPUT_DATA(ki=_KEYBDINPUT(0, unit, 0x0004, 0, 0))),
                               _INPUT(1, _INPUT_DATA(ki=_KEYBDINPUT(0, unit, 0x0006, 0, 0)))))
            self._send(inputs)
            return "Đã gửi văn bản vào cửa sổ được duyệt; hãy kiểm tra trên màn hình."
        if name == "press_keys":
            codes = [_KEYS[part] for part in args["keys"].casefold().replace(" ", "").split("+")]
            inputs = [_INPUT(1, _INPUT_DATA(ki=_KEYBDINPUT(code, 0, 0, 0, 0))) for code in codes]
            inputs.extend(_INPUT(1, _INPUT_DATA(ki=_KEYBDINPUT(code, 0, 0x0002, 0, 0)))
                          for code in reversed(codes))
            self._send(inputs)
            return "Đã gửi phím tắt vào cửa sổ được duyệt; hãy kiểm tra trên màn hình."
        raise ValueError("Hành động desktop không được hỗ trợ.")
