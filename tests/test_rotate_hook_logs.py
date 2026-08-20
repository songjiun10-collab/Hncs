"""tools/rotate_hook_logs.py 테스트 - retention 기간보다 오래된 항목이
월별 아카이브로 옮겨지고, 최근 항목은 활성 로그에 남는지, 여러 번
돌려도 안전한지(idempotent) 확인."""
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from tools.rotate_hook_logs import rotate


def _entry(hook, days_ago, now):
    ts = now - timedelta(days=days_ago)
    return json.dumps({"timestamp": ts.isoformat(timespec="seconds"), "hook": hook})


class TestRotateHookLogs(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.mkdtemp()
        self._log_path = os.path.join(self._dir, "violations_log.jsonl")
        self._now = datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc)

    def tearDown(self):
        shutil.rmtree(self._dir, ignore_errors=True)

    def _write(self, entries):
        with open(self._log_path, "w", encoding="utf-8") as f:
            f.write("\n".join(entries) + "\n")

    def test_recent_entries_kept_old_entries_archived(self):
        self._write([
            _entry("recent_hook", days_ago=1, now=self._now),
            _entry("old_hook", days_ago=200, now=self._now),  # 2026-01
        ])
        result = rotate(self._log_path, retention_days=90, now=self._now)
        self.assertEqual(result["kept"], 1)
        self.assertEqual(result["archived"], {"2026-01": 1})

        with open(self._log_path, encoding="utf-8") as f:
            kept = [json.loads(line) for line in f if line.strip()]
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["hook"], "recent_hook")

        archive_path = os.path.join(self._dir, "violations_log.2026-01.jsonl")
        self.assertTrue(os.path.exists(archive_path))
        with open(archive_path, encoding="utf-8") as f:
            archived = [json.loads(line) for line in f if line.strip()]
        self.assertEqual(archived[0]["hook"], "old_hook")

    def test_all_recent_nothing_archived(self):
        self._write([_entry("a", days_ago=1, now=self._now),
                     _entry("b", days_ago=10, now=self._now)])
        result = rotate(self._log_path, retention_days=90, now=self._now)
        self.assertEqual(result["kept"], 2)
        self.assertEqual(result["archived"], {})

    def test_multiple_months_split_correctly(self):
        self._write([
            _entry("jan", days_ago=220, now=self._now),   # 2026-01
            _entry("feb", days_ago=190, now=self._now),   # 2026-02
        ])
        result = rotate(self._log_path, retention_days=90, now=self._now)
        self.assertEqual(set(result["archived"]), {"2026-01", "2026-02"})

    def test_idempotent_second_run_no_op(self):
        self._write([_entry("old", days_ago=200, now=self._now)])
        rotate(self._log_path, retention_days=90, now=self._now)
        result2 = rotate(self._log_path, retention_days=90, now=self._now)
        self.assertEqual(result2["kept"], 0)
        self.assertEqual(result2["archived"], {})

    def test_unparseable_line_kept_not_dropped(self):
        with open(self._log_path, "w", encoding="utf-8") as f:
            f.write("not valid json\n")
        result = rotate(self._log_path, retention_days=90, now=self._now)
        self.assertEqual(result["kept"], 1)

    def test_missing_file_returns_empty(self):
        result = rotate(os.path.join(self._dir, "nonexistent.jsonl"), retention_days=90)
        self.assertEqual(result, {"kept": 0, "archived": {}})

    def test_appends_to_existing_archive_not_overwrite(self):
        archive_path = os.path.join(self._dir, "violations_log.2026-01.jsonl")
        with open(archive_path, "w", encoding="utf-8") as f:
            f.write(_entry("preexisting", days_ago=210, now=self._now) + "\n")
        self._write([_entry("new_old", days_ago=200, now=self._now)])
        rotate(self._log_path, retention_days=90, now=self._now)
        with open(archive_path, encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]
        self.assertEqual(len(lines), 2)
        hooks = {e["hook"] for e in lines}
        self.assertEqual(hooks, {"preexisting", "new_old"})


if __name__ == "__main__":
    unittest.main()
