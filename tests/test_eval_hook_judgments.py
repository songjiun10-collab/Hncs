"""tools/eval_hook_judgments.py 테스트 - decision_kind별 outcome 분류
(deny->blocked, ask->ask_unknown, 나머지는 git log 기반 revert 탐지),
min-N 게이트가 표본 부족일 때 rate/verdict를 절대 안 내는지, 실제 임시
git repo에서 revert 탐지가 진짜로 동작하는지, CLI가 learning_data.jsonl
에 정상적으로 기록하는지 확인. git 호출은 순수 함수 테스트에서는
@patch로 모킹(tests/CLAUDE.md의 "디코드 레이어는 모킹" 관례), revert
탐지만 별도로 실제 git repo로 end-to-end 확인한다."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from tools import eval_hook_judgments as ehj


def _entry(hook, severity, decision_kind, self_severity, confidence,
           target="x.py", ts=None, overridden=False):
    ts = ts or datetime.now(timezone.utc)
    return {
        "timestamp": ts.isoformat(timespec="seconds"),
        "hook": hook, "severity": severity, "overridden": overridden,
        "reason": "reason", "decision_kind": decision_kind, "target": target,
        "decision": {"self_severity": self_severity, "confidence": confidence,
                      "reason": "r", "expected_risk": "e"},
    }


class TestSignTestP(unittest.TestCase):
    def test_equal_wins_losses_p_is_one(self):
        self.assertAlmostEqual(ehj._sign_test_p(5, 5), 1.0)

    def test_all_wins_small_p(self):
        self.assertLess(ehj._sign_test_p(20, 0), 0.01)

    def test_zero_total_returns_one(self):
        self.assertEqual(ehj._sign_test_p(0, 0), 1.0)


class TestOverUnderMatch(unittest.TestCase):
    def test_over_when_self_severity_higher(self):
        entry = {"severity": "LOW", "decision": {"self_severity": "HIGH"}}
        self.assertEqual(ehj._over_under_match(entry), "over")

    def test_under_when_self_severity_lower(self):
        entry = {"severity": "CRITICAL", "decision": {"self_severity": "MEDIUM"}}
        self.assertEqual(ehj._over_under_match(entry), "under")

    def test_match_when_equal(self):
        entry = {"severity": "HIGH", "decision": {"self_severity": "HIGH"}}
        self.assertEqual(ehj._over_under_match(entry), "match")

    def test_unknown_severity_returns_none(self):
        entry = {"severity": "HIGH", "decision": {"self_severity": "NOT_A_SEVERITY"}}
        self.assertIsNone(ehj._over_under_match(entry))


class TestClassifyOutcome(unittest.TestCase):
    def test_deny_is_blocked(self):
        entry = _entry("h", "HIGH", "deny", "HIGH", 0.5)
        self.assertEqual(ehj.classify_outcome(entry), ehj._OUTCOME_BLOCKED)

    def test_ask_is_ask_unknown(self):
        entry = _entry("h", "HIGH", "ask", "HIGH", 0.5)
        self.assertEqual(ehj.classify_outcome(entry), ehj._OUTCOME_ASK_UNKNOWN)

    def test_still_inside_window_is_pending(self):
        entry = _entry("h", "MEDIUM", "override", "MEDIUM", 0.5,
                        ts=datetime.now(timezone.utc) - timedelta(hours=1))
        self.assertEqual(
            ehj.classify_outcome(entry, revert_window_hours=72),
            ehj._OUTCOME_PENDING)

    def test_no_commits_found_is_no_commit_signal(self):
        entry = _entry("h", "MEDIUM", "override", "MEDIUM", 0.5,
                        ts=datetime.now(timezone.utc) - timedelta(hours=100))
        with patch.object(ehj, "commits_touching", return_value=[]), \
             patch.object(ehj, "commits_since", return_value=[]):
            self.assertEqual(
                ehj.classify_outcome(entry, revert_window_hours=72),
                ehj._OUTCOME_NO_COMMIT_SIGNAL)

    def test_reverting_commit_found_is_reverted(self):
        entry = _entry("h", "MEDIUM", "override", "MEDIUM", 0.5,
                        ts=datetime.now(timezone.utc) - timedelta(hours=100))
        with patch.object(ehj, "commits_touching", return_value=[]), \
             patch.object(ehj, "commits_since", return_value=[("sha1", "fix: x")]), \
             patch.object(ehj, "find_reverting_commit", return_value="sha2"):
            self.assertEqual(
                ehj.classify_outcome(entry, revert_window_hours=72),
                ehj._OUTCOME_REVERTED)

    def test_no_reverting_commit_is_not_reverted(self):
        entry = _entry("h", "MEDIUM", "override", "MEDIUM", 0.5,
                        ts=datetime.now(timezone.utc) - timedelta(hours=100))
        with patch.object(ehj, "commits_touching", return_value=[]), \
             patch.object(ehj, "commits_since", return_value=[("sha1", "fix: x")]), \
             patch.object(ehj, "find_reverting_commit", return_value=None):
            self.assertEqual(
                ehj.classify_outcome(entry, revert_window_hours=72),
                ehj._OUTCOME_NOT_REVERTED)

    def test_unparseable_timestamp_is_no_commit_signal(self):
        entry = _entry("h", "MEDIUM", "override", "MEDIUM", 0.5)
        entry["timestamp"] = "not a timestamp"
        self.assertEqual(ehj.classify_outcome(entry), ehj._OUTCOME_NO_COMMIT_SIGNAL)


class TestComputeCalibration(unittest.TestCase):
    def _events(self, n, self_severity="HIGH", severity="HIGH"):
        return [_entry("h", severity, "deny", self_severity, 0.5) for _ in range(n)]

    def test_below_min_n_returns_insufficient(self):
        events = self._events(3)
        calibration = ehj.compute_calibration(events, min_n=20)
        self.assertIsNone(calibration["severity_calibration"]["p_value"])
        self.assertIn("표본 부족", calibration["severity_calibration"]["verdict"])

    def test_at_or_above_min_n_returns_verdict(self):
        # deny -> blocked, not "determinable" (reverted/not_reverted only) -
        # use log_and_allow + mock git so these count as determinable.
        events = [_entry("h", "HIGH", "log_and_allow", "HIGH", 0.5,
                          ts=datetime.now(timezone.utc) - timedelta(hours=100))
                  for _ in range(25)]
        with patch.object(ehj, "commits_touching", return_value=[]), \
             patch.object(ehj, "commits_since", return_value=[("s", "m")]), \
             patch.object(ehj, "find_reverting_commit", return_value=None):
            calibration = ehj.compute_calibration(events, min_n=20)
        self.assertEqual(calibration["n_determinable"], 25)
        self.assertIsNotNone(calibration["severity_calibration"]["p_value"])
        self.assertEqual(calibration["severity_calibration"]["match_count"], 25)

    def test_blocked_and_ask_unknown_not_counted_as_determinable(self):
        events = [_entry("h", "HIGH", "deny", "HIGH", 0.5),
                  _entry("h", "HIGH", "ask", "HIGH", 0.5)]
        calibration = ehj.compute_calibration(events, min_n=1)
        self.assertEqual(calibration["n_determinable"], 0)
        self.assertEqual(calibration["n_blocked"], 1)
        self.assertEqual(calibration["n_ask_unknown"], 1)

    def test_reverted_events_listed_regardless_of_sample_size(self):
        events = [_entry("h", "MEDIUM", "override", "MEDIUM", 0.9,
                          ts=datetime.now(timezone.utc) - timedelta(hours=100))]
        with patch.object(ehj, "commits_touching", return_value=[]), \
             patch.object(ehj, "commits_since", return_value=[("s", "m")]), \
             patch.object(ehj, "find_reverting_commit", return_value="s2"):
            calibration = ehj.compute_calibration(events, min_n=20)
        self.assertEqual(len(calibration["reverted_events"]), 1)


class TestRevertDetectionRealGitRepo(unittest.TestCase):
    """실제 임시 git repo에서 revert 탐지가 진짜로 동작하는지 -
    tests/test_hooks_branch.py의 임시 repo 패턴 재사용."""

    def setUp(self):
        self.repo = tempfile.mkdtemp()
        run = lambda *args: subprocess.run(  # noqa: E731
            args, cwd=self.repo, capture_output=True, text=True, check=True)
        run("git", "init", "-q", "-b", "main")
        run("git", "config", "user.email", "x@example.com")
        run("git", "config", "user.name", "x")
        with open(os.path.join(self.repo, "f.txt"), "w") as f:
            f.write("x")
        run("git", "add", "f.txt")
        run("git", "commit", "-q", "-m", "test: 되돌릴 커밋")
        run("git", "revert", "--no-edit", "HEAD")

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_find_reverting_commit_locates_real_revert(self):
        sha = ehj.find_reverting_commit("test: 되돌릴 커밋", repo_root=self.repo)
        self.assertIsNotNone(sha)

    def test_find_reverting_commit_none_for_unreverted_subject(self):
        sha = ehj.find_reverting_commit("never happened", repo_root=self.repo)
        self.assertIsNone(sha)

    def test_commits_since_finds_the_commit(self):
        since = (datetime.now(timezone.utc) - timedelta(hours=1)).timestamp()
        until = (datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()
        commits = ehj.commits_since(since, until, repo_root=self.repo)
        subjects = [s for _, s in commits]
        self.assertIn("test: 되돌릴 커밋", subjects)

    def test_classify_outcome_end_to_end_reports_reverted(self):
        entry = _entry("h", "MEDIUM", "override", "MEDIUM", 0.5, target="f.txt",
                        ts=datetime.now(timezone.utc) - timedelta(hours=100))
        outcome = ehj.classify_outcome(
            entry, repo_root=self.repo, revert_window_hours=0.001)
        self.assertEqual(outcome, ehj._OUTCOME_REVERTED)


class TestLoadDecisionEvents(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._violations = os.path.join(self._tmpdir, "v.jsonl")
        self._audit = os.path.join(self._tmpdir, "o.jsonl")

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_only_entries_with_decision_are_loaded(self):
        with open(self._violations, "w", encoding="utf-8") as f:
            f.write(json.dumps({"timestamp": "2026-08-16T00:00:00+00:00",
                                 "hook": "h", "severity": "HIGH"}) + "\n")
            f.write(json.dumps(_entry("h", "HIGH", "deny", "HIGH", 0.5)) + "\n")
        events = ehj.load_decision_events(self._violations, self._audit)
        self.assertEqual(len(events), 1)

    def test_override_audit_backfills_git_sha_not_double_counted(self):
        ts = "2026-08-16T00:00:00+00:00"
        entry = _entry("protect_never_touch", "CRITICAL", "override", "CRITICAL", 0.9,
                        target="brands/x.py")
        entry["timestamp"] = ts
        with open(self._violations, "w", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        with open(self._audit, "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "timestamp": ts, "rule": "protect_never_touch", "severity": "CRITICAL",
                "target": "brands/x.py", "reason": "r", "git_sha": "abc123",
                "decision": entry["decision"],
            }) + "\n")
        events = ehj.load_decision_events(self._violations, self._audit)
        self.assertEqual(len(events), 1, "override_audit는 별도 이벤트로 안 세야 함")
        self.assertEqual(events[0]["git_sha"], "abc123")


class TestCLISmoke(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._violations = os.path.join(self._tmpdir, "v.jsonl")
        self._audit = os.path.join(self._tmpdir, "o.jsonl")
        self._learning = os.path.join(self._tmpdir, "learning_data.jsonl")
        with open(self._violations, "w", encoding="utf-8") as f:
            f.write(json.dumps(_entry("h", "HIGH", "deny", "HIGH", 0.5)) + "\n")

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_cli_writes_one_learning_data_record(self):
        result = subprocess.run(
            [sys.executable, "-m", "tools.eval_hook_judgments",
             "--violations-log", self._violations,
             "--override-audit-log", self._audit,
             "--json-out", self._learning],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(os.path.exists(self._learning))
        with open(self._learning, encoding="utf-8") as f:
            records = [json.loads(line) for line in f if line.strip()]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["n_events"], 1)

    def test_no_record_flag_skips_learning_data(self):
        result = subprocess.run(
            [sys.executable, "-m", "tools.eval_hook_judgments",
             "--violations-log", self._violations,
             "--override-audit-log", self._audit,
             "--json-out", self._learning, "--no-record"],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(os.path.exists(self._learning))


if __name__ == "__main__":
    unittest.main()
