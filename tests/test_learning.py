import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mira.learning import LearningStore, _chunks
from mira.storage import MemoryStore


class LearningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = LearningStore(self.root / "learning.json")
        self.memories = MemoryStore(self.root / "memories.json")

    def tearDown(self):
        self.temp.cleanup()

    def test_only_selected_ready_sources_are_retrieved_and_reloaded(self):
        self.store.add_source("Dự án Cobalt", "Cobalt dùng Python để điều khiển robot. Pin robot cần sạc lúc 18h.")
        self.assertEqual(self.store.prompt_for("Cobalt dùng gì?"), "")
        self.store.study(busy=False, force=True)
        reloaded = LearningStore(self.store.path)
        context = reloaded.prompt_for("Cobalt dùng gì?")
        self.assertIn("Python", context)
        self.assertIn("Nguồn: Dự án Cobalt", context)
        self.assertEqual(reloaded.prompt_for("Cách nấu phở?"), "")
        self.assertLessEqual(len(context), 2400)

    def test_idle_scheduler_waits_for_opt_in_activity_and_chat(self):
        self.store.add_source("Cobalt", "Tài liệu Python cho robot Cobalt.")
        self.store.last_activity = 100
        self.assertIsNone(self.store.study(busy=False, now=500))
        self.store.configure(True, 1)
        self.assertIsNone(self.store.study(busy=True, now=500))
        self.assertIsNone(self.store.study(busy=False, now=150))
        self.assertIsNotNone(self.store.study(busy=False, now=500))
        self.assertIsNone(self.store.study(busy=False, now=520))
        self.assertIsNotNone(self.store.study(busy=False, now=560))
        self.store.configure(False, 1)
        self.assertIsNone(self.store.study(busy=False, now=700))

    def test_background_preparation_does_not_call_model_or_network(self):
        self.store.add_source("Python", "Python là ngôn ngữ lập trình.")
        with patch("urllib.request.urlopen", side_effect=AssertionError("no network")):
            report = self.store.study(busy=False, force=True)
        self.assertIn("Python", report["note"])
        self.assertEqual(self.store.snapshot()["sources"][0]["chunk_count"], 1)

    def test_explicit_user_preference_waits_for_review_and_deduplicates(self):
        self.assertTrue(self.store.observe_user("Tôi thích câu trả lời ngắn.", "chat1", self.memories))
        self.assertFalse(self.store.observe_user("Tôi thích câu trả lời ngắn.", "chat1", self.memories))
        self.assertFalse(self.store.observe_user("Hôm nay có mưa không?", "chat1", self.memories))
        self.assertEqual(self.memories.items, [])
        candidate = self.store.data["candidates"][0]
        self.assertEqual(candidate["chat_id"], "chat1")
        self.store.decide_candidate(candidate["id"], self.memories, accept=True,
                                    text="Tôi thích trả lời ngắn nhưng đủ ý.")
        self.assertEqual(self.memories.items[0]["text"], "Tôi thích trả lời ngắn nhưng đủ ý.")
        self.assertEqual(self.store.data["candidates"], [])
        self.assertEqual(MemoryStore(self.memories.path).items, self.memories.items)

    def test_sensitive_and_long_statements_do_not_become_candidates(self):
        for text in ("Nhớ rằng mật khẩu của tôi là abc123", "Tôi thích password: abc",
                     "Nhớ rằng API key của tôi là test", "Tôi thích " + "a" * 500):
            self.assertFalse(self.store.observe_user(text, "chat1", self.memories))
        self.assertTrue(self.store.observe_user("Nhớ rằng tôi đang học Python.", "chat1", self.memories))

    def test_reject_forget_and_invalid_accept_do_not_add_memory(self):
        self.store.observe_user("Tôi thích Python.", "chat1", self.memories)
        candidate = self.store.data["candidates"][0]
        with self.assertRaises(ValueError):
            self.store.decide_candidate(candidate["id"], self.memories, accept=True, text="")
        self.store.decide_candidate(candidate["id"], self.memories, accept=False)
        self.assertEqual(self.memories.items, [])
        self.assertEqual(LearningStore(self.store.path).data["candidates"], [])

    def test_remove_source_removes_retrieval_and_its_reports(self):
        source = self.store.add_source("Python", "Python được dùng cho robot.")
        self.store.study(busy=False, force=True)
        self.store.remove_source(source["id"])
        self.assertEqual(self.store.prompt_for("Python"), "")
        self.assertEqual(self.store.data["reports"], [])

    def test_size_limits_and_unbroken_text(self):
        with self.assertRaises(ValueError):
            self.store.add_source("Test", "x" * 32001)
        source = self.store.add_source("Test", "x" * 32000)
        self.store.study(busy=False, force=True)
        chunks = self.store.data["sources"][0]["chunks"]
        self.assertTrue(all(0 < len(c) <= 1400 for c in chunks))
        self.assertEqual("".join(chunks), source["text"])
        self.assertNotIn("text", self.store.snapshot()["sources"][0])
        self.assertNotIn("chunks", self.store.snapshot()["sources"][0])

    def test_failed_save_does_not_replace_in_memory_state(self):
        with patch("mira.learning.save_json", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.store.add_source("Test", "test")
        self.assertEqual(self.store.data["sources"], [])

    def test_reports_are_bounded_and_settings_survive_restart(self):
        self.store.add_source("Test", "Nội dung được chọn.")
        for _ in range(23):
            self.store.study(busy=False, force=True)
        self.store.configure(True, 15)
        reloaded = LearningStore(self.store.path)
        self.assertEqual(len(reloaded.data["reports"]), 20)
        self.assertTrue(reloaded.data["auto"])
        self.assertEqual(reloaded.data["interval"], 15)


if __name__ == "__main__":
    unittest.main()
