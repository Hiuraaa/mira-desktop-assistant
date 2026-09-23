"""Read and propose edits inside a folder explicitly selected by the user."""

from __future__ import annotations

import difflib
import ast
import os
import shutil
import stat
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


MAX_READ = 64 * 1024
MAX_WRITE = 128 * 1024
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "dist", "build", "__pycache__"}
PROTECTED = {".env", ".npmrc", ".pypirc", "id_rsa", "id_ed25519", "credentials.json"}
PROTECTED_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}


class WorkspaceError(ValueError):
    pass


class Workspace:
    def __init__(self, root: Path, backups: Path):
        root = Path(root).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise WorkspaceError("Hãy chọn một thư mục làm vùng làm việc.")
        self.root = root
        self.backups = backups

    def _path(self, relative: str) -> Path:
        if not isinstance(relative, str) or not relative or "\0" in relative:
            raise WorkspaceError("Đường dẫn không hợp lệ.")
        raw = Path(relative)
        if raw.is_absolute() or any(part in {"", ".", ".."} for part in raw.parts):
            raise WorkspaceError("Chỉ dùng đường dẫn tương đối bên trong vùng làm việc.")
        # Windows path spellings (drive, UNC, ADS) cannot be smuggled through on Unix.
        if ":" in relative or "\\" in relative:
            raise WorkspaceError("Dùng dấu / cho đường dẫn tương đối, không dùng ổ đĩa.")
        if any(part.lower() in SKIP_DIRS for part in raw.parts):
            raise WorkspaceError("Thư mục hệ thống hoặc thư mục sinh tự động bị loại trừ.")
        if any(part.lower() in PROTECTED or part.lower().startswith(".env.") or Path(part).suffix.lower() in PROTECTED_SUFFIXES for part in raw.parts):
            raise WorkspaceError("File chứa thông tin đăng nhập bị loại trừ.")

        target = self.root / raw
        current = self.root
        for part in raw.parts:
            current = current / part
            if current.is_symlink():
                raise WorkspaceError("Không đọc hoặc sửa đường dẫn liên kết (symlink).")
        if not target.resolve().is_relative_to(self.root):
            raise WorkspaceError("Đường dẫn nằm ngoài vùng làm việc.")
        return target

    def list_files(self, subfolder: str = ".") -> str:
        if subfolder == ".":
            start = self.root
        else:
            start = self._path(subfolder)
        if not start.is_dir():
            raise WorkspaceError("Thư mục không tồn tại.")
        results = []
        scanned = 0
        for folder, dirs, files in os.walk(start, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d.lower() not in SKIP_DIRS and not (Path(folder) / d).is_symlink())
            for name in sorted(files):
                scanned += 1
                path = Path(folder) / name
                rel = path.relative_to(self.root).as_posix()
                try:
                    self._path(rel)
                    if path.is_file() and not path.is_symlink():
                        results.append(rel)
                except WorkspaceError:
                    pass
                if len(results) >= 200 or scanned >= 3000:
                    return "\n".join(results) + "\n(Đã giới hạn kết quả; hãy chọn thư mục con để xem tiếp.)"
        return "\n".join(results) if results else "Thư mục chưa có file văn bản phù hợp."

    def read_file(self, relative: str) -> str:
        target = self._path(relative)
        if not target.is_file():
            raise WorkspaceError("File không tồn tại.")
        if target.stat().st_size > MAX_READ:
            raise WorkspaceError("File lớn hơn 64 KiB; hãy chia nhỏ trước khi cho trợ lý đọc.")
        raw = target.read_bytes()
        if b"\0" in raw:
            raise WorkspaceError("Đây có thể là file nhị phân; chỉ hỗ trợ file UTF-8.")
        try:
            contents = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise WorkspaceError("Chỉ hỗ trợ file văn bản UTF-8.") from exc
        return f"File: {relative}\n" + "\n".join(f"{i:>4}: {line}" for i, line in enumerate(contents.splitlines(), 1))

    def check_python_syntax(self, relative: str) -> str:
        """Parse Python code without executing it or creating bytecode files."""
        if not relative.lower().endswith(".py"):
            raise WorkspaceError("Chỉ kiểm tra cú pháp file .py.")
        target = self._path(relative)
        if not target.is_file() or target.stat().st_size > MAX_READ:
            raise WorkspaceError("File không tồn tại hoặc lớn hơn 64 KiB.")
        try:
            source = target.read_text(encoding="utf-8")
            ast.parse(source, filename=relative)
        except (UnicodeDecodeError, SyntaxError) as exc:
            if isinstance(exc, SyntaxError):
                return f"Lỗi cú pháp {relative}:{exc.lineno}:{exc.offset}: {exc.msg}"
            raise WorkspaceError("Chỉ hỗ trợ file văn bản UTF-8.") from exc
        return f"Cú pháp Python của {relative} hợp lệ (chưa chạy chương trình)."

    def search_text(self, query: str) -> str:
        if not isinstance(query, str) or not 2 <= len(query) <= 100:
            raise WorkspaceError("Cụm tìm kiếm cần dài 2–100 ký tự.")
        hits = []
        scanned = 0
        for folder, dirs, files in os.walk(self.root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d.lower() not in SKIP_DIRS and not (Path(folder) / d).is_symlink())
            for name in sorted(files):
                scanned += 1
                path = Path(folder) / name
                rel = path.relative_to(self.root).as_posix()
                try:
                    self._path(rel)
                    if path.stat().st_size > MAX_READ or not path.is_file():
                        continue
                    data = path.read_bytes()
                    if b"\0" in data:
                        continue
                    lines = data.decode("utf-8").splitlines()
                except (WorkspaceError, OSError, UnicodeDecodeError):
                    continue
                for number, line in enumerate(lines, 1):
                    if query.casefold() in line.casefold():
                        hits.append(f"{rel}:{number}: {line[:240]}")
                        if len(hits) >= 60:
                            return "\n".join(hits) + "\n(Đã giới hạn 60 kết quả.)"
                if scanned >= 3000:
                    return "\n".join(hits) + "\n(Đã giới hạn 3000 file.)"
        return "\n".join(hits) if hits else "Không tìm thấy."

    def propose_write_file(self, relative: str, content: str, reason: str,
                           approve: Callable[[str, str, str], bool]) -> str:
        target = self._path(relative)
        if not isinstance(content, str) or len(content.encode("utf-8")) > MAX_WRITE:
            raise WorkspaceError("Nội dung mới vượt quá 128 KiB.")
        if target.exists() and not target.is_file():
            raise WorkspaceError("Đường dẫn hiện có không phải file.")
        if target.exists() and target.stat().st_size > MAX_WRITE:
            raise WorkspaceError("File hiện tại vượt quá 128 KiB.")
        old_bytes = target.read_bytes() if target.exists() else None
        if old_bytes is not None:
            try:
                old = old_bytes.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise WorkspaceError("Chỉ sửa file văn bản UTF-8.") from exc
        else:
            old = ""
        if old_bytes is not None and old == content:
            return f"{relative}: không có thay đổi."
        diff = "".join(difflib.unified_diff(old.splitlines(keepends=True), content.splitlines(keepends=True),
                                             fromfile=f"a/{relative}", tofile=f"b/{relative}"))
        if not approve(relative, reason[:500], diff):
            return f"Người dùng không duyệt thay đổi ở {relative}. Không ghi file."

        # Reject stale proposals: the file may have changed while the approval dialog was open.
        target = self._path(relative)
        latest = target.read_bytes() if target.exists() and target.is_file() else None
        if latest != old_bytes:
            raise WorkspaceError("File đã thay đổi trong lúc chờ duyệt; hãy đọc lại rồi thử tiếp.")
        target.parent.mkdir(parents=True, exist_ok=True)
        target = self._path(relative)
        backup = None
        if old_bytes is not None:
            self.backups.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup = self.backups / f"{stamp}_{uuid.uuid4().hex[:8]}_{target.name}"
            shutil.copy2(target, backup)
        fd, temp_name = tempfile.mkstemp(prefix=".mira-", suffix=".tmp", dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content.encode("utf-8"))
                handle.flush()
                os.fsync(handle.fileno())
            if old_bytes is not None:
                os.chmod(temp_name, stat.S_IMODE(target.stat().st_mode))
            os.replace(temp_name, target)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        return f"Đã ghi {relative}." + (f" Bản sao cũ: {backup}" if backup else "")
