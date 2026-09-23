"""Small, local JSON stores for user preferences, memories and conversation."""

from __future__ import annotations

import json
import os
import re
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

    def edit(self, item_id: str, text: str) -> None:
        text = text.strip()
        if not text or len(text) > 500:
            raise ValueError("Điều cần nhớ phải dài từ 1 đến 500 ký tự.")
        if not any(item.get("id") == item_id for item in self.items):
            raise ValueError("Không tìm thấy điều cần sửa.")
        updated = [{**item, "text": text} if item.get("id") == item_id else item for item in self.items]
        save_json(self.path, updated)
        self.items = updated

    # Keep the v2 API used by existing installations and their checks.
    update = edit

    def prompt(self) -> str:
        return "\n".join(f"- {item['text']}" for item in self.items)

    def prompt_for(self, request: str) -> str:
        """Keep relevant and recent memories short for local inference."""
        words = set(re.findall(r"\w{3,}", request.casefold()))
        matching = [item for item in reversed(self.items)
                    if words & set(re.findall(r"\w{3,}", item["text"].casefold()))]
        selected = matching[:5]
        selected_ids = {item["id"] for item in selected}
        selected.extend(item for item in reversed(self.items) if item["id"] not in selected_ids)
        lines = []
        for item in selected:
            line = "- " + item["text"]
            if len("\n".join(lines)) + len(line) > 1200:
                break
            lines.append(line)
            if len(lines) == 8:
                break
        return "\n".join(lines)


class ChatStore:
    def __init__(self, path: Path):
        self.path = path
        data = load_json(path, [])
        if not isinstance(data, list):
            raise ValueError("Lịch sử trò chuyện không đúng định dạng.")
        self.messages = [m for m in data if isinstance(m, dict) and m.get("role") in {"user", "assistant"}
                         and isinstance(m.get("content"), str)]

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
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ConversationStore:
    """A small collection of local conversations; imports the original chat once."""

    def __init__(self, path: Path, legacy_path: Path | None = None):
        self.path = path
        if path.exists():
            data = load_json(path, [])
            if not isinstance(data, list):
                raise ValueError("Danh sách cuộc trò chuyện không đúng định dạng.")
            self.items = data
        else:
            self.items = []
            if legacy_path and legacy_path.exists():
                messages = ChatStore(legacy_path).messages
                if messages:
                    self.items = [self._item("Cuộc trò chuyện trước đây", messages)]
                    save_json(self.path, self.items)
        self._validate()

    @staticmethod
    def _item(title: str, messages: list[dict] | None = None) -> dict:
        stamp = _now()
        return {"id": uuid.uuid4().hex, "title": title, "created_at": stamp,
                "updated_at": stamp, "messages": messages or []}

    def _validate(self) -> None:
        for item in self.items:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not isinstance(item.get("messages"), list):
                raise ValueError("Một cuộc trò chuyện đã lưu không đúng định dạng.")
            if any(not isinstance(m, dict) or m.get("role") not in {"user", "assistant"}
                   or not isinstance(m.get("content"), str) for m in item["messages"]):
                raise ValueError("Tin nhắn đã lưu không đúng định dạng.")

    def get(self, chat_id: str) -> dict | None:
        for item in self.items:
            if item["id"] == chat_id:
                return item
        return None

    def list(self) -> list[dict]:
        return list(self.items)

    def messages(self, chat_id: str) -> list[dict]:
        item = self.get(chat_id)
        return list(item["messages"]) if item else []

    def create(self) -> str:
        return self.new()["id"]

    def new(self) -> dict:
        item = self._item("Cuộc trò chuyện mới")
        updated = [item] + self.items
        save_json(self.path, updated)
        self.items = updated
        return item

    def append(self, chat_id: str, role: str, content: str) -> None:
        if role not in {"user", "assistant"} or not isinstance(content, str):
            raise ValueError("Tin nhắn không hợp lệ.")
        item = self.get(chat_id)
        if item is None:
            raise ValueError("Không tìm thấy cuộc trò chuyện.")
        messages = item["messages"] + [{"role": role, "content": content}]
        title = item.get("title", "Cuộc trò chuyện mới")
        if role == "user" and not any(m["role"] == "user" for m in item["messages"]):
            title = " ".join(content.split())[:48] or title
        changed = {**item, "title": title, "updated_at": _now(), "messages": messages}
        updated = [changed] + [other for other in self.items if other["id"] != chat_id]
        save_json(self.path, updated)
        self.items = updated

    def rename(self, chat_id: str, title: str) -> None:
        title = " ".join(title.split())[:80]
        if not title:
            raise ValueError("Tên cuộc trò chuyện không được để trống.")
        if not any(item["id"] == chat_id for item in self.items):
            raise ValueError("Không tìm thấy cuộc trò chuyện.")
        updated = [{**item, "title": title} if item["id"] == chat_id else item for item in self.items]
        save_json(self.path, updated)
        self.items = updated

    def delete(self, chat_id: str) -> None:
        updated = [item for item in self.items if item["id"] != chat_id]
        if len(updated) == len(self.items):
            raise ValueError("Không tìm thấy cuộc trò chuyện.")
        save_json(self.path, updated)
        self.items = updated
