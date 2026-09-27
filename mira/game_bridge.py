"""Owner-started localhost connector: a game supplies state and legal actions."""

from __future__ import annotations

import hmac
import json
import re
import secrets
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


class GameBridgeError(ValueError):
    pass


EVENT_TTL_SECONDS = 180


def _short(value, limit: int, label: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= limit:
        raise GameBridgeError(f"{label} cần từ 1 đến {limit} ký tự.")
    return value.strip()


def _actions(raw) -> dict:
    if not isinstance(raw, list) or not 1 <= len(raw) <= 8:
        raise GameBridgeError("Game cần đăng ký từ 1 đến 8 hành động.")
    actions = {}
    for item in raw:
        if not isinstance(item, dict):
            raise GameBridgeError("Hành động game không hợp lệ.")
        name = item.get("name")
        if (not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", name)
                or name in actions):
            raise GameBridgeError("Tên hành động game không hợp lệ hoặc bị trùng.")
        description = _short(item.get("description"), 120, "Mô tả hành động")
        choices = item.get("options")
        if (not isinstance(choices, list) or not 1 <= len(choices) <= 12
                or any(not isinstance(x, str) or not 1 <= len(x) <= 40 for x in choices)
                or len(set(choices)) != len(choices)):
            raise GameBridgeError("Mỗi hành động cần 1 đến 12 lựa chọn ngắn và không trùng nhau.")
        actions[name] = {"name": name, "description": description, "options": choices}
    return actions


class GameBridge:
    def __init__(self, on_event, *, port: int = 0):
        self.on_event = on_event
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.game = ""
        self.actions = {}
        self.event = None
        self.last_event_at = 0.0
        self.closed = False
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass  # Never log the session key or game state.

            def _reply(self, code, value):
                body = json.dumps(value, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _handle(self):
                if self.client_address[0] not in ("127.0.0.1", "::1"):
                    return self._reply(403, {"error": "Chỉ nhận kết nối trên máy này."})
                if not hmac.compare_digest(self.headers.get("X-Mira-Game-Key", ""), bridge.token):
                    return self._reply(401, {"error": "Sai mã kết nối game."})
                try:
                    path = urlsplit(self.path)
                    if self.command == "POST":
                        if self.headers.get("Content-Type", "").split(";")[0].lower() != "application/json":
                            raise GameBridgeError("Chỉ nhận JSON.")
                        length = int(self.headers.get("Content-Length", "0"))
                        if not 0 < length <= 8192:
                            raise GameBridgeError("Gói dữ liệu game quá dài hoặc trống.")
                        data = json.loads(self.rfile.read(length))
                        if not isinstance(data, dict):
                            raise GameBridgeError("Dữ liệu game phải là một đối tượng JSON.")
                        if path.path == "/register":
                            return self._reply(200, bridge.register(data))
                        if path.path == "/event":
                            return self._reply(200, bridge.receive(data))
                    if self.command == "GET" and path.path == "/action":
                        event_id = parse_qs(path.query).get("id", [""])[0]
                        return self._reply(200, bridge.poll_action(event_id))
                    return self._reply(404, {"error": "Không có chức năng này."})
                except (ValueError, TypeError, json.JSONDecodeError) as exc:
                    return self._reply(400, {"error": str(exc)[:200]})

            do_POST = _handle
            do_GET = _handle

        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        with self.lock:
            self.closed = True
            self.event = None
            self.actions = {}
            self.game = ""
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def register(self, data: dict) -> dict:
        name = _short(data.get("game"), 64, "Tên game")
        actions = _actions(data.get("actions"))
        with self.lock:
            if self.closed:
                raise GameBridgeError("Kết nối đã tắt.")
            self.game, self.actions, self.event = name, actions, None
            self.last_event_at = 0.0
        return {"ok": True, "game": name, "actions": list(actions)}

    def receive(self, data: dict) -> dict:
        game = _short(data.get("game"), 64, "Tên game")
        context = _short(data.get("context"), 700, "Sự kiện game")
        state = _short(data.get("state"), 1200, "Trạng thái game")
        allowed = data.get("available")
        if not isinstance(allowed, dict) or len(allowed) > 8:
            raise GameBridgeError("Danh sách nước đi hợp lệ không đúng định dạng.")
        with self.lock:
            if self.closed or game != self.game:
                raise GameBridgeError("Game chưa được đăng ký trong phiên này.")
            now = time.monotonic()
            if now - self.last_event_at < 0.7:
                raise GameBridgeError("Game gửi sự kiện quá nhanh; hãy chờ một chút.")
            choices = {}
            for name, subset in allowed.items():
                registered = self.actions.get(name)
                if not registered or not isinstance(subset, list) or not subset or any(
                    not isinstance(x, str) or x not in registered["options"] for x in subset
                ) or len(set(subset)) != len(subset):
                    raise GameBridgeError("Game chỉ được dùng những nước đi đã đăng ký.")
                choices[name] = subset[:]
            self.last_event_at = now
            event = {"id": uuid.uuid4().hex, "game": game, "context": context,
                     "state": state, "available": choices, "actions": {
                         name: self.actions[name].copy() for name in choices},
                     "created_at": now, "status": "waiting", "chosen": None}
            self.event = event
            visible = self.snapshot()
        self.on_event(visible)
        return {"id": visible["id"], "status": "waiting"}

    def snapshot(self) -> dict | None:
        with self.lock:
            if not self.event or self.closed:
                return None
            item = self.event
            return {key: item[key] for key in ("id", "game", "context", "state", "available", "actions")}

    def tool_for(self, event_id: str) -> dict | None:
        with self.lock:
            event = self.event
            if (self.closed or not event or event["id"] != event_id
                    or event["status"] != "waiting" or time.monotonic() - event["created_at"] > EVENT_TTL_SECONDS
                    or not event["available"]):
                return None
            description = "; ".join(
                f"{name}: {event['actions'][name]['description']} (chọn: {', '.join(choices)})"
                for name, choices in event["available"].items())
            return {"type": "function", "function": {
                "name": "choose_game_action",
                "description": "Choose ONE registered game action for this turn. User approval is required before the game receives it. " + description,
                "parameters": {"type": "object", "properties": {
                    "name": {"type": "string", "enum": list(event["available"])},
                    "choice": {"type": "string"}}, "required": ["name", "choice"]}}}

    def choose(self, event_id: str, name: str, choice: str, approve) -> str:
        with self.lock:
            item = self.event
            if (self.closed or not item or item["id"] != event_id or
                    item["status"] != "waiting" or time.monotonic() - item["created_at"] > EVENT_TTL_SECONDS):
                return "Lượt game đã cũ hoặc kết nối đã tắt; chưa làm gì cả."
            if not isinstance(name, str) or not isinstance(choice, str) or choice not in item["available"].get(name, []):
                return "Nước đi không nằm trong danh sách game cho phép; chưa làm gì cả."
            description = f"Game: {item['game']}\nHành động: {name}\nLựa chọn: {choice}"
        accepted = approve(description)
        with self.lock:
            item = self.event
            if (self.closed or not item or item["id"] != event_id or
                    item["status"] != "waiting" or time.monotonic() - item["created_at"] > EVENT_TTL_SECONDS):
                return "Lượt game đã thay đổi khi chờ duyệt; chưa làm gì cả."
            if not accepted:
                item["status"] = "denied"
                return "Người dùng đã từ chối hành động game. Không được thử hành động khác trong lượt này."
            item["chosen"] = {"name": name, "choice": choice}
            item["status"] = "chosen"
            return f"Đã được duyệt nước đi {name}: {choice}. Chờ game áp dụng và gửi trạng thái mới."

    def poll_action(self, event_id: str) -> dict:
        with self.lock:
            item = self.event
            if self.closed or not item or item["id"] != event_id:
                return {"status": "expired"}
            if time.monotonic() - item["created_at"] > EVENT_TTL_SECONDS:
                item["status"] = "expired"
            if item["status"] == "chosen":
                item["status"] = "delivered"
                return {"status": "chosen", "action": item["chosen"]}
            return {"status": item["status"]}
