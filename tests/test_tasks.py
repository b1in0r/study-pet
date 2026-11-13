import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from studypet.tasks import TaskStore


class TaskStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "tasks.sqlite3"
        self.store = TaskStore(self.path)

    def test_persists_across_store_instances(self):
        task_id = self.store.add("阅读论文", datetime.fromisoformat("2026-11-14T19:00:00+08:00"))
        self.assertEqual(TaskStore(self.path).list()[0]["id"], task_id)

    def test_due_boundary_respects_timezone_and_excludes_done_and_future(self):
        cutoff = datetime.fromisoformat("2026-11-14T11:00:00+00:00")
        current = self.store.add("现在", datetime.fromisoformat("2026-11-14T19:00:00+08:00"))
        self.store.add("未来", datetime.fromisoformat("2026-11-14T19:00:01+08:00"))
        done = self.store.add("已完成", datetime.fromisoformat("2026-11-14T18:00:00+08:00"))
        self.store.complete(done)
        self.assertEqual([task["id"] for task in self.store.list(cutoff)], [current])

    def test_rejects_ambiguous_time_and_empty_title_without_saving(self):
        with self.assertRaises(ValueError):
            self.store.add("无时区", datetime(2026, 11, 14, 19))
        with self.assertRaises(ValueError):
            self.store.add("  ", datetime.fromisoformat("2026-11-14T19:00:00+08:00"))
        self.assertEqual(self.store.list(), [])

    def test_unknown_completion_does_not_change_existing_task(self):
        self.store.add("保留", datetime.fromisoformat("2026-11-14T19:00:00+08:00"))
        with self.assertRaises(ValueError):
            self.store.complete(999)
        self.assertEqual(self.store.list()[0]["status"], "pending")


if __name__ == "__main__":
    unittest.main()
