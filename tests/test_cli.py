import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class CLIEncodingTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "studypet", *args],
            cwd=Path(__file__).resolve().parents[1],
            env={**os.environ, "PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"},
            capture_output=True,
            encoding="utf-8",
            check=False,
        )

    def test_help_works_with_legacy_output_encoding(self):
        result = self.run_cli("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("本地任务工具", result.stdout)

    def test_unicode_task_roundtrip_and_error_with_legacy_output_encoding(self):
        with tempfile.TemporaryDirectory() as directory:
            db = str(Path(directory) / "tasks.sqlite3")
            added = self.run_cli(
                "--db", db, "add", "阅读论文", "--due", "2026-11-14T19:00:00+08:00"
            )
            self.assertEqual(added.returncode, 0, added.stderr)
            listed = self.run_cli("--db", db, "list")
            self.assertEqual(listed.returncode, 0, listed.stderr)
            self.assertEqual(json.loads(listed.stdout)[0]["title"], "阅读论文")
            invalid = self.run_cli(
                "--db", db, "add", "无时区", "--due", "2026-11-14T19:00:00"
            )
            self.assertEqual(invalid.returncode, 2)
            self.assertIn("时间必须包含时区", invalid.stderr)
