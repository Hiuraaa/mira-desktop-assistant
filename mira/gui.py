"""Mira's desktop chat window. Tk is only touched from its main thread."""

from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from .agent import Agent
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
        self.chats = ConversationStore(self.path / "conversations.json", self.path / "conversation.json")
        self.agent = Agent()
        self.busy = False
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
            selected = settings.get("active_chat_id")
            ids = {item["id"] for item in self.chats.items}
            self.active_chat_id = selected if selected in ids else self.chats.items[0]["id"]

        self._build()
        self._refresh_chat_list()
        self._render_chat()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(200, self._check_ollama)

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
        self._button(sidebar, "↥  Xuất cuộc trò chuyện", self._export_chat, subtle=True).grid(
            row=8, column=0, sticky="ew", pady=(3, 0))

        main = tk.Frame(self, bg=BG, padx=23, pady=16)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(3, weight=1)
        head = tk.Frame(main, bg=BG)
        head.grid(row=0, column=0, sticky="ew")
        tk.Label(head, textvariable=self.title_var, bg=BG, fg=TEXT,
                 font=("Segoe UI", 19, "bold"), anchor="w").pack(fill="x")
        tk.Label(head, textvariable=self.folder_var, bg=BG, fg=MUTED,
                 font=("Segoe UI", 10), anchor="w", wraplength=570).pack(fill="x", pady=(2, 12))

        health = tk.Frame(main, bg=PANEL, padx=13, pady=7)
        health.grid(row=1, column=0, sticky="ew", pady=(0, 11))
        self.health_label = tk.Label(health, textvariable=self.health_var, bg=PANEL, fg=ACCENT,
                                     anchor="w", font=("Segoe UI", 10, "bold"))
        self.health_label.pack(side="left", fill="x", expand=True)
        self._button(health, "Kiểm tra lại", self._check_ollama).pack(side="right", padx=(8, 0))
        self._button(health, "Cách cài", self._setup_guide).pack(side="right")

        self.starters = tk.Frame(main, bg=BG)
        self.starters.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        for label, prompt in (
            ("Giải thích lỗi code", "Giúp tôi hiểu và sửa lỗi code này: "),
            ("Tìm trong dự án", "Tìm trong thư mục đã chọn nơi xử lý: "),
            ("Kiểm tra Python", "Kiểm tra cú pháp file Python này: "),
            ("Lên kế hoạch", "Giúp tôi chia việc này thành các bước cụ thể: "),
        ):
            self._button(self.starters, label, lambda p=prompt: self._fill_prompt(p)).pack(
                side="left", padx=(0, 8))

        conversation = tk.Frame(main, bg=PANEL)
        conversation.grid(row=3, column=0, sticky="nsew")
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
        composer.grid(row=4, column=0, sticky="ew")
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
        status.grid(row=5, column=0, sticky="ew")
        tk.Label(status, textvariable=self.status_var, bg=BG, fg=MUTED,
                 anchor="w", font=("Segoe UI", 9)).pack(side="left", fill="x", expand=True)
        self.retry_button = self._button(status, "Thử gửi lại", self._retry)
        self.input.focus_set()

    def _save_settings(self):
        save_json(self.settings_path, {
            "name": self.name_var.get().strip()[:40] or "Mira",
            "model": self.model_var.get().strip(),
            "folder": str(self.workspace.root) if self.workspace else "",
            "active_chat_id": self.active_chat_id,
        })

    def _close(self):
        try:
            self._save_settings()
        except OSError:
            pass
        self.destroy()

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

    def _add_message(self, sender: str, content: str, *, user=False):
        self.output.configure(state="normal")
        self.output.insert("end", sender + "\n", "you" if user else "mira")
        self.output.insert("end", content + "\n\n")
        self.output.configure(state="disabled")
        self.output.see("end")

    def _select_chat(self, event=None):
        selected = self.chat_list.curselection()
        if selected and selected[0] < len(self.chats.items):
            selected_id = self.chats.items[selected[0]]["id"]
            if selected_id != self.active_chat_id:
                self.active_chat_id = selected_id
                self._render_chat()
                if self.retry_text and self.retry_chat_id == selected_id:
                    self.retry_button.pack(side="right")
                else:
                    self.retry_button.pack_forget()
                self._save_settings()

    def _new_chat(self):
        try:
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
        reload()

    def _settings_dialog(self):
        dialog = tk.Toplevel(self)
        dialog.title("Mô hình & cài đặt")
        dialog.geometry("520x385")
        dialog.configure(bg=BG)
        dialog.transient(self)
        tk.Label(dialog, text="Thiết lập Mira", bg=BG, fg=TEXT,
                 font=("Segoe UI", 17, "bold")).pack(anchor="w", padx=20, pady=(20, 12))
        tk.Label(dialog, text="Tên gọi", bg=BG, fg=MUTED).pack(anchor="w", padx=20)
        name = tk.Entry(dialog, font=("Segoe UI", 12), bg="#f7fbff", fg=INK)
        name.insert(0, self.name_var.get())
        name.pack(fill="x", padx=20, pady=(3, 12))
        tk.Label(dialog, text="Mô hình Ollama (đã tải trên máy)", bg=BG, fg=MUTED).pack(anchor="w", padx=20)
        model = ttk.Combobox(dialog, values=self.available_models, font=("Segoe UI", 12))
        model.set(self.model_var.get())
        model.pack(fill="x", padx=20, pady=(3, 8))
        tk.Label(dialog, text="Mặc định: qwen3:4b. Nhấn Kiểm tra lại để xem các mô hình đã cài.",
                 bg=BG, fg=MUTED).pack(anchor="w", padx=20)

        def save():
            chosen_name = name.get().strip()
            chosen_model = model.get().strip()
            if not chosen_name or not chosen_model or any(c.isspace() for c in chosen_model):
                messagebox.showerror("Thiếu thông tin", "Hãy nhập tên và mô hình Ollama hợp lệ.", parent=dialog)
                return
            self.name_var.set(chosen_name[:40])
            self.model_var.set(chosen_model)
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
        dialog.geometry("550x370")
        dialog.configure(bg=BG)
        dialog.transient(self)
        tk.Label(dialog, text="Bắt đầu trò chuyện với Mira", bg=BG, fg=TEXT,
                 font=("Segoe UI", 16, "bold")).pack(anchor="w", padx=20, pady=(20, 12))
        instructions = ("1. Cài Ollama cho Windows rồi mở Ollama.\n\n"
                        "2. Mở PowerShell và chạy:\n    ollama pull qwen3:4b\n"
                        "   Để Mira xem ảnh, dùng: ollama pull qwen3-vl:4b\n\n"
                        "3. Quay lại Mira và bấm Kiểm tra lại.\n"
                        "   Ô NHẮN MIRA ở dưới cùng là nơi bắt đầu chat.")
        tk.Label(dialog, text=instructions, bg=BG, fg=TEXT, justify="left",
                 anchor="w", font=("Segoe UI", 11)).pack(fill="x", padx=20)
        self._button(dialog, "Mở trang tải Ollama", lambda: webbrowser.open("https://ollama.com/download/windows"),
                     primary=True).pack(anchor="w", padx=20, pady=14)

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
                self.available_models = models
                if on_done:
                    on_done(models)
                if error:
                    self.health_var.set("●  " + error)
                    self.health_label.configure(fg="#ffc59f")
                elif not models:
                    self.health_var.set("●  Ollama đang chạy • chưa có mô hình. Xem Cách cài.")
                    self.health_label.configure(fg="#ffc59f")
                elif self.model_var.get() not in models:
                    self.health_var.set(f"●  Chưa có {self.model_var.get()} • hãy tải hoặc chọn mô hình đã cài.")
                    self.health_label.configure(fg="#ffc59f")
                else:
                    self.health_var.set(f"●  Ollama sẵn sàng • {self.model_var.get()}")
                    self.health_label.configure(fg=ACCENT)

            self.after(0, update)

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
        decision = [False]

        def show():
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

        self.after(0, show)
        done.wait()
        return decision[0]

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
        self.status_var.set("Mira đang trả lời… Có thể mất thêm thời gian với mô hình chạy trên máy.")
        workspace = self.workspace
        memories = self.memories.prompt()

        def report(action):
            self.after(0, self.status_var.set, action)

        def run():
            try:
                answer = self.agent.respond(text, history, model, name, memories, workspace,
                                            self._approve_edit, report, image=image)
                error = None
            except Exception as exc:
                answer, error = "", str(exc)

            def complete():
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
                    self.status_var.set("Sẵn sàng • Enter để gửi, Shift+Enter để xuống dòng")
                self.busy = False
                self.send_button.configure(state="normal")
                self.input.focus_set()

            self.after(0, complete)

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
