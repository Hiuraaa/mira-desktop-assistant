"""Mira's desktop chat window. Tk is only touched from its main thread."""

from __future__ import annotations

import threading
import queue
import base64
import shutil
import struct
import subprocess
import sys
import time
import tkinter as tk
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from .agent import Agent, is_cloud_model
from .avatar import AnimeAvatar, STYLES
from .desktop import DesktopController, capture_primary_screen
from .device import device_status
from .lessons import LessonStore
from .mobile_server import PhoneServer
from .preferences import PreferenceStore
from .preferences_ui import open_preference_dialog
from .reminders import ReminderStore, draft_reminder
from .speech import SpeechPlayer
from .storage import ConversationStore, MemoryStore, data_dir, load_json, save_json
from .telegram_bot import TelegramBot
from .workspace import Workspace, WorkspaceError


BG = "#0b1220"
SIDE = "#111a2b"
PANEL = "#19263b"
SURFACE = "#24344d"
BORDER = "#31415b"
TEXT = "#f5f4ff"
MUTED = "#aeb9d0"
ACCENT = "#b5a0ff"
BLUE = "#8cdaeb"
INK = "#211c38"


class MiraApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Mira • trợ lý cá nhân")
        self.geometry("1280x820")
        self.minsize(880, 620)
        self.configure(bg=BG)
        theme = ttk.Style(self)
        theme.theme_use("clam")
        theme.configure("TCombobox", fieldbackground=PANEL, background=PANEL,
                        foreground=TEXT, arrowcolor=ACCENT, bordercolor=BORDER,
                        lightcolor=BORDER, darkcolor=BORDER, padding=5)
        theme.map("TCombobox", fieldbackground=[("readonly", PANEL)],
                  foreground=[("readonly", TEXT)])
        theme.configure("Vertical.TScrollbar", background=SURFACE, troughcolor=BG,
                        bordercolor=BG, arrowcolor=MUTED, lightcolor=SURFACE,
                        darkcolor=SURFACE, relief="flat")
        self.path = data_dir()
        self.settings_path = self.path / "settings.json"
        settings = load_json(self.settings_path, {})
        if not isinstance(settings, dict):
            raise ValueError("Cài đặt Mira không đúng định dạng.")
        self.memories = MemoryStore(self.path / "memories.json")
        self.lessons = LessonStore(self.path / "game_lessons.json")
        self.preferences = PreferenceStore(self.path / "preferences.json")
        self.chats = ConversationStore(self.path / "conversations.json", self.path / "conversation.json")
        self.reminders = ReminderStore(self.path / "reminders.json")
        self.agent = Agent()
        self.phone_server: PhoneServer | None = None
        self.telegram_bot: TelegramBot | None = None
        self.telegram_token: str | None = None
        self.telegram_credentials_path = self.path / "telegram_credentials.json"
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
        self.web_var = tk.BooleanVar(value=settings.get("web_enabled") is True)
        self.desktop = DesktopController()
        self.desktop_enabled = False
        self.device_enabled = False
        self.phone_screen_enabled = False
        self.phone_files_enabled = False
        self.desktop_hid_for_action = False
        self.stream_chat_id: str | None = None
        self.stream_text = ""
        self.avatar_state = "idle"
        self.avatar_tick = 0
        self.avatar_style = settings.get("avatar_style", "violet")
        if self.avatar_style not in STYLES:
            self.avatar_style = "violet"
        self.custom_avatar_path = self.path / "mira_character.png"
        self.avatar_custom = settings.get("avatar_custom") is True and self.custom_avatar_path.is_file()
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
        self.after(5_000, self._poll_reminders)
        saved_bot = load_json(self.telegram_credentials_path, {})
        if isinstance(saved_bot, dict) and saved_bot.get("enabled") and isinstance(saved_bot.get("token"), str):
            try:
                self._start_telegram(saved_bot["token"])
            except (OSError, ValueError):
                self.status_var.set("Telegram chưa kết nối được; mở mục Điện thoại để kiểm tra.")

    def _button(self, parent, label, command, *, primary=False, subtle=False,
                compact=False, background=None):
        normal = ACCENT if primary else (background or (SIDE if subtle else PANEL))
        hovered = "#cbbdff" if primary else ("#354865" if normal == SURFACE else SURFACE)
        button = tk.Button(parent, text=label, command=command, relief="flat", cursor="hand2",
                           bg=normal, fg=INK if primary else TEXT,
                           activebackground=hovered, activeforeground=INK if primary else TEXT,
                           font=("Segoe UI", 10, "bold"),
                           padx=10 if compact else 13, pady=6 if compact else 9,
                           borderwidth=0, takefocus=True)
        button.bind("<Enter>", lambda _: button.configure(bg=hovered)
                    if button.cget("state") == "normal" else None)
        button.bind("<Leave>", lambda _: button.configure(bg=normal))
        return button

    def _build(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        sidebar = tk.Frame(self, bg=SIDE, width=248, padx=14, pady=19)
        sidebar.grid(row=0, column=0, sticky="ns")
        sidebar.grid_propagate(False)
        sidebar.grid_columnconfigure(0, weight=1)
        sidebar.grid_rowconfigure(5, weight=1)
        brand = tk.Frame(sidebar, bg=SIDE)
        brand.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        tk.Label(brand, text="✦", bg=SIDE, fg=ACCENT,
                 font=("Segoe UI", 25, "bold")).pack(side="left", padx=(0, 9))
        tk.Label(brand, text="Mira", bg=SIDE, fg=TEXT,
                 font=("Segoe UI", 24, "bold")).pack(side="left")
        tk.Label(sidebar, text="TRỢ LÝ CÁ NHÂN", bg=SIDE, fg=MUTED,
                 font=("Segoe UI", 9, "bold"), anchor="w").grid(
                     row=1, column=0, sticky="ew", pady=(0, 23))
        self._button(sidebar, "＋  Cuộc trò chuyện mới", self._new_chat, primary=True).grid(
            row=2, column=0, sticky="ew", pady=(0, 11))
        self._button(sidebar, "☁  Điện thoại khi máy tắt",
                     self._cloud_phone_dialog, primary=True).grid(row=3, column=0,
                                                                  sticky="ew", pady=(0, 9))
        self.phone_button = self._button(sidebar, "◈  Kết nối khi máy bật",
                                         self._mobile_dialog, background=SURFACE)
        self.phone_button.grid(row=4, column=0, sticky="ew", pady=(0, 16))
        archive = tk.Frame(sidebar, bg=SIDE)
        archive.grid(row=5, column=0, sticky="nsew")
        archive.grid_columnconfigure(0, weight=1)
        archive.grid_rowconfigure(1, weight=1)
        tk.Label(archive, text="GẦN ĐÂY", bg=SIDE, fg=MUTED,
                 font=("Segoe UI", 9, "bold"), anchor="w").grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.chat_list = tk.Listbox(archive, selectmode="browse", activestyle="none", relief="flat",
                                    bg=SIDE, fg=TEXT, selectbackground="#37335f", selectforeground=TEXT,
                                    font=("Segoe UI", 10), highlightthickness=0, borderwidth=0)
        self.chat_list.grid(row=1, column=0, sticky="nsew")
        self.chat_list.bind("<<ListboxSelect>>", self._select_chat)
        actions = tk.Frame(sidebar, bg=SIDE)
        actions.grid(row=6, column=0, sticky="ew", pady=(8, 8))
        self._button(actions, "Đổi tên", self._rename_chat, subtle=True).pack(side="left", fill="x", expand=True)
        self._button(actions, "Xóa", self._delete_chat, subtle=True).pack(side="left", fill="x", expand=True)
        tools = tk.Frame(sidebar, bg=SIDE)
        tools.grid(row=7, column=0, sticky="ew", pady=(7, 0))
        tools.grid_columnconfigure(0, weight=1)
        tk.Label(tools, text="CÔNG CỤ", bg=SIDE, fg=MUTED,
                 font=("Segoe UI", 9, "bold"), anchor="w").grid(
                     row=0, column=0, sticky="ew", pady=(0, 6))
        shortcuts = (
            ("▤  Chọn thư mục", self._choose_folder),
            ("✦  Dạy Mira / bộ nhớ", self._show_memories),
            ("⚙  Mô hình & cài đặt", self._settings_dialog),
            ("↗  Mô hình mạnh & tốc độ", self._model_lab_dialog),
            ("☁  AI cloud cho máy yếu", self._cloud_dialog),
            ("↻  Kiểm tra kết nối AI", self._check_ollama),
            ("🌐  Bật / tắt tra cứu web", lambda: self._toggle_web(not self.web_var.get())),
            ("🖱  Bật / tắt điều khiển máy", self._toggle_desktop),
            ("◉  Bật / tắt xem trạng thái PC", self._toggle_device),
            ("▣  Chụp màn hình để hỏi Mira", self._attach_screen),
            ("✦  Nhân vật Mira", self._avatar_dialog),
            ("☁  Mira trên điện thoại khi máy tắt", self._cloud_phone_dialog),
            ("?  Hướng dẫn cài AI", self._setup_guide),
            ("↑  Xuất cuộc trò chuyện", self._export_chat),
        )
        menu = tk.Menu(self, tearoff=False, bg=PANEL, fg=TEXT,
                       activebackground=SURFACE, activeforeground=TEXT,
                       font=("Segoe UI", 10), borderwidth=1)
        for label, command in shortcuts:
            menu.add_command(label=label, command=command)

        def show_tools():
            try:
                menu.tk_popup(open_tools.winfo_rootx() + 6,
                              open_tools.winfo_rooty() - 8 * 34)
            finally:
                menu.grab_release()

        open_tools = self._button(tools, "☰  Mở tất cả công cụ", show_tools,
                                  compact=True, background=SURFACE)
        open_tools.grid(row=1, column=0, sticky="ew")

        main = tk.Frame(self, bg=BG, padx=20, pady=15)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(0, weight=1)
        workspace = tk.Frame(main, bg=BG)
        workspace.grid(row=0, column=0, sticky="nsew")
        workspace.grid_columnconfigure(0, weight=1)
        workspace.grid_rowconfigure(0, weight=1)
        # Start below the minimum window width; resize after the parent has a real size.
        desk = tk.Frame(workspace, bg=BG, width=540, height=420)
        self.desk = desk
        desk.grid(row=0, column=0, sticky="ns")
        desk.grid_propagate(False)
        desk.grid_columnconfigure(0, weight=1)
        desk.grid_rowconfigure(1, weight=1)
        workspace.bind("<Configure>", lambda event: desk.configure(
            width=min(900, max(440, event.width - 20))))

        head = tk.Frame(desk, bg=BG)
        head.grid(row=0, column=0, sticky="ew", pady=(4, 16))
        self.avatar = AnimeAvatar(head, size=74, bg=BG, style=self.avatar_style,
                                  image_path=self.custom_avatar_path if self.avatar_custom else None,
                                  command=self._avatar_dialog)
        self.avatar.pack(side="right", padx=(12, 0))
        self._button(head, "☁ Điện thoại", self._cloud_phone_dialog, compact=True,
                     primary=True).pack(side="right", padx=(6, 0))
        self._button(head, "Lịch nhắc", self._reminders_dialog, compact=True,
                     background=SURFACE).pack(side="right", padx=(10, 0))
        compact_tools = tk.Frame(head, bg=BG)
        compact_tools.pack(side="right", padx=(5, 8))
        tk.Checkbutton(compact_tools, text="✦ Hoạt bát", variable=self.playful_var,
                       command=self._toggle_persona, bg=BG, fg=ACCENT, selectcolor=SIDE,
                       activebackground=BG, activeforeground=TEXT,
                       font=("Segoe UI", 9), cursor="hand2").pack()
        titles = tk.Frame(head, bg=BG)
        titles.pack(side="left", fill="x", expand=True)
        tk.Label(titles, text="KHÔNG GIAN CỦA BẠN  /  TRÒ CHUYỆN", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 9, "bold"), anchor="w").pack(fill="x")
        tk.Label(titles, textvariable=self.title_var, bg=BG, fg=TEXT,
                 font=("Segoe UI", 20, "bold"), anchor="w", wraplength=500,
                 justify="left").pack(fill="x", pady=(3, 0))
        tk.Label(titles, textvariable=self.folder_var, bg=BG, fg=MUTED,
                 font=("Segoe UI", 9), anchor="w", wraplength=480,
                 justify="left").pack(fill="x", pady=(3, 0))
        tk.Label(titles, textvariable=self.health_var, bg=BG, fg=ACCENT,
                 font=("Segoe UI", 9), anchor="w", wraplength=480,
                 justify="left").pack(fill="x", pady=(5, 0))

        conversation = tk.Frame(desk, bg=BG)
        conversation.grid(row=1, column=0, sticky="nsew")
        conversation.grid_columnconfigure(0, weight=1)
        conversation.grid_rowconfigure(0, weight=1)
        self.feed_canvas = tk.Canvas(conversation, bg=BG, highlightthickness=0, bd=0)
        self.feed_canvas.grid(row=0, column=0, sticky="nsew")
        feed_scroll = ttk.Scrollbar(conversation, orient="vertical", command=self.feed_canvas.yview)
        feed_scroll.grid(row=0, column=1, sticky="ns")
        self.feed_canvas.configure(yscrollcommand=feed_scroll.set)
        self.messages_frame = tk.Frame(self.feed_canvas, bg=BG)
        self.feed_window = self.feed_canvas.create_window((0, 0), window=self.messages_frame,
                                                           anchor="nw")
        self.messages_frame.bind("<Configure>", lambda _: self.feed_canvas.configure(
            scrollregion=self.feed_canvas.bbox("all")))
        self.feed_canvas.bind("<Configure>", self._resize_feed)
        self._bind_feed_scroll(self.feed_canvas)
        self._message_labels: list[tk.Label] = []
        self._pending_row: tk.Frame | None = None
        self._pending_label: tk.Label | None = None
        self.starters: tk.Frame | None = None

        composer = tk.Frame(desk, bg=PANEL, padx=14, pady=10,
                            highlightthickness=1, highlightbackground=BORDER)
        composer.grid(row=2, column=0, sticky="ew", pady=(14, 8))
        composer.grid_columnconfigure(0, weight=1)
        tk.Label(composer, text="NHẮN MIRA", bg=PANEL, fg=ACCENT,
                 font=("Segoe UI", 9, "bold"), anchor="w").grid(
                     row=0, column=0, sticky="ew", pady=(0, 3))
        self.input = tk.Text(composer, height=2, wrap="word", bg=PANEL, fg=TEXT,
                             insertbackground=ACCENT, relief="flat", borderwidth=0,
                             padx=2, pady=6, font=("Segoe UI", 12), undo=True)
        self.input.grid(row=1, column=0, sticky="ew")
        self.input.bind("<Return>", self._send)
        self.input.bind("<Control-Return>", self._send)
        self.input.bind("<Shift-Return>", self._newline)
        compose_tools = tk.Frame(composer, bg=PANEL)
        compose_tools.grid(row=2, column=0, sticky="ew", pady=(5, 0))
        self._button(compose_tools, "＋ Ảnh", self._attach_image, compact=True,
                     background=PANEL).pack(side="left")
        self.screen_button = self._button(compose_tools, "▣ Màn hình", self._attach_screen,
                                          compact=True, background=PANEL)
        self.screen_button.pack(side="left")
        self._button(compose_tools, "＋ File", self._attach_file, compact=True,
                     background=PANEL).pack(side="left")
        self._button(compose_tools, "▶ Kiểm thử", self._run_tests, compact=True,
                     background=PANEL).pack(side="left")
        tk.Label(compose_tools, textvariable=self.attachment_var, bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 9), anchor="w", width=12).pack(side="left", padx=5)
        self._button(compose_tools, "Bỏ ảnh", self._clear_image, compact=True,
                     background=PANEL).pack(side="left")
        self.send_button = self._button(compose_tools, "Gửi  ↗", self._send,
                                        primary=True, compact=True)
        self.send_button.pack(side="right")
        status = tk.Frame(desk, bg=BG)
        status.grid(row=3, column=0, sticky="ew")
        tk.Label(status, textvariable=self.status_var, bg=BG, fg=MUTED,
                 anchor="w", font=("Segoe UI", 9)).pack(side="left", fill="x", expand=True)
        self.retry_button = self._button(status, "Thử gửi lại", self._retry, compact=True)
        self.listen_button = self._button(status, "🔊 Nghe", self._listen_last, compact=True,
                                          background=BG)
        self.listen_button.pack(side="right", padx=(4, 0))
        self.copy_button = self._button(status, "⧉ Sao chép", self._copy_last_answer,
                                        compact=True, background=BG)
        self.copy_button.pack(side="right")

        rail = tk.Frame(main, bg=BG, width=276, padx=14)
        self.side_panel = rail
        rail.grid(row=0, column=1, sticky="ns", padx=(10, 0))
        rail.grid_propagate(False)
        tk.Label(rail, text="TRUNG TÂM MIRA", bg=BG, fg=ACCENT, anchor="w",
                 font=("Segoe UI", 9, "bold")).pack(fill="x", pady=(8, 15))
        model_card = tk.Frame(rail, bg=PANEL, padx=15, pady=16,
                              highlightthickness=1, highlightbackground=BORDER)
        model_card.pack(fill="x", pady=(0, 12))
        tk.Label(model_card, text="✦  Trạng thái AI", bg=PANEL, fg=TEXT,
                 font=("Segoe UI", 13, "bold"), anchor="w").pack(fill="x")
        tk.Label(model_card, textvariable=self.model_var, bg=PANEL, fg=ACCENT,
                 font=("Segoe UI", 10, "bold"), anchor="w",
                 wraplength=220).pack(fill="x", pady=(11, 5))
        self.health_label = tk.Label(model_card, textvariable=self.health_var,
                                     bg=PANEL, fg=MUTED, justify="left", anchor="w",
                                     wraplength=220, font=("Segoe UI", 9))
        self.health_label.pack(fill="x", pady=(0, 12))
        self._button(model_card, "Kiểm tra lại", self._check_ollama,
                     compact=True, background=SURFACE).pack(side="left")
        self._button(model_card, "Cách cài", self._setup_guide,
                     compact=True, background=SURFACE).pack(side="right")

        actions_card = tk.Frame(rail, bg=PANEL, padx=15, pady=16,
                                highlightthickness=1, highlightbackground=BORDER)
        actions_card.pack(fill="x", pady=(0, 12))
        tk.Label(actions_card, text="Lối tắt của bạn", bg=PANEL, fg=TEXT,
                 font=("Segoe UI", 13, "bold"), anchor="w").pack(fill="x", pady=(0, 10))
        for label, action in (("⌚  Đặt lịch nhắc", self._reminders_dialog),
                              ("◈  Chat trên điện thoại", self._mobile_dialog),
                              ("✦  Nhân vật Mira", self._avatar_dialog),
                              ("✦  Dạy Mira nhớ", self._show_memories),
                              ("▤  Chọn thư mục", self._choose_folder)):
            self._button(actions_card, label, action, compact=True,
                         background=SURFACE).pack(fill="x", pady=3)

        work_card = tk.Frame(rail, bg=PANEL, padx=15, pady=16,
                             highlightthickness=1, highlightbackground=BORDER)
        work_card.pack(fill="x")
        tk.Label(work_card, text="Làm việc với file", bg=PANEL, fg=TEXT,
                 font=("Segoe UI", 13, "bold"), anchor="w").pack(fill="x", pady=(0, 8))
        self._button(work_card, "＋ Chọn file", self._attach_file,
                     compact=True, background=SURFACE).pack(fill="x", pady=3)
        self._button(work_card, "▶ Chạy kiểm thử", self._run_tests,
                     compact=True, background=SURFACE).pack(fill="x", pady=3)
        tk.Checkbutton(work_card, text="🌐 Cho Mira tra cứu web", variable=self.web_var,
                       command=self._toggle_web, bg=PANEL, fg=TEXT, selectcolor=SIDE,
                       activebackground=PANEL, activeforeground=TEXT,
                       font=("Segoe UI", 10), cursor="hand2").pack(anchor="w", pady=(6, 0))
        self.desktop_button = self._button(work_card, "🖱 Bật điều khiển máy", self._toggle_desktop,
                                           compact=True, background=SURFACE)
        self.desktop_button.pack(fill="x", pady=(6, 3))
        if sys.platform != "win32":
            self.desktop_button.configure(state="disabled", text="Điều khiển: chỉ Windows")
        self.device_button = self._button(work_card, "◉ Cho Mira xem trạng thái PC", self._toggle_device,
                                          compact=True, background=SURFACE)
        self.device_button.pack(fill="x", pady=(4, 3))
        if sys.platform != "win32":
            self.device_button.configure(state="disabled", text="Trạng thái PC: chỉ Windows")
        tk.Checkbutton(work_card, text="✦ Mira hoạt bát", variable=self.playful_var,
                       command=self._toggle_persona, bg=PANEL, fg=ACCENT, selectcolor=SIDE,
                       activebackground=PANEL, activeforeground=TEXT,
                       font=("Segoe UI", 10, "bold"), cursor="hand2").pack(anchor="w", pady=(9, 0))

        def resize_main(event):
            if event.widget is main:
                if event.width >= 1280:
                    rail.grid()
                else:
                    rail.grid_remove()

        main.bind("<Configure>", resize_main)
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
            "avatar_style": self.avatar_style,
            "avatar_custom": self.avatar_custom,
            "web_enabled": self.web_var.get(),
            "folder": str(self.workspace.root) if self.workspace else "",
            "active_chat_id": self.active_chat_id,
            "current_chat": self.active_chat_id,
        })
        if self.phone_server:
            self.phone_server.update_config(
                model=selected_model, name=self.name_var.get().strip()[:40] or "Mira",
                cloud_consent=self.cloud_consent, fast=self.fast_var.get(),
                web_enabled=self.web_var.get(),
                persona="playful" if self.playful_var.get() else "standard",
                persona_note=self.persona_note,
                avatar_style=self.avatar_style, avatar_custom=self.avatar_custom,
                status_reader=self._read_status_if_enabled if self.device_enabled else None,
                screen_reader=capture_primary_screen if self.phone_screen_enabled else None,
                workspace=self.workspace if self.phone_files_enabled else None)
        if self.telegram_bot:
            self.telegram_bot.update_config(
                model=selected_model, name=self.name_var.get().strip()[:40] or "Mira",
                cloud_consent=self.cloud_consent, fast=self.fast_var.get(),
                web_enabled=self.web_var.get(),
                persona="playful" if self.playful_var.get() else "standard",
                persona_note=self.persona_note)

    def _toggle_persona(self):
        try:
            self._save_settings()
            self.status_var.set("Đã bật Mira hoạt bát." if self.playful_var.get()
                                else "Đã chuyển sang Mira thường.")
        except OSError as exc:
            messagebox.showerror("Không lưu được tính cách", str(exc))

    def _toggle_web(self, enabled=None):
        if enabled is not None:
            self.web_var.set(enabled)
        if self.web_var.get() and not messagebox.askyesno(
                "Cho Mira tra cứu web?",
                "Mira sẽ gửi câu tìm kiếm đến DuckDuckGo. Khi dịch vụ này không trả kết quả, "
                "Mira chỉ thử Wikipedia và sẽ nói rõ giới hạn. Tìm kiếm không dùng API trả phí.\n\n"
                "Bật tra cứu web cho desktop, Telegram và chat điện thoại?", parent=self):
            self.web_var.set(False)
            return
        try:
            self._save_settings()
            self.status_var.set("Đã bật tra cứu web." if self.web_var.get()
                                else "Đã tắt tra cứu web.")
        except OSError as exc:
            self.web_var.set(False)
            messagebox.showerror("Không lưu được quyền web", str(exc), parent=self)

    def _toggle_desktop(self):
        if sys.platform != "win32":
            messagebox.showinfo("Chỉ hỗ trợ Windows", "Quyền điều khiển này chỉ chạy trong Mira trên Windows.")
            return
        if not self.desktop_enabled:
            if not messagebox.askyesno(
                    "Cho Mira điều khiển máy trong phiên này?",
                    "Mira có thể mở ứng dụng Windows, nhấp chuột, gõ chữ và nhấn phím tắt "
                    "trên màn hình chính. Mỗi thao tác đều hiện nội dung cụ thể để bạn duyệt.\n\n"
                    "Quyền này chỉ có hiệu lực trong cửa sổ Mira hiện tại; Telegram và điện thoại "
                    "không thể điều khiển máy qua AI. Hãy xem nội dung trước khi duyệt.",
                    parent=self):
                return
            self.desktop_enabled = True
            self.desktop_button.configure(text="🖱 Tắt điều khiển máy")
            self.status_var.set("Điều khiển máy đang bật • từng thao tác vẫn cần bạn duyệt.")
        else:
            self.desktop_enabled = False
            self.desktop.target_window = 0
            self.desktop_button.configure(text="🖱 Bật điều khiển máy")
            self.status_var.set("Đã tắt quyền điều khiển máy.")

    def _read_status_if_enabled(self):
        if not self.device_enabled:
            raise RuntimeError("Quyền đọc trạng thái PC đã bị tắt trên máy tính.")
        return device_status()

    def _toggle_device(self, *, parent=None):
        if sys.platform != "win32":
            return
        if not self.device_enabled and not messagebox.askyesno(
                "Cho Mira đọc trạng thái PC?",
                "Mira có thể kiểm tra pin, máy có đang cắm nguồn, RAM và dung lượng trống "
                "của ổ hệ thống khi bạn hỏi từ ứng dụng hoặc điện thoại đã ghép nối. "
                "Nếu dùng AI cloud, các thông tin đã đọc có thể đi cùng yêu cầu tới Ollama. "
                "Quyền này hết khi đóng Mira và bạn có thể tắt bất cứ lúc nào.",
                parent=parent or self):
            return
        self.device_enabled = not self.device_enabled
        self.device_button.configure(text=("◉ Tắt xem trạng thái PC" if self.device_enabled else
                                           "◉ Cho Mira xem trạng thái PC"))
        self.status_var.set("Đã bật quyền đọc trạng thái PC." if self.device_enabled else
                            "Đã tắt quyền đọc trạng thái PC.")
        if self.phone_server:
            self.phone_server.update_config(status_reader=self._read_status_if_enabled if self.device_enabled else None)

    def _close(self):
        self.closed = True
        self.lessons.stop_event.set()
        self.device_enabled = False
        self.phone_screen_enabled = False
        self.phone_files_enabled = False
        if self.phone_server:
            self.phone_server.stop()
            self.phone_server = None
        if self.telegram_bot:
            self.telegram_bot.stop()
            self.telegram_bot = None
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

    def _poll_reminders(self):
        if self.closed:
            return
        try:
            due = self.reminders.due()
            if due:
                lines = ["• " + item["title"] for item in due]
                self.status_var.set(f"Đã đến giờ {len(due)} lịch nhắc.")
                messagebox.showinfo("Mira nhắc bạn", "Đã tới lúc:\n" + "\n".join(lines), parent=self)
        except (OSError, ValueError) as exc:
            self.status_var.set("Không kiểm tra được lịch nhắc: " + str(exc))
        finally:
            if not self.closed:
                self.after(30_000, self._poll_reminders)

    def _animate_avatar(self):
        if self.closed:
            return
        self.avatar_tick += 1
        self.avatar.set_state(self.avatar_state, self.avatar_tick)
        self.after(280, self._animate_avatar)

    def _avatar_dialog(self):
        dialog = tk.Toplevel(self)
        dialog.title("Nhân vật anime của Mira")
        dialog.geometry("530x530")
        dialog.configure(bg=BG)
        dialog.transient(self)
        tk.Label(dialog, text="Nhân vật Mira", font=("Segoe UI", 18, "bold"),
                 bg=BG, fg=TEXT).pack(pady=(18, 4))
        tk.Label(dialog, text="Nhấp vào ảnh nhỏ ở góc chat để mở lại. Mira chớp mắt, suy nghĩ "
                 "và cử động miệng khi trả lời hoặc đọc thành tiếng.", bg=BG, fg=MUTED,
                 wraplength=475, justify="center").pack(padx=18, pady=(0, 8))
        preview = AnimeAvatar(dialog, size=250, bg=BG, style=self.avatar_style,
                              image_path=self.custom_avatar_path if self.avatar_custom else None)
        preview.pack()

        def animate_preview():
            if dialog.winfo_exists():
                preview.set_state(self.avatar_state, self.avatar_tick)
                dialog.after(300, animate_preview)

        dialog.after(300, animate_preview)
        row = tk.Frame(dialog, bg=BG)
        row.pack(pady=(7, 7))
        tk.Label(row, text="Màu tóc:", bg=BG, fg=TEXT).pack(side="left", padx=(0, 9))
        names = [item[0] for item in STYLES.values()]
        choices = list(STYLES)
        style = ttk.Combobox(row, state="readonly", values=names, width=19)
        style.current(choices.index(self.avatar_style))
        style.pack(side="left")

        def set_style(_=None):
            self.avatar_style = choices[style.current()]
            self.avatar_custom = False
            self.avatar.configure_avatar(style=self.avatar_style)
            preview.configure_avatar(style=self.avatar_style)
            self._save_settings()

        style.bind("<<ComboboxSelected>>", set_style)

        def import_png():
            filename = filedialog.askopenfilename(title="Chọn ảnh PNG nhân vật anime",
                                                  filetypes=[("Ảnh PNG", "*.png")], parent=dialog)
            if not filename:
                return
            try:
                source = Path(filename)
                blob = source.read_bytes()
                if len(blob) > 5 * 1024 * 1024 or not blob.startswith(b"\x89PNG\r\n\x1a\n"):
                    raise ValueError("Chỉ nhận PNG dưới 5 MiB.")
                width, height = struct.unpack(">II", blob[16:24])
                if width < 64 or height < 64 or width * height > 4_000_000:
                    raise ValueError("Ảnh cần rộng và cao ít nhất 64 px, tối đa 4 triệu điểm ảnh.")
                # Test with Tk before changing the saved avatar.
                tk.PhotoImage(data=base64.b64encode(blob).decode("ascii"), format="png", master=dialog)
                self.custom_avatar_path.write_bytes(blob)
                self.avatar_custom = True
                self.avatar.configure_avatar(image_path=self.custom_avatar_path)
                preview.configure_avatar(image_path=self.custom_avatar_path)
                self._save_settings()
            except (OSError, ValueError, tk.TclError, struct.error) as exc:
                messagebox.showerror("Ảnh nhân vật không hợp lệ", str(exc), parent=dialog)

        self._button(dialog, "＋ Dùng ảnh PNG nhân vật của bạn", import_png,
                     primary=True).pack(pady=(3, 5))
        tk.Label(dialog, text="Ảnh PNG tĩnh dành cho giao diện Mira trên máy tính. "
                 "Trang điện thoại cloud có biểu tượng 2D nhẹ, chạy cả khi laptop tắt.", bg=BG, fg=MUTED,
                 wraplength=475).pack(padx=18)

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
        self._remove_pending()
        for widget in self.messages_frame.winfo_children():
            widget.destroy()
        self._message_labels.clear()
        for message in item["messages"]:
            self._add_message("Bạn" if message["role"] == "user" else self.name_var.get(),
                              message["content"], user=message["role"] == "user")
        if not item["messages"]:
            self._render_welcome()
        if self.busy and self.stream_chat_id == self.active_chat_id:
            self._show_pending(self.name_var.get())
        self.after_idle(lambda: self.feed_canvas.yview_moveto(
            1.0 if item["messages"] else 0.0))

    def _render_welcome(self):
        self.starters = tk.Frame(self.messages_frame, bg=BG)
        self.starters.pack(fill="x", padx=20, pady=(45, 15))
        tk.Label(self.starters, text="✦", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 34, "bold")).pack(anchor="w")
        tk.Label(self.starters, text="Hôm nay mình giúp gì cho bạn?", bg=BG, fg=TEXT,
                 font=("Segoe UI", 21, "bold"), anchor="w").pack(fill="x", pady=(2, 4))
        self._welcome_note = tk.Label(
            self.starters, text="Bắt đầu bằng một câu hỏi, hoặc chọn việc bạn muốn làm.",
            bg=BG, fg=MUTED, font=("Segoe UI", 11), anchor="w", justify="left",
            wraplength=550)
        self._welcome_note.pack(fill="x", pady=(0, 25))
        choices = tk.Frame(self.starters, bg=BG)
        choices.pack(fill="x")
        choices.grid_columnconfigure(0, weight=1, uniform="prompts")
        choices.grid_columnconfigure(1, weight=1, uniform="prompts")
        for index, (title, hint, prompt) in enumerate((
            ("◈  Lên kế hoạch", "Chia việc thành từng bước", "Giúp tôi chia việc này thành các bước cụ thể: "),
            ("✦  Viết lại nội dung", "Ngắn gọn và tự nhiên hơn", "Viết lại nội dung này sao cho dễ hiểu: "),
            ("◇  Giải thích cho tôi", "Bắt đầu từ điều cơ bản", "Giải thích thật dễ hiểu cho tôi về: "),
            ("⌘  Hỗ trợ lập trình", "Tìm và sửa lỗi code", "Giúp tôi hiểu và sửa lỗi code này: "),
        )):
            button = tk.Button(choices, text=f"{title}\n{hint}",
                               command=lambda value=prompt: self._fill_prompt(value),
                               bg=PANEL, fg=TEXT, activebackground=SURFACE,
                               activeforeground=TEXT, relief="flat", borderwidth=0,
                               font=("Segoe UI", 10, "bold"), justify="left", anchor="w",
                               padx=17, pady=13, cursor="hand2", wraplength=250)
            button.grid(row=index // 2, column=index % 2, sticky="ew",
                        padx=(0, 9) if index % 2 == 0 else (0, 0), pady=(0, 9))
            self._bind_feed_scroll(button)

    def _resize_feed(self, event):
        self.feed_canvas.itemconfigure(self.feed_window, width=event.width)
        wrap = max(240, min(700, event.width - 100))
        for label in self._message_labels:
            if label.winfo_exists():
                label.configure(wraplength=wrap)
        if hasattr(self, "_welcome_note") and self._welcome_note.winfo_exists():
            self._welcome_note.configure(wraplength=max(220, event.width - 75))

    def _bind_feed_scroll(self, widget):
        widget.bind("<MouseWheel>", self._scroll_feed)
        widget.bind("<Button-4>", self._scroll_feed)
        widget.bind("<Button-5>", self._scroll_feed)

    def _scroll_feed(self, event):
        direction = -1 if getattr(event, "num", None) == 4 or event.delta > 0 else 1
        self.feed_canvas.yview_scroll(direction * 3, "units")
        return "break"

    def _message_card(self, sender: str, content: str, *, user=False):
        row = tk.Frame(self.messages_frame, bg=BG)
        row.pack(fill="x", pady=7)
        color = "#263a59" if user else PANEL
        card = tk.Frame(row, bg=color, padx=17, pady=13,
                        highlightthickness=1,
                        highlightbackground="#435b85" if user else BORDER)
        card.pack(side="right" if user else "left",
                  padx=(46, 12) if user else (12, 46))
        heading = tk.Frame(card, bg=color)
        heading.pack(fill="x", pady=(0, 8))
        tk.Label(heading, text=("↗  " if user else "✦  ") + sender,
                 bg=color, fg=BLUE if user else ACCENT,
                 font=("Segoe UI", 10, "bold")).pack(side="left")
        copy = tk.Button(heading, text="Sao chép", relief="flat", borderwidth=0,
                         bg=color, fg=MUTED, activebackground=SURFACE,
                         activeforeground=TEXT, font=("Segoe UI", 9), cursor="hand2",
                         command=lambda value=content: self._copy_message(value))
        copy.pack(side="right", padx=(20, 0))
        body = tk.Label(card, text=content, bg=color, fg=TEXT,
                        font=("Segoe UI", 11), justify="left", anchor="w",
                        wraplength=650)
        body.pack(anchor="w")
        copy.configure(command=lambda widget=body: self._copy_message(widget.cget("text")))
        self._message_labels.append(body)
        for widget in (row, card, heading, body, copy):
            self._bind_feed_scroll(widget)
        return row, body

    def _add_message(self, sender: str, content: str, *, user=False):
        at_bottom = self.feed_canvas.yview()[1] >= 0.96
        self._message_card(sender, content, user=user)
        if at_bottom:
            self.after_idle(lambda: self.feed_canvas.yview_moveto(1.0))

    def _copy_message(self, content: str):
        self.clipboard_clear()
        self.clipboard_append(content)
        self.status_var.set("Đã sao chép tin nhắn.")

    def _copy_last_answer(self):
        item = self.chats.get(self.active_chat_id)
        answer = next((entry["content"] for entry in reversed(item["messages"])
                       if entry["role"] == "assistant"), None)
        if not answer:
            self.status_var.set("Cuộc trò chuyện này chưa có câu trả lời để sao chép.")
            return
        self.clipboard_clear()
        self.clipboard_append(answer)
        self.status_var.set("Đã sao chép câu trả lời mới nhất của Mira.")

    def _remove_pending(self):
        if self._pending_row is not None:
            if self._pending_row.winfo_exists():
                self._pending_row.destroy()
            if self._pending_label in self._message_labels:
                self._message_labels.remove(self._pending_label)
            self._pending_row = None
            self._pending_label = None

    def _show_pending(self, name: str):
        if self._pending_label is None:
            self._pending_row, self._pending_label = self._message_card(
                name, "Đang chuẩn bị câu trả lời…")
        self._pending_label.configure(text=self.stream_text or "Đang chuẩn bị câu trả lời…")
        if self.feed_canvas.yview()[1] >= 0.96:
            self.after_idle(lambda: self.feed_canvas.yview_moveto(1.0))

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
                selected = Workspace(Path(folder), self.path / "backups")
                if self.workspace is None or self.workspace.root != selected.root:
                    self.phone_files_enabled = False
                self.workspace = selected
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

    def _cloud_phone_dialog(self):
        dialog = tk.Toplevel(self)
        dialog.title("Mira trên điện thoại khi laptop tắt")
        dialog.geometry("640x510")
        dialog.configure(bg=BG)
        dialog.transient(self)
        tk.Label(dialog, text="Mira đi cùng bạn", bg=BG, fg=TEXT,
                 font=("Segoe UI", 20, "bold")).pack(anchor="w", padx=22, pady=(22, 7))
        tk.Label(dialog, text="Giao diện điện thoại cloud chạy độc lập: chat, sở thích, "
                 "lịch nhắc qua Telegram kể cả khi laptop đang tắt.", bg=BG, fg=MUTED,
                 justify="left", wraplength=590).pack(anchor="w", padx=22)
        tk.Label(dialog, text="CÀI MỘT LẦN, DÙNG TRÊN ĐIỆN THOẠI", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=22, pady=(22, 8))
        steps = ("1. Tạo tài khoản Cloudflare Free và cài Node.js trên PC.\n"
                 "2. Mở thư mục cloud trong bản Mira này, chạy python setup.py.\n"
                 "3. Lưu khóa truy cập và URL *.workers.dev, mở URL trên điện thoại.\n"
                 "4. Để Mira báo lịch trong Telegram: tạo bot riêng và chạy python setup_telegram.py.")
        tk.Label(dialog, text=steps, bg=PANEL, fg=TEXT, padx=17, pady=17,
                 justify="left", wraplength=570).pack(fill="x", padx=22)
        tk.Label(dialog, text="Gói miễn phí có hạn mức. Lịch nhắc chỉ gửi thông báo khi đã "
                 "cấu hình bot Telegram. Chat cloud và chat trong app PC lưu ở hai nơi riêng. "
                 "Khi máy tắt, không thể xem pin, màn hình hay điều khiển máy.",
                 bg=BG, fg=MUTED, justify="left", wraplength=580).pack(
                     anchor="w", padx=22, pady=(14, 8))

        def open_guide():
            guide = Path(__file__).resolve().parent.parent / "cloud" / "README.md"
            if not guide.is_file():
                messagebox.showerror("Chưa có hướng dẫn", "Giải nén lại đầy đủ bản Mira mới, bao gồm thư mục cloud.", parent=dialog)
                return
            if sys.platform == "win32":
                subprocess.Popen(["notepad.exe", str(guide)])
            else:
                webbrowser.open(guide.as_uri())

        row = tk.Frame(dialog, bg=BG)
        row.pack(anchor="w", padx=22, pady=(10, 0))
        self._button(row, "Đọc hướng dẫn từng bước", open_guide, primary=True).pack(side="left")
        self._button(row, "Kết nối máy đang bật", self._mobile_dialog).pack(side="left", padx=10)

    def _mobile_dialog(self):
        dialog = tk.Toplevel(self)
        dialog.title("Điện thoại & truy cập từ xa")
        dialog.geometry("700x745")
        dialog.configure(bg=BG)
        dialog.transient(self)
        tk.Label(dialog, text="Kết nối với laptop đang bật", bg=BG, fg=TEXT,
                 font=("Segoe UI", 17, "bold")).pack(anchor="w", padx=20, pady=(18, 8))
        instructions = ("1. Cài Tailscale trên máy tính và điện thoại; đăng nhập cùng tài khoản.\n"
                        "2. Bấm Bật giao diện dưới đây. Trong PowerShell trên máy tính chạy:\n"
                        "    tailscale serve --bg 8765\n"
                        "3. Mở địa chỉ HTTPS do Tailscale in ra trên điện thoại, rồi nhập mã ghép nối.")
        tk.Label(dialog, text=instructions, bg=BG, fg=TEXT, wraplength=625,
                 justify="left").pack(anchor="w", padx=20)
        tk.Label(dialog, text="Laptop phải đang bật và ứng dụng Mira đang chạy. Nếu laptop tắt, "
                 "hãy dùng Mira cloud ở nút Điện thoại khi máy tắt. Giao diện này chỉ lắng nghe 127.0.0.1; dùng Tailscale Serve để "
                 "mở riêng cho các thiết bị trong mạng của bạn. Không dùng Funnel hoặc mở cổng router.",
                 bg=BG, fg=MUTED, wraplength=625, justify="left").pack(
                     anchor="w", padx=20, pady=(9, 12))
        status = tk.StringVar(value="Đang tắt • chưa ai có thể chat qua điện thoại")
        code = tk.StringVar(value="—")
        tk.Label(dialog, textvariable=status, bg=BG, fg=ACCENT,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=20)
        tk.Label(dialog, text="Mã ghép nối chỉ dùng một lần, hết hạn sau 5 phút:",
                 bg=BG, fg=MUTED).pack(anchor="w", padx=20, pady=(12, 2))
        tk.Label(dialog, textvariable=code, bg=PANEL, fg=ACCENT, padx=14, pady=8,
                 font=("Consolas", 20, "bold")).pack(anchor="w", padx=20)

        def start():
            if self.phone_server is None:
                try:
                    server = PhoneServer(
                        self.path, self.agent, self.reminders, self.memories, self.preferences,
                        model=self.model_var.get().strip(), name=self.name_var.get().strip() or "Mira",
                        cloud_consent=self.cloud_consent, fast=self.fast_var.get(),
                        web_enabled=self.web_var.get(),
                        persona="playful" if self.playful_var.get() else "standard",
                        persona_note=self.persona_note,
                        avatar_style=self.avatar_style, avatar_custom=self.avatar_custom,
                        status_reader=self._read_status_if_enabled if self.device_enabled else None,
                        screen_reader=capture_primary_screen if self.phone_screen_enabled else None,
                        workspace=self.workspace if self.phone_files_enabled else None)
                    server.start()
                    self.phone_server = server
                except (OSError, ValueError) as exc:
                    messagebox.showerror("Không bật được điện thoại", str(exc), parent=dialog)
                    return
            code.set(self.phone_server.new_pairing_code())
            status.set("Đã bật • mở trang riêng qua Tailscale Serve và nhập mã bên dưới")

        def stop():
            if self.phone_server:
                self.phone_server.stop()
                self.phone_server = None
            self.phone_screen_enabled = False
            self.phone_files_enabled = False
            screen_permission.set(False)
            files_permission.set(False)
            code.set("—")
            status.set("Đã tắt • các phiên điện thoại vừa bị ngắt")

        controls = tk.Frame(dialog, bg=BG)
        controls.pack(fill="x", padx=20, pady=(14, 12))
        self._button(controls, "Bật / tạo mã mới", start, primary=True).pack(side="left")
        self._button(controls, "Ngắt kết nối", stop).pack(side="left", padx=8)
        self._button(controls, "Lịch nhắc", self._reminders_dialog).pack(side="left")
        self._button(controls, "Nhắc qua Telegram", self._telegram_dialog).pack(side="left", padx=(8, 0))
        tk.Label(dialog, text="MIRA ĐƯỢC XEM GÌ TRONG MÁY? (CHỈ PHIÊN NÀY)",
                 bg=BG, fg=ACCENT, font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=20, pady=(4, 0))
        device_permission = tk.BooleanVar(value=self.device_enabled)
        screen_permission = tk.BooleanVar(value=self.phone_screen_enabled)
        files_permission = tk.BooleanVar(value=self.phone_files_enabled)

        def toggle_device():
            self._toggle_device(parent=dialog)
            device_permission.set(self.device_enabled)

        def toggle_screen():
            wanted = screen_permission.get()
            if wanted and (sys.platform != "win32" or not messagebox.askyesno(
                    "Cho điện thoại chụp màn hình?",
                    "Điện thoại đã ghép nối có thể yêu cầu chụp MỘT ảnh màn hình chính. "
                    "Ảnh sẽ hiện trên điện thoại để bạn xem trước. Nếu bấm Gửi ảnh và dùng "
                    "mô hình cloud, ảnh có thể được chuyển tới Ollama. Quyền hết khi đóng Mira.",
                    parent=dialog)):
                wanted = False
            self.phone_screen_enabled = wanted
            screen_permission.set(wanted)
            if self.phone_server:
                self.phone_server.update_config(screen_reader=capture_primary_screen if wanted else None)

        def toggle_files():
            wanted = files_permission.get()
            if wanted and self.workspace is None:
                messagebox.showinfo("Chọn thư mục", "Hãy chọn thư mục được phép đọc trên máy tính trước.", parent=dialog)
                wanted = False
            if wanted and not messagebox.askyesno(
                    "Cho điện thoại đọc thư mục?",
                    f"Mira trên điện thoại được tìm và đọc file văn bản trong:\n{self.workspace.root}\n\n"
                    "Nội dung file được gửi vào mô hình bạn đang chọn, kể cả Ollama Cloud nếu bạn đã bật. "
                    "Điện thoại không thể sửa file hay chạy lệnh. Quyền hết khi đóng Mira.", parent=dialog):
                wanted = False
            self.phone_files_enabled = wanted
            files_permission.set(wanted)
            if self.phone_server:
                self.phone_server.update_config(workspace=self.workspace if wanted else None)

        for label, variable, command in (
                ("Cho Mira xem pin, sạc, RAM và dung lượng trống từ điện thoại", device_permission, toggle_device),
                ("Cho điện thoại chụp màn hình (xem trước mỗi ảnh)", screen_permission, toggle_screen),
                ("Cho điện thoại đọc thư mục đã chọn (chỉ file văn bản)", files_permission, toggle_files)):
            tk.Checkbutton(dialog, text=label, variable=variable, command=command,
                           bg=BG, fg=TEXT, selectcolor=PANEL, activebackground=BG,
                           activeforeground=TEXT, font=("Segoe UI", 10)).pack(anchor="w", padx=20, pady=2)
        tk.Label(dialog, text="Chat điện thoại lưu riêng. Không quyền chạy lệnh hoặc điều khiển chuột/bàn phím "
                 "qua AI. Các quyền trên mặc định tắt và có thể thu hồi ngay tại đây.",
                 bg=BG, fg=MUTED, wraplength=625, justify="left").pack(anchor="w", padx=20)
        links = tk.Frame(dialog, bg=BG)
        links.pack(fill="x", padx=20, pady=(13, 0))
        self._button(links, "Cài Tailscale", lambda: webbrowser.open(
            "https://tailscale.com/download")).pack(side="left")
        self._button(links, "Điều khiển màn hình máy tính", lambda: webbrowser.open(
            "https://remotedesktop.google.com/access")).pack(side="left", padx=7)
        tk.Label(dialog, text="Điều khiển chuột/bàn phím từ điện thoại cần cài Chrome "
                 "Remote Desktop trên máy tính. Máy phải bật và không ngủ.",
                 bg=BG, fg="#ffc59f", wraplength=625, justify="left").pack(
                     anchor="w", padx=20, pady=(12, 0))
        if self.phone_server:
            code.set(self.phone_server.new_pairing_code())
            status.set("Đã bật • mã mới vừa được tạo cho điện thoại")

    def _start_telegram(self, token: str):
        if self.telegram_bot and self.telegram_token == token and self.telegram_bot.running():
            return
        candidate = TelegramBot(self.path, token, self.agent, self.reminders,
                                self.memories, self.preferences,
                                model=self.model_var.get().strip(),
                                name=self.name_var.get().strip() or "Mira",
                                cloud_consent=self.cloud_consent, fast=self.fast_var.get(),
                                web_enabled=self.web_var.get(),
                                persona="playful" if self.playful_var.get() else "standard",
                                persona_note=self.persona_note)
        if self.telegram_bot:
            self.telegram_bot.stop()
        self.telegram_bot = candidate
        self.telegram_token = token
        candidate.start()

    def _telegram_dialog(self):
        dialog = tk.Toplevel(self)
        dialog.title("Mira qua Telegram")
        dialog.geometry("670x620")
        dialog.configure(bg=BG)
        dialog.transient(self)
        tk.Label(dialog, text="Mira nhắn lịch qua Telegram", bg=BG, fg=TEXT,
                 font=("Segoe UI", 17, "bold")).pack(anchor="w", padx=20, pady=(17, 8))
        tk.Label(dialog, text="1. Nhắn /newbot cho @BotFather trên Telegram. Sao chép token bot.\n"
                 "2. Dán token vào đây và bấm Bật. Chờ trạng thái sẵn sàng.\n"
                 "3. Trên điện thoại, mở bot của bạn và gửi /start theo sau là mã 8 chữ số.",
                 bg=BG, fg=TEXT, justify="left", wraplength=605).pack(anchor="w", padx=20)
        self._button(dialog, "Mở @BotFather", lambda: webbrowser.open(
            "https://t.me/BotFather")).pack(anchor="w", padx=20, pady=(9, 7))
        tk.Label(dialog, text="Token bot (chỉ nhập trong Mira; không gửi cho người khác)",
                 bg=BG, fg=MUTED).pack(anchor="w", padx=20)
        token_entry = tk.Entry(dialog, show="•", font=("Consolas", 11), bg=PANEL, fg=TEXT,
                               insertbackground=ACCENT, relief="flat", highlightthickness=1,
                               highlightbackground=BORDER, highlightcolor=ACCENT)
        token_entry.pack(fill="x", padx=20, pady=(4, 9))
        saved = load_json(self.telegram_credentials_path, {})
        if isinstance(saved, dict) and isinstance(saved.get("token"), str):
            token_entry.insert(0, saved["token"])
        elif self.telegram_token:
            token_entry.insert(0, self.telegram_token)
        remember = tk.BooleanVar(value=bool(isinstance(saved, dict) and saved.get("token")))
        tk.Checkbutton(dialog, text="Lưu token trong hồ sơ Windows và tự bật khi mở Mira",
                       variable=remember, bg=BG, fg=TEXT, activebackground=BG,
                       activeforeground=TEXT, selectcolor=PANEL).pack(anchor="w", padx=20)
        status = tk.StringVar(value="Telegram chưa bật")
        code = tk.StringVar(value="—")
        tk.Label(dialog, textvariable=status, bg=BG, fg=ACCENT,
                 wraplength=605).pack(anchor="w", padx=20, pady=(9, 3))
        tk.Label(dialog, text="Mã ghép nối một lần, hiệu lực 5 phút:", bg=BG,
                 fg=MUTED).pack(anchor="w", padx=20)
        tk.Label(dialog, textvariable=code, bg=PANEL, fg=ACCENT, padx=14, pady=8,
                 font=("Consolas", 20, "bold")).pack(anchor="w", padx=20, pady=(4, 0))

        def activate():
            token = token_entry.get().strip()
            try:
                self._start_telegram(token)
                if remember.get():
                    save_json(self.telegram_credentials_path, {"token": token, "enabled": True})
                else:
                    self.telegram_credentials_path.unlink(missing_ok=True)
                code.set(self.telegram_bot.new_pairing_code())
                status.set(self.telegram_bot.status())
            except (OSError, ValueError) as exc:
                messagebox.showerror("Không bật được Telegram", str(exc), parent=dialog)

        def disable():
            if self.telegram_bot:
                self.telegram_bot.stop()
                self.telegram_bot = None
                self.telegram_token = None
            if remember.get():
                save_json(self.telegram_credentials_path,
                          {"token": token_entry.get().strip(), "enabled": False})
            else:
                self.telegram_credentials_path.unlink(missing_ok=True)
            status.set("Đã tắt Telegram")
            code.set("—")

        def revoke():
            if self.telegram_bot and messagebox.askyesno(
                    "Thu hồi điện thoại", "Ngắt quyền bot của điện thoại đã ghép nối?", parent=dialog):
                try:
                    self.telegram_bot.unpair()
                    code.set(self.telegram_bot.new_pairing_code())
                    status.set("Đã thu hồi; điện thoại cần ghép nối lại")
                except OSError as exc:
                    messagebox.showerror("Không thu hồi được", str(exc), parent=dialog)

        buttons = tk.Frame(dialog, bg=BG)
        buttons.pack(fill="x", padx=20, pady=(12, 7))
        self._button(buttons, "Bật / tạo mã mới", activate, primary=True).pack(side="left")
        self._button(buttons, "Tắt", disable).pack(side="left", padx=7)
        self._button(buttons, "Thu hồi điện thoại", revoke).pack(side="left")
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        tk.Label(dialog, text=f"Trên Telegram: /nhac {tomorrow} 09:00 | Gọi mẹ → "
                 "kiểm tra → bấm Lưu. Hoặc /nhac Nhắc tôi ngày mai lúc 9 giờ gọi mẹ "
                 "để AI điền bản nháp. /lich xem lịch. Chat thường không có quyền sửa file hay chạy lệnh.",
                 bg=BG, fg=MUTED, wraplength=605, justify="left").pack(
                     anchor="w", padx=20, pady=(4, 0))

        def refresh():
            if not dialog.winfo_exists() or self.closed:
                return
            if self.telegram_bot:
                status.set(self.telegram_bot.status())
            dialog.after(1200, refresh)

        refresh()

    def _reminders_dialog(self):
        dialog = tk.Toplevel(self)
        dialog.title("Lịch nhắc của Mira")
        dialog.geometry("650x610")
        dialog.configure(bg=BG)
        dialog.transient(self)
        tk.Label(dialog, text="Lịch nhắc của Mira", bg=BG, fg=TEXT,
                 font=("Segoe UI", 17, "bold")).pack(anchor="w", padx=20, pady=(15, 7))
        tk.Label(dialog, text="Nhắc trên máy khi Mira đang mở. Xuất .ics để "
                 "ứng dụng lịch trên điện thoại nhắc khi máy tính tắt.", bg=BG, fg=MUTED,
                 wraplength=600, justify="left").pack(anchor="w", padx=20)
        idea = tk.Entry(dialog, font=("Segoe UI", 11), bg=PANEL, fg=TEXT,
                        insertbackground=ACCENT, relief="flat", highlightthickness=1,
                        highlightbackground=BORDER, highlightcolor=ACCENT)
        idea.pack(fill="x", padx=20, pady=(13, 4))
        idea.insert(0, "Nhắc tôi ngày mai lúc 9 giờ...")
        form = tk.Frame(dialog, bg=BG)
        form.pack(fill="x", padx=20, pady=6)
        tk.Label(form, text="Nội dung", bg=BG, fg=TEXT).grid(row=0, column=0, sticky="w")
        tk.Label(form, text="Ngày giờ YYYY-MM-DD HH:MM", bg=BG, fg=TEXT).grid(
            row=0, column=1, sticky="w", padx=8)
        title = tk.Entry(form, font=("Segoe UI", 11), bg=PANEL, fg=TEXT,
                         insertbackground=ACCENT, relief="flat", highlightthickness=1,
                         highlightbackground=BORDER, highlightcolor=ACCENT)
        title.grid(row=1, column=0, sticky="ew")
        when = tk.Entry(form, font=("Segoe UI", 11), bg=PANEL, fg=TEXT,
                        insertbackground=ACCENT, relief="flat", highlightthickness=1,
                        highlightbackground=BORDER, highlightcolor=ACCENT)
        when.grid(row=1, column=1, sticky="ew", padx=8)
        form.grid_columnconfigure(0, weight=1)
        form.grid_columnconfigure(1, weight=1)
        lead_labels = {"Đúng giờ": 0, "Trước 5 phút": 5, "Trước 15 phút": 15,
                       "Trước 1 giờ": 60, "Trước 1 ngày": 1440}
        lead = ttk.Combobox(dialog, values=list(lead_labels), state="readonly", font=("Segoe UI", 10))
        lead.set("Đúng giờ")
        lead.pack(anchor="w", padx=20, pady=(3, 7))
        status = tk.StringVar(value="Mira chỉ gợi ý lịch; bạn kiểm tra và bấm Lưu để xác nhận.")
        tk.Label(dialog, textvariable=status, bg=BG, fg=MUTED, wraplength=600,
                 justify="left").pack(anchor="w", padx=20)
        listing = tk.Listbox(dialog, font=("Segoe UI", 10), bg=PANEL, fg=TEXT,
                             selectbackground="#325976", relief="flat", activestyle="none")
        listing.pack(fill="both", expand=True, padx=20, pady=11)
        ids = []

        def refresh():
            ids.clear()
            listing.delete(0, "end")
            for item in self.reminders.list():
                stamp = datetime.fromisoformat(item["when"]).astimezone().strftime("%d/%m/%Y %H:%M")
                listing.insert("end", f"{stamp}  •  {item['title']}" +
                               ("  ✓" if item.get("notified_at") else ""))
                ids.append(item["id"])

        def selected_id():
            selected = listing.curselection()
            if not selected:
                status.set("Hãy chọn một lịch trong danh sách trước.")
                return None
            return ids[selected[0]]

        def save():
            try:
                self.reminders.create(title.get(), when.get(), lead_labels[lead.get()])
                refresh()
                status.set("Đã lưu lịch. Mira sẽ nhắc khi đang mở trên máy tính.")
            except (OSError, ValueError, KeyError) as exc:
                messagebox.showerror("Không tạo được lịch", str(exc), parent=dialog)

        def propose():
            model = self.model_var.get().strip()
            if not self._confirm_cloud(model, parent=dialog):
                return
            try:
                self._save_settings()
            except OSError as exc:
                messagebox.showerror("Không lưu được", str(exc), parent=dialog)
                return
            request = idea.get().strip()
            status.set("Mira đang hiểu ngày giờ…")

            def run():
                try:
                    offset = int(datetime.now().astimezone().utcoffset().total_seconds() / 60)
                    draft = draft_reminder(self.agent.client, model, request, offset)
                    error = None
                except (ValueError, RuntimeError, OSError) as exc:
                    draft, error = None, str(exc)

                def finish():
                    if self.closed or not dialog.winfo_exists():
                        return
                    if error:
                        status.set(error)
                    else:
                        title.delete(0, "end")
                        title.insert(0, draft["title"])
                        when.delete(0, "end")
                        when.insert(0, draft["when"].replace("T", " "))
                        lead.set(next((key for key, value in lead_labels.items()
                                       if value == draft["lead_minutes"]), "Đúng giờ"))
                        status.set("Mira đã điền biểu mẫu. Hãy kiểm tra ngày giờ và bấm Lưu.")

                try:
                    self.after(0, finish)
                except RuntimeError:
                    pass

            threading.Thread(target=run, daemon=True).start()

        def export():
            item_id = selected_id()
            if item_id is None:
                return
            filename = filedialog.asksaveasfilename(title="Xuất lịch cho điện thoại", parent=dialog,
                                                    defaultextension=".ics", initialfile="mira-reminder.ics",
                                                    filetypes=[("Lịch", "*.ics")])
            if filename:
                try:
                    Path(filename).write_bytes(self.reminders.calendar_file(item_id))
                    status.set("Đã xuất lịch; hãy thêm file vào ứng dụng Lịch trên điện thoại.")
                except (ValueError, OSError) as exc:
                    messagebox.showerror("Không xuất được lịch", str(exc), parent=dialog)

        def delete():
            item_id = selected_id()
            if item_id and messagebox.askyesno("Xóa lịch nhắc", "Bạn muốn xóa lịch đã chọn?", parent=dialog):
                try:
                    self.reminders.delete(item_id)
                    refresh()
                    status.set("Đã xóa lịch nhắc trên Mira.")
                except (ValueError, OSError) as exc:
                    messagebox.showerror("Không xóa được lịch", str(exc), parent=dialog)

        controls = tk.Frame(dialog, bg=BG)
        controls.pack(fill="x", padx=20, pady=(0, 15))
        self._button(controls, "Mira đọc lịch", propose).pack(side="left")
        self._button(controls, "Lưu lịch", save, primary=True).pack(side="left", padx=7)
        self._button(controls, "Xuất .ics", export).pack(side="left")
        self._button(controls, "Xóa", delete).pack(side="right")
        refresh()

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
        name = tk.Entry(dialog, font=("Segoe UI", 12), bg=PANEL, fg=TEXT,
                        insertbackground=ACCENT, relief="flat", highlightthickness=1,
                        highlightbackground=BORDER, highlightcolor=ACCENT)
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
        tk.Checkbutton(dialog, text="Hoạt bát: gần gũi, ứng biến; chỉ đùa khi hợp lúc",
                       variable=dialog_playful, bg=BG, fg=TEXT, selectcolor=PANEL,
                       activebackground=BG, activeforeground=TEXT).pack(anchor="w", padx=20)
        tk.Label(dialog, text="Mira vẫn ưu tiên trả lời chính xác khi làm việc hoặc khi bạn cần sự nghiêm túc.",
                 bg=BG, fg=MUTED, wraplength=530, justify="left").pack(anchor="w", padx=20)
        tk.Label(dialog, text="Cách xưng hô, độ dài, mức độ hài hước bạn thích (tùy chọn)",
                 bg=BG, fg=MUTED).pack(anchor="w", padx=20, pady=(10, 2))
        persona_note = tk.Text(dialog, height=3, wrap="word", font=("Segoe UI", 10),
                               bg=PANEL, fg=TEXT, insertbackground=ACCENT,
                               highlightthickness=1, highlightbackground=BORDER,
                               highlightcolor=ACCENT, padx=7, pady=5)
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
        self.phone_files_enabled = False
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

    def _attach_screen(self):
        if self.busy:
            return
        if sys.platform != "win32":
            messagebox.showinfo("Chỉ hỗ trợ Windows", "Nút chụp màn hình hiện chỉ chạy trên Windows.",
                                parent=self)
            return
        error = None
        try:
            self.iconify()  # Reveal the app behind Mira in the screenshot.
            self.update_idletasks()
            time.sleep(0.3)
            data = capture_primary_screen()
        except (OSError, RuntimeError) as exc:
            error = str(exc)
        finally:
            if not self.closed:
                self.deiconify()
                self.lift()
        if error:
            messagebox.showerror("Không chụp được màn hình", error, parent=self)
            return
        width, height = struct.unpack(">II", data[16:24])
        try:
            photo = tk.PhotoImage(data=base64.b64encode(data).decode("ascii"), format="png")
        except tk.TclError as exc:
            messagebox.showerror("Không xem được ảnh", str(exc), parent=self)
            return
        factor = max(1, (width + 739) // 740, (height + 399) // 400)
        preview = photo.subsample(factor, factor)
        dialog = tk.Toplevel(self)
        dialog.title("Xem trước màn hình gửi cho Mira")
        dialog.configure(bg=BG)
        dialog.transient(self)
        dialog.grab_set()
        tk.Label(dialog, text="Ảnh màn hình chính vừa chụp • " + f"{width} × {height}",
                 bg=BG, fg=TEXT, font=("Segoe UI", 12, "bold")).pack(padx=18, pady=(16, 8))
        label = tk.Label(dialog, image=preview, bg=BG)
        label.image = preview
        label.pack(padx=16)
        tk.Label(dialog, text="Chỉ gửi nếu ảnh không chứa thông tin bạn muốn giữ riêng. "
                 "Nếu dùng mô hình cloud, ảnh sẽ được gửi đến Ollama Cloud khi bạn bấm Gửi.",
                 bg=BG, fg=MUTED, wraplength=720, justify="left").pack(padx=18, pady=(9, 12))

        def finish(attach=False):
            if attach:
                self.attachment_data = data
                self.attachment_name = f"Màn hình chính {width}x{height}.png"
                self.desktop.screen_size = (width, height)
                self.attachment_var.set("Ảnh màn hình đã chọn")
                self.input.focus_set()
            dialog.destroy()

        row = tk.Frame(dialog, bg=BG)
        row.pack(pady=(0, 16))
        self._button(row, "Hủy", finish).pack(side="left", padx=6)
        self._button(row, "Đính kèm ảnh này", lambda: finish(True), primary=True).pack(side="left")
        dialog.protocol("WM_DELETE_WINDOW", finish)

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

    def _approve_desktop_action(self, description: str) -> bool:
        done = threading.Event()
        self.pending_approval = done
        decision = [False]

        def show():
            if self.closed or not self.desktop_enabled:
                done.set()
                return
            self.deiconify()
            self.lift()
            decision[0] = messagebox.askyesno(
                "Duyệt thao tác trên máy",
                "Mira đề nghị thao tác này:\n\n" + description +
                "\n\nChỉ bấm Có nếu đúng ứng dụng và đúng nội dung bạn muốn. "
                "Bạn có thể chọn Không để dừng bước này.",
                parent=self,
            )
            if decision[0] and not self.closed and self.desktop_enabled:
                self.iconify()
                self.desktop_hid_for_action = True
                self.after(300, done.set)
            else:
                done.set()

        try:
            self.after(0, show)
        except RuntimeError:
            return False
        done.wait()
        self.pending_approval = None
        return decision[0] and not self.closed and self.desktop_enabled

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
                if self.starters is not None and self.starters.winfo_exists():
                    self.starters.pack_forget()
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
        web_enabled = self.web_var.get()
        desktop = self.desktop if self.desktop_enabled else None
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
                                            persona_note=persona_note, think=think,
                                            web_enabled=web_enabled, desktop=desktop,
                                            status_reader=self._read_status_if_enabled if self.device_enabled else None,
                                            approve_action=self._approve_desktop_action if desktop else None,
                                            lessons=self.lessons if desktop else None)
                error = None
            except Exception as exc:
                answer, error = "", str(exc)

            def complete():
                if self.desktop_hid_for_action and not self.closed:
                    self.deiconify()
                    self.lift()
                    self.desktop_hid_for_action = False
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
