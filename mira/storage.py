"""Small, local JSON stores for user preferences, memories and conversation."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path


def data_dir() -> Path:
    base = os.environ.get("MIRA_DATA_DIR")
    if base:
        return Path(base).expanduser().resolve()
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
    return Path(base).expanduser() / "Mira" if base else Path.home() / ".local" / "share" / "Mira"


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise ValueError(f"Không đọc được dữ liệu {path}. Hãy sao lưu file này trước khi sửa: {exc}") from exc


def save_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    fd, temp_name = tempfile.mkstemp(prefix=".mira-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


class MemoryStore:
    def __init__(self, path: Path):
        self.path = path
        data = load_json(path, [])
        if not isinstance(data, list):
            raise ValueError("Bộ nhớ Mira không đúng định dạng.")
        self.items = data

    def add(self, text: str) -> dict:
        text = text.strip()
        if not text or len(text) > 500:
            raise ValueError("Điều cần nhớ phải dài từ 1 đến 500 ký tự.")
        if len(self.items) >= 50:
            raise ValueError("Bộ nhớ đã đủ 50 mục. Hãy xóa một mục cũ.")
        item = {"id": uuid.uuid4().hex, "text": text}
        updated = self.items + [item]
        save_json(self.path, updated)
        self.items = updated
        return item

    def forget(self, item_id: str) -> None:
        kept = [item for item in self.items if item.get("id") != item_id]
        if len(kept) == len(self.items):
            raise ValueError("Không tìm thấy điều cần quên.")
        save_json(self.path, kept)
        self.items = kept

    def update(self, item_id: str, text: str) -> None:
        text = text.strip()
        if not text or len(text) > 500:
            raise ValueError("Điều cần nhớ phải dài từ 1 đến 500 ký tự.")
        updated = [dict(item, text=text) if item.get("id") == item_id else item for item in self.items]
        if updated == self.items:
            raise ValueError("Không tìm thấy điều cần sửa.")
        save_json(self.path, updated)
        self.items = updated

    def prompt(self) -> str:
        return "\n".join(f"- {item['text']}" for item in self.items)


class ChatStore:
    def __init__(self, path: Path):
        self.path = path
        data = load_json(path, [])
        if not isinstance(data, list):
            raise ValueError("Lịch sử trò chuyện không đúng định dạng.")
        self.messages = [m for m in data if m.get("role") in {"user", "assistant"} and isinstance(m.get("content"), str)]

    def append(self, role: str, content: str) -> None:
        if role not in {"user", "assistant"}:
            raise ValueError("Vai trò tin nhắn không hợp lệ.")
        updated = self.messages + [{"role": role, "content": content}]
        save_json(self.path, updated[-40:])
        self.messages = updated[-40:]

    def clear(self) -> None:
        save_json(self.path, [])
        self.messages = []


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConversationStore:
    """Named conversations; imports the v1 conversation on first launch."""

    def __init__(self, path: Path, legacy_path: Path | None = None):
        self.path = path
        if path.exists():
            data = load_json(path, [])
        else:
            legacy = load_json(legacy_path, []) if legacy_path else []
            data = [{
                "id": uuid.uuid4().hex,
                "title": "Cuộc trò chuyện trước",
                "updated_at": _now(),
                "messages": legacy[-60:],
            }] if isinstance(legacy, list) and legacy else []
            if data:
                save_json(path, data)
        if not isinstance(data, list):
            raise ValueError("Lịch sử trò chuyện không đúng định dạng.")
        self.chats = [item for item in data if isinstance(item, dict)
                      and isinstance(item.get("id"), str)
                      and isinstance(item.get("messages"), list)]

    def list(self) -> list[dict]:
        return sorted(self.chats, key=lambda item: item.get("updated_at", ""), reverse=True)

    def get(self, chat_id: str) -> dict | None:
        return next((item for item in self.chats if item["id"] == chat_id), None)

    def messages(self, chat_id: str) -> list[dict]:
        chat = self.get(chat_id)
        return list(chat["messages"]) if chat else []

    def create(self) -> str:
        item = {"id": uuid.uuid4().hex, "title": "Cuộc trò chuyện mới",
                "updated_at": _now(), "messages": []}
        updated = self.chats + [item]
        save_json(self.path, updated)
        self.chats = updated
        return item["id"]

    def append(self, chat_id: str, role: str, content: str) -> None:
        if role not in {"user", "assistant"}:
            raise ValueError("Vai trò tin nhắn không hợp lệ.")
        chat = self.get(chat_id)
        if chat is None:
            raise ValueError("Không tìm thấy cuộc trò chuyện.")
        updated = []
        for item in self.chats:
            if item["id"] != chat_id:
                updated.append(item)
                continue
            messages = (item["messages"] + [{"role": role, "content": content}])[-60:]
            title = item["title"]
            if role == "user" and not any(m.get("role") == "user" for m in item["messages"]):
                title = (content.strip().splitlines()[0][:38] or "Cuộc trò chuyện mới")
            updated.append(dict(item, messages=messages, title=title, updated_at=_now()))
        save_json(self.path, updated)
        self.chats = updated

    def rename(self, chat_id: str, title: str) -> None:
        title = title.strip()[:60]
        if not title or self.get(chat_id) is None:
            raise ValueError("Tên cuộc trò chuyện không hợp lệ.")
        updated = [dict(item, title=title) if item["id"] == chat_id else item for item in self.chats]
        save_json(self.path, updated)
        self.chats = updated

    def delete(self, chat_id: str) -> None:
        updated = [item for item in self.chats if item["id"] != chat_id]
        if len(updated) == len(self.chats):
            raise ValueError("Không tìm thấy cuộc trò chuyện.")
        save_json(self.path, updated)
        self.chats = updated
