"""Private local VRM studio: browser UI, desktop chat and bounded game lessons."""

from __future__ import annotations

import json
import os
import secrets
import struct
import tempfile
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .agent import is_cloud_model
from .desktop import capture_primary_screen
from .lessons import LessonStore


MAX_MODEL_BYTES = 20 * 1024 * 1024
ASSETS = Path(__file__).with_name("studio_assets")
STATIC = {
    "/": (ASSETS / "index.html", "text/html; charset=utf-8"),
    "/assets/studio.js": (ASSETS / "studio.js", "text/javascript; charset=utf-8"),
    "/assets/studio.css": (ASSETS / "studio.css", "text/css; charset=utf-8"),
    "/assets/vendor/three.module.js": (ASSETS / "vendor/three.module.js", "text/javascript"),
    "/assets/vendor/three.core.js": (ASSETS / "vendor/three.core.js", "text/javascript"),
    "/assets/vendor/loaders/GLTFLoader.js": (ASSETS / "vendor/loaders/GLTFLoader.js", "text/javascript"),
    "/assets/vendor/utils/BufferGeometryUtils.js": (ASSETS / "vendor/utils/BufferGeometryUtils.js", "text/javascript"),
}


def check_vrm(data: bytes) -> dict:
    """Accept self-contained VRM 0.x / 1.0 GLBs within a small budget."""
    if not isinstance(data, bytes) or len(data) > MAX_MODEL_BYTES or len(data) < 32:
        raise ValueError("File VRM cần nhỏ hơn 20 MiB.")
    magic, version, size = struct.unpack_from("<4sII", data)
    if magic != b"glTF" or version != 2 or size != len(data):
        raise ValueError("Đây không phải file VRM/GLB phiên bản 2 hợp lệ.")
    chunk_size, chunk_type = struct.unpack_from("<I4s", data, 12)
    if chunk_type != b"JSON" or chunk_size > 2 * 1024 * 1024 or 20 + chunk_size > len(data):
        raise ValueError("Phần mô tả model không hợp lệ hoặc quá lớn.")
    try:
        info = json.loads(data[20:20 + chunk_size])
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Không đọc được thông tin model.") from exc
    if (not isinstance(info, dict) or not isinstance(info.get("asset"), dict)
            or info["asset"].get("version") != "2.0"
            or not isinstance(info.get("scenes"), list) or not info["scenes"]
            or not isinstance(info.get("nodes"), list) or not info["nodes"]
            or not isinstance(info.get("extensions"), dict)):
        raise ValueError("File GLB thiếu dữ liệu VRM.")
    extensions = info["extensions"]
    if not any(ext in extensions for ext in ("VRM", "VRMC_vrm")):
        raise ValueError("Hãy chọn model .vrm, không phải GLB chung.")
    if any(isinstance(entry, dict) and entry.get("uri") and not str(entry["uri"]).startswith("data:")
           for group in ("buffers", "images") for entry in info.get(group, [])):
        raise ValueError("VRM tham chiếu file ngoài; hãy xuất bản VRM tự chứa.")
    return {"version": "1.0" if "VRMC_vrm" in extensions else "0.x",
            "size": len(data)}


class StudioServer:
    def __init__(self, owner, *, port: int = 0):
        self.owner = owner
        self.lessons = owner.lessons
        self.model_path = owner.path / "mira_character.vrm"
        self.token = secrets.token_urlsafe(32)
        self._chat_lock = threading.Lock()
        self._run_lock = threading.Lock()
        self._stop = threading.Event()
        self._screens: dict[str, tuple[float, bytes]] = {}
        self._screens_lock = threading.Lock()
        server = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def log_message(self, *args):
                return

            def _valid_host(self):
                return (self.client_address[0] in ("127.0.0.1", "::1")
                        and self.headers.get("Host", "") == f"127.0.0.1:{server.port}")

            def _authorized(self):
                return (self._valid_host() and secrets.compare_digest(
                    self.headers.get("X-Mira-Session", ""), server.token))

            def _respond(self, status, body: bytes, mime="application/json; charset=utf-8"):
                self.send_response(status)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("X-Frame-Options", "DENY")
                self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; "
                                 "style-src 'self'; connect-src 'self'; img-src 'self' data: blob:; "
                                 "media-src 'self' blob:; base-uri 'none'; form-action 'none'; "
                                 "frame-ancestors 'none'")
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def _json(self, status, value):
                self._respond(status, json.dumps(value, ensure_ascii=False).encode("utf-8"))

            def _input(self, max_size=8192):
                if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
                    raise ValueError("Yêu cầu cần JSON.")
                try:
                    count = int(self.headers.get("Content-Length", ""))
                except ValueError as exc:
                    raise ValueError("Thiếu độ dài dữ liệu.") from exc
                if not 0 < count <= max_size:
                    raise ValueError("Dữ liệu quá dài.")
                try:
                    obj = json.loads(self.rfile.read(count))
                except (ValueError, UnicodeDecodeError) as exc:
                    raise ValueError("JSON không hợp lệ.") from exc
                if not isinstance(obj, dict):
                    raise ValueError("Dữ liệu không hợp lệ.")
                return obj

            def do_GET(self):
                if not self._valid_host():
                    self._json(403, {"error": "Trang này chỉ mở trên máy của bạn."})
                    return
                parsed = urlsplit(self.path)
                path = parsed.path
                if path in STATIC:
                    source, mime = STATIC[path]
                    self._respond(200, source.read_bytes(), mime)
                    return
                if not self._authorized():
                    self._json(401, {"error": "Phiên Mira không hợp lệ. Hãy mở lại từ ứng dụng Mira."})
                    return
                if path == "/api/state":
                    try:
                        self._json(200, server.state())
                    except (RuntimeError, ValueError) as exc:
                        self._json(503, {"error": str(exc)})
                elif path == "/api/model":
                    model = server.model_path
                    if not model.is_file() or model.stat().st_size > MAX_MODEL_BYTES:
                        self._json(404, {"error": "Chưa có model."})
                    else:
                        self._respond(200, model.read_bytes(), "model/gltf-binary")
                elif path == "/api/screen":
                    ticket = parse_qs(parsed.query).get("ticket", [""])[0]
                    with server._screens_lock:
                        entry = server._screens.get(ticket)
                    if entry and time.monotonic() - entry[0] < 120:
                        self._respond(200, entry[1], "image/png")
                    else:
                        self._json(404, {"error": "Ảnh đã hết hạn."})
                else:
                    self._json(404, {"error": "Không tìm thấy."})

            def do_POST(self):
                if not self._authorized() or self.headers.get("Origin", f"http://127.0.0.1:{server.port}") != f"http://127.0.0.1:{server.port}":
                    self._json(403, {"error": "Không có quyền trong phiên Mira này."})
                    return
                try:
                    if self.path == "/api/import":
                        if self.headers.get("Content-Type") != "model/gltf-binary":
                            raise ValueError("Hãy gửi file VRM.")
                        count = int(self.headers.get("Content-Length", "0"))
                        if not 32 <= count <= MAX_MODEL_BYTES:
                            raise ValueError("VRM phải dưới 20 MiB.")
                        data = self.rfile.read(count)
                        meta = check_vrm(data)
                        fd, temp = tempfile.mkstemp(dir=server.model_path.parent, suffix=".vrm")
                        try:
                            with os.fdopen(fd, "wb") as out:
                                out.write(data)
                            os.replace(temp, server.model_path)
                        finally:
                            if os.path.exists(temp):
                                os.unlink(temp)
                        self._json(200, meta)
                        return
                    obj = self._input()
                    if self.path == "/api/chat":
                        server.chat(self, obj)
                        return
                    if self.path == "/api/teach":
                        item = server.lessons.add(obj.get("name"), obj.get("steps"))
                        self._json(200, {"lesson": item})
                    elif self.path == "/api/delete-lesson":
                        server.lessons.remove(obj.get("id"))
                        self._json(200, {"ok": True})
                    elif self.path == "/api/memory":
                        item = server._tk(lambda: server.owner.memories.add(obj.get("text")))
                        self._json(200, {"memory": item})
                    elif self.path == "/api/new-chat":
                        def create():
                            owner = server.owner
                            owner.active_chat_id = owner.chats.create()
                            owner._refresh_chat_list()
                            owner._render_chat()
                            owner._save_settings()
                            return owner.active_chat_id
                        self._json(200, {"id": server._tk(create)})
                    elif self.path == "/api/select-chat":
                        def select():
                            owner = server.owner
                            if not isinstance(obj.get("id"), str) or not owner.chats.get(obj["id"]):
                                raise ValueError("Không tìm thấy cuộc trò chuyện.")
                            owner.active_chat_id = obj["id"]
                            owner._refresh_chat_list()
                            owner._render_chat()
                            owner._save_settings()
                        server._tk(select)
                        self._json(200, {"ok": True})
                    elif self.path == "/api/forget":
                        server._tk(lambda: server.owner.memories.forget(obj.get("id")))
                        self._json(200, {"ok": True})
                    elif self.path == "/api/desktop":
                        server._tk(server.owner._toggle_desktop)
                        self._json(200, {"enabled": server._tk(lambda: server.owner.desktop_enabled)})
                    elif self.path == "/api/target":
                        if not server._tk(lambda: server.owner.desktop_enabled):
                            raise ValueError("Bật quyền điều khiển máy trước.")
                        time.sleep(3)
                        if not server._tk(lambda: server.owner.desktop_enabled):
                            raise ValueError("Quyền điều khiển đã tắt.")
                        title = server.owner.desktop.select_foreground()
                        self._json(200, {"title": title})
                    elif self.path == "/api/run":
                        if not server._tk(lambda: server.owner.desktop_enabled):
                            raise ValueError("Bật quyền điều khiển máy trước.")
                        if not server._run_lock.acquire(blocking=False):
                            raise ValueError("Một bài học đang chạy.")
                        try:
                            server._stop.clear()
                            answer = server.lessons.run(obj.get("id"), server.owner.desktop,
                                                        server.owner._approve_desktop_action, server._stop)
                            self._json(200, {"result": answer})
                        finally:
                            server._run_lock.release()
                    elif self.path == "/api/stop":
                        server._stop.set()
                        server.lessons.stop_event.set()
                        self._json(200, {"ok": True})
                    elif self.path == "/api/screenshot":
                        if not server._tk(lambda: server.owner._ask_studio_screen()):
                            raise ValueError("Bạn đã hủy chia sẻ màn hình.")
                        time.sleep(2)
                        picture = capture_primary_screen()
                        ticket = secrets.token_urlsafe(18)
                        with server._screens_lock:
                            server._screens.clear()
                            server._screens[ticket] = (time.monotonic(), picture)
                        self._json(200, {"ticket": ticket})
                    elif self.path == "/api/desktop-window":
                        server._tk(lambda: (server.owner.deiconify(), server.owner.lift()))
                        self._json(200, {"ok": True})
                    else:
                        self._json(404, {"error": "Không tìm thấy hành động."})
                except (OSError, RuntimeError, TypeError, ValueError) as exc:
                    self._json(400, {"error": str(exc)})

        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def url(self):
        return f"http://127.0.0.1:{self.port}/#session={self.token}"

    def open(self):
        webbrowser.open(self.url())

    def stop(self):
        self._stop.set()
        self.lessons.stop_event.set()
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=3)

    def _tk(self, action):
        event = threading.Event()
        result = []

        def perform():
            try:
                if self.owner.closed:
                    raise RuntimeError("Mira đã đóng.")
                result.append((True, action()))
            except Exception as exc:
                result.append((False, exc))
            finally:
                event.set()

        try:
            self.owner.after(0, perform)
        except RuntimeError as exc:
            raise RuntimeError("Mira đã đóng.") from exc
        if not event.wait(60):
            raise RuntimeError("Giao diện Mira không phản hồi.")
        ok, value = result[0]
        if ok:
            return value
        raise value

    def state(self):
        def snapshot():
            owner = self.owner
            chat = owner.chats.get(owner.active_chat_id)
            try:
                target = owner.desktop._target_title() if owner.desktop.target_window else ""
            except (RuntimeError, ValueError):
                target = ""
            return {"name": owner.name_var.get(), "model": owner.model_var.get(),
                    "cloud_allowed": owner.cloud_consent, "desktop_enabled": owner.desktop_enabled,
                    "target": target,
                    "chat_id": owner.active_chat_id, "chats": [
                        {"id": item["id"], "title": item["title"]} for item in owner.chats.list()[:40]],
                    "messages": list(chat["messages"][-40:]) if chat else [],
                    "memories": list(owner.memories.items[-20:]),
                    "model_loaded": self.model_path.is_file(), "platform": os.name}

        data = self._tk(snapshot)
        data["lessons"] = self.lessons.list()
        return data

    def chat(self, handler, obj):
        prompt = obj.get("text")
        if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 3000:
            raise ValueError("Tin nhắn cần từ 1 đến 3000 ký tự.")
        if not self._chat_lock.acquire(blocking=False):
            raise ValueError("Mira đang trả lời một tin nhắn khác.")
        try:
            config = self._tk(lambda: {"model": self.owner.model_var.get().strip(),
                                       "cloud": self.owner.cloud_consent, "chat_id": self.owner.active_chat_id,
                                       "name": self.owner.name_var.get().strip()[:40] or "Mira",
                                       "busy": self.owner.busy})
            if config["busy"]:
                raise ValueError("Mira đang trả lời trong cửa sổ máy tính.")
            if is_cloud_model(config["model"]) and not config["cloud"]:
                raise ValueError("Bạn cần đồng ý dùng Ollama Cloud trong cửa sổ Mira trước.")
            ticket = obj.get("screen_ticket")
            image = None
            if ticket:
                with self._screens_lock:
                    entry = self._screens.pop(ticket, None)
                if not entry or time.monotonic() - entry[0] > 120:
                    raise ValueError("Ảnh màn hình đã hết hạn; hãy chụp lại.")
                image = entry[1]
            text = prompt.strip()

            def before():
                chat_id = config["chat_id"]
                history = self.owner.chats.messages(chat_id)
                self.owner.chats.append(chat_id, "user", text + ("\n[Ảnh màn hình đã cấp]" if image else ""))
                if self.owner.active_chat_id == chat_id:
                    self.owner._refresh_chat_list()
                    self.owner._render_chat()
                return history

            history = self._tk(before)
            handler.send_response(HTTPStatus.OK)
            handler.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            handler.send_header("Cache-Control", "no-store")
            handler.send_header("X-Content-Type-Options", "nosniff")
            handler.send_header("Connection", "close")
            handler.end_headers()

            def event(data):
                try:
                    handler.wfile.write((json.dumps(data, ensure_ascii=False) + "\n").encode("utf-8"))
                    handler.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass

            event({"type": "started"})
            try:
                memory = self._tk(lambda: ("Bộ sở thích:\n" + self.owner.preferences.prompt_for(text) +
                                            "\nGhi nhớ:\n" + self.owner.memories.prompt_for(text)))
                settings = self._tk(lambda: {"workspace": self.owner.workspace,
                                             "web": self.owner.web_var.get(),
                                             "desktop": self.owner.desktop if self.owner.desktop_enabled else None,
                                             "device": self.owner.device_enabled,
                                             "fast": self.owner.fast_var.get(),
                                             "persona": "playful" if self.owner.playful_var.get() else "standard",
                                             "note": self.owner.persona_note,
                                             "think": self.owner.deep_var.get()})
                answer = self.owner.agent.respond(
                    text, history, config["model"], config["name"], memory, settings["workspace"],
                    self.owner._approve_edit, image=image, on_token=lambda word: event({"type": "token", "text": word}),
                    fast=settings["fast"], persona=settings["persona"], persona_note=settings["note"],
                    think=settings["think"], web_enabled=settings["web"], desktop=settings["desktop"],
                    approve_action=self.owner._approve_desktop_action if settings["desktop"] else None,
                    status_reader=self.owner._read_status_if_enabled if settings["device"] else None,
                    lessons=self.lessons if settings["desktop"] else None)
                self._tk(lambda: self.owner.chats.append(config["chat_id"], "assistant", answer))
                self._tk(lambda: self.owner._render_chat() if self.owner.active_chat_id == config["chat_id"] else None)
                event({"type": "done", "answer": answer})
            except Exception as exc:
                event({"type": "error", "error": str(exc)})
        finally:
            self._chat_lock.release()
