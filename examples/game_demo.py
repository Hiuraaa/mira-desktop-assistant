"""Small playable Tic Tac Toe adapter for Mira's localhost game connector."""

from __future__ import annotations

import json
import os
import tkinter as tk
import urllib.error
import urllib.request


GAME = "Cờ caro 3x3"
PORT = os.environ.get("MIRA_GAME_PORT", "")
KEY = os.environ.pop("MIRA_GAME_KEY", "")


class Demo(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Cờ caro · bạn X, Mira O")
        self.geometry("410x490")
        self.configure(bg="#111a2b")
        self.board = [""] * 9
        self.waiting = False
        self.finished = False
        self.event_id = ""
        self.generation = 0
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        tk.Label(self, text="Bạn X · Mira O", bg="#111a2b", fg="#b5a0ff",
                 font=("Segoe UI", 19, "bold")).pack(pady=(18, 7))
        self.status = tk.StringVar(value="Chọn ô đầu tiên để chơi.")
        tk.Label(self, textvariable=self.status, bg="#111a2b", fg="white",
                 wraplength=370, font=("Segoe UI", 10)).pack(pady=(0, 12))
        grid = tk.Frame(self, bg="#111a2b")
        grid.pack()
        self.cells = []
        for i in range(9):
            button = tk.Button(grid, text="", font=("Segoe UI", 23, "bold"), width=3,
                               height=1, bg="#24344d", fg="white", relief="flat",
                               command=lambda index=i: self.play(index))
            button.grid(row=i // 3, column=i % 3, padx=5, pady=5)
            self.cells.append(button)
        controls = tk.Frame(self, bg="#111a2b")
        controls.pack(pady=16)
        tk.Button(controls, text="Gửi lại lượt Mira", command=self.retry,
                  bg="#544b82", fg="white").pack(side="left", padx=5)
        tk.Button(controls, text="Chơi ván mới", command=self.restart,
                  bg="#544b82", fg="white").pack(side="left", padx=5)
        self._api("POST", "/register", {"game": GAME, "actions": [{
            "name": "play_cell", "description": "Đặt quân O vào một ô trống của bàn 3x3",
            "options": [str(i) for i in range(1, 10)]}]})

    def _api(self, method, path, payload=None):
        request = urllib.request.Request(
            f"http://127.0.0.1:{PORT}{path}", method=method,
            headers={"X-Mira-Game-Key": KEY, "Content-Type": "application/json"},
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None)
        with self.opener.open(request, timeout=3) as response:
            return json.load(response)

    def state(self):
        lines = [" ".join(self.board[i:i + 3][j] or str(i + j + 1) for j in range(3))
                 for i in (0, 3, 6)]
        return "Bàn cờ (số là ô trống):\n" + "\n".join(lines) + "\nBạn X, Mira O."

    def outcome(self):
        for a, b, c in ((0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7),
                        (2, 5, 8), (0, 4, 8), (2, 4, 6)):
            if self.board[a] and self.board[a] == self.board[b] == self.board[c]:
                return self.board[a]
        return "Hòa" if all(self.board) else ""

    def post(self, context, *, choose=False):
        if self.finished and choose:
            return
        choices = [str(i + 1) for i, value in enumerate(self.board) if not value]
        payload = {"game": GAME, "context": context, "state": self.state(),
                   "available": {"play_cell": choices} if choose and choices else {}}
        try:
            self.event_id = self._api("POST", "/event", payload)["id"]
            if choose:
                self.status.set("Đang chờ Mira chọn O. Mở Mira → Chơi game với Mira → Cho Mira phản ứng, hoặc bật tự nhận xét.")
                self.after(750, self.poll)
        except (OSError, ValueError, KeyError, urllib.error.HTTPError) as exc:
            self.status.set("Không gửi được lượt game: " + str(exc)[:100])

    def play(self, index):
        if self.finished or self.waiting or self.board[index]:
            return
        self.board[index] = "X"
        self.cells[index].configure(text="X", fg="#8cdaeb")
        result = self.outcome()
        if result:
            self.finish(result)
        else:
            self.waiting = True
            self.status.set("Đã đi X; đang gửi trạng thái cho Mira…")
            generation = self.generation
            self.after(800, lambda: self.post(f"Người chơi vừa đi X ở ô {index + 1}; tới lượt Mira.", choose=True)
                       if generation == self.generation and self.waiting else None)

    def poll(self):
        if not self.waiting or not self.event_id or self.finished:
            return
        try:
            answer = self._api("GET", "/action?id=" + self.event_id)
            if answer["status"] == "chosen":
                action = answer["action"]
                index = int(action["choice"]) - 1
                if action["name"] != "play_cell" or not 0 <= index < 9 or self.board[index]:
                    self.status.set("Nước đi không còn hợp lệ. Bấm Gửi lại lượt Mira.")
                    return
                self.board[index] = "O"
                self.cells[index].configure(text="O", fg="#b5a0ff")
                self.waiting = False
                result = self.outcome()
                if result:
                    self.finish(result)
                else:
                    self.status.set("Mira đã đi O. Đến lượt bạn chọn X.")
                    generation = self.generation
                    self.after(800, lambda: self.post(f"Mira vừa đi O ở ô {index + 1}.")
                               if generation == self.generation else None)
                return
            if answer["status"] in ("denied", "expired", "delivered"):
                self.status.set("Lượt game đã bị từ chối hoặc hết hạn. Bấm Gửi lại lượt Mira nếu muốn tiếp tục.")
                return
            self.after(800, self.poll)
        except (OSError, ValueError, KeyError, urllib.error.HTTPError) as exc:
            self.status.set("Mất kết nối Mira: " + str(exc)[:100])

    def retry(self):
        if self.waiting and not self.finished:
            generation = self.generation
            self.after(800, lambda: self.post("Gửi lại lượt Mira; bàn cờ không đổi.", choose=True)
                       if generation == self.generation and self.waiting else None)

    def finish(self, result):
        self.finished = True
        self.waiting = False
        self.status.set("Bạn thắng!" if result == "X" else "Mira thắng!" if result == "O" else "Hòa nhau!")
        generation = self.generation
        self.after(800, lambda: self.post("Kết quả ván: " + self.status.get())
                   if generation == self.generation else None)

    def restart(self):
        self.generation += 1
        self.board = [""] * 9
        self.waiting = self.finished = False
        self.event_id = ""
        for cell in self.cells:
            cell.configure(text="")
        self.status.set("Ván mới: chọn ô đầu tiên để chơi X.")


if __name__ == "__main__":
    if not PORT.isdecimal() or not KEY:
        raise SystemExit("Hãy mở trò mẫu từ Mira → Chơi game với Mira.")
    Demo().mainloop()
