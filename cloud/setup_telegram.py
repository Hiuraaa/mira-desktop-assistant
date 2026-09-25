"""Connect a new private Telegram bot to the owner's Cloudflare Worker."""

from __future__ import annotations

import getpass
import json
import secrets
import urllib.error
import urllib.request
from urllib.parse import urlparse

from setup import wrangler


def telegram(token: str, endpoint: str, payload: dict | None = None) -> dict:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{endpoint}",
        data=body, headers={"Content-Type": "application/json"} if body else {},
        method="POST" if body else "GET",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        data = json.load(response)
    if not data.get("ok"):
        raise RuntimeError("Telegram từ chối yêu cầu. Kiểm tra bot và token.")
    return data


def main() -> None:
    print("Tạo MỘT bot mới với @BotFather, không dùng chung token của bot Mira đang chạy trên laptop.")
    token = getpass.getpass("Dán token bot mới (không hiển thị trên màn hình): ").strip()
    if not token:
        raise RuntimeError("Chưa có token bot.")
    telegram(token, "getMe")
    print("Mở bot mới trên điện thoại, bấm Start hoặc nhắn /start, rồi quay lại đây.")
    input("Sau khi đã gửi tin, nhấn Enter…")
    updates = telegram(token, "getUpdates")["result"]
    ids = dict.fromkeys(str(message["message"]["from"]["id"]) for message in updates
                        if message.get("message", {}).get("chat", {}).get("type") == "private"
                        and message["message"].get("from", {}).get("id") == message["message"]["chat"]["id"])
    if not ids:
        raise RuntimeError("Bot chưa nhận tin nhắn riêng nào. Nhắn /start trên điện thoại rồi chạy lại.")
    print("ID người đã nhắn bot:", ", ".join(ids))
    user_id = input("Nhập CHÍNH XÁC ID tài khoản Telegram của bạn ở trên: ").strip()
    if user_id not in ids:
        raise RuntimeError("ID chưa có trong tin nhắn riêng gửi đến bot.")
    address = input("Nhập URL *.workers.dev đã hiện khi deploy (https://…): ").strip().rstrip("/")
    parsed = urlparse(address)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or not parsed.hostname.startswith("mira-phone.")
            or not parsed.hostname.endswith(".workers.dev")
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        raise RuntimeError("Hãy nhập đúng URL https://mira-phone.<subdomain>.workers.dev/ được in ra khi deploy.")
    webhook_key = secrets.token_urlsafe(36)
    print("Đang cài token vào Cloudflare Secrets (không ghi token ra file)…")
    wrangler("secret", "put", "TELEGRAM_BOT_TOKEN", secret=token)
    wrangler("secret", "put", "TELEGRAM_USER_ID", secret=user_id)
    wrangler("secret", "put", "TELEGRAM_WEBHOOK_SECRET", secret=webhook_key)
    telegram(token, "setWebhook", {"url": address + "/telegram", "secret_token": webhook_key,
                                    "allowed_updates": ["message"]})
    print("Đã kết nối bot Telegram. Nhắn /help cho bot để xem lệnh.")
    print("Mira sẽ gửi lịch nhắc từ cloud dù laptop tắt. Lịch có thể chậm khoảng một phút.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError, urllib.error.URLError) as error:
        print(f"Chưa xong: {error}. Xem README.md để thử lại.")
        raise SystemExit(1) from None
