"""Editor for the small local preference dataset."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog

from .preferences import PreferenceStore
from .storage import save_json

BG = "#0b1220"
PANEL = "#19263b"
TEXT = "#f5f4ff"
MUTED = "#aeb9d0"


def open_preference_dialog(parent: tk.Tk, store: PreferenceStore, button):
    dialog = tk.Toplevel(parent)
    dialog.title("Bộ sở thích của Mira")
    dialog.geometry("780x540")
    dialog.minsize(650, 440)
    dialog.configure(bg=BG)
    dialog.transient(parent)
    tk.Label(dialog, text="Bộ dữ liệu sở thích", bg=BG, fg=TEXT,
             font=("Segoe UI", 16, "bold")).pack(anchor="w", padx=18, pady=(16, 4))
    tk.Label(dialog, text="Các quy tắc và ví dụ được lưu trên máy. Mira chọn ví dụ liên quan đến câu hỏi để trả lời hợp ý bạn.",
             bg=BG, fg=MUTED, wraplength=730, justify="left").pack(anchor="w", padx=18)
    box = tk.Listbox(dialog, font=("Segoe UI", 11), bg=PANEL, fg=TEXT,
                     selectbackground="#325976", relief="flat", activestyle="none")
    box.pack(fill="both", expand=True, padx=18, pady=12)
    displayed: list[tuple[str, dict]] = []

    def refresh():
        box.delete(0, "end")
        displayed.clear()
        for item in store.data["rules"]:
            box.insert("end", "QUY TẮC  ·  " + item["text"])
            displayed.append(("rules", item))
        for item in store.data["examples"]:
            box.insert("end", "VÍ DỤ  ·  " + item["request"])
            displayed.append(("examples", item))

    def selected():
        index = box.curselection()
        return displayed[index[0]] if index else None

    def ask_example(item=None):
        values = []
        for title, field in (("Từ khóa kích hoạt", "tags"), ("Câu hỏi mẫu", "request"),
                             ("Cách Mira nên trả lời", "ideal_answer")):
            value = simpledialog.askstring(title, title + ":", initialvalue=item.get(field, "") if item else "",
                                           parent=dialog)
            if value is None:
                return None
            values.append(value)
        return dict(zip(("tags", "request", "ideal_answer"), values))

    def add_rule():
        value = simpledialog.askstring("Quy tắc mới", "Mira nên trả lời như thế nào?", parent=dialog)
        if value is not None:
            try:
                store.add_rule(value)
                refresh()
            except (OSError, ValueError) as exc:
                messagebox.showerror("Không lưu được", str(exc), parent=dialog)

    def add_example():
        values = ask_example()
        if values:
            try:
                store.add_example(**values)
                refresh()
            except (OSError, ValueError) as exc:
                messagebox.showerror("Không lưu được", str(exc), parent=dialog)

    def edit():
        chosen = selected()
        if chosen:
            group, item = chosen
            if group == "rules":
                value = simpledialog.askstring("Sửa quy tắc", "Nội dung:", initialvalue=item["text"], parent=dialog)
                fields = {"text": value} if value is not None else None
            else:
                fields = ask_example(item)
            if fields is not None:
                try:
                    store.update(item["id"], **fields)
                    refresh()
                except (OSError, ValueError) as exc:
                    messagebox.showerror("Không sửa được", str(exc), parent=dialog)

    def remove():
        chosen = selected()
        if chosen and messagebox.askyesno("Xóa sở thích", "Xóa mục đã chọn?", parent=dialog):
            store.remove(chosen[1]["id"])
            refresh()

    def export():
        filename = filedialog.asksaveasfilename(title="Xuất bộ sở thích", initialfile="mira-preferences.json",
                                                defaultextension=".json", filetypes=[("JSON", "*.json")])
        if filename:
            try:
                save_json(Path(filename), store.data)
            except OSError as exc:
                messagebox.showerror("Không xuất được", str(exc), parent=dialog)

    def import_file():
        filename = filedialog.askopenfilename(title="Nhập bộ sở thích", filetypes=[("JSON", "*.json")])
        if filename and messagebox.askyesno("Thay bộ sở thích", "Thay các quy tắc và ví dụ hiện có?", parent=dialog):
            try:
                store.replace_from_file(Path(filename))
                refresh()
            except (OSError, ValueError) as exc:
                messagebox.showerror("Không nhập được", str(exc), parent=dialog)

    controls = tk.Frame(dialog, bg=BG)
    controls.pack(fill="x", padx=18, pady=(0, 4))
    for label, action in (("+ Quy tắc", add_rule), ("+ Ví dụ", add_example),
                          ("Sửa", edit), ("Xóa", remove)):
        button(controls, label, action).pack(side="left", padx=(0, 6))
    transfers = tk.Frame(dialog, bg=BG)
    transfers.pack(fill="x", padx=18, pady=(0, 14))
    button(transfers, "Xuất JSON", export).pack(side="left", padx=(0, 6))
    button(transfers, "Nhập JSON", import_file).pack(side="left")

    def restore():
        if messagebox.askyesno("Khôi phục mẫu", "Thay bộ sở thích hiện có bằng bản mẫu?", parent=dialog):
            try:
                store.reset()
                refresh()
            except (OSError, ValueError) as exc:
                messagebox.showerror("Không khôi phục được", str(exc), parent=dialog)

    button(transfers, "Khôi phục mẫu", restore).pack(side="right")
    refresh()
