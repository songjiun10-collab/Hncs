# HNCS Hook Evolution Phase 1: 2-Agent Consensus - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` if installed by execution
> time; otherwise execute task-by-task in one session, self-reviewing
> against each task's Definition of Done before moving on. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give all 6 HIGH-tier hooks a 2-agent-consensus fast path
(agreement -> hook auto-decides, disagreement/no-data -> existing
`ask()`/subagent-deny path unchanged) and extend the Decision Record
schema with `intended_scope`/`deviation`/`human_judgment`, per the
2026-08-19 brainstorming decisions recorded in
`docs/superpowers/specs/2026-08-19-hook-evolution-design.md`.

**Architecture:** A controller dispatches two independent Agent calls
(same model, different role framing - see Task 3) *before* a guarded
HIGH-risk action, each ending its response with a `CONSENSUS-VERDICT`
marker. A new PostToolUse hook (`record_consensus_judgment.py`) parses
both markers into a shared sentinel file. The 6 existing HIGH-tier guard
hooks check that sentinel, between the existing override check and the
existing `high_tier_decision()` fallback: agreement resolves
automatically (safe->allow, risky->deny), disagreement or missing data
falls through to today's unchanged behavior. This mirrors the MEDIUM
tier's `record_agent_approval.py` -> `medium_approval()` pattern exactly,
just with two verdicts instead of one.

**Tech Stack:** Python 3 stdlib only (matches every existing hook -
`json`/`os`/`re`/`time`), `unittest` for tests (project convention, no
pytest).

## Global Constraints

- No hook may call the `Agent` tool itself - PreToolUse/PostToolUse hooks
  are synchronous stdin/stdout processes with no tool-call capability
  (confirmed via `_hook_common.py`'s existing MEDIUM-tier design and the
  spec's "부록: 구현 제약"). All two-agent dispatching is the
  controller's job, not the hook's.
- Every new sentinel file gets a fresh, matching, single-use (consumed on
  read) contract identical in shape to `sentinel_override()`/
  `medium_approval()`/`decision_record()` - 10-minute max age, rule+target
  matching, deleted on successful read. Do not invent a different
  contract for consistency's sake alone, but do not silently diverge
  either.
- Every new sentinel path must be covered by the Edit/Write bypass guard
  (Task 1.2) - the 2차 라운드 finding #8 (`.last_whole_branch_review_sha`
  unprotected) is exactly the mistake to not repeat here.
- `require_decision_or_deny()` stays the mandatory first gate for all 6
  HIGH hooks, unchanged - consensus is evaluated *after* it, same as the
  existing override check.
- Override still wins over consensus if both are present - override is a
  more deliberate, higher-friction declaration (sentinel file + reason
  text) and should not be second-guessed by an agreement/disagreement
  computed from two dispatches the controller may not have even run.
- Full test suite green (`python3 -m unittest discover -s tests`) before
  any commit, per root `CLAUDE.md`. No file in this plan is
  `apply_*`/`hybrid_engine/assets/profiles/*` - `protect_never_touch.py`
  does not apply here, no override needed for any step.
- **Open question, not resolved by this plan - flag for the user before
  Task 2 starts**: should `record_consensus_judgment.py` require
  `resolvedModel` to match opus (matching MEDIUM tier's bar), or accept
  any model? The 2026-08-19 brainstorming answers covered role/framing
  diversity but not model-tier requirement. Task 2 below defaults to
  **requiring opus for both A and B**, matching MEDIUM's existing bar and
  this project's "opus only for the higher-stakes marker mechanisms"
  precedent - but this is this plan's assumption, not a confirmed user
  decision, and should be surfaced for explicit confirmation before
  Task 2 is implemented.

---

### Task 1: `_hook_common.py` - consensus sentinel primitives + bypass guard

**Files:**
- Modify: `.claude/hooks/_hook_common.py`
- Modify: `.claude/hooks/protect_decision_record_bypass.py`
- Test: `tests/test_hooks_consensus.py` (new)

**Interfaces:**
- Produces: `write_consensus_verdict(rule, target, role, verdict, reasoning)`,
  `consensus_verdict(rule, target)` -> `None | "agree_safe" | "agree_risky" | "disagree"`,
  `allow_with_consensus(hook_name, severity, rule, target, verdicts, decision_id=None, decision=_UNSET)`.
  All three follow the existing `_UNSET`/`decision=` threading convention
  used by `allow_with_override()`/`allow_with_medium_approval()`.
- Consumes (from existing code): `_log_event()`, `_record_override()`
  (reused for the audit trail - see 1.3), `decision_record()`,
  `_DECISION_RECORD_PATH` pattern for the new `_CONSENSUS_PATH` constant.

- [ ] **Step 1.1: Write the failing tests for the sentinel contract**

```python
# tests/test_hooks_consensus.py
import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks"))


class TestConsensusVerdictSentinel(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._path = os.path.join(self._tmp, ".pending_consensus.json")
        os.environ["HNCS_HOOK_CONSENSUS_SENTINEL"] = self._path
        import _hook_common
        import importlib
        importlib.reload(_hook_common)
        self.hc = _hook_common

    def tearDown(self):
        del os.environ["HNCS_HOOK_CONSENSUS_SENTINEL"]
        if os.path.exists(self._path):
            os.remove(self._path)

    def test_single_verdict_not_enough_for_consensus(self):
        self.hc.write_consensus_verdict("protect_branch", "main", "A", "SAFE", "looks fine")
        self.assertIsNone(self.hc.consensus_verdict("protect_branch", "main"))

    def test_both_agree_safe(self):
        self.hc.write_consensus_verdict("protect_branch", "main", "A", "SAFE", "r1")
        self.hc.write_consensus_verdict("protect_branch", "main", "B", "SAFE", "r2")
        self.assertEqual(self.hc.consensus_verdict("protect_branch", "main"), "agree_safe")

    def test_both_agree_risky(self):
        self.hc.write_consensus_verdict("protect_branch", "main", "A", "RISKY", "r1")
        self.hc.write_consensus_verdict("protect_branch", "main", "B", "RISKY", "r2")
        self.assertEqual(self.hc.consensus_verdict("protect_branch", "main"), "agree_risky")

    def test_disagreement(self):
        self.hc.write_consensus_verdict("protect_branch", "main", "A", "SAFE", "r1")
        self.hc.write_consensus_verdict("protect_branch", "main", "B", "RISKY", "r2")
        self.assertEqual(self.hc.consensus_verdict("protect_branch", "main"), "disagree")

    def test_consumed_on_read(self):
        self.hc.write_consensus_verdict("protect_branch", "main", "A", "SAFE", "r1")
        self.hc.write_consensus_verdict("protect_branch", "main", "B", "SAFE", "r2")
        self.assertEqual(self.hc.consensus_verdict("protect_branch", "main"), "agree_safe")
        self.assertIsNone(self.hc.consensus_verdict("protect_branch", "main"))

    def test_mismatched_target_starts_fresh(self):
        self.hc.write_consensus_verdict("protect_branch", "main", "A", "SAFE", "r1")
        self.hc.write_consensus_verdict("protect_branch", "other-branch", "A", "SAFE", "r1b")
        # writing a different target overwrites the pending record entirely -
        # the stale "main"/A verdict is gone, not merged
        self.assertIsNone(self.hc.consensus_verdict("protect_branch", "main"))
        self.assertIsNone(self.hc.consensus_verdict("protect_branch", "other-branch"))  # only A, still waiting on B

    def test_stale_record_expires(self):
        self.hc.write_consensus_verdict("protect_branch", "main", "A", "SAFE", "r1")
        self.hc.write_consensus_verdict("protect_branch", "main", "B", "SAFE", "r2")
        data = json.load(open(self._path))
        data["timestamp"] = time.time() - 601
        json.dump(data, open(self._path, "w"))
        self.assertIsNone(self.hc.consensus_verdict("protect_branch", "main"))

    def test_same_role_overwrites_own_slot_not_merges(self):
        self.hc.write_consensus_verdict("protect_branch", "main", "A", "SAFE", "r1")
        self.hc.write_consensus_verdict("protect_branch", "main", "A", "RISKY", "r1-corrected")
        self.assertIsNone(self.hc.consensus_verdict("protect_branch", "main"))  # still only A, waiting on B
```

- [ ] **Step 1.2: Run to verify all fail** (`ModuleNotFoundError`/`AttributeError` on `write_consensus_verdict`)

Run: `python3 -m unittest tests.test_hooks_consensus -v`
Expected: FAIL - `AttributeError: module '_hook_common' has no attribute 'write_consensus_verdict'`

- [ ] **Step 1.3: Implement in `_hook_common.py`**

Add near the other sentinel-path constants (after `_DECISION_RECORD_PATH`):

```python
_CONSENSUS_PATH = os.environ.get(
    "HNCS_HOOK_CONSENSUS_SENTINEL", os.path.join(_HOOKS_DIR, ".pending_consensus.json"))
_CONSENSUS_MAX_AGE_SECONDS = 600
_CONSENSUS_ROLES = ("A", "B")
```

Add near `medium_approval()`/`write_medium_approval()`:

```python
def write_consensus_verdict(rule, target, role, verdict, reasoning):
    """Called by record_consensus_judgment.py after parsing a genuine
    CONSENSUS-VERDICT marker out of one of the two independently-dispatched
    agents' responses. `role` is "A" or "B", `verdict` is "SAFE" or
    "RISKY". If an existing pending record matches rule+target and is
    fresh, merges this role's verdict into it (so A and B can arrive in
    either order); otherwise starts a fresh record (this also means a
    verdict for a *different* target discards whatever was pending -
    same single-slot-per-target design as every other sentinel here)."""
    if role not in _CONSENSUS_ROLES:
        raise ValueError(f"role must be one of {_CONSENSUS_ROLES}")
    existing = None
    if os.path.exists(_CONSENSUS_PATH):
        try:
            with open(_CONSENSUS_PATH, encoding="utf-8") as f:
                data = json.load(f)
            age = time.time() - float(data.get("timestamp", 0))
            if (age <= _CONSENSUS_MAX_AGE_SECONDS
                    and data.get("rule") == rule and data.get("target") == target):
                existing = data
        except Exception:
            existing = None
    verdicts = dict(existing.get("verdicts", {})) if existing else {}
    verdicts[role] = {"verdict": verdict, "reasoning": reasoning}
    with open(_CONSENSUS_PATH, "w", encoding="utf-8") as f:
        json.dump({"rule": rule, "target": target, "verdicts": verdicts,
                    "timestamp": time.time()}, f)


def consensus_verdict(rule, target):
    """Checks `.pending_consensus.json` for a fresh (<=10min), matching
    (same rule+target) record with BOTH "A" and "B" verdicts present.
    Returns None if no record, stale, wrong rule/target, or only one role
    has reported yet (still consumed as _UNSET-equivalent - it just isn't
    ready). Returns "agree_safe"/"agree_risky" if both roles gave the
    same verdict, "disagree" otherwise. Consumes (deletes) the record ONLY
    when both roles are present and a verdict is returned - a lone,
    not-yet-complete record is left alone so the second role's write can
    still merge into it."""
    if not os.path.exists(_CONSENSUS_PATH):
        return None
    try:
        with open(_CONSENSUS_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    try:
        age = time.time() - float(data.get("timestamp", 0))
    except (TypeError, ValueError):
        return None
    if age > _CONSENSUS_MAX_AGE_SECONDS:
        return None
    if data.get("rule") != rule or data.get("target") != target:
        return None
    verdicts = data.get("verdicts", {})
    if not all(r in verdicts for r in _CONSENSUS_ROLES):
        return None
    try:
        os.remove(_CONSENSUS_PATH)
    except OSError:
        pass
    a, b = verdicts["A"]["verdict"], verdicts["B"]["verdict"]
    if a == b == "SAFE":
        return "agree_safe"
    if a == b == "RISKY":
        return "agree_risky"
    return "disagree"
```

Add near `allow_with_medium_approval()`:

```python
def allow_with_consensus(hook_name, severity, rule, target, verdict, decision_id=None, decision=_UNSET):
    """HIGH tier, 2-agent consensus resolved (consensus_verdict() ==
    "agree_safe" or "agree_risky"). Logs like an override - both
    violations_log.jsonl (near real denials) and override_audit.jsonl
    (tagged with the consensus outcome) - then allows or denies to match
    the agreed verdict. Only called for "agree_safe"/"agree_risky" -
    "disagree" and None fall through to the existing ask()/deny path in
    each guard hook, unchanged."""
    dr = decision_record(rule, target=target, decision_id=decision_id) if decision is _UNSET else decision
    note = f"CONSENSUS ({verdict}, rule={rule}): 2-agent independent review agreed"
    if verdict == "agree_safe":
        _log_event(hook_name, severity, note, overridden=True,
                    decision_kind="consensus_allow", target=target, decision=dr)
        _record_override(rule, severity, target, note, decision=dr)
        allow()
    else:
        _log_event(hook_name, severity, note, overridden=False,
                    decision_kind="consensus_deny", target=target, decision=dr)
        deny(hook_name, f"{note} - both independent reviewers judged this risky.",
             severity=severity, target=target, decision_id=decision_id, decision=dr)
```

- [ ] **Step 1.4: Run to verify all pass**

Run: `python3 -m unittest tests.test_hooks_consensus -v`
Expected: PASS, 8/8.

- [ ] **Step 1.5: Extend the bypass guard to cover `.pending_consensus.json`**

`protect_decision_record_bypass.py` currently hardcodes a single
protected path (`_DECISION_RECORD_PATH`). Generalize it to a list so this
new sentinel gets the same "MCP/dedicated-writer tool only, no raw
Write, no override" protection without a second near-duplicate hook file
(and without repeating the 2차 라운드 finding #8 mistake of shipping a
new sentinel with zero Edit/Write coverage):

```python
# protect_decision_record_bypass.py - replace the single-path check
from _hook_common import _CONSENSUS_PATH, _DECISION_RECORD_PATH, allow, deny

HOOK_NAME = "protect_decision_record_bypass"
SEVERITY = "CRITICAL"

_PROTECTED_SENTINELS = {
    os.path.abspath(_DECISION_RECORD_PATH): (
        "must_hook_server.py의 write_decision_record MCP 툴"),
    os.path.abspath(_CONSENSUS_PATH): (
        "record_consensus_judgment.py (PostToolUse, 실제 Agent 디스패치 응답 파싱)"),
}


def protected_sentinel_writer(file_path):
    if not file_path:
        return None
    return _PROTECTED_SENTINELS.get(os.path.abspath(file_path))


def main():
    data = read_input()
    if data.get("tool_name") not in ("Edit", "Write", "MultiEdit"):
        allow()
        return
    file_path = (data.get("tool_input") or {}).get("file_path", "")
    writer = protected_sentinel_writer(file_path)
    if writer is None:
        allow()
        return
    deny(
        HOOK_NAME,
        f"{file_path}는 {writer}로만 써야 함(2026-08-16/2026-08-19) - Write/Edit로 "
        "직접 쓰는 건 검증을 우회하는 경로라 항상 막힘, override 없음.",
        severity=SEVERITY, target=file_path,
    )


if __name__ == "__main__":
    main()
```

(`HOOK_NAME`/`SEVERITY` module-level constants and `read_input()` stay
unchanged from the existing file - only the path-check section above
changes.)

- [ ] **Step 1.6: Add a regression test for the generalized bypass guard**

Add to `tests/test_hooks_decision_record.py` (existing file, which
already end-to-end tests `protect_decision_record_bypass.py` for
`_DECISION_RECORD_PATH`) a parallel case for `_CONSENSUS_PATH`:

```python
def test_bypass_guard_also_blocks_consensus_sentinel_path(self):
    # mirrors the existing _DECISION_RECORD_PATH bypass test, targeting
    # _CONSENSUS_PATH instead
    ...  # implementer: copy the existing test's subprocess-invocation
         # shape, substitute the file path and expected deny reason text
```

- [ ] **Step 1.7: Run full suite, commit**

Run: `python3 -m unittest discover -s tests`
Expected: all green, including the 9 new/modified consensus + bypass tests.

```bash
git add .claude/hooks/_hook_common.py .claude/hooks/protect_decision_record_bypass.py \
        tests/test_hooks_consensus.py tests/test_hooks_decision_record.py
git commit -m "feat: consensus sentinel primitives + generalize bypass guard"
```

---

### Task 2: `record_consensus_judgment.py` - new PostToolUse hook

**Files:**
- Create: `.claude/hooks/record_consensus_judgment.py`
- Modify: `.claude/settings.json` (PostToolUse, `Agent` matcher block -
  add alongside `record_whole_branch_review.py`/`record_agent_approval.py`)
- Test: `tests/test_hooks_consensus.py` (append to the file from Task 1)

**Interfaces:**
- Consumes: `_hook_common.write_consensus_verdict()` (Task 1).
- Produces: nothing new consumed by later tasks except its existence in
  `settings.json`'s PostToolUse chain (Task 3's guards read the sentinel
  it writes, not this file directly).

**Marker format** (agents append this to their final response, one line,
role-specific):

```
CONSENSUS-VERDICT: <rule> :: <target> :: <role:A|B> :: <SAFE|RISKY> :: <reasoning>
```

- [ ] **Step 2.1: Confirm the opus-requirement assumption with the user**
  (see Global Constraints) before writing this file - it gates the
  `_OPUS_RE` check below being present or removed.

- [ ] **Step 2.2: Write the hook** (mirrors `record_agent_approval.py`
  exactly, two differences: the marker regex has an extra `role` capture
  group, and it calls `write_consensus_verdict` instead of
  `write_medium_approval`):

```python
#!/usr/bin/env python3
"""PostToolUse hook (matcher: Agent). Implements the 2-Agent Consensus
half of the HNCS Hook Evolution phase 1 design
(docs/superpowers/specs/2026-08-19-hook-evolution-design.md, section 5) -
watches every completed Agent dispatch's response for an explicit
consensus marker, one line anywhere in the subagent's final response:

    CONSENSUS-VERDICT: <rule> :: <target> :: <role:A|B> :: <SAFE|RISKY> :: <reasoning>

Same field-shape and matching discipline as record_agent_approval.py's
MEDIUM-APPROVE marker (see that file's docstring) - `tool_response.
content[0].text`/`resolvedModel` confirmed present on PostToolUse's Agent
matcher input via the same 2026-08-15 live-dispatch measurement.
Requires resolvedModel to be opus, same bar as MEDIUM's MEDIUM-APPROVE
marker (2026-08-19 default per this plan's Global Constraints - flagged
for confirmation, not yet a user-confirmed decision the way MEDIUM's was).

Two independent dispatches (role A, role B - different framing per the
2026-08-19 brainstorming decision, NOT different models) each produce
their own PostToolUse event and each call write_consensus_verdict()
separately - _hook_common.consensus_verdict() merges them and only
resolves once both roles have reported."""
import json
import re
import sys

from _hook_common import write_consensus_verdict

_VERDICT_RE = re.compile(
    r"^\s*CONSENSUS-VERDICT:\s*(?P<rule>[\w.-]+)\s*::\s*(?P<target>[^:]+?)\s*::\s*"
    r"(?P<role>[AB])\s*::\s*(?P<verdict>SAFE|RISKY)\s*::\s*(?P<reasoning>.+?)\s*$",
    re.MULTILINE,
)
_OPUS_RE = re.compile(r"^claude-opus-", re.IGNORECASE)


def read_input():
    return json.load(sys.stdin)


def response_text(data):
    tr = data.get("tool_response") or {}
    content = tr.get("content") or []
    parts = [c.get("text", "") for c in content
             if isinstance(c, dict) and c.get("type") == "text"]
    return "\n".join(parts)


def main():
    data = read_input()
    if data.get("tool_name") != "Agent":
        return
    tr = data.get("tool_response") or {}
    model = str(tr.get("resolvedModel") or "")
    if not _OPUS_RE.match(model):
        return  # only opus dispatches count - see module docstring

    m = _VERDICT_RE.search(response_text(data))
    if not m:
        return
    write_consensus_verdict(
        m.group("rule"), m.group("target").strip(), m.group("role"),
        m.group("verdict"), m.group("reasoning").strip())


if __name__ == "__main__":
    main()
```

**Note on `_OPUS_RE`**: uses `^claude-opus-` anchored match, not the bare
substring `re.compile(r"opus")` that `record_agent_approval.py` uses -
2026-08-18 4차 라운드 finding #1 in `.claude/hooks/README.md` documented
that substring match as a real (if low-severity, since `resolvedModel` is
runtime-controlled) code-level defect. Don't copy that bug into new code -
this is the fix already proposed in that finding's "대응 방향" applied
here first; `record_agent_approval.py`'s own regex is a separate,
pre-existing file this plan does not touch.

- [ ] **Step 2.3: Add settings.json wiring**

In `.claude/settings.json`, `"PostToolUse"` array, the existing `"matcher":
"Agent"` block (currently `record_whole_branch_review.py` +
`record_agent_approval.py`) gets a third hook appended:

```json
          {
            "type": "command",
            "command": "python3 .claude/hooks/record_consensus_judgment.py",
            "timeout": 15
          }
```

- [ ] **Step 2.4: Write subprocess end-to-end tests** (append to
  `tests/test_hooks_consensus.py`)

```python
class TestRecordConsensusJudgmentEndToEnd(unittest.TestCase):
    # mirrors tests/test_hooks_medium_approval.py's
    # TestRecordAgentApproval subprocess pattern: invoke
    # record_consensus_judgment.py via subprocess with HNCS_HOOK_*
    # env pointed at a tempdir, feed synthetic PostToolUse JSON on stdin.
    #
    # implementer: cover at minimum -
    #  - opus response with a valid role-A SAFE marker -> sentinel has
    #    verdicts={"A": {...}}, no "B" key yet
    #  - non-opus (sonnet) response with a valid marker -> no sentinel
    #    written at all
    #  - opus response with no marker -> no sentinel written
    #  - two sequential subprocess calls (role A then role B, matching
    #    rule/target) -> second call's resulting file has both roles
    pass
```

- [ ] **Step 2.5: Run full suite, commit**

Run: `python3 -m unittest discover -s tests`

```bash
git add .claude/hooks/record_consensus_judgment.py .claude/settings.json \
        tests/test_hooks_consensus.py
git commit -m "feat: record_consensus_judgment.py - 2-agent consensus PostToolUse hook"
```

---

### Task 3: Wire all 6 HIGH-tier guard hooks to the consensus fast path

**Files:**
- Modify: `.claude/hooks/protect_branch.py`
- Modify: `.claude/hooks/protect_test_coverage.py`
- Modify: `.claude/hooks/protect_experiment_integrity.py`
- Modify: `.claude/hooks/protect_reviewer_prejudging.py`
- Modify: `.claude/hooks/protect_ready_without_review.py`
- Modify: `.claude/hooks/protect_rubber_stamp_approval.py`
- Test: `tests/test_hooks_consensus.py` (append)

**Interfaces:**
- Consumes: `_hook_common.consensus_verdict()`, `allow_with_consensus()`
  (Task 1).

**The shared edit, identical shape in all 6 files**: insert a consensus
check between the existing override check and the existing
`high_tier_decision(...)` call. Using `protect_branch.py` as the
concrete example (the other 5 follow the exact same insertion pattern
around their own existing `override_reason = ...` / `high_tier_decision(...)`
lines):

```python
# protect_branch.py, current tail of main():
    override_reason = bash_override(HOOK_NAME, command)
    if override_reason:
        allow_with_override(HOOK_NAME, SEVERITY, HOOK_NAME, branch, override_reason,
                             decision=decision)
        return

    high_tier_decision(
        HOOK_NAME, SEVERITY,
        f"{reason} To override: add a trailing `# HNCS-OVERRIDE: "
        f"{HOOK_NAME}: <reason>` comment to the command.",
        data, target=branch, decision=decision,
    )
```

becomes:

```python
    override_reason = bash_override(HOOK_NAME, command)
    if override_reason:
        allow_with_override(HOOK_NAME, SEVERITY, HOOK_NAME, branch, override_reason,
                             decision=decision)
        return

    verdict = consensus_verdict(HOOK_NAME, branch)
    if verdict in ("agree_safe", "agree_risky"):
        allow_with_consensus(HOOK_NAME, SEVERITY, HOOK_NAME, branch, verdict, decision=decision)
        return

    high_tier_decision(
        HOOK_NAME, SEVERITY,
        f"{reason} To override: add a trailing `# HNCS-OVERRIDE: "
        f"{HOOK_NAME}: <reason>` comment to the command.",
        data, target=branch, decision=decision,
    )
```

Plus the import line in each file gains `consensus_verdict,
allow_with_consensus` (alphabetical, matching each file's existing
import-sort convention).

- [ ] **Step 3.1**: Apply this insertion to `protect_branch.py`
  (`target=branch`), `protect_test_coverage.py` (`target=target`),
  `protect_experiment_integrity.py` (`target=file_path`),
  `protect_reviewer_prejudging.py` (`target=target`),
  `protect_rubber_stamp_approval.py` (`target=target`) - each using that
  file's own existing target variable name, right before that file's own
  existing `high_tier_decision(...)` call.

- [ ] **Step 3.2**: `protect_ready_without_review.py` is the one
  structural outlier - its target is `f"{owner}/{repo}#{pullNumber}"` and
  it's triggered by `mcp__github__update_pull_request`, not `Bash`/`Agent`,
  but its override-check-then-`high_tier_decision()` tail has the exact
  same shape as the other 5, so the same insertion pattern applies
  verbatim with `target=target` (the variable it already builds).

- [ ] **Step 3.3: Write per-hook consensus tests** (append to
  `tests/test_hooks_consensus.py`) - one test per hook confirming
  `agree_safe` allows and `agree_risky` denies without reaching
  `ask()`/subagent-deny, e.g.:

```python
class TestProtectBranchConsensusFastPath(unittest.TestCase):
    # subprocess-invoke protect_branch.py (HNCS_HOOK_* env into a tempdir
    # + a real git repo checked out to a non-default branch, matching
    # the existing tests/test_hooks_branch.py tempfile.mkdtemp()+git init
    # pattern), pre-seed a decision record AND a consensus sentinel with
    # both roles agreeing "SAFE", then assert permissionDecision=="allow"
    # and no ask()-shaped output.
    #
    # implementer: repeat for protect_test_coverage.py,
    # protect_experiment_integrity.py, protect_reviewer_prejudging.py,
    # protect_ready_without_review.py, protect_rubber_stamp_approval.py -
    # 6 hooks x (agree_safe allows, agree_risky denies, disagree falls
    # through to existing ask()/deny) = 18 cases minimum.
    pass
```

- [ ] **Step 3.4: Run full suite, commit**

Run: `python3 -m unittest discover -s tests`

```bash
git add .claude/hooks/protect_branch.py .claude/hooks/protect_test_coverage.py \
        .claude/hooks/protect_experiment_integrity.py .claude/hooks/protect_reviewer_prejudging.py \
        .claude/hooks/protect_ready_without_review.py .claude/hooks/protect_rubber_stamp_approval.py \
        tests/test_hooks_consensus.py
git commit -m "feat: wire all 6 HIGH-tier hooks to the 2-agent consensus fast path"
```

---

### Task 4: Controller workflow doc (how to actually invoke 2-agent consensus)

**Files:**
- Modify: `.claude/hooks/README.md` (new subsection under "심각도 4단계"'s
  HIGH bullet, plus a new guard-list-adjacent note)
- Modify: root `CLAUDE.md`'s Controller section (one line, cross-reference
  only - do not duplicate the mechanism, matching this project's existing
  "not duplicated here to avoid drift" convention already used for the
  Never-touch hook cross-reference)

**Interfaces:** none (docs only).

The mechanism from Task 1-3 is inert until a controller actually
dispatches two agents with the right marker instructions before a
HIGH-risk action - this task documents exactly how, so it's discoverable
the same way MEDIUM-APPROVE already is.

- [ ] **Step 4.1**: Add to `.claude/hooks/README.md`'s HIGH bullet (심각도
  4단계 section), immediately after the existing "6개가 이 등급" sentence,
  a new paragraph:

```
**2-Agent Consensus 경로(2026-08-19, phase 1)**: 위 6개 훅 전부, ask()/
서브에이전트-deny로 가기 전에 먼저 consensus sentinel을 확인한다. 컨트롤러가
가드된 액션 **전에** 같은 모델(기본 opus)로 서로 다른 프레이밍의 Agent 2개를
독립 디스패치하면(A: "승인 기준으로 검토해라", B: "거부 사유를 적극적으로
찾아라" - 정확한 문구는 상황별) - 각자 응답 끝에
`CONSENSUS-VERDICT: <rule> :: <target> :: <role:A|B> :: <SAFE|RISKY> :: <reasoning>`을
붙이도록 지시 - `record_consensus_judgment.py`(PostToolUse, Agent matcher)가
둘 다 파싱해서 합의 시 자동 allow/deny, 불일치 시 기존 ask()/deny로 그대로
fallback한다. 안 쓰면(디스패치를 아예 안 하면) 오늘까지의 동작과 완전히
동일 - 순수 추가 기능, 기존 경로 안 건드림.
```

- [ ] **Step 4.2**: Add one cross-reference line to root `CLAUDE.md`'s
  Controller section (after the existing "Never tell a reviewer..."
  bullet): `- HIGH-risk 액션 전 2-agent consensus 디스패치 절차는
  `.claude/hooks/README.md`의 "2-Agent Consensus 경로" 참고.`

- [ ] **Step 4.3: Commit**

```bash
git add .claude/hooks/README.md CLAUDE.md
git commit -m "docs: document the 2-agent consensus controller workflow"
```

---

### Task 5: Decision Record schema extension (`intended_scope`/`deviation`/`human_judgment`)

**Files:**
- Modify: `.claude/hooks/_hook_common.py` (`write_decision_record()`,
  `decision_record()`, `_decision_payload()`)
- Modify: `.claude/hooks/must_hook_server.py` (new optional MCP tool
  parameters)
- Test: `tests/test_hooks_decision_record.py` (extend existing tests)

**Interfaces:**
- Modifies (backward-compatible, all new params optional/default `None`):
  `write_decision_record(rule, severity, confidence, reason, expected_risk,
  target=None, decision_id=None, intended_scope=None, deviation=None)`.
  `human_judgment` is deliberately NOT a `write_decision_record()`
  parameter - per the 2026-08-19 brainstorming decision it's populated
  later (a human reviewing the outcome, not the agent self-reporting at
  decision time) - it belongs in `tools/eval_hook_judgments.py`'s output
  schema (phase 2 concern, not this plan) or a manual log-annotation
  step, not the sentinel write path.

- [ ] **Step 5.1**: Extend `write_decision_record()`'s signature and the
  dict it dumps to include `intended_scope`/`deviation` (both optional,
  default `None`, no validation beyond existing `confidence`/target-or-id
  checks - these are free-text like `reason`/`expected_risk`).

- [ ] **Step 5.2**: Extend `_decision_payload()` (the function that
  shapes what gets attached to `violations_log.jsonl`/
  `override_audit.jsonl` entries) to include `intended_scope`/`deviation`
  when present on the stored record, `None` when absent - same
  optional-field, backward-compatible pattern already used for the
  existing 4 fields.

- [ ] **Step 5.3**: Extend `must_hook_server.py`'s
  `_write_decision_record_tool` with two new optional `Annotated`
  parameters (`intended_scope: Optional[str] = None`,
  `deviation: Optional[str] = None`), threaded through to the underlying
  `write_decision_record()` call - same pydantic `Field` pattern as the
  existing optional `target`/`decision_id` params (no `min_length`
  constraint, since these are optional and a caller who has nothing to
  say about scope/deviation should be able to omit them entirely, not be
  forced into an empty string).

- [ ] **Step 5.4**: Extend `tests/test_hooks_decision_record.py`'s
  existing sentinel-contract tests with cases for: writing with
  `intended_scope`/`deviation` present -> both appear in
  `_decision_payload()`'s output; writing without them -> both come back
  `None`, existing entries' shape is byte-identical to before this task
  (backward compatibility assertion, not just "doesn't crash").

- [ ] **Step 5.5: Run full suite, commit**

```bash
git add .claude/hooks/_hook_common.py .claude/hooks/must_hook_server.py \
        tests/test_hooks_decision_record.py
git commit -m "feat: extend Decision Record schema with intended_scope/deviation"
```

---

### Task 6: `.claude/hooks/README.md` - Decision Record section update + phase-1 closeout note

**Files:**
- Modify: `.claude/hooks/README.md`

- [ ] **Step 6.1**: In the "Decision Record" section's MCP-tool call
  example block, add the two new optional parameters with a one-line
  note that they're optional and what they're for (`intended_scope`:
  뭘 하려고 했는지 자기선언, `deviation`: 실제 행동이 그 범위에서 얼마나
  벗어났는지 자기평가) - matching the existing terse per-field
  descriptions already there for `severity`/`confidence`/`reason`.
- [ ] **Step 6.2**: Add a short "Phase 1 완료 (2026-08-19)" note near the
  top of the file (dated correction convention, not a rewrite) pointing
  at `docs/superpowers/specs/2026-08-19-hook-evolution-design.md` and
  this plan file, noting phase 2 (blanket Agent-Drift observation, opus
  hypothesis-generation tool) is deliberately not started yet.
- [ ] **Step 6.3: Commit**

```bash
git add .claude/hooks/README.md
git commit -m "docs: phase 1 closeout note + Decision Record schema doc update"
```

---

## Explicitly out of scope for this plan (phase 2)

Per the scoping decision in this plan's header:
- The opus-subagent tool that mines `learning_data.jsonl` for new-hook
  candidates (spec item 4) - depends on this phase's schema existing
  first, and is a standalone `tools/`-style script, not a hook-chain
  change, so it can be its own plan once phase 1's fields are actually
  populated by real usage.
- Blanket Agent-Drift observation across *all* tool calls (not just
  MEDIUM/HIGH/CRITICAL decision-record-gated ones) - the 2026-08-19
  brainstorming decision already narrowed this to "extend existing gated
  events only," which Task 5 delivers in full; a wider net was
  explicitly declined, not deferred.

## Self-Review

**Spec coverage**: brainstorming decision 1 (6 hooks at once) -> Task 3.
Decision 2 (same model, different framing) -> Task 2's docstring +
Task 4's controller-workflow doc (framing text itself is a
dispatch-time controller choice, not hookable - correctly left as
guidance, not code). Decision 3 (extend existing gated events) -> Task 5.
Decision 4 (opus subagent proposes, human deploys) -> explicitly out of
scope, not silently dropped (see "Explicitly out of scope" above).

**Placeholder scan**: Tasks 2.4, 3.3, 5's tests, and 1.6 contain
"implementer: ..." comments describing what to cover rather than full
literal test bodies - flagged here rather than silently passed off as
complete, per this plan's stated scoping tradeoff (core mechanism code
is complete; the more repetitive/parametrized parts of the test surface
are specified precisely enough to implement without design judgment, not
spelled out line-by-line). Everything else (all sentinel/hook/guard
production code) is complete, no placeholders.

**Type consistency**: `consensus_verdict()` return type
(`None | "agree_safe" | "agree_risky" | "disagree"`) used identically in
Task 1's tests, Task 2's docstring, and all 6 Task 3 insertions -
verified consistent across every reference above.
