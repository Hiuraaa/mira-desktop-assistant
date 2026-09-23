"""Mira desktop interface: chat first, with explicit file and model controls."""

from __future__ import annotations

import shutil
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from .agent import Agent
from .storage import ConversationStore, MemoryStore, data_dir, load_json, save_json
from .workspace import Workspace, WorkspaceError


BG = "#0b1422"
SIDE = "#101f31"
PANEL = "#172a40"
INPUT = "#203852"
BORDER = "#38556d"
TEXT = "#f2f7ff"
MUTED = "#b4c7d9"
ACCENT = "#83edcf"
RED = "#ffadad"


class MiraApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Mira — trợ lý cá nhân")
        screen_width, screen_height = self.winfo_screenwidth(), self.winfo_screenheight()
        width = min(1120, max(720, screen_width - 80))
        height = min(750, max(440, screen_height - 90))
        self.geometry(f"{width}x{height}")
        self.minsize(700, 430)
        self.configure(bg=BG)
        self.path = data_dir()
        self.settings_path = self.path / "settings.json"
        settings = load_json(self.settings_path, {})
        if not isinstance(settings, dict):
            raise ValueError("Cài đặt Mira không đúng định dạng.")
        self.memories = MemoryStore(self.path / "memories.json")
        self.chats = ConversationStore(self.path / "conversations.json",
                                       self.path / "conversation.json")
        self.agent = Agent()
        self.busy = False
        self.closed = False
        self.pending_edit = None
        self.installed_models = []
        self.name_var = tk.StringVar(value=settings.get("name", "Mira"))
        self.model_var = tk.StringVar(value=settings.get("model", "qwen3:4b"))
        self.folder_var = tk.StringVar(value="Chưa chọn thư mục")
        self.status_var = tk.StringVar(value="Đang kiểm tra Ollama…")
        self.workspace = None
        try:
            if settings.get("folder"):
                self.workspace = Workspace(Path(settings["folder"]),
                                           self.path / "backups")
                self.folder_var.set(str(self.workspace.root))
        except (OSError, WorkspaceError):
            self.folder_var.set("Thư mục cũ không còn tồn tại. Hãy chọn lại.")
        self.current_id = settings.get("current_chat")
        if self.chats.get(self.current_id) is None:
            existing = self.chats.list()
            self.current_id = existing[0]["id"] if existing else self.chats.create()
        self._build()
        self._refresh_history()
        self._render_chat()
        self._check_model()
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _button(self, parent, label, command, primary=False):
        return tk.Button(
            parent, text=label, command=command, relief="flat",
            bg=ACCENT if primary else PANEL, fg=BG if primary else TEXT,
            activebackground="#b4ffe5" if primary else INPUT,
            activeforeground=BG if primary else TEXT,
            font=("Segoe UI", 10, "bold" if primary else "normal"),
            padx=12, pady=8, cursor="hand2", borderwidth=0,
        )

    def _label(self, parent, text, size=10, color=TEXT, bold=False, bg=BG, **kwargs):
        return tk.Label(parent, text=text, bg=bg, fg=color,
                        font=("Segoe UI", size, "bold" if bold else "normal"), **kwargs)

    def _build(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        sidebar = tk.Frame(self, bg=SIDE, width=260, padx=18, pady=18)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        self._label(sidebar, "✦  MIRA", 21, ACCENT, True, SIDE).pack(anchor="w")
        self._label(sidebar, "Trợ lý cá nhân của bạn", 10, MUTED, bg=SIDE).pack(anchor="w", pady=(0, 22))
        self.new_button = self._button(sidebar, "＋  Cuộc trò chuyện mới", self._new_chat, True)
        self.new_button.pack(fill="x")
        self._label(sidebar, "LỊCH SỬ TRÒ CHUYỆN", 9, MUTED, True, SIDE).pack(anchor="w", pady=(24, 8))
        history_frame = tk.Frame(sidebar, bg=SIDE)
        history_frame.pack(fill="both", expand=True)
        self.history = tk.Listbox(history_frame, bg=SIDE, fg=TEXT, selectbackground=INPUT,
                                  selectforeground=ACCENT, relief="flat", highlightthickness=0,
                                  activestyle="none", font=("Segoe UI", 10),
                                  borderwidth=0, exportselection=False)
        bar = tk.Scrollbar(history_frame, command=self.history.yview)
        self.history.configure(yscrollcommand=bar.set)
        self.history.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self.history.bind("<<ListboxSelect>>", self._select_chat)
        row = tk.Frame(sidebar, bg=SIDE)
        row.pack(fill="x", pady=(8, 18))
        self._button(row, "Đổi tên", self._rename_chat).pack(side="left", fill="x", expand=True, padx=(0, 5))
        self._button(row, "Xóa chat", self._delete_chat).pack(side="left", fill="x", expand=True)
        self._button(sidebar, "🧠  Bộ nhớ của Mira", self._memory_manager).pack(fill="x", pady=4)
        self._button(sidebar, "⚙  Mô hình & cài đặt", self._settings).pack(fill="x", pady=4)
        self._button(sidebar, "?  Hướng dẫn nhanh", self._help).pack(fill="x", pady=4)
        self._label(sidebar, "Dữ liệu chat và bộ nhớ lưu trên máy.",
                    9, MUTED, bg=SIDE, wraplength=220, justify="left").pack(anchor="w", pady=(18, 0))

        main = tk.Frame(self, bg=BG, padx=24, pady=18)
        main.grid(row=0, column=1, sticky="nsew")
        header = tk.Frame(main, bg=BG)
        header.pack(fill="x")
        self._label(header, "Trò chuyện với Mira", 19, TEXT, True).pack(side="left")
        self._button(header, "Xuất chat", self._export_chat).pack(side="right")
        self._label(main, "Hỏi bất cứ điều gì, nhờ giải thích code hoặc yêu cầu sửa file.",
                    10, MUTED).pack(anchor="w", pady=(2, 11))
        model_row = tk.Frame(main, bg=BG)
        model_row.pack(fill="x", pady=(0, 10))
        self.model_status = self._label(model_row, "", 10, MUTED)
        self.model_status.pack(side="left")
        self._button(model_row, "Kiểm tra lại", self._check_model).pack(side="right")

        project = tk.Frame(main, bg=PANEL, padx=13, pady=10)
        project.pack(fill="x", pady=(0, 12))
        left = tk.Frame(project, bg=PANEL)
        left.pack(side="left", fill="x", expand=True)
        self._label(left, "THƯ MỤC MIRA ĐƯỢC PHÉP DÙNG", 9, ACCENT, True, PANEL).pack(anchor="w")
        self._label(left, "", 9, MUTED, bg=PANEL, textvariable=self.folder_var,
                    anchor="w").pack(anchor="w", fill="x")
        self._button(project, "Chọn thư mục", self._choose_folder).pack(side="right", padx=(8, 0))

        chat_box = tk.Frame(main, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        self.output = tk.Text(chat_box, wrap="word", state="disabled", bg=PANEL, fg=TEXT,
                              insertbackground=TEXT, relief="flat", padx=18, pady=18,
                              font=("Segoe UI", 11), spacing3=10, borderwidth=0)
        scroll = tk.Scrollbar(chat_box, command=self.output.yview)
        self.output.configure(yscrollcommand=scroll.set)
        self.output.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.output.tag_configure("sender", foreground=ACCENT, font=("Segoe UI", 11, "bold"))
        self.output.tag_configure("welcome", foreground=TEXT, font=("Segoe UI", 17, "bold"))
        self.output.tag_configure("hint", foreground=MUTED, font=("Segoe UI", 11))

        shortcuts = tk.Frame(main, bg=BG)
        self._button(shortcuts, "＋ Chọn file", self._attach_file).pack(side="left", padx=(0, 7))
        self._button(shortcuts, "▶ Chạy kiểm thử", self._run_tests).pack(side="left", padx=(0, 7))
        self._button(shortcuts, "Gợi ý hỏi", self._suggest).pack(side="left")

        composer = tk.Frame(main, bg=INPUT, highlightbackground=ACCENT, highlightthickness=2,
                            padx=12, pady=9)
        self._label(composer, "NHẬP TIN NHẮN CHO MIRA", 9, ACCENT, True, INPUT).pack(anchor="w")
        input_row = tk.Frame(composer, bg=INPUT)
        input_row.pack(fill="x", pady=(5, 0))
        self.input = tk.Text(input_row, height=3, wrap="word", bg=INPUT, fg=TEXT,
                             insertbackground=TEXT, relief="flat", borderwidth=0,
                             font=("Segoe UI", 12), undo=True)
        self.input.pack(side="left", fill="both", expand=True)
        self.input.bind("<Return>", self._on_enter)
        self.input.bind("<Control-Return>", self._send)
        self.send_button = self._button(input_row, "Gửi  ➤", self._send, True)
        self.send_button.pack(side="right", padx=(12, 0), anchor="se")
        self.hint_label = self._label(main, "Enter để gửi  ·  Shift+Enter để xuống dòng", 9, MUTED)
        self.status_label = self._label(main, "", 9, MUTED, textvariable=self.status_var)
        # Reserve bottom space first. The chat transcript shrinks on small displays;
        # the composer and Send button must always remain visible.
        self.status_label.pack(side="bottom", anchor="w", pady=(3, 0))
        self.hint_label.pack(side="bottom", anchor="w", pady=(7, 0))
        composer.pack(side="bottom", fill="x")
        shortcuts.pack(side="bottom", fill="x", pady=(8, 5))
        chat_box.pack(fill="both", expand=True)
        self.input.focus_set()

    def _on_enter(self, event):
        if event.state & 0x0001:  # Shift+Enter: normal newline
            return None
        return self._send()

    def _save_settings(self):
        save_json(self.settings_path, {
            "name": self.name_var.get().strip()[:40] or "Mira",
            "model": self.model_var.get().strip(),
            "folder": str(self.workspace.root) if self.workspace else "",
            "current_chat": self.current_id,
        })

    def _refresh_history(self):
        self.history_ids = [item["id"] for item in self.chats.list()]
        self.history.delete(0, "end")
        for item in self.chats.list():
            self.history.insert("end", "  " + item.get("title", "Cuộc trò chuyện"))
        if self.current_id in self.history_ids:
            index = self.history_ids.index(self.current_id)
            self.history.selection_set(index)
            self.history.see(index)

    def _select_chat(self, event=None):
        selection = self.history.curselection()
        if not selection or self.busy:
            return
        chat_id = self.history_ids[selection[0]]
        if chat_id != self.current_id:
            self.current_id = chat_id
            self._save_settings()
            self._render_chat()

    def _render_chat(self):
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        messages = self.chats.messages(self.current_id)
        if messages:
            for message in messages:
                self._insert_message("Bạn" if message["role"] == "user"
                                     else self.name_var.get().strip() or "Mira",
                                     message["content"])
        else:
            self.output.insert("end", "Xin chào, mình là Mira ✦\n\n", "welcome")
            self.output.insert("end",
                "Ô chat của bạn nằm ngay bên dưới. Hãy thử hỏi một câu, hoặc chọn thư mục "
                "để mình giúp đọc và sửa file.\n\n"
                "Ví dụ: “Giải thích đoạn code này”, “Tìm lỗi trong dự án”, "
                "“Lập kế hoạch học tiếng Anh cho tôi”.", "hint")
        self.output.configure(state="disabled")
        self.output.see("end")

    def _insert_message(self, sender, content):
        self.output.insert("end", sender + "\n", "sender")
        self.output.insert("end", content + "\n\n")

    def _add_message(self, sender, content):
        self.output.configure(state="normal")
        if not self.chats.messages(self.current_id)[:-1] and sender == "Bạn":
            self.output.delete("1.0", "end")
        self._insert_message(sender, content)
        self.output.configure(state="disabled")
        self.output.see("end")

    def _new_chat(self):
        if self.busy:
            return
        try:
            self.current_id = self.chats.create()
            self._save_settings()
        except (OSError, ValueError) as exc:
            messagebox.showerror("Không tạo được chat", str(exc))
            return
        self._refresh_history()
        self._render_chat()
        self.input.focus_set()

    def _rename_chat(self):
        chat = self.chats.get(self.current_id)
        if not chat:
            return
        title = simpledialog.askstring("Đổi tên", "Tên cuộc trò chuyện:", parent=self,
                                       initialvalue=chat["title"])
        if title is not None:
            try:
                self.chats.rename(self.current_id, title)
                self._refresh_history()
            except (OSError, ValueError) as exc:
                messagebox.showerror("Không đổi được tên", str(exc))

    def _delete_chat(self):
        if self.busy or not messagebox.askyesno("Xóa cuộc trò chuyện",
                                                 "Xóa cuộc trò chuyện đang chọn? Bộ nhớ Mira vẫn được giữ."):
            return
        try:
            self.chats.delete(self.current_id)
            remaining = self.chats.list()
            self.current_id = remaining[0]["id"] if remaining else self.chats.create()
            self._save_settings()
        except (OSError, ValueError) as exc:
            messagebox.showerror("Không xóa được chat", str(exc))
            return
        self._refresh_history()
        self._render_chat()

    def _memory_manager(self):
        dialog = tk.Toplevel(self)
        dialog.title("Bộ nhớ cá nhân của Mira")
        dialog.geometry("650x460")
        dialog.transient(self)
        self._label(dialog, "Những điều bạn đã dạy Mira", 15, TEXT, True, SIDE).pack(fill="x")
        tk.Label(dialog, text="Mira dùng những điều này khi trả lời. Đây là bộ nhớ, chưa phải huấn luyện lại mô hình.",
                 anchor="w", wraplength=600, justify="left").pack(fill="x", padx=12, pady=10)
        box = tk.Listbox(dialog, font=("Segoe UI", 11))
        box.pack(fill="both", expand=True, padx=12)
        ids = []

        def refresh():
            box.delete(0, "end")
            ids.clear()
            for item in self.memories.items:
                box.insert("end", item["text"])
                ids.append(item["id"])

        def selected_id():
            selected = box.curselection()
            return ids[selected[0]] if selected else None

        def add():
            value = simpledialog.askstring("Dạy Mira", "Điều bạn muốn Mira ghi nhớ:", parent=dialog)
            if value is not None:
                try:
                    self.memories.add(value)
                    refresh()
                except (OSError, ValueError) as exc:
                    messagebox.showerror("Không lưu được", str(exc), parent=dialog)

        def edit():
            item_id = selected_id()
            if item_id:
                current = next(item["text"] for item in self.memories.items if item["id"] == item_id)
                value = simpledialog.askstring("Sửa bộ nhớ", "Nội dung mới:", parent=dialog,
                                               initialvalue=current)
                if value is not None:
                    try:
                        self.memories.update(item_id, value)
                        refresh()
                    except (OSError, ValueError) as exc:
                        messagebox.showerror("Không sửa được", str(exc), parent=dialog)

        def forget():
            item_id = selected_id()
            if item_id and messagebox.askyesno("Quên điều này?", "Xóa mục đã chọn khỏi bộ nhớ?", parent=dialog):
                try:
                    self.memories.forget(item_id)
                    refresh()
                except (OSError, ValueError) as exc:
                    messagebox.showerror("Không xóa được", str(exc), parent=dialog)

        actions = tk.Frame(dialog)
        actions.pack(pady=12)
        ttk.Button(actions, text="＋ Dạy điều mới", command=add).pack(side="left", padx=5)
        ttk.Button(actions, text="Sửa", command=edit).pack(side="left", padx=5)
        ttk.Button(actions, text="Quên", command=forget).pack(side="left", padx=5)
        refresh()

    def _settings(self):
        dialog = tk.Toplevel(self)
        dialog.title("Cài đặt Mira")
        dialog.geometry("500x290")
        dialog.resizable(False, False)
        dialog.transient(self)
        frame = tk.Frame(dialog, padx=18, pady=18)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text="Tên trợ lý").pack(anchor="w")
        name = ttk.Entry(frame, width=35)
        name.insert(0, self.name_var.get())
        name.pack(fill="x", pady=(4, 16))
        tk.Label(frame, text="Mô hình Ollama").pack(anchor="w")
        model = ttk.Combobox(frame, values=self.installed_models)
        model.set(self.model_var.get())
        model.pack(fill="x", pady=(4, 8))
        tk.Label(frame, text="Nếu danh sách trống, hãy mở Ollama và tải mô hình qwen3:4b.",
                 wraplength=440, justify="left").pack(anchor="w")

        def apply():
            if not model.get().strip():
                messagebox.showerror("Thiếu mô hình", "Hãy nhập tên mô hình.", parent=dialog)
                return
            self.name_var.set(name.get().strip()[:40] or "Mira")
            self.model_var.set(model.get().strip())
            try:
                self._save_settings()
            except OSError as exc:
                messagebox.showerror("Không lưu được cài đặt", str(exc), parent=dialog)
                return
            dialog.destroy()
            self._check_model()

        row = tk.Frame(frame)
        row.pack(fill="x", pady=18)
        ttk.Button(row, text="Hướng dẫn cài mô hình", command=self._help).pack(side="left")
        ttk.Button(row, text="Lưu", command=apply).pack(side="right")

    def _help(self):
        dialog = tk.Toplevel(self)
        dialog.title("Bắt đầu với Mira")
        dialog.geometry("620x370")
        dialog.transient(self)
        message = (
            "1. Cài Python 3.11+ và Ollama cho Windows.\n"
            "2. Mở Ollama. Trong PowerShell chạy: ollama pull qwen3:4b\n"
            "3. Nhập câu hỏi ở ô có nhãn NHẬP TIN NHẮN CHO MIRA bên dưới và nhấn Enter.\n"
            "4. Chọn thư mục để Mira có thể đọc, tìm và đề xuất sửa file.\n"
            "5. Mỗi lần sửa file bạn sẽ được xem diff và chọn Duyệt hoặc Từ chối.\n"
            "6. Dùng Bộ nhớ của Mira để dạy sở thích và quy tắc bạn muốn lưu."
        )
        tk.Label(dialog, text=message, font=("Segoe UI", 11), wraplength=570,
                 justify="left", anchor="nw", padx=20, pady=20).pack(fill="both", expand=True)

        def copy_command():
            self.clipboard_clear()
            self.clipboard_append("ollama pull qwen3:4b")
            messagebox.showinfo("Đã sao chép", "Dán lệnh vào PowerShell để tải mô hình.", parent=dialog)

        ttk.Button(dialog, text="Sao chép lệnh tải mô hình", command=copy_command).pack(pady=12)

    def _check_model(self):
        self.model_status.configure(text="●  Đang kiểm tra Ollama…", fg=MUTED)

        def run():
            try:
                models = self.agent.client.list_models()
                error = None
            except RuntimeError as exc:
                models, error = [], str(exc)

            def done():
                if self.closed:
                    return
                self.installed_models = models
                if error:
                    self.model_status.configure(text="●  Chưa kết nối Ollama • mở Cài đặt để xem hướng dẫn", fg=RED)
                    self.status_var.set(error)
                elif not models:
                    self.model_status.configure(text="●  Ollama đang chạy • chưa tải mô hình", fg=RED)
                    self.status_var.set("Tải qwen3:4b để bắt đầu trò chuyện.")
                elif self.model_var.get() not in models:
                    self.model_status.configure(text="●  Mô hình đã chọn chưa có trên máy", fg=RED)
                    self.status_var.set("Chọn một mô hình trong Cài đặt hoặc tải mô hình đã chọn.")
                else:
                    self.model_status.configure(text="●  Ollama sẵn sàng  •  " + self.model_var.get(), fg=ACCENT)
                    self.status_var.set("Sẵn sàng trò chuyện.")

            try:
                self.after(0, done)
            except RuntimeError:
                pass

        threading.Thread(target=run, daemon=True).start()

    def _choose_folder(self):
        if self.busy:
            return
        folder = filedialog.askdirectory(title="Chọn thư mục Mira được phép xem và sửa",
                                         initialdir=str(self.workspace.root) if self.workspace else None)
        if folder:
            try:
                self.workspace = Workspace(Path(folder), self.path / "backups")
                self.folder_var.set(str(self.workspace.root))
                self._save_settings()
                self.status_var.set("Đã chọn thư mục. Giờ bạn có thể nhờ Mira xem hoặc sửa file.")
            except (WorkspaceError, OSError) as exc:
                messagebox.showerror("Thư mục không hợp lệ", str(exc))

    def _attach_file(self):
        if not self.workspace:
            messagebox.showinfo("Chọn thư mục", "Hãy chọn thư mục trước khi đính kèm file.")
            return
        path = filedialog.askopenfilename(title="Chọn file trong thư mục đã cho phép",
                                          initialdir=str(self.workspace.root))
        if not path:
            return
        try:
            relative = Path(path).resolve().relative_to(self.workspace.root).as_posix()
            self.workspace._path(relative)
        except (ValueError, WorkspaceError):
            messagebox.showerror("Ngoài phạm vi", "File phải thuộc thư mục đã chọn và không phải symlink.")
            return
        prefix = self.input.get("1.0", "end").strip()
        self.input.delete("1.0", "end")
        self.input.insert("1.0", (prefix + "\n" if prefix else "") +
                          "Hãy đọc file " + relative + " và giúp tôi: ")
        self.input.focus_set()

    def _suggest(self):
        self.input.delete("1.0", "end")
        self.input.insert("1.0", "Hãy xem cấu trúc thư mục tôi đã chọn, giải thích dự án và đề xuất bước cải thiện đầu tiên.")
        self.input.focus_set()

    def _export_chat(self):
        messages = self.chats.messages(self.current_id)
        if not messages:
            messagebox.showinfo("Chưa có tin nhắn", "Cuộc trò chuyện này chưa có nội dung để xuất.")
            return
        path = filedialog.asksaveasfilename(title="Xuất cuộc trò chuyện", defaultextension=".md",
                                            filetypes=[("Markdown", "*.md"), ("Văn bản", "*.txt")])
        if path:
            try:
                name = self.name_var.get().strip() or "Mira"
                content = "# Cuộc trò chuyện với " + name + "\n\n"
                content += "\n\n".join("## " + ("Bạn" if m["role"] == "user" else name) +
                                       "\n\n" + m["content"] for m in messages) + "\n"
                Path(path).write_text(content, encoding="utf-8")
                self.status_var.set("Đã xuất cuộc trò chuyện.")
            except OSError as exc:
                messagebox.showerror("Không xuất được", str(exc))

    def _run_tests(self):
        if self.busy or not self.workspace:
            messagebox.showinfo("Chọn thư mục", "Hãy chọn thư mục dự án trước.")
            return
        root = self.workspace.root
        if (root / "tests").is_dir():
            args = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]
            display = "python -m unittest discover -s tests -v"
        elif (root / "package.json").is_file() and shutil.which("npm"):
            args = ["npm", "test"]
            display = "npm test"
        else:
            messagebox.showinfo("Chưa có bộ kiểm thử", "Mira hỗ trợ dự án có thư mục tests (Python) hoặc package.json (npm).")
            return
        if not messagebox.askyesno("Chạy kiểm thử trong dự án",
                                   "Lệnh: " + display + "\nThư mục: " + str(root) +
                                   "\n\nKiểm thử sẽ chạy code của dự án. Bạn đồng ý chạy?"):
            return
        self.status_var.set("Đang chạy kiểm thử…")

        def run():
            try:
                result = subprocess.run(args, cwd=root, capture_output=True, text=True,
                                        encoding="utf-8", errors="replace", timeout=120,
                                        shell=False)
                summary = "Mã thoát: " + str(result.returncode) + "\n\n" + (result.stdout + result.stderr)[-20000:]
            except (OSError, subprocess.TimeoutExpired) as exc:
                summary = "Không chạy được: " + str(exc)

            def show():
                if self.closed:
                    return
                self.status_var.set("Đã hoàn tất kiểm thử.")
                dialog = tk.Toplevel(self)
                dialog.title("Kết quả kiểm thử")
                dialog.geometry("820x570")
                area = tk.Text(dialog, wrap="word", font=("Consolas", 10))
                area.pack(fill="both", expand=True, padx=12, pady=12)
                area.insert("1.0", display + "\n\n" + summary)
                area.configure(state="disabled")

            try:
                self.after(0, show)
            except RuntimeError:
                pass

        threading.Thread(target=run, daemon=True).start()

    def _approve_edit(self, path, reason, diff):
        done = threading.Event()
        self.pending_edit = done
        accepted = [False]

        def show():
            if self.closed:
                done.set()
                return
            dialog = tk.Toplevel(self)
            dialog.title("Duyệt thay đổi — " + path)
            dialog.geometry("890x630")
            dialog.minsize(620, 420)
            dialog.transient(self)
            dialog.grab_set()
            tk.Label(dialog, text="File: " + path + "\n" + reason +
                     "\n\nHãy xem các dòng + / − trước khi duyệt. File cũ sẽ được sao lưu.",
                     justify="left", anchor="w", wraplength=830, padx=16, pady=12).pack(fill="x")
            frame = tk.Frame(dialog)
            frame.pack(fill="both", expand=True, padx=16)
            preview = tk.Text(frame, wrap="none", font=("Consolas", 10))
            ybar = tk.Scrollbar(frame, command=preview.yview)
            xbar = tk.Scrollbar(frame, orient="horizontal", command=preview.xview)
            preview.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
            preview.tag_configure("add", foreground="#126b36")
            preview.tag_configure("remove", foreground="#a42222")
            for line in diff.splitlines(keepends=True):
                tag = "add" if line.startswith("+") else "remove" if line.startswith("-") else ""
                preview.insert("end", line, tag)
            preview.configure(state="disabled")
            preview.grid(row=0, column=0, sticky="nsew")
            ybar.grid(row=0, column=1, sticky="ns")
            xbar.grid(row=1, column=0, sticky="ew")
            frame.grid_rowconfigure(0, weight=1)
            frame.grid_columnconfigure(0, weight=1)

            def finish(value=False):
                accepted[0] = value
                done.set()
                dialog.destroy()

            controls = tk.Frame(dialog, pady=12)
            controls.pack()
            ttk.Button(controls, text="Từ chối", command=finish).pack(side="left", padx=8)
            ttk.Button(controls, text="Duyệt và ghi file",
                       command=lambda: finish(True)).pack(side="left", padx=8)
            dialog.protocol("WM_DELETE_WINDOW", finish)

        try:
            self.after(0, show)
        except RuntimeError:
            return False
        done.wait()
        self.pending_edit = None
        return accepted[0] and not self.closed

    def _set_busy(self, value):
        self.busy = value
        self.send_button.configure(state="disabled" if value else "normal")
        self.new_button.configure(state="disabled" if value else "normal")

    def _send(self, event=None):
        if self.busy:
            return "break"
        text = self.input.get("1.0", "end").strip()
        if not text:
            return "break"
        name = self.name_var.get().strip()[:40] or "Mira"
        model = self.model_var.get().strip()
        try:
            self._save_settings()
            previous = self.chats.messages(self.current_id)
            self.chats.append(self.current_id, "user", text)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Không lưu được tin nhắn", str(exc))
            return "break"
        self.input.delete("1.0", "end")
        self._add_message("Bạn", text)
        self._refresh_history()
        self._set_busy(True)
        self.status_var.set("Mira đang suy nghĩ…")
        workspace = self.workspace
        memories = self.memories.prompt()
        chat_id = self.current_id

        def run():
            try:
                answer = self.agent.respond(text, previous, model, name, memories,
                                            workspace, self._approve_edit,
                                            lambda action: self.after(0, self.status_var.set, action))
            except Exception as exc:
                answer = "Có lỗi: " + str(exc)

            def complete():
                if self.closed:
                    return
                try:
                    self.chats.append(chat_id, "assistant", answer)
                except (OSError, ValueError) as exc:
                    messagebox.showerror("Không lưu được câu trả lời", str(exc))
                self._add_message(name, answer)
                self._refresh_history()
                self._set_busy(False)
                self.status_var.set("Sẵn sàng trò chuyện.")
                self.input.focus_set()

            try:
                self.after(0, complete)
            except RuntimeError:
                pass

        threading.Thread(target=run, daemon=True).start()
        return "break"

    def _close(self):
        self.closed = True
        if self.pending_edit:
            self.pending_edit.set()
        self.destroy()


def main():
    try:
        app = MiraApp()
    except (OSError, ValueError) as exc:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Không mở được Mira", str(exc))
        root.destroy()
        return
    app.mainloop()
