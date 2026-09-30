"""Real desktop bridge with synthetic data and an offline test agent for UI QA."""

from __future__ import annotations

import json
import time

from mira.gui import MiraApp
from mira.studio import DesktopStudio


class OfflineAgent:
    client = None

    def __init__(self):
        self.client = self

    def list_models(self):
        return ["qwen3:4b", "qwen3-vl:4b"]

    def respond(self, text, _history, _model, _name, memories, *_args, on_token=None, **_kwargs):
        if "Cobalt" in text and "18h" in memories:
            answer = "Theo nguồn Dự án Cobalt, robot dùng Python và cần sạc lúc 18h."
        elif text.startswith("Tôi thích"):
            answer = "Mình ghi nhận rồi. Bạn có thể duyệt điều này trong **Bộ nhớ** nhé."
        else:
            answer = ("Mình sẽ chia việc thành những bước ngắn, dễ bắt đầu.\n\n"
                      "1. Chọn một việc quan trọng cho hôm nay.\n2. Dành 15 phút bắt đầu việc đó.\n"
                      "3. Ghi lại điều còn vướng để mình cùng xử lý.\n\nBạn đang muốn ưu tiên điều gì?")
        if on_token:
            for offset in range(0,len(answer),14):
                on_token(answer[offset:offset+14])
                time.sleep(.025)
        return answer


def main():
    app = MiraApp(studio=True)
    app.agent = OfflineAgent()
    app.memories.add("Tôi thích câu trả lời ngắn gọn, dễ bắt đầu.")
    app.memories.add("Tôi đang học Python và làm trợ lý Mira.")
    app.learning.add_source("Dự án Cobalt", "Cobalt dùng Python để điều khiển robot. Pin robot cần sạc lúc 18h.")
    app.learning.study(busy=False, force=True)
    app.studio = DesktopStudio(app)
    app.withdraw()
    app.studio.server.start()
    app.after(40, app.studio._pump)
    app.after(180_000, app._close)
    print(json.dumps({"url":app.studio.server.url}),flush=True)
    app.mainloop()


if __name__ == "__main__":
    main()
