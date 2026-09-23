"""Mira's desktop chat window. Tk is only touched from its main thread."""

from __future__ import annotations

import threading
import queue
import shutil
import subprocess
import sys
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from .agent import Agent, is_cloud_model
from .preferences import PreferenceStore
from .preferences_ui import open_preference_dialog
from .speech import SpeechPlayer
from .storage import ConversationStore, MemoryStore, data_dir, load_json, save_json
from .workspace import Workspace, WorkspaceError


BG = "#0c1422"
SIDE = "#142136"
PANEL = "#1b2b42"
TEXT = "#f5f8fd"
MUTED = "#acc1d4"
ACCENT = "#6ce0c5"
INK = "#152337"


class MiraApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Mira • trợ lý cá nhân")
        self.geometry("1160x760")
        self.minsize(860, 610)
        self.configure(bg=BG)
        self.path = data_dir()
        self.settings_path = self.path / "settings.json"
        settings = load_json(self.settings_path, {})
        if not isinstance(settings, dict):
            raise ValueError("Cài đặt Mira không đúng định dạng.")
        self.memories = MemoryStore(self.path / "memories.json")
        self.preferences = PreferenceStore(self.path / "preferences.json")
        self.chats = ConversationStore(self.path / "conversations.json", self.path / "conversation.json")
        self.agent = Agent()
        self.speaker = SpeechPlayer()
        self.busy = False
        self.closed = False
        self.pending_approval: threading.Event | None = None
        self.retry_text: str | None = None
        self.retry_chat_id: str | None = None
        self.retry_image: bytes | None = None
        self.retry_image_name: str | None = None
        self.attachment_data: bytes | None = None
        self.attachment_name: str | None = None
        self.attachment_var = tk.StringVar(value="Chưa đính kèm ảnh")
        self.available_models: list[str] = []
        self.name_var = tk.StringVar(value=settings.get("name") or "Mira")
        self.model_var = tk.StringVar(value=settings.get("model") or "qwen3:4b")
        self.cloud_consent = settings.get("cloud_consent") is True
        self.last_local_model = str(settings.get("last_local_model") or "qwen3:4b")
        if not is_cloud_model(self.model_var.get()):
            self.last_local_model = self.model_var.get()
        self.fast_var = tk.BooleanVar(value=settings.get("fast_mode", True))
        self.deep_var = tk.BooleanVar(value=settings.get("deep_thinking", False))
        self.voice_auto_var = tk.BooleanVar(value=settings.get("voice_auto", False))
        self.playful_var = tk.BooleanVar(value=settings.get("persona_mode", "playful") == "playful")
        self.persona_note = str(settings.get("persona_note") or "")[:400]
        self.stream_chat_id: str | None = None
        self.stream_text = ""
        self.avatar_state = "idle"
        self.avatar_tick = 0
        self.folder_var = tk.StringVar(value="Chưa chọn thư mục • Mira chỉ trò chuyện")
        self.health_var = tk.StringVar(value="Đang kiểm tra Ollama…")
        self.status_var = tk.StringVar(value="Sẵn sàng • Enter để gửi, Shift+Enter để xuống dòng")
        self.title_var = tk.StringVar(value="Cuộc trò chuyện")
        self.workspace: Workspace | None = None
        try:
            if settings.get("folder"):
                self.workspace = Workspace(Path(settings["folder"]), self.path / "backups")
                self.folder_var.set(str(self.workspace.root))
        except (OSError, WorkspaceError):
            self.folder_var.set("Thư mục cũ không còn tồn tại • hãy chọn lại")

        if not self.chats.items:
            self.active_chat_id = self.chats.new()["id"]
        else:
            selected = settings.get("active_chat_id") or settings.get("current_chat")
            ids = {item["id"] for item in self.chats.items}
            self.active_chat_id = selected if selected in ids else self.chats.items[0]["id"]

        self._build()
        self._refresh_chat_list()
        self._render_chat()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(200, self._check_ollama)
        self.after(280, self._animate_avatar)

    def _button(self, parent, label, command, *, primary=False, subtle=False):
        return tk.Button(parent, text=label, command=command, relief="flat", cursor="hand2",
                         bg=ACCENT if primary else (SIDE if subtle else PANEL),
                         fg=INK if primary else TEXT, activebackground="#a4f0dc" if primary else "#304967",
                         activeforeground=INK if primary else TEXT, font=("Segoe UI", 10, "bold"),
                         padx=13, pady=9, borderwidth=0, takefocus=True)

    def _build(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        sidebar = tk.Frame(self, bg=SIDE, width=252, padx=14, pady=16)
        sidebar.grid(row=0, column=0, sticky="ns")
        sidebar.grid_propagate(False)
        sidebar.grid_columnconfigure(0, weight=1)
        sidebar.grid_rowconfigure(3, weight=1)
        tk.Label(sidebar, text="✦  Mira", bg=SIDE, fg=ACCENT,
                 font=("Segoe UI", 23, "bold"), anchor="w").grid(row=0, column=0, sticky="ew")
        tk.Label(sidebar, text="Trợ lý trên máy tính của bạn", bg=SIDE, fg=MUTED,
                 font=("Segoe UI", 10), anchor="w").grid(row=1, column=0, sticky="ew", pady=(0, 24))
        self._button(sidebar, "+  Cuộc trò chuyện mới", self._new_chat, primary=True).grid(
            row=2, column=0, sticky="ew", pady=(0, 17))
        archive = tk.Frame(sidebar, bg=SIDE)
        archive.grid(row=3, column=0, sticky="nsew")
        archive.grid_columnconfigure(0, weight=1)
        archive.grid_rowconfigure(1, weight=1)
        tk.Label(archive, text="LỊCH SỬ TRÒ CHUYỆN", bg=SIDE, fg=MUTED,
                 font=("Segoe UI", 9, "bold"), anchor="w").grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.chat_list = tk.Listbox(archive, selectmode="browse", activestyle="none", relief="flat",
                                    bg=SIDE, fg=TEXT, selectbackground="#325976", selectforeground=TEXT,
                                    font=("Segoe UI", 11), highlightthickness=0, borderwidth=0)
        self.chat_list.grid(row=1, column=0, sticky="nsew")
        self.chat_list.bind("<<ListboxSelect>>", self._select_chat)
        actions = tk.Frame(sidebar, bg=SIDE)
        actions.grid(row=4, column=0, sticky="ew", pady=(13, 11))
        self._button(actions, "Đổi tên", self._rename_chat, subtle=True).pack(side="left", fill="x", expand=True)
        self._button(actions, "Xóa", self._delete_chat, subtle=True).pack(side="left", fill="x", expand=True)
        self._button(sidebar, "📁  Chọn thư mục làm việc", self._choose_folder, subtle=True).grid(
            row=5, column=0, sticky="ew", pady=3)
        self._button(sidebar, "✦  Dạy Mira / bộ nhớ", self._show_memories, subtle=True).grid(
            row=6, column=0, sticky="ew", pady=3)
        self._button(sidebar, "⚙  Mô hình & cài đặt", self._settings_dialog, subtle=True).grid(
            row=7, column=0, sticky="ew", pady=3)
        self._button(sidebar, "🚀  Mô hình mạnh & tốc độ", self._model_lab_dialog, subtle=True).grid(
            row=8, column=0, sticky="ew", pady=3)
        self._button(sidebar, "☁  AI cloud cho máy yếu", self._cloud_dialog, subtle=True).grid(
            row=9, column=0, sticky="ew", pady=3)
        self._button(sidebar, "↥  Xuất cuộc trò chuyện", self._export_chat, subtle=True).grid(
            row=10, column=0, sticky="ew", pady=(3, 0))

        main = tk.Frame(self, bg=BG, padx=23, pady=16)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(4, weight=1)
        head = tk.Frame(main, bg=BG)
        head.grid(row=0, column=0, sticky="ew")
        self.avatar = tk.Canvas(head, width=50, height=52, bg=BG, highlightthickness=0)
        self.avatar.pack(side="left", padx=(0, 11))
        self.avatar_ring = self.avatar.create_oval(2, 2, 48, 48, fill=SIDE, outline=ACCENT, width=2)
        self.avatar.create_oval(10, 13, 18, 21, fill=ACCENT, outline="")
        self.avatar.create_oval(31, 13, 39, 21, fill=ACCENT, outline="")
        self.avatar_mouth = self.avatar.create_arc(17, 22, 34, 36, start=180, extent=180,
                                                   style="arc", outline=ACCENT, width=2)
        titles = tk.Frame(head, bg=BG)
        titles.pack(side="left", fill="x", expand=True)
        tk.Label(titles, textvariable=self.title_var, bg=BG, fg=TEXT,
                 font=("Segoe UI", 19, "bold"), anchor="w").pack(fill="x")
        tk.Label(titles, textvariable=self.folder_var, bg=BG, fg=MUTED,
                 font=("Segoe UI", 10), anchor="w", wraplength=520).pack(fill="x", pady=(2, 12))

        health = tk.Frame(main, bg=PANEL, padx=13, pady=7)
        health.grid(row=1, column=0, sticky="ew", pady=(0, 11))
        self.health_label = tk.Label(health, textvariable=self.health_var, bg=PANEL, fg=ACCENT,
                                     anchor="w", font=("Segoe UI", 10, "bold"))
        self.health_label.pack(side="left", fill="x", expand=True)
        self._button(health, "Kiểm tra lại", self._check_ollama).pack(side="right", padx=(8, 0))
        self._button(health, "Cách cài", self._setup_guide).pack(side="right")

        project_actions = tk.Frame(main, bg=BG)
        project_actions.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        self._button(project_actions, "＋ Chọn file", self._attach_file).pack(side="left", padx=(0, 8))
        self._button(project_actions, "▶ Chạy kiểm thử", self._run_tests).pack(side="left")
        tk.Checkbutton(project_actions, text="✦ Mira hoạt bát", variable=self.playful_var,
                       command=self._toggle_persona, bg=BG, fg=ACCENT, selectcolor=PANEL,
                       activebackground=BG, activeforeground=TEXT,
                       font=("Segoe UI", 10, "bold"), cursor="hand2").pack(side="right")

        self.starters = tk.Frame(main, bg=BG)
        self.starters.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        for label, prompt in (
            ("Giải thích lỗi code", "Giúp tôi hiểu và sửa lỗi code này: "),
            ("Tìm trong dự án", "Tìm trong thư mục đã chọn nơi xử lý: "),
            ("Kiểm tra Python", "Kiểm tra cú pháp file Python này: "),
            ("Lên kế hoạch", "Giúp tôi chia việc này thành các bước cụ thể: "),
        ):
            self._button(self.starters, label, lambda p=prompt: self._fill_prompt(p)).pack(
                side="left", padx=(0, 8))

        conversation = tk.Frame(main, bg=PANEL)
        conversation.grid(row=4, column=0, sticky="nsew")
        conversation.grid_columnconfigure(0, weight=1)
        conversation.grid_rowconfigure(0, weight=1)
        self.output = tk.Text(conversation, wrap="word", state="disabled", bg=PANEL, fg=TEXT,
                              insertbackground=TEXT, relief="flat", padx=22, pady=20,
                              font=("Segoe UI", 11), spacing1=3, spacing3=12, cursor="arrow")
        self.output.grid(row=0, column=0, sticky="nsew")
        scroll = tk.Scrollbar(conversation, command=self.output.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.output.configure(yscrollcommand=scroll.set)
        self.output.tag_configure("mira", foreground=ACCENT, font=("Segoe UI", 11, "bold"))
        self.output.tag_configure("you", foreground="#a9caff", font=("Segoe UI", 11, "bold"))

        composer = tk.Frame(main, bg=BG, pady=14)
        composer.grid(row=5, column=0, sticky="ew")
        composer.grid_columnconfigure(0, weight=1)
        tk.Label(composer, text="NHẮN MIRA", bg=BG, fg=ACCENT, anchor="w",
                 font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        self.input = tk.Text(composer, height=4, wrap="word", bg="#f7fbff", fg=INK,
                             insertbackground=INK, relief="flat", highlightthickness=2,
                             highlightbackground=ACCENT, highlightcolor=ACCENT,
                             padx=14, pady=10, font=("Segoe UI", 12), undo=True)
        self.input.grid(row=1, column=0, sticky="ew")
        self.input.bind("<Return>", self._send)
        self.input.bind("<Control-Return>", self._send)
        self.input.bind("<Shift-Return>", self._newline)
        self.send_button = self._button(composer, "Gửi  ↗", self._send, primary=True)
        self.send_button.grid(row=1, column=1, sticky="ns", padx=(10, 0))
        tk.Label(composer, text="Nhập câu hỏi hoặc yêu cầu sửa file • Enter gửi • Shift+Enter xuống dòng",
                 bg=BG, fg=MUTED, font=("Segoe UI", 9), anchor="w").grid(
                     row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        attachment = tk.Frame(composer, bg=BG)
        attachment.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(5, 0))
        self._button(attachment, "＋ Đính kèm ảnh", self._attach_image).pack(side="left")
        tk.Label(attachment, textvariable=self.attachment_var, bg=BG, fg=MUTED,
                 font=("Segoe UI", 9), width=30, anchor="w").pack(side="left", padx=8)
        self._button(attachment, "Bỏ ảnh", self._clear_image).pack(side="right")
        status = tk.Frame(main, bg=BG)
        status.grid(row=6, column=0, sticky="ew")
        tk.Label(status, textvariable=self.status_var, bg=BG, fg=MUTED,
                 anchor="w", font=("Segoe UI", 9)).pack(side="left", fill="x", expand=True)
        self.retry_button = self._button(status, "Thử gửi lại", self._retry)
        self.listen_button = self._button(status, "🔊 Nghe", self._listen_last)
        self.listen_button.pack(side="right", padx=(8, 0))
        if not self.speaker.available():
            self.listen_button.configure(state="disabled")
        self.input.focus_set()

    def _save_settings(self):
        selected_model = self.model_var.get().strip()
        if selected_model and not is_cloud_model(selected_model):
            self.last_local_model = selected_model
        save_json(self.settings_path, {
            "name": self.name_var.get().strip()[:40] or "Mira",
            "model": selected_model,
            "cloud_consent": self.cloud_consent,
            "last_local_model": self.last_local_model,
            "fast_mode": self.fast_var.get(),
            "deep_thinking": self.deep_var.get(),
            "voice_auto": self.voice_auto_var.get(),
            "persona_mode": "playful" if self.playful_var.get() else "standard",
            "persona_note": self.persona_note,
            "folder": str(self.workspace.root) if self.workspace else "",
            "active_chat_id": self.active_chat_id,
            "current_chat": self.active_chat_id,
        })

    def _toggle_persona(self):
        try:
            self._save_settings()
            self.status_var.set("Đã bật Mira hoạt bát." if self.playful_var.get()
                                else "Đã chuyển sang Mira thường.")
        except OSError as exc:
            messagebox.showerror("Không lưu được tính cách", str(exc))

    def _close(self):
        self.closed = True
        self.speaker.stop()
        if getattr(self, "model_download_proc", None):
            process = self.model_download_proc
            if process.poll() is None:
                process.terminate()
        if self.pending_approval:
            self.pending_approval.set()
        try:
            self._save_settings()
        except OSError:
            pass
        self.destroy()

    def _animate_avatar(self):
        if self.closed:
            return
        self.avatar_tick += 1
        active = self.avatar_state != "idle"
        color = ACCENT if self.avatar_state != "thinking" or self.avatar_tick % 2 else "#a9caff"
        self.avatar.itemconfigure(self.avatar_ring, outline=color, width=3 if active else 2)
        if self.avatar_state == "speaking" and self.avatar_tick % 2:
            self.avatar.coords(self.avatar_mouth, 20, 24, 30, 37)
        else:
            self.avatar.coords(self.avatar_mouth, 17, 22, 34, 36)
        self.after(280, self._animate_avatar)

    def _refresh_chat_list(self):
        self.chat_list.delete(0, "end")
        for item in self.chats.items:
            self.chat_list.insert("end", "  " + item.get("title", "Cuộc trò chuyện"))
        for index, item in enumerate(self.chats.items):
            if item["id"] == self.active_chat_id:
                self.chat_list.selection_set(index)
                self.chat_list.see(index)
                break

    def _render_chat(self):
        item = self.chats.get(self.active_chat_id)
        self.title_var.set(item.get("title", "Cuộc trò chuyện"))
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.configure(state="disabled")
        for message in item["messages"]:
            self._add_message("Bạn" if message["role"] == "user" else self.name_var.get(),
                              message["content"], user=message["role"] == "user")
        if not item["messages"]:
            self._add_message(self.name_var.get(),
                              "Chào bạn! Bạn có thể nhắn cho mình ngay ở ô sáng phía dưới. "
                              "Nếu muốn mình xem hoặc sửa code, hãy chọn thư mục làm việc trước.")
            self.starters.grid()
        else:
            self.starters.grid_remove()
        if self.busy and self.stream_chat_id == self.active_chat_id and self.stream_text:
            self._show_pending(self.name_var.get())

    def _add_message(self, sender: str, content: str, *, user=False):
        self.output.configure(state="normal")
        self.output.insert("end", sender + "\n", "you" if user else "mira")
        self.output.insert("end", content + "\n\n")
        self.output.configure(state="disabled")
        self.output.see("end")

    def _remove_pending(self):
        ranges = self.output.tag_ranges("pending")
        if ranges:
            self.output.configure(state="normal")
            self.output.delete(ranges[0], ranges[-1])
            self.output.configure(state="disabled")

    def _show_pending(self, name: str):
        self._remove_pending()
        self.output.configure(state="normal")
        self.output.insert("end", name + "\n", ("mira", "pending"))
        self.output.insert("end", (self.stream_text or "Đang chuẩn bị câu trả lời…") + "\n\n", "pending")
        self.output.configure(state="disabled")
        self.output.see("end")

    def _select_chat(self, event=None):
        selected = self.chat_list.curselection()
        if selected and selected[0] < len(self.chats.items):
            selected_id = self.chats.items[selected[0]]["id"]
            if selected_id != self.active_chat_id:
                self.speaker.stop()
                self.listen_button.configure(text="🔊 Nghe")
                self.avatar_state = "thinking" if self.busy else "idle"
                self.active_chat_id = selected_id
                self._render_chat()
                if self.retry_text and self.retry_chat_id == selected_id:
                    self.retry_button.pack(side="right")
                else:
                    self.retry_button.pack_forget()
                self._save_settings()

    def _new_chat(self):
        try:
            self.speaker.stop()
            self.listen_button.configure(text="🔊 Nghe")
            self.avatar_state = "thinking" if self.busy else "idle"
            self.active_chat_id = self.chats.new()["id"]
            self.retry_button.pack_forget()
            self._refresh_chat_list()
            self._render_chat()
            self._save_settings()
            self.input.focus_set()
        except (OSError, ValueError) as exc:
            messagebox.showerror("Không tạo được cuộc trò chuyện", str(exc))

    def _rename_chat(self):
        item = self.chats.get(self.active_chat_id)
        title = simpledialog.askstring("Đổi tên", "Tên cuộc trò chuyện:", initialvalue=item["title"], parent=self)
        if title is not None:
            try:
                self.chats.rename(self.active_chat_id, title)
                self._refresh_chat_list()
                self._render_chat()
            except (OSError, ValueError) as exc:
                messagebox.showerror("Không đổi được tên", str(exc))

    def _delete_chat(self):
        if self.busy:
            messagebox.showinfo("Đang trả lời", "Hãy đợi Mira trả lời xong trước khi xóa cuộc trò chuyện.")
            return
        if not messagebox.askyesno("Xóa cuộc trò chuyện", "Xóa cuộc trò chuyện này khỏi máy?", parent=self):
            return
        try:
            self.chats.delete(self.active_chat_id)
            self.active_chat_id = (self.chats.items[0] if self.chats.items else self.chats.new())["id"]
            self._refresh_chat_list()
            self._render_chat()
            self._save_settings()
        except (OSError, ValueError) as exc:
            messagebox.showerror("Không xóa được", str(exc))

    def _export_chat(self):
        item = self.chats.get(self.active_chat_id)
        filename = filedialog.asksaveasfilename(title="Xuất cuộc trò chuyện", defaultextension=".txt",
                                                filetypes=[("Văn bản UTF-8", "*.txt")], initialfile="mira-chat.txt")
        if filename:
            try:
                content = "\n\n".join(("Bạn" if m["role"] == "user" else self.name_var.get())
                                       + ":\n" + m["content"] for m in item["messages"])
                Path(filename).write_text(content + "\n", encoding="utf-8")
                self.status_var.set("Đã xuất cuộc trò chuyện.")
            except OSError as exc:
                messagebox.showerror("Không xuất được", str(exc))

    def _choose_folder(self):
        if self.busy:
            messagebox.showinfo("Đang trả lời", "Hãy đợi Mira trả lời xong trước khi đổi thư mục.")
            return
        folder = filedialog.askdirectory(title="Chọn thư mục Mira được phép đọc và đề xuất sửa")
        if folder:
            try:
                self.workspace = Workspace(Path(folder), self.path / "backups")
                self.folder_var.set(str(self.workspace.root))
                self._save_settings()
            except (WorkspaceError, OSError) as exc:
                messagebox.showerror("Thư mục không hợp lệ", str(exc))

    def _attach_file(self):
        if not self.workspace:
            messagebox.showinfo("Chọn thư mục", "Hãy chọn thư mục làm việc trước khi chọn file.")
            return
        filename = filedialog.askopenfilename(title="Chọn file trong thư mục đã cho phép",
                                              initialdir=str(self.workspace.root))
        if not filename:
            return
        try:
            relative = Path(filename).resolve().relative_to(self.workspace.root).as_posix()
            self.workspace._path(relative)
        except (ValueError, WorkspaceError):
            messagebox.showerror("Ngoài phạm vi", "File phải thuộc thư mục đã chọn và không phải symlink.")
            return
        previous = self.input.get("1.0", "end").strip()
        self.input.delete("1.0", "end")
        self.input.insert("1.0", (previous + "\n" if previous else "") +
                          "Hãy đọc file " + relative + " và giúp tôi: ")
        self.input.focus_set()

    def _run_tests(self):
        if self.busy or not self.workspace:
            messagebox.showinfo("Chọn thư mục", "Hãy chọn thư mục dự án trước.")
            return
        root = self.workspace.root
        if (root / "tests").is_dir():
            args = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]
            display = "python -m unittest discover -s tests -v"
        elif (root / "package.json").is_file() and shutil.which("npm"):
            args, display = ["npm", "test"], "npm test"
        else:
            messagebox.showinfo("Chưa có bộ kiểm thử", "Cần thư mục tests (Python) hoặc package.json (npm).")
            return
        if not messagebox.askyesno("Chạy kiểm thử trong dự án",
                                   "Lệnh: " + display + "\nThư mục: " + str(root) +
                                   "\n\nKiểm thử sẽ chạy code trong dự án. Bạn đồng ý chạy?"):
            return
        self.status_var.set("Đang chạy kiểm thử…")

        def run():
            try:
                result = subprocess.run(args, cwd=root, capture_output=True, text=True,
                                        encoding="utf-8", errors="replace", timeout=120, shell=False)
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

    def _show_memories(self):
        dialog = tk.Toplevel(self)
        dialog.title("Bộ nhớ của Mira")
        dialog.geometry("640x420")
        dialog.minsize(460, 320)
        dialog.configure(bg=BG)
        dialog.transient(self)
        tk.Label(dialog, text="Những điều bạn dạy Mira", bg=BG, fg=TEXT,
                 font=("Segoe UI", 16, "bold")).pack(anchor="w", padx=18, pady=(18, 4))
        tk.Label(dialog, text="Mira dùng các ghi nhớ này khi chat. Bạn có thể thêm hoặc quên từng mục.",
                 bg=BG, fg=MUTED).pack(anchor="w", padx=18)
        box = tk.Listbox(dialog, font=("Segoe UI", 11), bg=PANEL, fg=TEXT,
                         selectbackground="#325976", relief="flat", activestyle="none")
        box.pack(fill="both", expand=True, padx=18, pady=13)
        ids: list[str] = []

        def reload():
            box.delete(0, "end")
            ids.clear()
            for item in self.memories.items:
                box.insert("end", item["text"])
                ids.append(item["id"])

        def teach():
            value = simpledialog.askstring("Dạy Mira", "Điều bạn muốn mình nhớ cho các lần sau:", parent=dialog)
            if value is not None:
                try:
                    self.memories.add(value)
                    reload()
                    self.status_var.set("Mira đã ghi nhớ điều bạn dạy.")
                except (OSError, ValueError) as exc:
                    messagebox.showerror("Không ghi nhớ được", str(exc), parent=dialog)

        def forget():
            selected = box.curselection()
            if selected:
                try:
                    self.memories.forget(ids[selected[0]])
                    reload()
                except (OSError, ValueError) as exc:
                    messagebox.showerror("Không quên được", str(exc), parent=dialog)

        def edit():
            selected = box.curselection()
            if selected:
                value = simpledialog.askstring("Sửa ghi nhớ", "Sửa điều Mira cần nhớ:",
                                               initialvalue=self.memories.items[selected[0]]["text"], parent=dialog)
                if value is not None:
                    try:
                        self.memories.edit(ids[selected[0]], value)
                        reload()
                    except (OSError, ValueError) as exc:
                        messagebox.showerror("Không sửa được", str(exc), parent=dialog)

        controls = tk.Frame(dialog, bg=BG)
        controls.pack(fill="x", padx=18, pady=(0, 16))
        self._button(controls, "+ Dạy Mira", teach, primary=True).pack(side="left")
        self._button(controls, "Sửa mục", edit).pack(side="left", padx=(8, 0))
        self._button(controls, "Quên mục đã chọn", forget).pack(side="left", padx=8)
        self._button(controls, "Bộ sở thích", lambda: open_preference_dialog(self, self.preferences,
                     self._button)).pack(side="right")
        reload()

    def _model_lab_dialog(self):
        dialog = tk.Toplevel(self)
        dialog.title("Mô hình mạnh & tốc độ")
        dialog.geometry("660x450")
        dialog.configure(bg=BG)
        dialog.transient(self)
        tk.Label(dialog, text="Chọn sức mạnh theo đúng máy bạn", bg=BG, fg=TEXT,
                 font=("Segoe UI", 16, "bold")).pack(anchor="w", padx=20, pady=(17, 8))
        description = ("qwen3.5:9b (tải ~6,6 GB): giỏi hơn cho trò chuyện, code và ảnh, "
                       "nhưng có thể chậm nếu máy thiếu RAM/VRAM. qwen3.5:4b (tải ~3,4 GB) "
                       "nhẹ hơn. Các mô hình chạy cục bộ và không cần API trả phí.")
        tk.Label(dialog, text=description, bg=BG, fg=MUTED, wraplength=600,
                 justify="left").pack(anchor="w", padx=20)
        current = tk.StringVar(value="Mô hình đang chọn: " + self.model_var.get())
        tk.Label(dialog, textvariable=current, bg=BG, fg=ACCENT,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=20, pady=(12, 4))
        result = tk.Text(dialog, height=7, state="disabled", wrap="word", bg=PANEL,
                         fg=TEXT, relief="flat", padx=10, pady=8, font=("Segoe UI", 10))
        result.pack(fill="both", expand=True, padx=20, pady=(4, 8))

        def show(line):
            if not self.closed and dialog.winfo_exists():
                result.configure(state="normal")
                result.insert("end", line + "\n")
                result.see("end")
                result.configure(state="disabled")

        def set_model(model_name):
            if model_name not in self.available_models:
                show("Chưa có " + model_name + ". Hãy tải trước rồi bấm Kiểm tra lại.")
                return
            self.model_var.set(model_name)
            try:
                self._save_settings()
            except OSError as exc:
                show("Không lưu được mô hình: " + str(exc))
                return
            current.set("Mô hình đang chọn: " + model_name)
            self._check_ollama()
            show("Đã chọn " + model_name + " cho những tin nhắn tiếp theo.")

        def download(model_name):
            if getattr(self, "model_downloading", False):
                show("Mô hình vẫn đang tải. Hãy chờ hoàn tất.")
                return
            if not shutil.which("ollama"):
                show("Không tìm thấy lệnh ollama. Mở PowerShell và chạy: ollama pull " + model_name)
                return
            self.model_downloading = True
            size = "~6,6 GB" if model_name == "qwen3.5:9b" else "~3,4 GB"
            show(f"Đang tải {model_name} ({size}); quá trình có thể mất nhiều phút.")

            def run():
                try:
                    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                    process = subprocess.Popen(["ollama", "pull", model_name],
                                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                               text=True, encoding="utf-8", errors="replace",
                                               creationflags=flags)
                    self.model_download_proc = process
                    output, _ = process.communicate()
                    error = None if process.returncode == 0 else (output or "Ollama tải thất bại.")[-350:]
                except OSError as exc:
                    error = str(exc)
                finally:
                    self.model_download_proc = None

                def done():
                    self.model_downloading = False
                    if self.closed or not dialog.winfo_exists():
                        return
                    if error:
                        show("Không tải được: " + error)
                    else:
                        show("Đã tải xong. Đang cập nhật danh sách mô hình…")
                        self._check_ollama(lambda models: set_model(model_name)
                                           if model_name in models and dialog.winfo_exists() else None)

                try:
                    self.after(0, done)
                except RuntimeError:
                    pass

            threading.Thread(target=run, daemon=True).start()

        def compare():
            if getattr(self, "model_downloading", False):
                show("Hãy đợi tải mô hình xong rồi đo để tránh ảnh hưởng kết quả.")
                return
            if getattr(self, "model_benchmarking", False):
                show("Phép đo trước vẫn đang chạy.")
                return
            self.model_benchmarking = True
            show("Đang đo; mỗi mô hình sẽ tạo một câu trả lời ngắn trên máy bạn…")

            def run():
                try:
                    installed = self.agent.client.list_models()
                    candidates = [m for m in ("qwen3:4b", "qwen3.5:4b", "qwen3.5:9b", self.model_var.get())
                                  if m in installed and not is_cloud_model(m)]
                    candidates = list(dict.fromkeys(candidates))
                    if not candidates:
                        raise RuntimeError("Chưa cài mô hình nào. Hãy tải một mô hình trước.")
                    for name in candidates:
                        metric = self.agent.client.benchmark(name)
                        line = (f"{name}: {metric['tokens_per_second']:.1f} token/giây; "
                                f"tải {metric['load_seconds']:.1f}s; tổng {metric['total_seconds']:.1f}s")
                        self.after(0, show, line)
                    self.after(0, show, "Tốc độ này đo một câu ngắn; câu dài và sửa file sẽ khác.")
                except (RuntimeError, OSError, ValueError) as exc:
                    try:
                        self.after(0, show, "Không đo được: " + str(exc))
                    except RuntimeError:
                        pass
                finally:
                    self.model_benchmarking = False

            threading.Thread(target=run, daemon=True).start()

        buttons = tk.Frame(dialog, bg=BG)
        buttons.pack(fill="x", padx=20, pady=(0, 8))
        self._button(buttons, "Tải 9B", lambda: download("qwen3.5:9b"), primary=True).pack(side="left")
        self._button(buttons, "Tải 4B", lambda: download("qwen3.5:4b")).pack(side="left", padx=5)
        self._button(buttons, "Chọn 9B", lambda: set_model("qwen3.5:9b")).pack(side="left")
        self._button(buttons, "Đo tốc độ", compare).pack(side="left", padx=5)
        tk.Checkbutton(dialog, text="Suy luận sâu khi hỏi việc khó (câu trả lời có thể chậm hơn)",
                       variable=self.deep_var, command=self._set_deep_thinking, bg=BG, fg=TEXT,
                       selectcolor=PANEL, activebackground=BG, activeforeground=TEXT).pack(
                           anchor="w", padx=20, pady=(0, 12))
        self._check_ollama()

    def _confirm_cloud(self, model: str, *, parent=None) -> bool:
        if not is_cloud_model(model) or self.cloud_consent:
            return True
        accepted = messagebox.askyesno(
            "Cho phép gửi dữ liệu đến Ollama Cloud?",
            "Mô hình cloud chạy trên máy chủ, cần Internet. Mira có thể gửi câu hỏi, "
            "lịch sử chat gần đây, bộ nhớ và sở thích liên quan, ảnh bạn đính kèm, "
            "cùng nội dung file mà Mira được phép đọc qua Ollama Cloud.\n\n"
            "Gói Free có hạn mức. Nếu tài khoản Ollama đã nạp credit, dịch vụ có thể "
            "trừ credit khi hết lượt miễn phí; Mira không thể khóa việc này.\n\n"
            "Bạn đồng ý dùng mô hình cloud cho các tin nhắn tiếp theo? "
            "Có thể thu hồi trong mục AI cloud cho máy yếu.",
            parent=parent or self,
        )
        if accepted:
            self.cloud_consent = True
        return accepted

    def _cloud_dialog(self):
        dialog = tk.Toplevel(self)
        dialog.title("AI cloud cho máy yếu")
        dialog.geometry("680x570")
        dialog.configure(bg=BG)
        dialog.transient(self)
        tk.Label(dialog, text="Mira trên máy yếu", bg=BG, fg=TEXT,
                 font=("Segoe UI", 17, "bold")).pack(anchor="w", padx=20, pady=(18, 8))
        intro = ("Mira và Ollama vẫn mở trên máy; mô hình cloud xử lý trên máy chủ. "
                 "Bạn cần mạng và tài khoản Ollama, nhưng không cần GPU mạnh hay tải "
                 "trọng số mô hình nhiều GB.")
        tk.Label(dialog, text=intro, bg=BG, fg=MUTED, wraplength=630,
                 justify="left").pack(anchor="w", padx=20)
        steps = ("1. Mở Ollama; trong PowerShell chạy: ollama signin\n"
                 "2. Xem mô hình được dùng trong gói Free của tài khoản Ollama, rồi chạy:\n"
                 "    ollama pull <tên-mô-hình-cloud>\n"
                 "3. Bấm Kiểm tra lại và chọn mô hình xuất hiện bên dưới.")
        tk.Label(dialog, text=steps, bg=BG, fg=TEXT, wraplength=630,
                 justify="left").pack(anchor="w", padx=20, pady=(14, 6))
        tk.Label(dialog, text="Lệnh pull cho cloud chỉ đăng ký mô hình, không tải trọng số lớn. "
                 "Chọn mô hình hỗ trợ công cụ nếu muốn Mira làm việc với file/code.",
                 bg=BG, fg=MUTED, wraplength=630, justify="left").pack(anchor="w", padx=20)
        tk.Label(dialog, text="Mô hình cloud Ollama đã đăng ký", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=20, pady=(15, 4))
        cloud_models = [m for m in self.available_models if is_cloud_model(m)]
        chosen = ttk.Combobox(dialog, values=cloud_models, state="readonly", font=("Segoe UI", 11))
        if is_cloud_model(self.model_var.get()) and self.model_var.get() in cloud_models:
            chosen.set(self.model_var.get())
        elif cloud_models:
            chosen.set(cloud_models[0])
        chosen.pack(fill="x", padx=20)
        current = tk.StringVar(value="Đang dùng: " + self.model_var.get())
        tk.Label(dialog, textvariable=current, bg=BG, fg=ACCENT,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=20, pady=(12, 3))
        note = tk.StringVar(value="Không thấy mô hình? Đăng nhập, chạy ollama pull rồi bấm Kiểm tra lại.")
        tk.Label(dialog, textvariable=note, bg=BG, fg=MUTED, wraplength=630,
                 justify="left").pack(anchor="w", padx=20)

        def refreshed(models):
            if not dialog.winfo_exists():
                return
            choices = [m for m in models if is_cloud_model(m)]
            chosen.configure(values=choices)
            if chosen.get() not in choices:
                chosen.set(choices[0] if choices else "")
            note.set(f"Đã tìm thấy {len(choices)} mô hình cloud."
                     if choices else "Chưa thấy mô hình cloud. Hãy đăng nhập và chạy ollama pull.")

        def use_cloud():
            model = chosen.get()
            if not model or model not in self.available_models:
                note.set("Hãy đăng ký mô hình cloud, sau đó bấm Kiểm tra lại.")
                return
            if not self._confirm_cloud(model, parent=dialog):
                note.set("Chưa bật cloud; tin nhắn vẫn ở trên máy.")
                return
            previous = self.model_var.get()
            self.model_var.set(model)
            try:
                self._save_settings()
            except OSError as exc:
                self.model_var.set(previous)
                messagebox.showerror("Không lưu được", str(exc), parent=dialog)
                return
            current.set("Đang dùng: " + model)
            note.set("Đã bật cloud cho tin nhắn tiếp theo. Hạn mức Free do Ollama quy định.")
            self._check_ollama()

        def use_local():
            local = [m for m in self.available_models if not is_cloud_model(m)]
            model = self.last_local_model if self.last_local_model in local else (local[0] if local else "")
            if not model:
                note.set("Chưa có mô hình trên máy. Hãy tải mô hình nhỏ bằng ollama pull qwen3:1.7b.")
                return
            previous = self.model_var.get()
            self.model_var.set(model)
            try:
                self._save_settings()
            except OSError as exc:
                self.model_var.set(previous)
                messagebox.showerror("Không lưu được", str(exc), parent=dialog)
                return
            current.set("Đang dùng: " + model)
            note.set("Đã trở về mô hình trên máy.")
            self._check_ollama()

        def revoke():
            previous = self.cloud_consent
            self.cloud_consent = False
            try:
                self._save_settings()
            except OSError as exc:
                self.cloud_consent = previous
                messagebox.showerror("Không lưu được", str(exc), parent=dialog)
                return
            note.set("Đã thu hồi đồng ý. Mira sẽ hỏi lại trước khi gửi tin nhắn lên cloud.")
            self._check_ollama()

        buttons = tk.Frame(dialog, bg=BG)
        buttons.pack(fill="x", padx=20, pady=(15, 8))
        self._button(buttons, "Dùng cloud", use_cloud, primary=True).pack(side="left")
        self._button(buttons, "Kiểm tra lại", lambda: self._check_ollama(refreshed)).pack(side="left", padx=6)
        self._button(buttons, "Về AI trên máy", use_local).pack(side="left")
        self._button(dialog, "Thu hồi đồng ý gửi lên cloud", revoke).pack(anchor="w", padx=20)
        tk.Label(dialog, text="Free có hạn mức và có thể hết lượt; nếu tài khoản đã mua credit, "
                 "hãy kiểm tra cách Ollama sử dụng credit. Mira không tự nạp tiền.",
                 bg=BG, fg="#ffc59f", wraplength=630, justify="left").pack(
                     anchor="w", padx=20, pady=(10, 2))
        links = tk.Frame(dialog, bg=BG)
        links.pack(fill="x", padx=20)
        self._button(links, "Xem mô hình cloud", lambda: webbrowser.open(
            "https://ollama.com/search?c=cloud")).pack(side="left")
        self._button(links, "Xem giá & hạn mức", lambda: webbrowser.open(
            "https://ollama.com/pricing")).pack(side="left", padx=6)
        self._check_ollama(refreshed)

    def _set_deep_thinking(self):
        try:
            self._save_settings()
            self.status_var.set("Đã bật suy luận sâu; phản hồi có thể chậm hơn." if self.deep_var.get()
                                else "Đã tắt suy luận sâu để ưu tiên phản hồi nhanh.")
        except OSError as exc:
            messagebox.showerror("Không lưu được cài đặt", str(exc))

    def _listen_last(self):
        if self.busy:
            self.status_var.set("Hãy đợi Mira trả lời xong rồi bấm Nghe.")
            return
        if self.avatar_state == "speaking":
            self.speaker.stop()
            self.listen_button.configure(text="🔊 Nghe")
            self.avatar_state = "idle"
            self.status_var.set("Đã dừng giọng đọc.")
            return
        messages = self.chats.get(self.active_chat_id)["messages"]
        answer = next((item["content"] for item in reversed(messages)
                       if item["role"] == "assistant"), "")
        if not answer:
            self.status_var.set("Hãy đợi Mira trả lời rồi bấm Nghe.")
        else:
            self._speak(answer)

    def _speak(self, text):
        try:
            self.avatar_state = "speaking"
            self.status_var.set("Mira đang đọc bằng giọng Windows đã cài…")
            self.speaker.speak(text, lambda error: self.after(0, self._voice_done, error))
            self.listen_button.configure(text="■ Dừng đọc")
        except (OSError, RuntimeError, ValueError) as exc:
            self.avatar_state = "idle"
            self.listen_button.configure(text="🔊 Nghe")
            self.status_var.set(str(exc))

    def _voice_done(self, error):
        if not self.closed:
            self.avatar_state = "thinking" if self.busy else "idle"
            self.listen_button.configure(text="🔊 Nghe")
            if error:
                self.status_var.set(error)

    def _settings_dialog(self):
        dialog = tk.Toplevel(self)
        dialog.title("Mô hình & cài đặt")
        dialog.geometry("600x640")
        dialog.configure(bg=BG)
        dialog.transient(self)
        tk.Label(dialog, text="Thiết lập Mira", bg=BG, fg=TEXT,
                 font=("Segoe UI", 17, "bold")).pack(anchor="w", padx=20, pady=(20, 12))
        tk.Label(dialog, text="Tên gọi", bg=BG, fg=MUTED).pack(anchor="w", padx=20)
        name = tk.Entry(dialog, font=("Segoe UI", 12), bg="#f7fbff", fg=INK)
        name.insert(0, self.name_var.get())
        name.pack(fill="x", padx=20, pady=(3, 12))
        tk.Label(dialog, text="Mô hình Ollama (trên máy hoặc cloud đã đăng ký)",
                 bg=BG, fg=MUTED).pack(anchor="w", padx=20)
        model = ttk.Combobox(dialog, values=self.available_models, font=("Segoe UI", 12))
        model.set(self.model_var.get())
        model.pack(fill="x", padx=20, pady=(3, 8))
        tk.Label(dialog, text="Mặc định: qwen3:4b. Nhấn Kiểm tra lại để xem các mô hình đã cài.",
                 bg=BG, fg=MUTED).pack(anchor="w", padx=20)
        tk.Checkbutton(dialog, text="Ưu tiên tốc độ (ngữ cảnh gọn, trả lời hiện dần)",
                       variable=self.fast_var, bg=BG, fg=TEXT, selectcolor=PANEL,
                       activebackground=BG, activeforeground=TEXT).pack(anchor="w", padx=20, pady=(12, 0))
        tk.Label(dialog, text="Muốn nhanh hơn nữa: chạy ollama pull qwen3:1.7b rồi chọn mô hình đó.",
                 bg=BG, fg=MUTED, wraplength=510, justify="left").pack(anchor="w", padx=20)
        dialog_voice = tk.BooleanVar(value=self.voice_auto_var.get())
        tk.Checkbutton(dialog, text="Tự đọc câu trả lời bằng giọng Windows (miễn phí, xử lý trên máy)",
                       variable=dialog_voice, bg=BG, fg=TEXT, selectcolor=PANEL,
                       activebackground=BG, activeforeground=TEXT).pack(anchor="w", padx=20, pady=(7, 0))
        tk.Label(dialog, text="Tính cách Mira", bg=BG, fg=TEXT,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=20, pady=(14, 3))
        dialog_playful = tk.BooleanVar(value=self.playful_var.get())
        tk.Checkbutton(dialog, text="Hoạt bát: tò mò, ứng biến và đùa đúng lúc",
                       variable=dialog_playful, bg=BG, fg=TEXT, selectcolor=PANEL,
                       activebackground=BG, activeforeground=TEXT).pack(anchor="w", padx=20)
        tk.Label(dialog, text="Mira vẫn ưu tiên trả lời chính xác khi làm việc hoặc khi bạn cần sự nghiêm túc.",
                 bg=BG, fg=MUTED, wraplength=530, justify="left").pack(anchor="w", padx=20)
        tk.Label(dialog, text="Thêm nét tính cách bạn thích (tùy chọn)",
                 bg=BG, fg=MUTED).pack(anchor="w", padx=20, pady=(10, 2))
        persona_note = tk.Text(dialog, height=3, wrap="word", font=("Segoe UI", 10),
                               bg="#f7fbff", fg=INK, padx=7, pady=5)
        persona_note.insert("1.0", self.persona_note)
        persona_note.pack(fill="x", padx=20)

        def save():
            chosen_name = name.get().strip()
            chosen_model = model.get().strip()
            if not chosen_name or not chosen_model or any(c.isspace() for c in chosen_model):
                messagebox.showerror("Thiếu thông tin", "Hãy nhập tên và mô hình Ollama hợp lệ.", parent=dialog)
                return
            if not self._confirm_cloud(chosen_model, parent=dialog):
                return
            self.name_var.set(chosen_name[:40])
            self.model_var.set(chosen_model)
            self.playful_var.set(dialog_playful.get())
            self.voice_auto_var.set(dialog_voice.get())
            self.persona_note = persona_note.get("1.0", "end").strip()[:400]
            try:
                self._save_settings()
            except OSError as exc:
                messagebox.showerror("Không lưu được", str(exc), parent=dialog)
                return
            self._render_chat()
            self._check_ollama()
            dialog.destroy()

        controls = tk.Frame(dialog, bg=BG)
        controls.pack(fill="x", padx=20, pady=18)
        self._button(controls, "Lưu", save, primary=True).pack(side="right")
        self._button(controls, "Hướng dẫn cài", self._setup_guide).pack(side="left")
        self._button(controls, "Kiểm tra lại", lambda: self._check_ollama(
            lambda choices: model.configure(values=choices) if dialog.winfo_exists() else None)).pack(side="left", padx=7)
        self._button(controls, "AI cloud", self._cloud_dialog).pack(side="left")
        if self.workspace:
            self._button(dialog, "Bỏ quyền truy cập thư mục", self._clear_folder).pack(anchor="w", padx=20)

    def _clear_folder(self):
        if self.busy:
            messagebox.showinfo("Đang trả lời", "Hãy đợi Mira trả lời xong trước khi bỏ thư mục.")
            return
        self.workspace = None
        self.folder_var.set("Chưa chọn thư mục • Mira chỉ trò chuyện")
        self._save_settings()
        self.status_var.set("Đã bỏ quyền truy cập thư mục.")

    def _setup_guide(self):
        dialog = tk.Toplevel(self)
        dialog.title("Cài Ollama cho Mira")
        dialog.geometry("550x440")
        dialog.configure(bg=BG)
        dialog.transient(self)
        tk.Label(dialog, text="Bắt đầu trò chuyện với Mira", bg=BG, fg=TEXT,
                 font=("Segoe UI", 16, "bold")).pack(anchor="w", padx=20, pady=(20, 12))
        instructions = ("1. Cài Ollama cho Windows rồi mở Ollama.\n\n"
                        "2. Mở PowerShell và chạy:\n    ollama pull qwen3:4b\n"
                        "   Mô hình mạnh hơn: ollama pull qwen3.5:9b\n"
                        "   Máy yếu, ưu tiên tốc độ: ollama pull qwen3:1.7b\n"
                        "   Ảnh và công cụ: qwen3.5:9b hoặc qwen3-vl:4b\n\n"
                        "3. Quay lại Mira và bấm Kiểm tra lại.\n"
                        "   Ô NHẮN MIRA ở dưới cùng là nơi bắt đầu chat.")
        tk.Label(dialog, text=instructions, bg=BG, fg=TEXT, justify="left",
                 anchor="w", font=("Segoe UI", 11)).pack(fill="x", padx=20)
        self._button(dialog, "Mở trang tải Ollama", lambda: webbrowser.open("https://ollama.com/download/windows"),
                     primary=True).pack(anchor="w", padx=20, pady=14)
        self._button(dialog, "Máy yếu: dùng AI cloud miễn phí có hạn mức", self._cloud_dialog).pack(
            anchor="w", padx=20)

    def _check_ollama(self, on_done=None):
        self.health_var.set("Đang kiểm tra Ollama trên máy…")
        self.health_label.configure(fg=MUTED)

        def run():
            try:
                models = self.agent.client.list_models()
                error = None
            except RuntimeError as exc:
                models, error = [], str(exc)

            def update():
                if self.closed:
                    return
                self.available_models = models
                if on_done:
                    on_done(models)
                if error:
                    self.health_var.set("●  " + error)
                    self.health_label.configure(fg="#ffc59f")
                elif not models:
                    self.health_var.set("●  Chưa có mô hình • xem Cách cài hoặc AI cloud cho máy yếu.")
                    self.health_label.configure(fg="#ffc59f")
                elif self.model_var.get() not in models:
                    if is_cloud_model(self.model_var.get()):
                        self.health_var.set("●  Chưa có mô hình cloud • đăng nhập, đăng ký rồi Kiểm tra lại.")
                    else:
                        self.health_var.set(f"●  Chưa có {self.model_var.get()} • hãy tải hoặc chọn mô hình đã cài.")
                    self.health_label.configure(fg="#ffc59f")
                else:
                    if is_cloud_model(self.model_var.get()):
                        detail = "Free có hạn mức" if self.cloud_consent else "chờ bạn đồng ý trước khi gửi"
                        self.health_var.set(f"☁  Cloud • {self.model_var.get()} • {detail}")
                    else:
                        self.health_var.set(f"●  Ollama sẵn sàng • {self.model_var.get()}")
                    self.health_label.configure(fg=ACCENT)

            try:
                self.after(0, update)
            except RuntimeError:
                pass

        threading.Thread(target=run, daemon=True).start()

    def _fill_prompt(self, prompt: str):
        self.input.delete("1.0", "end")
        self.input.insert("1.0", prompt)
        self.input.focus_set()
        self.input.mark_set("insert", "end-1c")

    def _attach_image(self):
        if self.busy:
            return
        filename = filedialog.askopenfilename(title="Chọn ảnh màn hình để gửi cho Mira",
                                              filetypes=[("Ảnh PNG / JPEG", "*.png *.jpg *.jpeg")])
        if filename:
            try:
                path = Path(filename)
                if path.stat().st_size > 5 * 1024 * 1024:
                    raise ValueError("Ảnh lớn hơn 5 MiB. Hãy giảm dung lượng trước khi gửi.")
                data = path.read_bytes()
                if not (data.startswith(b"\x89PNG\r\n\x1a\n") or data.startswith(b"\xff\xd8\xff")):
                    raise ValueError("Chỉ hỗ trợ ảnh PNG hoặc JPEG hợp lệ.")
                self.attachment_data = data
                self.attachment_name = path.name
                self.attachment_var.set("Ảnh: " + (path.name if len(path.name) <= 35 else path.name[:32] + "…"))
                self.input.focus_set()
            except (OSError, ValueError) as exc:
                messagebox.showerror("Không đính kèm được ảnh", str(exc))

    def _clear_image(self):
        self.attachment_data = None
        self.attachment_name = None
        self.attachment_var.set("Chưa đính kèm ảnh")

    @staticmethod
    def _newline(event):
        event.widget.insert("insert", "\n")
        return "break"

    def _approve_edit(self, path: str, reason: str, diff: str) -> bool:
        done = threading.Event()
        self.pending_approval = done
        decision = [False]

        def show():
            if self.closed:
                done.set()
                return
            dialog = tk.Toplevel(self)
            dialog.title("Duyệt thay đổi • " + path)
            dialog.geometry("880x640")
            dialog.minsize(650, 420)
            dialog.transient(self)
            dialog.grab_set()
            tk.Label(dialog, text=f"File: {path}\nLý do: {reason}\nChỉ ghi nếu bạn chọn Duyệt. File cũ được sao lưu.",
                     justify="left", anchor="w", padx=16, pady=12, wraplength=820).pack(fill="x")
            area = tk.Frame(dialog)
            area.pack(fill="both", expand=True, padx=16)
            preview = tk.Text(area, wrap="none", font=("Consolas", 10))
            ybar = tk.Scrollbar(area, command=preview.yview)
            xbar = tk.Scrollbar(area, orient="horizontal", command=preview.xview)
            preview.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
            preview.tag_configure("added", background="#d9f2df")
            preview.tag_configure("removed", background="#ffe0db")
            for line in diff.splitlines(keepends=True):
                tag = "added" if line.startswith("+") else "removed" if line.startswith("-") else None
                preview.insert("end", line, tag)
            preview.configure(state="disabled")
            preview.grid(row=0, column=0, sticky="nsew")
            ybar.grid(row=0, column=1, sticky="ns")
            xbar.grid(row=1, column=0, sticky="ew")
            area.grid_columnconfigure(0, weight=1)
            area.grid_rowconfigure(0, weight=1)

            def finish(accepted=False):
                decision[0] = accepted
                done.set()
                dialog.destroy()

            controls = tk.Frame(dialog, pady=13)
            controls.pack()
            ttk.Button(controls, text="Từ chối", command=finish).pack(side="left", padx=8)
            ttk.Button(controls, text="Duyệt và ghi file", command=lambda: finish(True)).pack(side="left", padx=8)
            dialog.protocol("WM_DELETE_WINDOW", finish)
            dialog.focus_set()

        try:
            self.after(0, show)
        except RuntimeError:
            return False
        done.wait()
        self.pending_approval = None
        return decision[0] and not self.closed

    def _send(self, event=None):
        if not self.busy:
            self._submit(self.input.get("1.0", "end").strip())
        return "break"

    def _retry(self):
        if not self.busy and self.retry_text and self.retry_chat_id == self.active_chat_id:
            self._submit(self.retry_text, retry=True, image=self.retry_image,
                         image_name=self.retry_image_name)

    def _submit(self, text: str, *, retry=False, image=None, image_name=None):
        if not retry:
            image, image_name = self.attachment_data, self.attachment_name
        if not text and image is not None:
            text = "Hãy xem ảnh này và giúp tôi hiểu hoặc xử lý vấn đề."
        if not text:
            return
        display_text = text + (f"\n[Đính kèm ảnh: {image_name}]" if image_name else "")
        chat_id = self.active_chat_id
        name = self.name_var.get().strip()[:40] or "Mira"
        model = self.model_var.get().strip()
        if not self._confirm_cloud(model):
            self.status_var.set("Đã hủy gửi lên cloud; tin nhắn vẫn ở ô soạn thảo.")
            return
        try:
            self._save_settings()
            existing = list(self.chats.get(chat_id)["messages"])
            if retry and existing and existing[-1] == {"role": "user", "content": display_text}:
                history = existing[:-1]
            else:
                history = existing
                self.chats.append(chat_id, "user", display_text)
                self._add_message("Bạn", display_text, user=True)
                self.starters.grid_remove()
                self._refresh_chat_list()
                self.title_var.set(self.chats.get(chat_id)["title"])
        except (OSError, ValueError) as exc:
            messagebox.showerror("Không lưu được tin nhắn", str(exc))
            return
        self.input.delete("1.0", "end")
        self._clear_image()
        self.busy = True
        self.retry_text = None
        self.retry_chat_id = None
        self.retry_image = None
        self.retry_image_name = None
        self.retry_button.pack_forget()
        self.send_button.configure(state="disabled")
        self.speaker.stop()
        self.listen_button.configure(text="🔊 Nghe")
        self.avatar_state = "thinking"
        think = self.deep_var.get()
        self.status_var.set("Mira đang suy luận sâu…" if think else
                            "Mira đang trả lời… Nội dung sẽ xuất hiện dần.")
        workspace = self.workspace
        memories = ("Bộ sở thích:\n" + self.preferences.prompt_for(text) +
                    "\nGhi nhớ được chọn:\n" + (self.memories.prompt_for(text) or "(chưa có)"))
        fast = self.fast_var.get()
        persona = "playful" if self.playful_var.get() else "standard"
        persona_note = self.persona_note
        self.stream_chat_id = chat_id
        self.stream_text = ""
        chunks = queue.SimpleQueue()
        started = time.monotonic()
        self._show_pending(name)

        def drain():
            parts = []
            while True:
                try:
                    parts.append(chunks.get_nowait())
                except queue.Empty:
                    break
            if parts:
                self.stream_text += "".join(parts)
                self.avatar_state = "speaking"
                self.status_var.set("Mira đang tạo câu trả lời…")
                if self.active_chat_id == chat_id:
                    self._show_pending(name)

        def pump():
            if self.busy and self.stream_chat_id == chat_id:
                drain()
                self.after(90, pump)

        self.after(90, pump)

        def report(action):
            if not self.closed:
                try:
                    self.after(0, self.status_var.set, action)
                except RuntimeError:
                    pass

        def run():
            try:
                answer = self.agent.respond(text, history, model, name, memories, workspace,
                                            self._approve_edit, report, image=image,
                                            on_token=chunks.put, fast=fast, persona=persona,
                                            persona_note=persona_note, think=think)
                error = None
            except Exception as exc:
                answer, error = "", str(exc)

            def complete():
                drain()
                self._remove_pending()
                self.stream_chat_id = None
                self.stream_text = ""
                self.avatar_state = "idle"
                if error:
                    self.retry_text = text
                    self.retry_chat_id = chat_id
                    self.retry_image = image
                    self.retry_image_name = image_name
                    if self.active_chat_id == chat_id:
                        self.retry_button.pack(side="right")
                    self.status_var.set("Không gửi được • xem hướng dẫn hoặc bấm Thử gửi lại.")
                    if self.active_chat_id == chat_id:
                        self._add_message("Mira · lỗi", error)
                else:
                    try:
                        self.chats.append(chat_id, "assistant", answer)
                        self._refresh_chat_list()
                    except (OSError, ValueError) as exc:
                        messagebox.showerror("Không lưu được câu trả lời", str(exc))
                    if self.active_chat_id == chat_id:
                        self._add_message(name, answer)
                    self.status_var.set(f"Sẵn sàng • trả lời trong {time.monotonic() - started:.1f} giây")
                self.busy = False
                self.send_button.configure(state="normal")
                if not error and self.voice_auto_var.get() and self.active_chat_id == chat_id:
                    self._speak(answer)
                self.input.focus_set()

            try:
                self.after(0, complete)
            except RuntimeError:
                pass

        threading.Thread(target=run, daemon=True).start()


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
