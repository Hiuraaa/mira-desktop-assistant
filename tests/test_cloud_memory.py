"""The owner must opt in before a cloud exchange can replace local memories."""

import tempfile
import unittest
from pathlib import Path

from mira.cloud_memory import CloudMemoryClient, validate_cloud_url
from mira.storage import MemoryStore


class CloudMemoryTests(unittest.TestCase):
    def test_only_expected_https_worker_url_is_allowed(self):
        self.assertEqual(validate_cloud_url('https://mira-phone.owner.workers.dev/'),
                         'https://mira-phone.owner.workers.dev/api/memories')
        for url in ('http://mira-phone.owner.workers.dev/',
                    'https://mira-phone.owner.workers.dev.evil.example/',
                    'https://example.com/',
                    'https://mira-phone.owner.workers.dev/redirect',
                    'https://mira-phone.owner.workers.dev/?key=leak'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                CloudMemoryClient(url, 'long-enough-demo-key-1234567890')

    def test_invalid_remote_memory_cannot_erase_existing_local_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = MemoryStore(Path(tmp) / 'memories.json')
            store.add('Mình thích trả lời ngắn.')
            saved = list(store.items)
            with self.assertRaises(ValueError):
                store.replace([{'id': 'bad', 'text': 'value'}])
            self.assertEqual(MemoryStore(store.path).items, saved)
            remote = [{'id': '12345678-1234-4234-9234-123456789abc', 'text': 'Đang học Python'}]
            store.replace(remote)
            self.assertEqual(MemoryStore(store.path).items, remote)


if __name__ == '__main__':
    unittest.main()
