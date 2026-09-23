"""User-approved, one-time reminders and portable calendar invitations."""

from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .storage import load_json, save_json


def _phone_timezone(offset_minutes: int) -> timezone:
    if type(offset_minutes) is not int or not -720 <= offset_minutes <= 840:
        raise ValueError("Múi giờ của điện thoại không hợp lệ.")
    return timezone(timedelta(minutes=offset_minutes))


def validate_reminder(title: str, when: str, lead_minutes: int = 0,
                      offset_minutes: int | None = None) -> tuple[str, datetime, int]:
    if not isinstance(title, str) or not isinstance(when, str):
        raise ValueError("Hãy nhập tên và thời gian cho lịch nhắc.")
    title = " ".join(title.split())
    if not title or len(title) > 120 or any(ord(c) < 32 for c in title):
        raise ValueError("Tên lịch nhắc phải dài từ 1 đến 120 ký tự.")
    if type(lead_minutes) is not int or lead_minutes not in (0, 5, 15, 60, 1440):
        raise ValueError("Chọn thời điểm nhắc hợp lệ.")
    try:
        start = datetime.fromisoformat(when)
    except ValueError as exc:
        raise ValueError("Ngày giờ không hợp lệ. Hãy dùng dạng YYYY-MM-DD HH:MM.") from exc
    if start.tzinfo is None:
        start = start.replace(tzinfo=_phone_timezone(offset_minutes) if offset_minutes is not None
                                      else start.astimezone().tzinfo)
    now = datetime.now(timezone.utc)
    if not now < start.astimezone(timezone.utc) < now + timedelta(days=366):
        raise ValueError("Chọn thời điểm trong tương lai, tối đa một năm tới.")
    return title, start, lead_minutes


class ReminderStore:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        data = load_json(path, [])
        if not isinstance(data, list) or any(not isinstance(item, dict)
                                             or not isinstance(item.get("id"), str)
                                             or not isinstance(item.get("when"), str)
                                             or not isinstance(item.get("title"), str)
                                             for item in data):
            raise ValueError("Lịch nhắc đã lưu không đúng định dạng.")
        self._items = data

    def list(self) -> list[dict]:
        with self.lock:
            return sorted((item.copy() for item in self._items),
                          key=lambda item: datetime.fromisoformat(item["when"]).timestamp())

    def create(self, title: str, when: str, lead_minutes: int = 0,
               offset_minutes: int | None = None) -> dict:
        title, start, lead_minutes = validate_reminder(title, when, lead_minutes, offset_minutes)
        with self.lock:
            if sum(item.get("notified_at") is None for item in self._items) >= 100:
                raise ValueError("Đã có 100 lịch chưa hoàn thành. Hãy xóa bớt trước khi thêm.")
            item = {"id": uuid.uuid4().hex, "title": title, "when": start.isoformat(timespec="minutes"),
                    "lead_minutes": lead_minutes, "notified_at": None}
            updated = self._items + [item]
            save_json(self.path, updated)
            self._items = updated
            return item.copy()

    def delete(self, reminder_id: str) -> None:
        with self.lock:
            updated = [item for item in self._items if item["id"] != reminder_id]
            if len(updated) == len(self._items):
                raise ValueError("Không tìm thấy lịch nhắc.")
            save_json(self.path, updated)
            self._items = updated

    def due(self, now: datetime | None = None) -> list[dict]:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ValueError("Thời gian kiểm tra phải có múi giờ.")
        now = now.astimezone(timezone.utc)
        ready = []
        with self.lock:
            updated = []
            for item in self._items:
                start = datetime.fromisoformat(item["when"]).astimezone(timezone.utc)
                due_at = start - timedelta(minutes=item["lead_minutes"])
                if item.get("notified_at") is None and now >= due_at:
                    changed = {**item, "notified_at": now.isoformat(timespec="seconds")}
                    if now <= start + timedelta(hours=24):
                        ready.append(changed.copy())
                    updated.append(changed)
                else:
                    updated.append(item)
            if updated != self._items:
                save_json(self.path, updated)
                self._items = updated
        return ready

    def calendar_file(self, reminder_id: str) -> bytes:
        with self.lock:
            item = next((item.copy() for item in self._items if item["id"] == reminder_id), None)
        if item is None:
            raise ValueError("Không tìm thấy lịch nhắc.")
        start = datetime.fromisoformat(item["when"]).astimezone(timezone.utc)
        stamp = datetime.now(timezone.utc)
        fmt = lambda value: value.strftime("%Y%m%dT%H%M%SZ")
        summary = _ics_escape(item["title"])
        lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Mira//Personal Reminders//VI",
                 "CALSCALE:GREGORIAN", "BEGIN:VEVENT", f"UID:{item['id']}@mira.local",
                 f"DTSTAMP:{fmt(stamp)}", f"DTSTART:{fmt(start)}",
                 f"DTEND:{fmt(start + timedelta(minutes=30))}", f"SUMMARY:{summary}",
                 "BEGIN:VALARM", f"TRIGGER:-PT{item['lead_minutes']}M",
                 "ACTION:DISPLAY", f"DESCRIPTION:{summary}", "END:VALARM", "END:VEVENT", "END:VCALENDAR"]
        return ("\r\n".join(_fold_ics(line) for line in lines) + "\r\n").encode("utf-8")


def _ics_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold_ics(line: str) -> str:
    pieces, current = [], ""
    for char in line:
        if len((current + char).encode("utf-8")) > 74:
            pieces.append(current)
            current = " " + char
        else:
            current += char
    pieces.append(current)
    return "\r\n".join(pieces)


def draft_reminder(client, model: str, request: str, offset_minutes: int = 0) -> dict:
    """An AI proposes editable fields; this function never writes a reminder."""
    if not isinstance(request, str) or not 3 <= len(request.strip()) <= 600:
        raise ValueError("Hãy mô tả lịch nhắc trong 3–600 ký tự.")
    tz = _phone_timezone(offset_minutes)
    now = datetime.now(tz)
    prompt = ("Chuyển yêu cầu thành MỘT lịch nhắc một lần. Chỉ xuất JSON với "
              "title (chuỗi ngắn), when (YYYY-MM-DDTHH:MM), lead_minutes (0, 5, 15, 60 hoặc 1440). "
              "Nếu không đủ ngày/giờ thì chọn ngày gần nhất hợp lý. Không tự lưu. "
              f"Thời gian hiện tại: {now.isoformat(timespec='minutes')}.")
    response = client.chat(model, [{"role": "system", "content": prompt},
                                   {"role": "user", "content": request.strip()}], [], fast=True)
    raw = str(response.get("message", {}).get("content", "")).strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE)
    try:
        value = json.loads(raw)
        title, start, lead = validate_reminder(value["title"], value["when"],
                                               value.get("lead_minutes", 0), offset_minutes)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Mira chưa hiểu rõ ngày giờ. Hãy nhập trực tiếp vào biểu mẫu.") from exc
    return {"title": title, "when": start.astimezone(tz).strftime("%Y-%m-%dT%H:%M"),
            "lead_minutes": lead}
