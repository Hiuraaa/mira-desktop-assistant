"""Opt-in Telegram companion: private pairing, chat and confirmed reminders."""

from __future__ import annotations

import json
import re
import secrets
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .agent import is_cloud_model
from .mobile_server import MobileConversation
from .reminders import draft_reminder, validate_reminder
from .storage import load_json, save_json


class TelegramError(RuntimeError):
    pass


class TelegramAPI:
    def __init__(self, token: str):
        if not re.fullmatch(r"\d{5,15}:[A-Za-z0-9_-]{20,}", token):
            raise ValueError("Token bot không đúng dạng. Hãy sao chép từ @BotFather.")
        self._token = token

    def call(self, method: str, payload: dict) -> object:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"https://api.telegram.org/bot{self._token}/{method}", data=data,
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=18) as response:
                result = json.load(response)
        except urllib.error.HTTPError as exc:
            # Never propagate the URL: it includes the private bot token.
            if exc.code == 401:
                raise TelegramError("Token bot không hợp lệ; kiểm tra lại trong @BotFather.") from None
            if exc.code == 409:
                raise TelegramError("Bot đang chạy ở nơi khác hoặc đã bật webhook. Hãy tắt bản cũ.") from None
            raise TelegramError(f"Telegram trả về lỗi {exc.code}. Hãy thử lại.") from None
        except (OSError, ValueError):
            raise TelegramError("Không kết nối được Telegram. Hãy kiểm tra mạng trên máy tính.") from None
        if not result.get("ok"):
            raise TelegramError("Telegram từ chối yêu cầu. Hãy kiểm tra bot và thử lại.")
        return result.get("result")


class TelegramBot:
    """Telegram long polling runs on a worker; all actions stay outside Tk."""

    def __init__(self, path: Path, token: str, agent, reminders, memories, preferences,
                 *, model: str, name: str, cloud_consent: bool, fast: bool,
                 persona: str, persona_note: str, api=None):
        self.api = api or TelegramAPI(token)
        self.agent, self.reminders = agent, reminders
        self.memories, self.preferences = memories, preferences
        self.chat = MobileConversation(path / "telegram_conversation.json")
        self.binding_path = path / "telegram_binding.json"
        binding = load_json(self.binding_path, {})
        if not isinstance(binding, dict):
            raise ValueError("Thông tin ghép nối Telegram không đúng định dạng.")
        self.binding = binding
        self.config = {"model": model, "name": name, "cloud_consent": cloud_consent,
                       "fast": fast, "persona": persona, "persona_note": persona_note}
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._attempts: deque[float] = deque()
        self._code = ""
        self._code_expires = 0.0
        self._pending: dict[str, tuple[dict, float]] = {}
        self._state = "Đang khởi động Telegram…"
        self._bot_id = None

    def start(self):
        self._thread.start()

    def running(self) -> bool:
        return self._thread.is_alive() and not self._stop.is_set()

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=1)

    def status(self) -> str:
        with self._lock:
            suffix = " • đã ghép nối điện thoại" if self.binding.get("chat_id") else " • chờ ghép nối"
            return self._state + suffix

    def update_config(self, **changes):
        with self._lock:
            self.config.update(changes)

    def new_pairing_code(self) -> str:
        with self._lock:
            self._code = f"{secrets.randbelow(100_000_000):08d}"
            self._code_expires = time.monotonic() + 300
            return self._code

    def unpair(self):
        with self._lock:
            self.chat.clear()
            save_json(self.binding_path, {})
            self.binding = {}
            self._pending.clear()
            self._code = ""

    def _send(self, chat_id: int, text: str, **extra):
        # Telegram permits at most 4096 characters per sendMessage.
        while text:
            segment, text = text[:3500], text[3500:]
            self.api.call("sendMessage", {"chat_id": chat_id, "text": segment,
                                          **(extra if not text else {})})

    def _snapshot(self) -> dict:
        with self._lock:
            config = self.config.copy()
        if is_cloud_model(config["model"]) and not config["cloud_consent"]:
            raise TelegramError("Hãy cho phép Ollama Cloud trên Mira ở máy tính trước.")
        return config

    def _authorized(self, msg: dict) -> bool:
        chat, user = msg.get("chat", {}), msg.get("from", {})
        with self._lock:
            return (chat.get("type") == "private" and type(chat.get("id")) is int
                    and chat.get("id") == self.binding.get("chat_id")
                    and user.get("id") == self.binding.get("user_id")
                    and self.binding.get("bot_id") == self._bot_id)

    def _pair(self, msg: dict, text: str) -> None:
        chat, user = msg.get("chat", {}), msg.get("from", {})
        if (chat.get("type") != "private" or type(chat.get("id")) is not int
                or type(user.get("id")) is not int):
            return
        match = re.fullmatch(r"/start\s+(\d{8})", text.strip())
        if not match:
            self._send(chat["id"], "Mở Mira trên máy tính → Điện thoại & lịch nhắc → Telegram, "
                     "rồi gửi /start và mã 8 chữ số hiển thị tại đó.")
            return
        now = time.monotonic()
        with self._lock:
            while self._attempts and now - self._attempts[0] > 60:
                self._attempts.popleft()
            if len(self._attempts) >= 5:
                matched = False
            else:
                self._attempts.append(now)
                matched = bool(self._code and now < self._code_expires
                               and secrets.compare_digest(match[1], self._code))
            if matched:
                self.chat.clear()
                binding = {"chat_id": chat["id"], "user_id": user["id"],
                           "bot_id": self._bot_id,
                           "offset_minutes": int(datetime.now().astimezone().utcoffset().total_seconds() / 60)}
                save_json(self.binding_path, binding)
                self.binding = binding
                self._code = ""
        self._send(chat["id"],
                   "Đã ghép nối Mira! Gõ /help để xem cách chat và đặt nhắc lịch."
                   if matched else "Mã không đúng, hết hạn hoặc đã thử quá nhiều lần. Tạo mã mới trên Mira.")

    def _offset(self) -> int:
        with self._lock:
            return self.binding.get("offset_minutes", 0)

    def _draft(self, text: str) -> dict:
        offset = self._offset()
        exact = re.fullmatch(r"(\d{4}-\d{2}-\d{2})\s+(\d{1,2}):(\d{2})\s*\|\s*(.{1,120})", text)
        if exact:
            when = f"{exact[1]}T{int(exact[2]):02d}:{exact[3]}"
            title, start, lead = validate_reminder(exact[4], when, 0, offset)
            return {"title": title, "when": start.strftime("%Y-%m-%dT%H:%M"),
                    "lead_minutes": lead}
        config = self._snapshot()
        return draft_reminder(self.agent.client, config["model"], text, offset)

    def _new_reminder(self, chat_id: int, text: str):
        draft = self._draft(text)
        nonce = uuid.uuid4().hex
        with self._lock:
            self._pending = {nonce: (draft, time.monotonic() + 600)}
        self._send(chat_id, f"📅 Mira hiểu là: {draft['title']}\n"
                   f"{draft['when'].replace('T', ' ')} (UTC{self._offset() / 60:+g})\n"
                   "Kiểm tra ngày giờ rồi bấm Lưu. Muốn sửa, gửi /nhac một lần nữa.",
                   reply_markup={"inline_keyboard": [[
                       {"text": "✅ Lưu lịch", "callback_data": "save:" + nonce},
                       {"text": "Hủy", "callback_data": "cancel:" + nonce}]]})

    def _callback(self, query: dict):
        msg = {**query.get("message", {}), "from": query.get("from", {})}
        if not self._authorized(msg):
            self.api.call("answerCallbackQuery", {"callback_query_id": query["id"]})
            return
        self.api.call("answerCallbackQuery", {"callback_query_id": query["id"]})
        action, _, nonce = query.get("data", "").partition(":")
        with self._lock:
            item = self._pending.pop(nonce, None)
        chat_id = msg["chat"]["id"]
        if item is None or time.monotonic() > item[1]:
            self._send(chat_id, "Bản nháp đã hết hạn. Gửi /nhac để tạo lại.")
            return
        if action == "cancel":
            self._send(chat_id, "Đã hủy bản nháp; chưa có lịch nào được lưu.")
            return
        if action != "save":
            return
        draft = item[0]
        created = self.reminders.create(draft["title"], draft["when"],
                                        draft["lead_minutes"], self._offset())
        self._send(chat_id, f"Đã lưu: {created['title']} — {draft['when'].replace('T', ' ')}. "
                   "Mira sẽ nhắn Telegram khi tới giờ, nếu máy tính đang bật và Mira còn chạy.")

    def _list_reminders(self, chat_id: int):
        offset = timezone(timedelta(minutes=self._offset()))
        items = [item for item in self.reminders.list()
                 if datetime.fromisoformat(item["when"]) > datetime.now(timezone.utc)]
        if not items:
            self._send(chat_id, "Chưa có lịch sắp tới.")
            return
        lines = [f"{item['id'][:8]} • {datetime.fromisoformat(item['when']).astimezone(offset):%d/%m %H:%M} "
                 f"• {item['title']}" for item in items[:10]]
        self._send(chat_id, "Lịch sắp tới:\n" + "\n".join(lines) +
                   "\nXóa bằng /xoa <8 ký tự đầu>.")

    def _handle_message(self, msg: dict):
        text = msg.get("text", "")
        if not isinstance(text, str) or not text.strip():
            return
        if not self._authorized(msg):
            if text.startswith("/start"):
                self._pair(msg, text)
            return
        chat_id = msg["chat"]["id"]
        if text.startswith(("/help", "/start")):
            sample = (datetime.now(timezone(timedelta(minutes=self._offset())))
                      + timedelta(days=1)).strftime("%Y-%m-%d")
            self._send(chat_id, "Nhắn tin để chat với Mira.\n"
                       f"/nhac {sample} 09:00 | Gọi mẹ — đặt lịch chính xác, không cần AI.\n"
                       "/nhac Nhắc tôi ngày mai 9 giờ gọi mẹ — Mira điền bản nháp bằng AI.\n"
                       "/lich — xem lịch; /xoa <mã> — xóa lịch.\n"
                       "/muigio +7 hoặc /muigio -5:30 — chỉnh múi giờ.\n"
                       "Mỗi lịch chỉ lưu khi bạn bấm ✅ Lưu lịch.")
        elif text.startswith("/muigio"):
            match = re.fullmatch(r"/muigio\s+([+-])(\d{1,2})(?::(00|15|30|45))?", text.strip())
            if not match:
                raise ValueError("Ví dụ: /muigio +7 hoặc /muigio -5:30")
            offset = (1 if match[1] == "+" else -1) * (int(match[2]) * 60 + int(match[3] or 0))
            timezone(timedelta(minutes=offset))
            if not -720 <= offset <= 840:
                raise ValueError("Múi giờ phải nằm trong khoảng UTC−12 đến UTC+14.")
            with self._lock:
                binding = {**self.binding, "offset_minutes": offset}
                save_json(self.binding_path, binding)
                self.binding = binding
            self._send(chat_id, f"Đã đổi múi giờ thành UTC{offset / 60:+g}.")
        elif text.startswith("/nhac"):
            request = text[len("/nhac"):].strip()
            if not request:
                raise ValueError("Thêm nội dung sau /nhac. Gõ /help để xem ví dụ.")
            self._new_reminder(chat_id, request)
        elif text.strip() == "/lich":
            self._list_reminders(chat_id)
        elif text.startswith("/xoa"):
            prefix = text[len("/xoa"):].strip().lower()
            if not re.fullmatch(r"[0-9a-f]{8}", prefix):
                raise ValueError("Nhập /xoa rồi tới 8 ký tự của lịch trong /lich.")
            matched = [item for item in self.reminders.list() if item["id"].startswith(prefix)]
            if len(matched) != 1:
                raise ValueError("Không tìm thấy một lịch duy nhất với mã này.")
            self.reminders.delete(matched[0]["id"])
            self._send(chat_id, "Đã xóa lịch trên Mira: " + matched[0]["title"])
        elif text.startswith("/"):
            self._send(chat_id, "Lệnh chưa được hỗ trợ. Gõ /help để xem cách dùng.")
        else:
            if not 1 <= len(text.strip()) <= 2000:
                raise ValueError("Tin nhắn phải dài từ 1 đến 2000 ký tự.")
            config = self._snapshot()
            self.api.call("sendChatAction", {"chat_id": chat_id, "action": "typing"})
            memories = ("Trên Telegram, chat không tự đặt lịch hay điều khiển máy. "
                        "Nếu được nhờ đặt lịch, hướng dẫn dùng /nhac và xác nhận bằng nút Lưu.\n"
                        "Bộ sở thích:\n" + self.preferences.prompt_for(text) +
                        "\nGhi nhớ liên quan:\n" + (self.memories.prompt_for(text) or "(chưa có)"))
            answer = self.agent.respond(text, self.chat.list(), config["model"],
                                        config["name"], memories, None, lambda *_: False,
                                        fast=config["fast"], persona=config["persona"],
                                        persona_note=config["persona_note"])
            self.chat.append_exchange(text, answer)
            self._send(chat_id, answer)

    def _handle(self, update: dict):
        try:
            if "message" in update:
                self._handle_message(update["message"])
            elif "callback_query" in update:
                self._callback(update["callback_query"])
        except (OSError, ValueError, RuntimeError) as exc:
            msg = update.get("message") or update.get("callback_query", {}).get("message", {})
            if self._authorized({**msg, "from": (update.get("callback_query", {}).get("from")
                                                  or msg.get("from", {}))}):
                # Never send raw network errors containing the private token.
                safe = str(exc) if isinstance(exc, (ValueError, TelegramError)) else "Không xử lý được yêu cầu. Hãy thử lại."
                try:
                    self._send(msg["chat"]["id"], safe)
                except (OSError, RuntimeError):
                    pass

    def _notify_due(self, now: datetime | None = None):
        with self._lock:
            chat_id = self.binding.get("chat_id") if self.binding.get("bot_id") == self._bot_id else None
        if chat_id is None:
            return
        for item in self.reminders.pending_telegram(now):
            if self._stop.is_set():
                return
            self._send(chat_id, "🔔 Mira nhắc bạn: " + item["title"])
            self.reminders.mark_telegram_notified(item["id"])

    def _run(self):
        try:
            me = self.api.call("getMe", {})
            self._bot_id = me["id"]
            info = self.api.call("getWebhookInfo", {})
            if info.get("url"):
                raise TelegramError("Bot đã dùng webhook ở nơi khác. Hãy tạo bot riêng qua @BotFather.")
            recent = self.api.call("getUpdates", {"offset": -1, "limit": 1, "timeout": 0,
                                                  "allowed_updates": ["message", "callback_query"]})
            offset = recent[-1]["update_id"] + 1 if recent else None
            with self._lock:
                self._state = "Telegram sẵn sàng"
            while not self._stop.is_set():
                payload = {"timeout": 8, "allowed_updates": ["message", "callback_query"]}
                if offset is not None:
                    payload["offset"] = offset
                try:
                    updates = self.api.call("getUpdates", payload)
                    for update in updates:
                        if self._stop.is_set():
                            break
                        self._handle(update)
                        offset = update["update_id"] + 1
                    self._notify_due()
                except (OSError, ValueError, RuntimeError):
                    if self._stop.wait(5):
                        break
                    with self._lock:
                        self._state = "Telegram tạm mất kết nối; đang thử lại"
                else:
                    with self._lock:
                        self._state = "Telegram sẵn sàng"
        except (OSError, ValueError, RuntimeError) as exc:
            with self._lock:
                self._state = str(exc) if isinstance(exc, (ValueError, TelegramError)) else "Không bật được Telegram."
