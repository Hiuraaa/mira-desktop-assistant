"""Small, explicit input lessons for a user-selected Windows window."""

from __future__ import annotations

import threading
import uuid
from pathlib import Path

from .storage import load_json, save_json


GAME_KEYS = frozenset("wasdqe rfcv1234567890".replace(" ", "")) | {
    "up", "down", "left", "right", "space", "enter", "esc", "shift", "ctrl", "tab"
}


def validate_steps(steps):
    if not isinstance(steps, list) or not 1 <= len(steps) <= 10:
        raise ValueError("Bài học cần từ 1 đến 10 bước.")
    result = []
    total = 0.0
    for step in steps:
        if not isinstance(step, dict) or step.get("kind") not in {"press", "hold"}:
            raise ValueError("Chỉ hỗ trợ bấm hoặc giữ phím trong bài học.")
        if set(step) != {"kind", "key", "duration"}:
            raise ValueError("Mỗi bước cần đúng loại, phím và thời gian.")
        key = step["key"]
        duration = step["duration"]
        if not isinstance(key, str) or key.casefold() not in GAME_KEYS:
            raise ValueError("Phím game không hợp lệ (W/A/S/D, Space, mũi tên…).")
        if isinstance(duration, bool) or not isinstance(duration, (int, float)):
            raise ValueError("Thời gian giữ phím không hợp lệ.")
        if step["kind"] == "hold" and not 0.05 <= duration <= 2.0:
            raise ValueError("Mỗi lần giữ phím từ 0,05 đến 2 giây.")
        if step["kind"] == "press" and duration != 0:
            raise ValueError("Bước bấm phím cần thời gian bằng 0.")
        total += duration + 0.12
        result.append({"kind": step["kind"], "key": key.casefold(), "duration": round(duration, 2)})
    if total > 9:
        raise ValueError("Bài học quá dài. Hãy chia thành nhiều bài nhỏ.")
    return result


class LessonStore:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        self.execution_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.items = load_json(path, [])
        if not isinstance(self.items, list) or len(self.items) > 30:
            raise ValueError("Danh sách bài học không hợp lệ.")
        for item in self.items:
            if (not isinstance(item, dict) or not isinstance(item.get("id"), str)
                    or not isinstance(item.get("name"), str) or not item["name"].strip()):
                raise ValueError("Bài học đã lưu không hợp lệ.")
            validate_steps(item.get("steps"))

    def list(self):
        with self.lock:
            return [{**item, "steps": [dict(step) for step in item["steps"]]} for item in self.items]

    def add(self, name: str, steps: list):
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 48:
            raise ValueError("Tên bài học từ 1 đến 48 ký tự.")
        clean = validate_steps(steps)
        with self.lock:
            if len(self.items) >= 30:
                raise ValueError("Tối đa 30 bài học.")
            item = {"id": uuid.uuid4().hex, "name": name.strip(), "steps": clean}
            updated = self.items + [item]
            save_json(self.path, updated)
            self.items = updated
            return dict(item)

    def remove(self, lesson_id: str):
        with self.lock:
            updated = [item for item in self.items if item["id"] != lesson_id]
            if len(updated) == len(self.items):
                raise ValueError("Không tìm thấy bài học.")
            save_json(self.path, updated)
            self.items = updated

    def run(self, lesson_id: str, desktop, approve, stopped: threading.Event | None = None):
        if not self.execution_lock.acquire(blocking=False):
            raise ValueError("Một bài học khác đang chạy.")
        try:
            return self._run(lesson_id, desktop, approve, stopped or self.stop_event)
        finally:
            self.execution_lock.release()

    def _run(self, lesson_id, desktop, approve, stopped):
        with self.lock:
            item = next((dict(i) for i in self.items if i["id"] == lesson_id), None)
        if not item:
            raise ValueError("Không tìm thấy bài học.")
        steps = validate_steps(item["steps"])
        title = desktop._target_title()  # The chosen window must still exist.
        description = "Bài học: " + item["name"] + "\nCửa sổ: " + title + "\n" + "\n".join(
            f"{n}. {'Giữ' if step['kind'] == 'hold' else 'Bấm'} {step['key']}"
            + (f" trong {step['duration']} giây" if step["kind"] == "hold" else "")
            for n, step in enumerate(steps, 1))
        if not approve(description):
            return "Người dùng đã từ chối hành động. Mira chưa gửi phím nào."
        if stopped.is_set():
            return "Đã dừng trước khi gửi phím."
        for step in steps:
            if stopped.is_set():
                return "Đã dừng bài học."
            if step["kind"] == "hold":
                desktop.execute("hold_key", {"key": step["key"], "duration": step["duration"]},
                                stopped=stopped)
            else:
                desktop.execute("press_keys", {"keys": step["key"]})
            if stopped.wait(0.12):
                return "Đã dừng bài học."
        return "Đã thực hiện bài học; Mira chưa tự nhìn thấy kết quả trong game."
