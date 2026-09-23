"""Small, local JSON stores for user preferences, memories and conversation."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
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
        self.items.append(item)
        save_json(self.path, self.items)
        return item

    def forget(self, item_id: str) -> None:
        kept = [item for item in self.items if item.get("id") != item_id]
        if len(kept) == len(self.items):
            raise ValueError("Không tìm thấy điều cần quên.")
        save_json(self.path, kept)
        self.items = kept

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
