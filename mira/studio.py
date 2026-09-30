"""Local desktop renderer, using the same agent, data and permissions as Tk."""

from __future__ import annotations

import copy
import json
import mimetypes
import os
import queue
import secrets
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .storage import load_json, save_json


ASSETS = Path(__file__).with_name("studio_assets")
COOKIE = "mira_studio_session"
MAX_BODY = 150_000


class StudioServer:
    """Loopback only; same-origin requests, session cookie and CSRF required."""

    def __init__(self, dispatch):
        self.dispatch = dispatch
        self.token = secrets.token_urlsafe(32)
        self.session = secrets.token_urlsafe(32)
        self.csrf = secrets.token_urlsafe(32)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.server.daemon_threads = True
        self.server.block_on_close = False
        self.host = f"127.0.0.1:{self.server.server_port}"
        self.origin = "http://" + self.host
        self.url = self.origin + "/#session=" + self.token
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        if self.thread.is_alive():
            self.server.shutdown()
        self.server.server_close()

    def _handler(self):
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                super().setup()
                self.connection.settimeout(10)

            def log_message(self, *_args):
                pass  # Never write prompts, local paths, cookies or token URLs to logs.

            def reply(self, code, body, content_type="application/json; charset=utf-8", *, cookie=False):
                if not isinstance(body, bytes):
                    body = json.dumps(body, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("X-Frame-Options", "DENY")
                self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; "
                                 "style-src 'self'; img-src 'self' data:; connect-src 'self'; "
                                 "font-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
                if cookie:
                    self.send_header("Set-Cookie", f"{COOKIE}={owner.session}; Path=/; HttpOnly; SameSite=Strict")
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def host_ok(self):
                return self.headers.get("Host") == owner.host

            def origin_ok(self):
                return self.headers.get("Origin") == owner.origin

            def authenticated(self):
                try:
                    cookies = SimpleCookie(self.headers.get("Cookie", ""))
                    value = cookies[COOKIE].value if COOKIE in cookies else ""
                    return secrets.compare_digest(value, owner.session)
                except Exception:
                    return False

            def do_GET(self):
                if not self.host_ok():
                    self.reply(403, {"error": "Địa chỉ truy cập không hợp lệ."})
                    return
                path = urlsplit(self.path).path
                allowed = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css",
                           "/mira.svg": "mira.svg"}
                if path in allowed:
                    filename = ASSETS / allowed[path]
                    asset = filename.read_bytes()
                    if path == "/mira.svg":
                        from urllib.parse import parse_qs
                        style = parse_qs(urlsplit(self.path).query).get("style", ["violet"])[0]
                        palettes = {"aqua": ("#c8e8e4", "#72aaa4", "#527d76"),
                                    "rose": ("#f0d5e1", "#c18fab", "#90627e")}
                        if style in palettes:
                            for old, new in zip(("#dcd1fa", "#a38ed6", "#625086"), palettes[style]):
                                asset = asset.replace(old.encode(), new.encode())
                    self.reply(200, asset,
                               mimetypes.guess_type(filename)[0] or "application/octet-stream")
                    return
                if not self.authenticated():
                    self.reply(401, {"error": "Hãy mở Mira bằng start_windows.bat trên máy này."})
                    return
                if path == "/api/state":
                    try:
                        self.reply(200, owner.dispatch("state", {}))
                    except (TimeoutError, RuntimeError):
                        self.reply(503, {"error": "Mira đang chờ hộp thoại trên máy tính."})
                elif path == "/api/avatar":
                    try:
                        data = owner.dispatch("avatar", {})
                        self.reply(200, data, "image/png")
                    except (ValueError, OSError, TimeoutError):
                        self.reply(404, {"error": "Chưa có ảnh nhân vật riêng."})
                else:
                    self.reply(404, {"error": "Không tìm thấy trang này."})

            def do_POST(self):
                if not self.host_ok() or not self.origin_ok():
                    self.reply(403, {"error": "Yêu cầu phải đến từ cửa sổ Mira trên máy này."})
                    return
                if self.headers.get_content_type() != "application/json":
                    self.reply(415, {"error": "Yêu cầu phải dùng JSON."})
                    return
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 1 <= size <= MAX_BODY:
                        raise ValueError("Yêu cầu quá lớn hoặc trống.")
                    body = json.loads(self.rfile.read(size))
                    if not isinstance(body, dict):
                        raise ValueError("Nội dung yêu cầu không hợp lệ.")
                except (ValueError, UnicodeError, TimeoutError):
                    self.reply(400, {"error": "Không đọc được yêu cầu."})
                    return
                if self.path == "/api/session":
                    token = body.get("token", "")
                    if self.authenticated() or (isinstance(token, str) and secrets.compare_digest(token, owner.token)):
                        self.reply(200, {"csrf": owner.csrf}, cookie=True)
                    else:
                        self.reply(401, {"error": "Phiên đã hết hạn. Đóng trang và mở lại Mira."})
                    return
                if not self.authenticated() or not secrets.compare_digest(
                        self.headers.get("X-Mira-CSRF", ""), owner.csrf):
                    self.reply(403, {"error": "Phiên không hợp lệ. Hãy mở lại Mira."})
                    return
                if self.path != "/api/command":
                    self.reply(404, {"error": "Không tìm thấy chức năng này."})
                    return
                operation = body.get("operation")
                data = body.get("data", {})
                if not isinstance(operation, str) or not isinstance(data, dict):
                    self.reply(400, {"error": "Lệnh không hợp lệ."})
                    return
                try:
                    self.reply(200, owner.dispatch(operation, data) or {"ok": True})
                except (ValueError, OSError, RuntimeError, TimeoutError) as exc:
                    self.reply(400, {"error": str(exc)})

        return Handler


def browser_executable() -> str | None:
    if sys.platform == "win32":
        for variable in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
            base = os.environ.get(variable)
            if not base:
                continue
            for relative in ("Microsoft/Edge/Application/msedge.exe", "Google/Chrome/Application/chrome.exe"):
                target = Path(base) / relative
                if target.is_file():
                    return str(target)
    for name in ("microsoft-edge", "google-chrome", "chromium", "chromium-browser"):
        executable = shutil.which(name)
        if executable:
            return executable
    return None


class DesktopStudio:
    """All Tk and store access is marshalled to the existing desktop main loop."""

    def __init__(self, app):
        self.app = app
        self.requests = queue.Queue(maxsize=32)
        self.closed = False
        self.last_heartbeat = time.monotonic()
        self.settings_path = app.path / "studio.json"
        self.settings = load_json(self.settings_path, {"theme": "light"})
        if not isinstance(self.settings, dict) or self.settings.get("theme") not in ("light", "dark"):
            self.settings = {"theme": "light"}
        self.server = StudioServer(self.dispatch)
        self.process = None
        self.window_handle = 0

    def minimize(self):
        if sys.platform != "win32":
            return
        import ctypes
        user32 = ctypes.windll.user32
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def inspect(handle, _):
            text = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(ctypes.c_void_p(handle), text, len(text))
            if "Mira Studio" in text.value and self.server.host in text.value:
                self.window_handle = handle
                return False
            return True
        user32.EnumWindows(callback_type(inspect), 0)
        if self.window_handle:
            user32.ShowWindow(ctypes.c_void_p(self.window_handle), 6)

    def restore(self):
        if sys.platform == "win32" and self.window_handle:
            import ctypes
            user32 = ctypes.windll.user32
            user32.ShowWindow(ctypes.c_void_p(self.window_handle), 9)
            user32.SetForegroundWindow(ctypes.c_void_p(self.window_handle))

    def start(self):
        executable = browser_executable()
        if not executable and sys.platform == "win32":
            raise RuntimeError("Không tìm thấy Microsoft Edge hoặc Google Chrome. Mira sẽ mở giao diện cổ điển.")
        self.server.start()
        try:
            if executable:
                profile = self.app.path / "studio-browser"
                self.process = subprocess.Popen([executable, "--app=" + self.server.url,
                                                 "--user-data-dir=" + str(profile),
                                                 "--no-first-run", "--no-default-browser-check",
                                                 "--window-size=1440,960"],
                                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif not webbrowser.open(self.server.url):
                raise RuntimeError("Không mở được cửa sổ Mira Studio.")
        except (OSError, RuntimeError):
            self.server.stop()
            raise
        self.app.withdraw()
        self.app.after(40, self._pump)
        opened_at = self.last_heartbeat
        def check_opened():
            if not self.closed and self.last_heartbeat <= opened_at:
                self.stop()
                self.app.studio = None
                self.app.studio_mode = False
                self.app.deiconify()
                self.app._render_chat()
                self.app._animate_avatar()
                self.app.status_var.set("Không kết nối được cửa sổ Studio; đang dùng giao diện cổ điển.")
        self.app.after(20_000, check_opened)

    def stop(self):
        if self.closed:
            return
        self.closed = True
        threading.Thread(target=self.server.stop, daemon=True).start()
        while not self.requests.empty():
            try:
                _, _, done, result = self.requests.get_nowait()
                result.append(RuntimeError("Mira đã đóng."))
                done.set()
            except queue.Empty:
                break

    def dispatch(self, operation, data):
        if self.closed:
            raise RuntimeError("Mira đã đóng.")
        done, result = threading.Event(), []
        try:
            self.requests.put_nowait((operation, data, done, result))
        except queue.Full as exc:
            raise RuntimeError("Mira đang xử lý nhiều yêu cầu. Hãy thử lại.") from exc
        # A native confirmation may remain open. Short-lived state reads never execute late mutations.
        if not done.wait(8 if operation in ("state", "avatar") else 300):
            done.set()  # An expired queued request must not mutate anything later.
            raise TimeoutError("Hãy hoàn tất hộp thoại Mira trên máy tính rồi thử lại.")
        if isinstance(result[0], Exception):
            raise result[0]
        return result[0]

    def _pump(self):
        if self.closed or self.app.closed:
            return
        for _ in range(8):
            try:
                operation, data, done, result = self.requests.get_nowait()
            except queue.Empty:
                break
            if done.is_set():
                continue
            try:
                result.append(self.handle(operation, data))
            except Exception as exc:
                result.append(exc if isinstance(exc, (ValueError, OSError, RuntimeError)) else
                              RuntimeError("Không thực hiện được thao tác: " + str(exc)))
            finally:
                done.set()
        self.app.after(40, self._pump)

    def snapshot(self):
        app = self.app
        self.last_heartbeat = time.monotonic()
        current = app.chats.get(app.active_chat_id)
        return {"version": "Mira Studio 3", "name": app.name_var.get(),
                "window_title": "Mira Studio · " + self.server.host, "error": app.last_error,
                "chat_id": app.active_chat_id, "title": current["title"],
                "chats": [{k: c[k] for k in ("id", "title", "updated_at")} for c in app.chats.list()],
                "messages": copy.deepcopy(current["messages"]), "busy": app.busy,
                "stream": app.stream_text if app.stream_chat_id == app.active_chat_id else "",
                "status": app.status_var.get(), "health": app.health_var.get(),
                "models": list(app.available_models), "attachment": app.attachment_name,
                "retry": bool(app.retry_text and app.retry_chat_id == app.active_chat_id),
                "folder": str(app.workspace.root) if app.workspace else "",
                "avatar_custom": app.avatar_custom, "avatar_style": app.avatar_style,
                "avatar_revision": app.custom_avatar_path.stat().st_mtime_ns if app.avatar_custom else 0,
                "memories": copy.deepcopy(app.memories.items),
                "preferences": copy.deepcopy(app.preferences.data),
                "learning": app.learning.snapshot(),
                "config": {"model": app.model_var.get(), "fast": app.fast_var.get(),
                           "deep": app.deep_var.get(), "playful": app.playful_var.get(),
                           "voice_auto": app.voice_auto_var.get(), "web": app.web_var.get(),
                           "desktop": app.desktop_enabled, "device": app.device_enabled,
                           "cloud_consent": app.cloud_consent, "persona_note": app.persona_note,
                           "theme": self.settings["theme"], "windows": sys.platform == "win32"}}

    @staticmethod
    def _text(data, key, maximum, *, optional=False):
        value = data.get(key, "")
        if not isinstance(value, str) or len(value.strip()) > maximum or (not optional and not value.strip()):
            raise ValueError(f"Nội dung {key} phải dài từ {0 if optional else 1} đến {maximum} ký tự.")
        return value.strip()

    def handle(self, operation, data):
        app = self.app
        if operation == "state":
            return self.snapshot()
        if operation == "avatar":
            if not app.avatar_custom:
                raise ValueError("Chưa chọn ảnh nhân vật.")
            if app.custom_avatar_path.stat().st_size > 5 * 1024 * 1024:
                raise ValueError("Ảnh nhân vật quá lớn.")
            return app.custom_avatar_path.read_bytes()
        if operation == "window_closing":
            stamp = time.monotonic()
            def close_if_gone():
                if not self.closed and self.last_heartbeat < stamp:
                    app._close()
            app.after(10_000, close_if_gone)
            return {"ok": True}
        if operation == "quit":
            app.after(150, app._close)
            return {"ok": True}
        app.learning.touch()
        if operation == "activity":
            return {"ok": True}
        if operation == "send":
            if app.busy:
                raise ValueError("Hãy đợi Mira trả lời xong.")
            text = self._text(data, "text", 24_000, optional=bool(app.attachment_data))
            app.input.delete("1.0", "end")
            app.input.insert("1.0", text)
            app._submit(text)
            return {"sent": app.busy}
        if operation == "retry":
            app._retry()
        elif operation in ("chat_new", "chat_select", "chat_rename", "chat_delete"):
            if app.busy:
                raise ValueError("Hãy đợi Mira trả lời xong rồi đổi cuộc trò chuyện.")
            chat_id = data.get("id", app.active_chat_id)
            if operation != "chat_new" and app.chats.get(chat_id) is None:
                raise ValueError("Cuộc trò chuyện không còn tồn tại.")
            if operation == "chat_new":
                app.active_chat_id = app.chats.new()["id"]
            elif operation == "chat_select":
                app.active_chat_id = chat_id
            elif operation == "chat_rename":
                app.chats.rename(chat_id, self._text(data, "title", 80))
            else:
                app.chats.delete(chat_id)
                if not app.chats.items:
                    app.chats.new()
                if app.active_chat_id == chat_id:
                    app.active_chat_id = app.chats.items[0]["id"]
            app._clear_image()
            app.last_error = ""
            app._refresh_chat_list()
            app._render_chat()
            app._save_settings()
        elif operation == "memory_add":
            app.memories.add(self._text(data, "text", 500))
        elif operation == "memory_edit":
            app.memories.edit(data.get("id"), self._text(data, "text", 500))
        elif operation == "memory_delete":
            app.memories.forget(data.get("id"))
        elif operation == "candidate_decide":
            if type(data.get("accept")) is not bool:
                raise ValueError("Thiếu lựa chọn lưu hay bỏ qua.")
            app.learning.decide_candidate(data.get("id"), app.memories, accept=data["accept"],
                                          text=data.get("text"))
        elif operation == "source_add":
            app.learning.add_source(self._text(data, "title", 100), self._text(data, "text", 32_000))
        elif operation == "source_import":
            from tkinter import filedialog
            filename = filedialog.askopenfilename(parent=app, title="Chọn tài liệu để Mira học",
                                                  filetypes=[("Văn bản UTF-8", "*.txt *.md")])
            if filename:
                source = Path(filename)
                if source.suffix.lower() not in (".txt", ".md") or source.stat().st_size > 128_000:
                    raise ValueError("Chỉ nhận file .txt hoặc .md UTF-8, tối đa 32.000 ký tự.")
                app.learning.add_source(source.stem[:100], source.read_text(encoding="utf-8-sig"))
        elif operation == "source_delete":
            app.learning.remove_source(data.get("id"))
        elif operation == "study_config":
            app.learning.configure(data.get("auto"), data.get("interval"))
        elif operation == "study_now":
            if app.busy:
                raise ValueError("Hãy đợi Mira trả lời xong trước khi ôn tài liệu.")
            report = app.learning.study(busy=False, force=True)
            if not report:
                raise ValueError("Hãy thêm một nguồn học trước.")
            app.status_var.set(report["title"])
        elif operation == "rule_add":
            app.preferences.add_rule(self._text(data, "text", 500))
        elif operation == "preference_delete":
            app.preferences.remove(data.get("id"))
        elif operation == "example_add":
            app.preferences.add_example(self._text(data, "tags", 500), self._text(data, "request", 500),
                                         self._text(data, "answer", 500))
        elif operation == "voice_auto":
            app._set_voice_auto(data.get("enabled"))
            return {"ok": True, "enabled": app.voice_auto_var.get()}
        elif operation == "settings":
            if app.busy:
                raise ValueError("Hãy đợi Mira trả lời xong rồi đổi cài đặt.")
            name = self._text(data, "name", 40)
            model = self._text(data, "model", 100)
            note = self._text(data, "persona_note", 400, optional=True)
            theme = data.get("theme")
            if theme not in ("light", "dark") or any(type(data.get(k)) is not bool
                                                     for k in ("fast", "deep", "playful", "voice_auto")):
                raise ValueError("Cài đặt giao diện không hợp lệ.")
            app.name_var.set(name)
            app.model_var.set(model)
            app.persona_note = note
            app.fast_var.set(data["fast"])
            app.deep_var.set(data["deep"])
            app.playful_var.set(data["playful"])
            app._set_voice_auto(data["voice_auto"])
            self.settings = {"theme": theme}
            save_json(self.settings_path, self.settings)
            app._check_ollama()
        elif operation == "tool":
            if data.get("name") == "file":
                draft = self._text(data, "draft", 24_000, optional=True)
                app.input.delete("1.0", "end")
                app.input.insert("1.0", draft)
            self._tool(data.get("name"))
            if data.get("name") == "file":
                return {"ok": True, "draft": app.input.get("1.0", "end").strip()}
        elif operation == "dictation":
            from .speech import start_windows_dictation
            if app.busy:
                raise ValueError("Hãy đợi Mira trả lời xong.")
            app.speaker.stop()
            start_windows_dictation()
        else:
            raise ValueError("Mira không hỗ trợ lệnh này.")
        return {"ok": True}

    def _tool(self, name):
        app = self.app
        tools = {"folder": app._choose_folder, "clear_folder": app._clear_folder,
                 "file": app._attach_file, "image": app._attach_image, "clear_image": app._clear_image,
                 "screen": app._attach_screen, "comment_screen": app._comment_on_screen,
                 "tests": app._run_tests, "reminders": app._reminders_dialog,
                 "phone": app._mobile_dialog, "phone_cloud": app._cloud_phone_dialog,
                 "telegram": app._telegram_dialog, "game": app._game_dialog,
                 "avatar": app._avatar_dialog, "export": app._export_chat,
                 "models": app._model_lab_dialog, "cloud": app._cloud_dialog,
                 "check": app._check_ollama, "guide": app._setup_guide,
                 "desktop": app._toggle_desktop, "device": app._toggle_device,
                 "web": lambda: app._toggle_web(not app.web_var.get()),
                 "listen": app._listen_last, "memories_advanced": app._show_memories}
        if name not in tools:
            raise ValueError("Công cụ này không được hỗ trợ.")
        if app.busy and name not in ("listen", "reminders", "device", "desktop", "web"):
            raise ValueError("Hãy đợi Mira trả lời xong rồi mở công cụ này.")
        tools[name]()
