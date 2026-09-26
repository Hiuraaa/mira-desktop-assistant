"""A tiny original 2D anime companion drawn by Tk, without a model download."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path


STYLES = {
    "violet": ("Tím lavender", "#ab9bea", "#615494", "#d7c8ff", "#8971e5"),
    "aqua": ("Xanh ngọc", "#83d6d2", "#366b83", "#c0fff0", "#57b8bd"),
    "rose": ("Hồng đào", "#f4a8bc", "#93577e", "#ffdae1", "#dc779f"),
}


class AnimeAvatar(tk.Canvas):
    """Idle blink, thinking glow and talking mouth; optional user-supplied PNG."""

    def __init__(self, parent, *, size=64, bg="#0b1220", style="violet", image_path=None, command=None):
        super().__init__(parent, width=size, height=size, bg=bg, highlightthickness=0,
                         borderwidth=0, cursor="hand2" if command else "arrow")
        self.size = size
        self.style = style if style in STYLES else "violet"
        self.image_path = image_path
        self.state = "idle"
        self.tick = 0
        self._photo = None
        self._image_original = None
        if command:
            self.bind("<Button-1>", lambda _: command())
        self.draw()

    def configure_avatar(self, *, style=None, image_path=None):
        if style is not None:
            self.style = style if style in STYLES else "violet"
        self.image_path = image_path
        self._image_original = None
        self.draw()

    def set_state(self, state, tick):
        self.state = state
        self.tick = tick
        self.draw()

    def draw(self):
        self.delete("all")
        s = self.size / 256
        hair, shade, light, iris = STYLES[self.style][1:]
        active = self.state != "idle"

        def oval(x1, y1, x2, y2, *, fill, outline="", width=1):
            return self.create_oval(x1*s, y1*s, x2*s, y2*s, fill=fill, outline=outline, width=width*s)

        def poly(*coords, fill, outline="", smooth=False, width=1):
            return self.create_polygon(*[p*s for p in coords], fill=fill,
                                       outline=outline, smooth=smooth, width=width*s)

        def line(*coords, fill, width=2, smooth=False):
            return self.create_line(*[p*s for p in coords], fill=fill,
                                    width=max(1, width*s), smooth=smooth, capstyle="round")

        # A ring makes the character's state visible even when an imported PNG is used.
        ring = light if active and self.tick % 2 else hair
        oval(4, 4, 252, 252, fill="#202641", outline=ring, width=3 if active else 2)
        oval(17, 18, 239, 239, fill="#26324f")
        if self.state == "thinking":
            for x, y in ((31, 59), (218, 47), (225, 143)):
                line(x-5, y, x+5, y, fill=light, width=2)
                line(x, y-5, x, y+5, fill=light, width=2)

        if self.image_path:
            try:
                if self._image_original is None:
                    self._image_original = tk.PhotoImage(file=str(Path(self.image_path)))
                factor = max(1, (max(self._image_original.width(), self._image_original.height()) + self.size - 24) // (self.size - 24))
                self._photo = self._image_original.subsample(factor)
                self.create_image(self.size//2, self.size//2, image=self._photo)
                return
            except (OSError, tk.TclError):
                self._image_original = None
                self._photo = None

        bob = -3 if self.tick % 6 in (2, 3) and self.size > 100 else 0
        # Hair silhouette, shoulders and sailor-style collar.
        oval(56, 40+bob, 202, 225+bob, fill=shade)
        poly(52, 138+bob, 70, 206+bob, 54, 236+bob, 106, 225+bob,
             94, 126+bob, fill=hair, smooth=True)
        poly(206, 132+bob, 193, 220+bob, 207, 236+bob, 161, 228+bob,
             164, 121+bob, fill=hair, smooth=True)
        oval(38, 186+bob, 218, 255, fill="#222f50")
        poly(83, 210+bob, 128, 248+bob, 170, 210+bob, 159, 196+bob,
             94, 197+bob, fill="#f6f1ff")
        poly(96, 195+bob, 129, 227+bob, 161, 195+bob, 169, 220+bob,
             129, 247+bob, 88, 219+bob, fill="#7e6bb5")
        oval(107, 228+bob, 148, 249+bob, fill=iris)
        poly(119, 202+bob, 139, 202+bob, 129, 235+bob, fill=light)
        # Face, side locks, fringe and a small ribbon in her hair.
        oval(73, 67+bob, 183, 204+bob, fill="#ffdfd2", outline="#e6bcb6", width=1)
        oval(66, 132+bob, 84, 156+bob, fill="#f7c9c2")
        oval(173, 132+bob, 191, 156+bob, fill="#f7c9c2")
        poly(68, 83+bob, 57, 133+bob, 70, 194+bob, 95, 178+bob,
             84, 102+bob, fill=hair, smooth=True)
        poly(188, 80+bob, 201, 126+bob, 188, 195+bob, 165, 180+bob,
             172, 97+bob, fill=hair, smooth=True)
        poly(64, 103+bob, 66, 61+bob, 103, 43+bob, 174, 53+bob,
             192, 103+bob, 168, 100+bob, 150, 114+bob,
             135, 80+bob, 107, 112+bob, 96, 96+bob, fill=hair, smooth=True)
        poly(102, 56+bob, 131, 60+bob, 90, 108+bob, fill=light)
        poly(175, 54+bob, 156, 76+bob, 164, 105+bob, fill=light)
        poly(155, 62+bob, 191, 56+bob, 178, 81+bob, fill="#f1ecff")
        poly(155, 62+bob, 188, 40+bob, 178, 81+bob, fill=iris)
        oval(173, 57+bob, 183, 67+bob, fill=light)
        blink = self.tick % 16 == 0 and self.state != "speaking"
        if blink:
            line(95, 139+bob, 117, 139+bob, fill=shade, width=4)
            line(143, 139+bob, 165, 139+bob, fill=shade, width=4)
        else:
            for x in (94, 143):
                oval(x, 123+bob, x+24, 153+bob, fill="#fff8f4")
                oval(x+5, 127+bob, x+19, 151+bob, fill=iris)
                oval(x+9, 129+bob, x+17, 146+bob, fill="#272344")
                oval(x+10, 129+bob, x+15, 135+bob, fill="white")
                line(x-2, 129+bob, x+22, 128+bob, fill=shade, width=3)
        oval(89, 157+bob, 110, 166+bob, fill="#f1b6bd")
        oval(151, 157+bob, 172, 166+bob, fill="#f1b6bd")
        oval(127, 156+bob, 133, 160+bob, fill="#edbcb3")
        if self.state == "speaking" and self.tick % 2:
            oval(122, 169+bob, 139, 184+bob, fill="#9d4a66")
            oval(127, 177+bob, 135, 182+bob, fill="#ffc7cc")
        else:
            line(122, 176+bob, 129, 179+bob, 137, 175+bob, fill="#ad647c", width=2, smooth=True)
        oval(33, 55, 38, 60, fill=light)
        oval(217, 93, 224, 100, fill=light)
