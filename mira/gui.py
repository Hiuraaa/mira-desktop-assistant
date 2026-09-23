"""A small, dependency-free Tkinter interface for Windows and other desktops."""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from .agent import Agent
from .storage import ChatStore, MemoryStore, data_dir, load_json, save_json
from .workspace import Workspace, WorkspaceError


BG = "#121a2a"
PANEL = "#1c2940"
TEXT = "#f2f6ff"
ACCENT = "#9ed6c8"


class MiraApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Mira • trợ lý máy tính")
        self.geometry("950x720")
        self.minsize(720, 540)
        self.configure(bg=BG)
        self.path = data_dir()
        self.settings_path = self.path / "settings.json"
        settings = load_json(self.settings_path, {})
        self.memories = MemoryStore(self.path / "memories.json")
        self.chat = ChatStore(self.path / "conversation.json")
        self.agent = Agent()
        self.busy = False
        self.name_var = tk.StringVar(value=settings.get("name", "Mira"))
        self.model_var = tk.StringVar(value=settings.get("model", "qwen3:4b"))
        self.folder_var = tk.StringVar(value=settings.get("folder", "Chưa chọn thư mục"))
        self.status_var = tk.StringVar(value="Sẵn sàng • dữ liệu được giữ trên máy")
        self.workspace = None
        try:
            folder = settings.get("folder")
            if folder:
                self.workspace = Workspace(Path(folder), self.path / "backups")
        except (OSError, WorkspaceError):
            self.folder_var.set("Thư mục cũ không còn tồn tại • hãy chọn lại")

        self._build()
        for message in self.chat.messages:
            self._add_message("Bạn" if message["role"] == "user" else self.name_var.get(), message["content"])
        if not self.chat.messages:
            self._add_message("Mira", "Chào bạn! Hãy chọn thư mục nếu muốn mình xem hoặc sửa file. Bạn cũng có thể hỏi chuyện ngay.")

    def _button(self, parent, text, command):
        return tk.Button(parent, text=text, command=command, bg=PANEL, fg=TEXT,
                         activebackground="#34506b", activeforeground=TEXT,
                         relief="flat", padx=12, pady=7, font=("Segoe UI", 10))

    def _build(self):
        header = tk.Frame(self, bg=BG, padx=22, pady=15)
        header.pack(fill="x")
        tk.Label(header, text="Mira", bg=BG, fg=ACCENT, font=("Segoe UI", 25, "bold")).pack(side="left")
        tk.Label(header, text="  Trợ lý cá nhân • trò chuyện, file, code", bg=BG, fg=TEXT,
                 font=("Segoe UI", 11)).pack(side="left", pady=8)

        config = tk.Frame(self, bg=BG, padx=22)
        config.pack(fill="x")
        tk.Label(config, text="Tên trợ lý", bg=BG, fg=TEXT).pack(side="left")
        tk.Entry(config, width=12, textvariable=self.name_var).pack(side="left", padx=(7, 18))
        tk.Label(config, text="Mô hình Ollama", bg=BG, fg=TEXT).pack(side="left")
        tk.Entry(config, width=23, textvariable=self.model_var).pack(side="left", padx=7)
        self._button(config, "Dạy Mira", self._teach).pack(side="right", padx=(6, 0))
        self._button(config, "Xem / quên điều đã dạy", self._show_memories).pack(side="right")

        project = tk.Frame(self, bg=BG, padx=22, pady=12)
        project.pack(fill="x")
        self.folder_button = self._button(project, "Chọn thư mục", self._choose_folder)
        self.folder_button.pack(side="left")
        tk.Label(project, textvariable=self.folder_var, bg=BG, fg="#b9cbdb", anchor="w").pack(side="left", fill="x", expand=True, padx=12)
        self._button(project, "Chat mới", self._new_chat).pack(side="right")

        chat_frame = tk.Frame(self, bg=BG, padx=22)
        chat_frame.pack(fill="both", expand=True)
        self.output = tk.Text(chat_frame, wrap="word", state="disabled", bg=PANEL, fg=TEXT,
                              insertbackground=TEXT, relief="flat", padx=17, pady=16,
                              font=("Segoe UI", 11), spacing3=12)
        scroll = tk.Scrollbar(chat_frame, command=self.output.yview)
        self.output.configure(yscrollcommand=scroll.set)
        self.output.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.output.tag_configure("sender", foreground=ACCENT, font=("Segoe UI", 11, "bold"))

        bottom = tk.Frame(self, bg=BG, padx=22, pady=12)
        bottom.pack(fill="x")
        self.input = tk.Text(bottom, height=4, wrap="word", bg=PANEL, fg=TEXT,
                             insertbackground=TEXT, relief="flat", padx=12, pady=9, font=("Segoe UI", 11))
        self.input.pack(side="left", fill="x", expand=True)
        self.input.bind("<Control-Return>", self._send)
        self.send_button = self._button(bottom, "Gửi\nCtrl+Enter", self._send)
        self.send_button.pack(side="right", padx=(12, 0))
        tk.Label(self, textvariable=self.status_var, bg=BG, fg="#a7bbca", anchor="w",
                 padx=22, pady=5).pack(fill="x")
        self.input.focus_set()

    def _add_message(self, sender: str, content: str):
        self.output.configure(state="normal")
        self.output.insert("end", sender + "\n", "sender")
        self.output.insert("end", content + "\n\n")
        self.output.configure(state="disabled")
        self.output.see("end")

    def _save_settings(self):
        save_json(self.settings_path, {
            "name": self.name_var.get().strip()[:40] or "Mira",
            "model": self.model_var.get().strip(),
            "folder": str(self.workspace.root) if self.workspace else "",
        })

    def _choose_folder(self):
        if self.busy:
            return
        folder = filedialog.askdirectory(title="Chọn thư mục Mira được phép xem và sửa")
        if folder:
            try:
                self.workspace = Workspace(Path(folder), self.path / "backups")
                self.folder_var.set(str(self.workspace.root))
                self._save_settings()
            except (WorkspaceError, OSError) as exc:
                messagebox.showerror("Thư mục không hợp lệ", str(exc))

    def _teach(self):
        value = simpledialog.askstring("Dạy Mira", "Điều bạn muốn Mira nhớ cho các lần sau:", parent=self)
        if value is not None:
            try:
                self.memories.add(value)
                self.status_var.set("Đã ghi nhớ. Bạn có thể xem hoặc xóa điều đã dạy.")
            except ValueError as exc:
                messagebox.showerror("Không thể ghi nhớ", str(exc))

    def _show_memories(self):
        dialog = tk.Toplevel(self)
        dialog.title("Những điều Mira nhớ")
        dialog.geometry("600x380")
        dialog.transient(self)
        box = tk.Listbox(dialog, font=("Segoe UI", 11))
        box.pack(fill="both", expand=True, padx=14, pady=14)
        ids = [item["id"] for item in self.memories.items]
        for item in self.memories.items:
            box.insert("end", item["text"])

        def forget():
            selected = box.curselection()
            if selected:
                index = selected[0]
                self.memories.forget(ids.pop(index))
                box.delete(index)

        self._button(dialog, "Quên mục được chọn", forget).pack(pady=(0, 14))

    def _new_chat(self):
        if self.busy:
            return
        self.chat.clear()
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.configure(state="disabled")
        self._add_message(self.name_var.get().strip() or "Mira", "Bắt đầu cuộc trò chuyện mới nhé.")

    def _approve_edit(self, path: str, reason: str, diff: str) -> bool:
        done = threading.Event()
        decision = [False]

        def show():
            dialog = tk.Toplevel(self)
            dialog.title("Duyệt thay đổi • " + path)
            dialog.geometry("860x630")
            dialog.minsize(600, 400)
            dialog.transient(self)
            dialog.grab_set()
            tk.Label(dialog, text=f"File: {path}\nLý do: {reason}\nChỉ ghi nếu bạn chọn Duyệt. File cũ sẽ được sao lưu.",
                     justify="left", anchor="w", padx=16, pady=12, wraplength=780).pack(fill="x")
            area = tk.Frame(dialog)
            area.pack(fill="both", expand=True, padx=16)
            preview = tk.Text(area, wrap="none", font=("Consolas", 10))
            ybar = tk.Scrollbar(area, command=preview.yview)
            xbar = tk.Scrollbar(area, orient="horizontal", command=preview.xview)
            preview.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
            preview.insert("1.0", diff)
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
        if self.busy:
            return "break"
        text = self.input.get("1.0", "end").strip()
        if not text:
            return "break"
        name = self.name_var.get().strip()[:40] or "Mira"
        model = self.model_var.get().strip()
        try:
            self._save_settings()
            previous = list(self.chat.messages)
            self.chat.append("user", text)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Lỗi lưu dữ liệu", str(exc))
            return "break"
        self.input.delete("1.0", "end")
        self._add_message("Bạn", text)
        self.busy = True
        self.send_button.configure(state="disabled")
        self.status_var.set("Đang chờ mô hình trả lời…")
        workspace = self.workspace
        memories = self.memories.prompt()

        def run():
            try:
                answer = self.agent.respond(text, previous, model, name, memories, workspace,
                    self._approve_edit, lambda action: self.after(0, self.status_var.set, action))
            except Exception as exc:
                answer = f"Có lỗi: {exc}"

            def complete():
                try:
                    self.chat.append("assistant", answer)
                except (OSError, ValueError) as exc:
                    messagebox.showerror("Lỗi lưu trò chuyện", str(exc))
                self._add_message(name, answer)
                self.busy = False
                self.send_button.configure(state="normal")
                self.status_var.set("Sẵn sàng")

            self.after(0, complete)

        threading.Thread(target=run, daemon=True).start()
        return "break"


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
