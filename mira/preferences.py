"""Small, editable on-device preference examples, selected per request."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

from .storage import save_json


SEED = Path(__file__).with_name("preferences_starter.json")


def _words(text: str) -> set[str]:
    return {word for word in re.findall(r"\w+", text.casefold()) if len(word) > 1}


class PreferenceStore:
    def __init__(self, path: Path, seed: Path = SEED):
        self.path = path
        self.seed = seed
        if path.exists():
            self.data = self._load(path)
        else:
            self.data = self._load(seed)
            save_json(path, self.data)

    @staticmethod
    def _load(path: Path) -> dict:
        if path.stat().st_size > 64 * 1024:
            raise ValueError("Bộ sở thích vượt quá 64 KiB.")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError("Không đọc được bộ sở thích; hãy kiểm tra file JSON.") from exc
        PreferenceStore._validate(data)
        return data

    def _commit(self, data: dict) -> None:
        self._validate(data)
        save_json(self.path, data)
        self.data = data

    @staticmethod
    def _validate(data: dict) -> None:
        if (not isinstance(data, dict) or data.get("version") != 1
                or not isinstance(data.get("rules"), list) or not isinstance(data.get("examples"), list)
                or len(data["rules"]) > 30 or len(data["examples"]) > 30):
            raise ValueError("Bộ sở thích không đúng định dạng hoặc quá nhiều mục.")
        ids = set()
        for group, fields in (("rules", ("text",)),
                              ("examples", ("tags", "request", "ideal_answer"))):
            for item in data[group]:
                if (not isinstance(item, dict) or not isinstance(item.get("id"), str)
                        or not item["id"] or item["id"] in ids):
                    raise ValueError("ID sở thích bị trùng hoặc không hợp lệ.")
                ids.add(item["id"])
                if any(not isinstance(item.get(key), str) or not item[key].strip()
                       or len(item[key]) > 500 for key in fields):
                    raise ValueError("Nội dung sở thích phải dài từ 1 đến 500 ký tự.")

    def add_rule(self, text: str) -> None:
        self._commit({**self.data, "rules": self.data["rules"] + [
            {"id": uuid.uuid4().hex, "text": text.strip()}]})

    def add_example(self, tags: str, request: str, ideal_answer: str) -> None:
        self._commit({**self.data, "examples": self.data["examples"] + [
            {"id": uuid.uuid4().hex, "tags": tags.strip(), "request": request.strip(),
             "ideal_answer": ideal_answer.strip()}]})

    def update(self, item_id: str, **fields: str) -> None:
        for group in ("rules", "examples"):
            if any(item["id"] == item_id for item in self.data[group]):
                allowed = {"text"} if group == "rules" else {"tags", "request", "ideal_answer"}
                if set(fields) != allowed:
                    raise ValueError("Thiếu thông tin để sửa sở thích.")
                items = [{**item, **{key: value.strip() for key, value in fields.items()}}
                         if item["id"] == item_id else item for item in self.data[group]]
                self._commit({**self.data, group: items})
                return
        raise ValueError("Không tìm thấy sở thích cần sửa.")

    def remove(self, item_id: str) -> None:
        for group in ("rules", "examples"):
            items = [item for item in self.data[group] if item["id"] != item_id]
            if len(items) != len(self.data[group]):
                self._commit({**self.data, group: items})
                return
        raise ValueError("Không tìm thấy sở thích cần xóa.")

    def replace_from_file(self, source: Path) -> None:
        self._commit(self._load(source))

    def reset(self) -> None:
        self._commit(self._load(self.seed))

    def prompt_for(self, request: str) -> str:
        lines = ["Quy tắc trả lời ưu tiên:"]
        for rule in self.data["rules"][-5:]:
            lines.append("- " + rule["text"])
        words = _words(request)
        matches = sorted(
            (item for item in self.data["examples"] if words & _words(item["tags"])),
            key=lambda item: len(words & _words(item["tags"])), reverse=True,
        )[:2]
        if matches:
            lines.append("Ví dụ phù hợp (tham khảo cách diễn đạt, không chép máy móc):")
            for item in matches:
                lines.append(f"- Hỏi: {item['request']}\n  Đáp: {item['ideal_answer']}")
        return "\n".join(lines)[:1800]
