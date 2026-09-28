"""Lightweight rounded Tk widgets for Mira's desktop window."""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont


def rounded_rectangle(canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int,
                      radius: int, *, fill: str, tag: str) -> None:
    """Draw a filled shape using only Tk's built-in canvas primitives."""
    radius = max(0, min(radius, (x2 - x1) // 2, (y2 - y1) // 2))
    if radius == 0:
        canvas.create_rectangle(x1, y1, x2, y2, fill=fill, outline="", tags=tag)
        return
    canvas.create_rectangle(x1 + radius, y1, x2 - radius, y2,
                            fill=fill, outline="", tags=tag)
    canvas.create_rectangle(x1, y1 + radius, x2, y2 - radius,
                            fill=fill, outline="", tags=tag)
    for left, top in ((x1, y1), (x2 - radius * 2, y1),
                      (x1, y2 - radius * 2), (x2 - radius * 2, y2 - radius * 2)):
        canvas.create_oval(left, top, left + radius * 2, top + radius * 2,
                           fill=fill, outline="", tags=tag)


class SoftButton(tk.Canvas):
    """A keyboard-accessible button whose surface can blend into any Tk frame."""

    def __init__(self, parent, text: str, command, *, fill: str, hover: str,
                 foreground: str, backdrop: str, compact: bool = False,
                 radius: int = 12):
        self._label = text
        self._command = command
        self._state = "normal"
        self._hover = False
        self._fill = fill
        self._hover_fill = hover
        self._foreground = foreground
        self._radius = radius
        self._pad_x = 13 if compact else 17
        self._pad_y = 8 if compact else 10
        self._font = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        width = self._font.measure(text) + self._pad_x * 2
        height = max(35 if compact else 42,
                     self._font.metrics("linespace") + self._pad_y * 2)
        super().__init__(parent, width=width, height=height, bg=backdrop,
                         bd=0, highlightthickness=0, cursor="hand2", takefocus=1)
        self.bind("<Configure>", self._paint)
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<Button-1>", lambda _: self.invoke())
        self.bind("<Return>", lambda _: self.invoke())
        self.bind("<space>", lambda _: self.invoke())
        self.bind("<FocusIn>", self._paint)
        self.bind("<FocusOut>", self._paint)

    def _enter(self, _event):
        self._hover = True
        self._paint()

    def _leave(self, _event):
        self._hover = False
        self._paint()

    def _paint(self, _event=None):
        self.delete("surface")
        width, height = self.winfo_width(), self.winfo_height()
        if width < 4 or height < 4:
            return
        fill = self._hover_fill if self._hover and self._state == "normal" else self._fill
        if self._state == "disabled":
            fill = self._fill
        if self.focus_get() == self:
            rounded_rectangle(self, 0, 0, width, height, self._radius + 1,
                              fill="#9b84ee", tag="surface")
            inset = 2
        else:
            inset = 0
        rounded_rectangle(self, inset, inset, width - inset, height - inset,
                          self._radius, fill=fill, tag="surface")
        self.create_text(width // 2, height // 2, text=self._label,
                         font=self._font, fill="#9993aa" if self._state == "disabled"
                         else self._foreground, tags="surface")

    def invoke(self):
        if self._state == "normal" and self._command:
            return self._command()
        return None

    def configure(self, cnf=None, **kw):
        if isinstance(cnf, dict):
            kw = {**cnf, **kw}
        if not kw:
            return super().configure()
        label = kw.pop("text", None)
        state = kw.pop("state", None)
        command = kw.pop("command", None)
        if label is not None:
            self._label = label
            super().configure(width=self._font.measure(label) + self._pad_x * 2)
        if state is not None:
            if state not in ("normal", "disabled"):
                raise ValueError("Unsupported button state")
            self._state = state
            super().configure(cursor="" if state == "disabled" else "hand2")
        if command is not None:
            self._command = command
        if kw:
            super().configure(**kw)
        self._paint()

    config = configure

    def cget(self, key):
        if key == "text":
            return self._label
        if key == "state":
            return self._state
        return super().cget(key)


class SoftCard(tk.Canvas):
    """Canvas surface with an inset Frame for ordinary Tk controls and labels."""

    def __init__(self, parent, *, fill: str, backdrop: str, pad_x: int = 12,
                 pad_y: int = 11, radius: int = 18, expand_content: bool = False):
        super().__init__(parent, width=120, height=40, bg=backdrop,
                         bd=0, highlightthickness=0)
        self._fill = fill
        self._radius = radius
        self._pad_x = pad_x
        self._pad_y = pad_y
        self._expand_content = expand_content
        self.content = tk.Frame(self, bg=fill)
        self._window = self.create_window(pad_x, pad_y, window=self.content,
                                          anchor="nw")
        self.content.bind("<Configure>", self._fit)
        self.bind("<Configure>", self._paint)

    def _fit(self, _event=None):
        width = self.content.winfo_reqwidth() + self._pad_x * 2
        height = self.content.winfo_reqheight() + self._pad_y * 2
        if not self._expand_content and self.winfo_reqwidth() != width:
            self.configure(width=width)
        if self.winfo_reqheight() != height:
            self.configure(height=height)

    def _paint(self, event=None):
        width = event.width if event else self.winfo_width()
        height = event.height if event else self.winfo_height()
        self.delete("surface")
        if width < 4 or height < 4:
            return
        rounded_rectangle(self, 0, 0, width, height, self._radius,
                          fill=self._fill, tag="surface")
        self.tag_lower("surface")
        if self._expand_content:
            self.itemconfigure(self._window, width=max(1, width - self._pad_x * 2))
