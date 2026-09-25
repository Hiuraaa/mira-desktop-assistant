"""Run on the owner's PC to set up free-tier phone Mira in their Cloudflare account."""

from __future__ import annotations

import re
import secrets
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "wrangler.toml"
PLACEHOLDER = "REPLACE_WITH_YOUR_D1_DATABASE_ID"
UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)


def wrangler(*args: str, secret: str | None = None, capture: bool = False) -> str:
    npm = shutil.which("npx")
    if not npm:
        raise RuntimeError("Chưa có npx. Hãy cài Node.js LTS từ nodejs.org rồi mở lại PowerShell.")
    command = [npm, "--yes", "wrangler", *args]
    result = subprocess.run(command, cwd=ROOT, check=True, text=True,
                            input=secret + "\n" if secret is not None else None,
                            stdout=subprocess.PIPE if capture else None)
    return result.stdout or ""


def main() -> None:
    print("Mira trên điện thoại · cài Cloudflare Workers Free")
    print("Bạn cần tự đăng nhập tài khoản Cloudflare Free trên trình duyệt PC.")
    input("Nhấn Enter để mở trang đăng nhập Cloudflare…")
    wrangler("login")

    config = CONFIG.read_text(encoding="utf-8")
    if PLACEHOLDER in config:
        print("Đang tạo cơ sở dữ liệu D1 của riêng bạn…")
        output = wrangler("d1", "create", "mira-phone", capture=True)
        match = UUID.search(output)
        if not match:
            print(output)
            raise RuntimeError("Chưa đọc được ID D1. Xem cloud/README.md để điền thủ công.")
        CONFIG.write_text(config.replace(PLACEHOLDER, match.group()), encoding="utf-8")
        print("Đã ghi mã D1 vào wrangler.toml (không chứa mật khẩu).")
    print("Đang tạo bảng lịch nhắc và cuộc trò chuyện…")
    wrangler("d1", "migrations", "apply", "mira-phone", "--remote")
    print("Đang đưa Mira lên cloud…")
    wrangler("deploy")
    key = secrets.token_urlsafe(32)
    wrangler("secret", "put", "MIRA_ACCESS_KEY", secret=key)
    print("\nHOÀN TẤT. Lưu khóa này vào nơi riêng tư, chỉ hiển thị lần này:")
    print(key)
    print("\nMở URL https://mira-phone.<tên-subdomain>.workers.dev/ hiển thị khi deploy trên điện thoại.")
    print("Để nhận nhắc lịch khi đóng trang, tạo bot Telegram riêng rồi chạy python setup_telegram.py.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, subprocess.CalledProcessError, RuntimeError) as error:
        print(f"\nChưa cài xong: {error}. Xem README.md trong cùng thư mục để xử lý.")
        raise SystemExit(1) from None
