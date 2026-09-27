"""Opt-in transfer of chosen memories between Mira desktop and the user's Worker."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request


def validate_cloud_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url.strip())
    if (parsed.scheme != "https" or not parsed.hostname or
            not parsed.hostname.endswith(".workers.dev") or
            parsed.hostname == "workers.dev" or parsed.username or parsed.password or
            parsed.port is not None or parsed.query or parsed.fragment or
            parsed.path not in ("", "/")):
        raise ValueError("Nhập URL HTTPS *.workers.dev của Mira, không kèm đường dẫn hay tham số.")
    return f"https://{parsed.hostname}/api/memories"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise ValueError("Máy chủ Mira chuyển hướng bất ngờ; đã dừng gửi khóa truy cập.")


class CloudMemoryClient:
    def __init__(self, url: str, key: str):
        self.url = validate_cloud_url(url)
        if not isinstance(key, str) or len(key) < 24:
            raise ValueError("Khóa Mira cloud phải có ít nhất 24 ký tự.")
        self.key = key
        self._opener = urllib.request.build_opener(_NoRedirect())

    def _request(self, method: str, data: dict | None = None) -> dict:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8") if data is not None else None
        request = urllib.request.Request(
            self.url, data=payload, method=method,
            headers={"X-Mira-Key": self.key, "Content-Type": "application/json"})
        try:
            with self._opener.open(request, timeout=15) as response:
                raw = response.read(120001)
            if len(raw) > 120000:
                raise ValueError("Bộ nhớ trên cloud quá lớn.")
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError("Phản hồi bộ nhớ cloud không hợp lệ.")
            return result
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise ValueError("Sai khóa truy cập Mira cloud.") from exc
            if exc.code == 409:
                raise ValueError("Bộ nhớ cloud vừa thay đổi. Tải lại và thử gửi lần nữa.") from exc
            raise ValueError(f"Không đồng bộ được bộ nhớ (HTTP {exc.code}). Kiểm tra migration và URL cloud.") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ValueError("Không kết nối được Mira cloud. Kiểm tra mạng và URL.") from exc

    def get(self) -> dict:
        result = self._request("GET")
        if not isinstance(result.get("items"), list) or not isinstance(result.get("version"), int):
            raise ValueError("Phản hồi bộ nhớ cloud không hợp lệ.")
        return result

    def put(self, items: list[dict], version: int) -> dict:
        return self._request("PUT", {"items": items, "version": version})
