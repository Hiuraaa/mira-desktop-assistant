"""Opt-in, loopback-only phone companion for a private Tailscale Serve connection."""

from __future__ import annotations

import json
import secrets
import threading
import time
from collections import deque
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .agent import is_cloud_model
from .reminders import draft_reminder
from .storage import load_json, save_json


class MobileConversation:
    """Separate phone history: web requests never touch Tk widgets or desktop chat state."""

    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        self.messages = load_json(path, [])
        if not isinstance(self.messages, list) or any(
            not isinstance(item, dict) or item.get("role") not in ("user", "assistant")
            or not isinstance(item.get("content"), str) for item in self.messages
        ):
            raise ValueError("Lịch sử chat điện thoại không đúng định dạng.")

    def list(self) -> list[dict]:
        with self.lock:
            return [item.copy() for item in self.messages[-40:]]

    def append_exchange(self, prompt: str, answer: str):
        with self.lock:
            updated = (self.messages + [{"role": "user", "content": prompt},
                                        {"role": "assistant", "content": answer}])[-40:]
            save_json(self.path, updated)
            self.messages = updated

    def clear(self):
        with self.lock:
            save_json(self.path, [])
            self.messages = []


class PhoneServer:
    """Serves chat/reminders on 127.0.0.1; Tailscale Serve supplies private HTTPS."""

    def __init__(self, path: Path, agent, reminders, memories, preferences,
                 *, port: int = 8765, model: str, name: str, cloud_consent: bool,
                 fast: bool, persona: str, persona_note: str):
        self.agent = agent
        self.reminders = reminders
        self.memories = memories
        self.preferences = preferences
        self.chat = MobileConversation(path / "phone_conversation.json")
        self._lock = threading.RLock()
        self._request_lock = threading.Lock()
        self._attempts: deque[float] = deque()
        self._sessions: dict[str, tuple[str, str, float]] = {}
        self._pair_code = ""
        self._pair_expires = 0.0
        self.config = {"model": model, "name": name, "cloud_consent": cloud_consent,
                       "fast": fast, "persona": persona, "persona_note": persona_note}
        self.new_pairing_code()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def setup(self):
                super().setup()
                self.connection.settimeout(15)

            def log_message(self, format, *args):
                return  # Never log prompts, pairing codes or cookies.

            def _headers(self, status: int, content_type: str, data: bytes, extra: dict | None = None):
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("X-Frame-Options", "DENY")
                self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; "
                                 "script-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; "
                                 "form-action 'self'; frame-ancestors 'none'")
                for key, value in (extra or {}).items():
                    self.send_header(key, value)
                self.end_headers()
                try:
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def _json(self, status: int, value: dict, extra: dict | None = None):
                self._headers(status, "application/json; charset=utf-8",
                              json.dumps(value, ensure_ascii=False).encode("utf-8"), extra)

            def _identity(self) -> str | None:
                # Tailscale Serve injects this header for a signed-in personal device.
                # The server is loopback-only and also requires a one-time code.
                login = self.headers.get("Tailscale-User-Login", "")
                hostname = self.headers.get("Host", "").split(":", 1)[0].lower()
                if hostname not in ("127.0.0.1", "localhost") and not hostname.endswith(".ts.net"):
                    return None
                return login if 0 < len(login) <= 254 else None

            def _session(self, identity: str) -> tuple[str, str] | None:
                try:
                    cookie = SimpleCookie()
                    cookie.load(self.headers.get("Cookie", ""))
                    token = cookie["mira_phone"].value
                except (KeyError, ValueError):
                    return None
                with owner._lock:
                    info = owner._sessions.get(token)
                    if not info or info[0] != identity or time.monotonic() > info[2]:
                        return None
                    return token, info[1]

            def _body(self) -> dict:
                if self.headers.get("Content-Type", "").split(";", 1)[0].lower() != "application/json":
                    raise ValueError("Yêu cầu cần JSON.")
                try:
                    size = int(self.headers.get("Content-Length", ""))
                except ValueError as exc:
                    raise ValueError("Thiếu dung lượng dữ liệu.") from exc
                if not 0 < size <= 8192:
                    raise ValueError("Dữ liệu quá dài.")
                try:
                    value = json.loads(self.rfile.read(size))
                except (ValueError, UnicodeDecodeError) as exc:
                    raise ValueError("Dữ liệu JSON không hợp lệ.") from exc
                if not isinstance(value, dict):
                    raise ValueError("Dữ liệu JSON không hợp lệ.")
                return value

            def _same_origin(self) -> bool:
                origin = self.headers.get("Origin")
                if not origin:
                    return True  # Non-browser clients still need CSRF and a session.
                parsed = urlsplit(origin)
                host = self.headers.get("Host", "").lower()
                if host.startswith(("127.0.0.1:", "localhost:")):
                    return ((parsed.scheme == "http" and parsed.netloc.lower() == host)
                            or (parsed.scheme == "https" and (parsed.hostname or "").endswith(".ts.net")))
                return parsed.scheme == "https" and parsed.netloc.lower() == host

            def do_GET(self):
                identity = self._identity()
                if not identity:
                    self._json(HTTPStatus.FORBIDDEN, {"error": "Hãy mở Mira qua Tailscale Serve."})
                    return
                if self.path == "/":
                    data = Path(__file__).with_name("phone.html").read_bytes()
                    self._headers(HTTPStatus.OK, "text/html; charset=utf-8", data)
                    return
                session = self._session(identity)
                if not session:
                    self._json(HTTPStatus.UNAUTHORIZED, {"error": "Hãy ghép nối điện thoại với Mira."})
                    return
                if self.path == "/api/state":
                    with owner._lock:
                        config = owner.config.copy()
                    self._json(HTTPStatus.OK, {"csrf": session[1], "messages": owner.chat.list(),
                                               "reminders": owner.reminders.list(),
                                               "model": config["model"],
                                               "cloud_allowed": not is_cloud_model(config["model"])
                                               or config["cloud_consent"]})
                elif self.path.startswith("/api/reminders/") and self.path.endswith(".ics"):
                    reminder_id = self.path[len("/api/reminders/"):-4]
                    try:
                        if len(reminder_id) != 32 or any(c not in "0123456789abcdef" for c in reminder_id):
                            raise ValueError("Không tìm thấy lịch nhắc.")
                        ics = owner.reminders.calendar_file(reminder_id)
                    except ValueError as exc:
                        self._json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
                        return
                    self._headers(HTTPStatus.OK, "text/calendar; charset=utf-8", ics,
                                  {"Content-Disposition": 'attachment; filename="mira-reminder.ics"'})
                else:
                    self._json(HTTPStatus.NOT_FOUND, {"error": "Không tìm thấy trang."})

            def do_POST(self):
                identity = self._identity()
                if not identity or not self._same_origin():
                    self._json(HTTPStatus.FORBIDDEN, {"error": "Kết nối không được cho phép."})
                    return
                if self.path == "/api/pair":
                    try:
                        data = self._body()
                        code = data.get("code")
                        if not isinstance(code, str):
                            raise ValueError("Hãy nhập mã ghép nối.")
                    except ValueError as exc:
                        self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                        return
                    token, csrf = owner.pair(identity, code)
                    if not token:
                        self._json(HTTPStatus.TOO_MANY_REQUESTS,
                                   {"error": "Sai mã hoặc mã đã hết hạn. Kiểm tra trên máy tính."})
                        return
                    cookie = f"mira_phone={token}; HttpOnly; SameSite=Strict; Secure; Path=/; Max-Age=43200"
                    self._json(HTTPStatus.OK, {"csrf": csrf}, {"Set-Cookie": cookie})
                    return
                session = self._session(identity)
                if not session or self.headers.get("X-Mira-CSRF", "") != session[1]:
                    self._json(HTTPStatus.FORBIDDEN, {"error": "Phiên đã hết hạn. Hãy ghép nối lại."})
                    return
                try:
                    data = self._body()
                    if self.path == "/api/chat":
                        answer = owner.reply(data.get("text"))
                        self._json(HTTPStatus.OK, {"answer": answer})
                    elif self.path == "/api/reminders/draft":
                        draft = owner.draft(data.get("text"), data.get("offset_minutes"))
                        self._json(HTTPStatus.OK, draft)
                    elif self.path == "/api/reminders":
                        item = owner.reminders.create(data.get("title"), data.get("when"),
                                                      data.get("lead_minutes", 0),
                                                      data.get("offset_minutes"))
                        self._json(HTTPStatus.CREATED, {"reminder": item})
                    elif self.path == "/api/reminders/delete":
                        owner.reminders.delete(data.get("id"))
                        self._json(HTTPStatus.OK, {"ok": True})
                    elif self.path == "/api/logout":
                        with owner._lock:
                            owner._sessions.pop(session[0], None)
                        self._json(HTTPStatus.OK, {"ok": True},
                                   {"Set-Cookie": "mira_phone=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict; Secure"})
                    else:
                        self._json(HTTPStatus.NOT_FOUND, {"error": "Không tìm thấy lệnh."})
                except ValueError as exc:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                except RuntimeError as exc:
                    self._json(HTTPStatus.CONFLICT, {"error": str(exc)})
                except OSError:
                    self._json(HTTPStatus.INTERNAL_SERVER_ERROR,
                               {"error": "Không lưu được dữ liệu trên máy tính. Hãy thử lại."})

        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(target=self.httpd.serve_forever,
                                       kwargs={"poll_interval": 0.1}, daemon=True)

    @property
    def port(self) -> int:
        return self.httpd.server_port

    def start(self):
        self.thread.start()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        with self._lock:
            self._sessions.clear()
            self._pair_code = ""

    def update_config(self, **changes):
        with self._lock:
            self.config.update(changes)

    def new_pairing_code(self) -> str:
        with self._lock:
            self._pair_code = f"{secrets.randbelow(100_000_000):08d}"
            self._pair_expires = time.monotonic() + 300
            return self._pair_code

    def pair(self, identity: str, code: str) -> tuple[str | None, str | None]:
        now = time.monotonic()
        with self._lock:
            while self._attempts and now - self._attempts[0] > 60:
                self._attempts.popleft()
            if len(self._attempts) >= 5:
                return None, None
            self._attempts.append(now)
            if now > self._pair_expires or not self._pair_code or not secrets.compare_digest(code, self._pair_code):
                return None, None
            self._pair_code = ""  # A code can pair exactly one phone.
            token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            self._sessions[token] = (identity, csrf, now + 43200)
            return token, csrf

    def _snapshot(self) -> dict:
        with self._lock:
            config = self.config.copy()
        if is_cloud_model(config["model"]) and not config["cloud_consent"]:
            raise RuntimeError("Hãy cho phép Ollama Cloud trong Mira trên máy tính trước khi gửi.")
        return config

    def reply(self, text: str) -> str:
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 2000:
            raise ValueError("Tin nhắn phải dài từ 1 đến 2000 ký tự.")
        if not self._request_lock.acquire(blocking=False):
            raise RuntimeError("Mira đang trả lời yêu cầu trên điện thoại. Hãy chờ một chút.")
        try:
            config = self._snapshot()
            request = text.strip()
            memories = ("Trên điện thoại, chat không tạo lịch và không điều khiển máy. "
                        "Nếu được nhờ đặt lịch trong chat, hướng dẫn người dùng mở tab Lịch nhắc, "
                        "kiểm tra biểu mẫu và bấm Lưu; không nhận đã đặt lịch.\n"
                        "Bộ sở thích:\n" + self.preferences.prompt_for(request) +
                        "\nGhi nhớ được chọn:\n" + (self.memories.prompt_for(request) or "(chưa có)"))
            answer = self.agent.respond(request, self.chat.list(), config["model"],
                                        config["name"], memories, None, lambda *_: False,
                                        fast=config["fast"], persona=config["persona"],
                                        persona_note=config["persona_note"])
            self.chat.append_exchange(request, answer)
            return answer
        finally:
            self._request_lock.release()

    def draft(self, text: str, offset_minutes: int) -> dict:
        if not self._request_lock.acquire(blocking=False):
            raise RuntimeError("Mira đang xử lý một yêu cầu khác trên điện thoại.")
        try:
            config = self._snapshot()
            return draft_reminder(self.agent.client, config["model"], text, offset_minutes)
        finally:
            self._request_lock.release()
