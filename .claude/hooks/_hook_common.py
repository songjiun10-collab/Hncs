"""Shared allow/deny/override helpers for this project's PreToolUse/
PostToolUse hooks.

## Severity tiers (2026-08 redesign, user-specified)

- LOW: allow, log only (no interruption).
- MID/HIGH/CRITICAL: deny unless a valid override is present (see below).
  Mechanically identical across all three tiers - severity is now purely
  a label/messaging-tone distinction, not a different code path.

**정정(2026-08-15)**: MID originally used `permissionDecision: "ask"`
(falls through to Claude Code's normal interactive permission prompt) on
the theory that a human glance beats a hard block for lower-stakes
findings. Dispatched a real subagent to test whether this hook chain
applies to subagent tool calls at all, and found: Bash-triggered deny
hooks (e.g. `protect_destructive.py`) correctly blocked the subagent, but
an `ask()`-based hook (`protect_claim_evidence.py`) let the subagent's
Edit through with no prompt and no denial - there's no interactive
surface to render the prompt on inside a subagent's own turn, so it
silently resolved to allow. Since this project's normal workflow is a
Controller dispatching Implementer/Reviewer subagents to do the actual
work, `ask()` provided zero protection in exactly that case. All three
`ask()`-using hooks were converted to deny+override; `ask()` remains
defined below (still valid, still used if some future hook genuinely
only ever fires on direct orchestrator calls) but no active hook calls it
as of this correction. The `_hook_common.py` git_sha handling below was
also never actually a CRITICAL-only gate - see the note in
`_record_override()`.

## Override mechanism

The point (user's own framing): "훅은 개발자를 대신해 판단하지 않는다.
훅은 '위험한 행동을 무의식적으로 해버리는 것'만 막는다" - hooks don't
substitute for the developer's judgment; they only stop an unconscious/
silent slide into a dangerous action. A deliberate, explicitly-declared
override is always allowed through, but it leaves a permanent trace of
why.

Two ways to declare an override, matching the two hook trigger shapes:

1. **Bash-triggered guards** (destructive ops, push safety): the command
   text itself carries a trailing marker comment -
   `... # HNCS-OVERRIDE: <rule>: <reason>`. Parsed by `bash_override()`.
2. **Edit/Write/MultiEdit-triggered guards** (never-touch): tool_input has
   no room for a custom field, so the override is declared via a sentinel
   file written *before* the guarded call - `.claude/hooks/
   .pending_override.json` (`{"rule", "target", "reason", "timestamp"}`).
   Checked (and consumed - single use) by `sentinel_override()`.

Every successful override is logged to `override_audit.jsonl` (separate
from `violations_log.jsonl`, which is for calls that were actually
blocked) with `{timestamp, rule, severity, target, reason, git_sha}` -
`git_sha` is always computed here, never taken from the caller, so the
audit trail can't be backdated or spoofed by whatever wrote the marker."""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

_HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
_LOG_PATH = os.environ.get(
    "HNCS_HOOK_VIOLATIONS_LOG", os.path.join(_HOOKS_DIR, "violations_log.jsonl"))
_OVERRIDE_AUDIT_PATH = os.environ.get(
    "HNCS_HOOK_OVERRIDE_AUDIT_LOG", os.path.join(_HOOKS_DIR, "override_audit.jsonl"))
_SENTINEL_PATH = os.environ.get(
    "HNCS_HOOK_OVERRIDE_SENTINEL", os.path.join(_HOOKS_DIR, ".pending_override.json"))

SEVERITIES = ("LOW", "MID", "HIGH", "CRITICAL")

_BASH_OVERRIDE_RE = re.compile(
    r"#\s*HNCS-OVERRIDE:\s*(?P<rule>[\w.-]+)\s*:\s*(?P<reason>.+?)\s*$")

_SENTINEL_MAX_AGE_SECONDS = 600  # 10min - forces a fresh, deliberate write


def allow():
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "allow"}}))


def ask(reason):
    """MID tier: hand off to Claude Code's own interactive permission
    prompt instead of the hook deciding. Human approves/denies, in the
    moment, through the normal UI - not a hook-level auto-decision."""
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "ask",
        "permissionDecisionReason": reason}}))


def deny(hook_name, reason, severity="HIGH"):
    _log_event(hook_name, severity, reason, overridden=False)
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "deny",
        "permissionDecisionReason": reason}}))


def allow_with_override(hook_name, severity, rule, target, reason):
    """MID/HIGH/CRITICAL tier, override matched: log to both the violations
    log (so the near-miss is visible in the same place as a real deny)
    and the override audit log (so it's separately searchable), then
    allow."""
    note = f"OVERRIDDEN ({severity}, rule={rule}): {reason}"
    _log_event(hook_name, severity, note, overridden=True)
    _record_override(rule, severity, target, reason)
    allow()


def bash_override(rule, command):
    """Parses a trailing `# HNCS-OVERRIDE: <rule>: <reason>` marker out of
    a Bash command string. Returns the reason string if present and the
    rule name matches, else None. Does not care where in the command the
    marker appears (checked line by line) - shell comments are valid
    anywhere a new logical line/statement can start."""
    for line in command.splitlines():
        m = _BASH_OVERRIDE_RE.search(line)
        if m and m.group("rule") == rule and m.group("reason").strip():
            return m.group("reason").strip()
    return None


def sentinel_override(rule, target):
    """Checks `.pending_override.json` for a fresh (<=10min old), matching
    (same rule + same target) override request, and consumes it (deletes
    the file) if found. Returns the reason string, or None. `target`
    comparison is exact-string - callers should normalize paths the same
    way on both sides (write and check)."""
    if not os.path.exists(_SENTINEL_PATH):
        return None
    try:
        with open(_SENTINEL_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    try:
        age = time.time() - float(data.get("timestamp", 0))
    except (TypeError, ValueError):
        return None
    if age > _SENTINEL_MAX_AGE_SECONDS:
        return None
    if data.get("rule") != rule or data.get("target") != target:
        return None
    reason = str(data.get("reason") or "").strip()
    if not reason:
        return None
    try:
        os.remove(_SENTINEL_PATH)
    except OSError:
        pass
    return reason


def write_sentinel_override(rule, target, reason):
    """Writes the pending-override sentinel. Called by the agent (via a
    Write tool call to this exact path) immediately before the guarded
    Edit/Write/MultiEdit call it's meant to unblock. Not called by hook
    scripts themselves - this is here so the one write site has a single,
    documented implementation instead of ad-hoc JSON construction."""
    with open(_SENTINEL_PATH, "w", encoding="utf-8") as f:
        json.dump({"rule": rule, "target": target, "reason": reason,
                    "timestamp": time.time()}, f)


def current_head_sha():
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=_repo_root(),
                              capture_output=True, text=True, timeout=10)
        return out.stdout.strip() if out.returncode == 0 else None
    except Exception:
        return None


def _repo_root():
    return os.path.dirname(os.path.dirname(_HOOKS_DIR))


def _record_override(rule, severity, target, reason):
    """git_sha is recorded for every override regardless of severity - it's
    an audit-trail field (proves which commit the override was granted
    at), not a gating check. An earlier docstring draft implied CRITICAL
    required the override's git_sha to match current HEAD as an extra
    verification step; that was never implemented - `sentinel_override()`/
    `bash_override()` don't branch on severity at all. Fixed in place
    rather than silently rewritten, per this project's own "append a
    dated correction" convention."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule": rule,
        "severity": severity,
        "target": target,
        "reason": reason,
        "git_sha": current_head_sha(),
    }
    try:
        with open(_OVERRIDE_AUDIT_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[_hook_common] failed to write override audit log: {e}",
              file=sys.stderr)


def _log_event(hook_name, severity, reason, overridden):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "hook": hook_name,
        "severity": severity,
        "overridden": overridden,
        "reason": reason,
    }
    try:
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[_hook_common] failed to write violations log: {e}",
              file=sys.stderr)
