#!/usr/bin/env python3
"""PreToolUse hook (matcher: Edit|Write|MultiEdit), HIGH severity. Scoped
to `hybrid_engine/EVALUATION.md` only. hybrid_engine/CLAUDE.md's
"Statistics - non-negotiable" section: "Never call a winner from a mean
difference... CI straddles zero -> inconclusive." Three "decisive wins"
in this repo's history turned out to be noise/non-determinism/an env-var
leak - all three would have been caught by requiring a CI mention next to
the result.

Heuristic (approximate, text-pattern based like every other hook here):
if the text being added looks like it's reporting a numeric result (has
a `%` improvement figure or "ΔE"/"개선폭") but doesn't mention a
confidence interval / bootstrap anywhere nearby, flag it. This can't
verify the CI was actually computed correctly, only that *some* CI
language is present - a determined session could still write "CI: fine"
and slip past. It raises the bar against the specific failure mode this
project already hit three times (reporting a mean-difference win with no
CI check at all), not a guarantee of statistical rigor.

Override: trailing note isn't possible via Edit's tool_input, so this
uses the same sentinel-file mechanism as `protect_never_touch.py` -
write `.claude/hooks/.pending_override.json` with rule
"protect_experiment_integrity" before retrying (e.g. for an entry that's
explicitly marked inconclusive/no-result, or a correction blockquote that
doesn't report a new number)."""
import json
import os
import re
import sys

from _hook_common import allow, allow_with_override, high_tier_decision, sentinel_override

HOOK_NAME = "protect_experiment_integrity"
SEVERITY = "HIGH"

_TARGET_FILE_RE = re.compile(r"(^|/)hybrid_engine/EVALUATION\.md$")

_RESULT_CLAIM_RE = re.compile(
    r"[+-]?\d+(?:\.\d+)?\s*%|"        # +9.12%, -3.5% etc.
    r"개선폭|improvement|"
    r"ΔE00?\s*[:=]?\s*\d"             # "ΔE00 2.78" / "ΔE: 3.1" style
)
_CI_MENTION_RE = re.compile(
    r"\bCI\b|신뢰구간|bootstrap|부트스트랩|confidence interval", re.IGNORECASE)


def read_input():
    return json.load(sys.stdin)


def is_evaluation_md(path):
    return bool(_TARGET_FILE_RE.search((path or "").replace(os.sep, "/")))


def missing_ci_reason(added_text):
    """Returns a reason string if `added_text` reports a numeric result
    with no nearby CI/bootstrap mention, else None."""
    if not _RESULT_CLAIM_RE.search(added_text):
        return None
    if _CI_MENTION_RE.search(added_text):
        return None
    return (
        "This addition to hybrid_engine/EVALUATION.md reports a numeric "
        "result (%/ΔE/개선폭 pattern) with no CI/bootstrap mention nearby. "
        "hybrid_engine/CLAUDE.md: \"Never call a winner from a mean "
        "difference\" - three past \"decisive wins\" here turned out to be "
        "noise, thread non-determinism, or an env-var leak, all of which a "
        "CI check would have caught."
    )


def main():
    data = read_input()
    tool = data.get("tool_name")
    if tool not in ("Edit", "Write", "MultiEdit"):
        allow()
        return
    ti = data.get("tool_input") or {}
    file_path = ti.get("file_path", "")
    if not is_evaluation_md(file_path):
        allow()
        return

    if tool == "Write":
        added_text = ti.get("content", "")
    elif tool == "MultiEdit":
        added_text = "\n".join(e.get("new_string", "") for e in (ti.get("edits") or []))
    else:
        added_text = ti.get("new_string", "")

    reason = missing_ci_reason(added_text)
    if reason is None:
        allow()
        return

    override_reason = sentinel_override(HOOK_NAME, file_path)
    if override_reason:
        allow_with_override(HOOK_NAME, SEVERITY, HOOK_NAME, file_path, override_reason)
        return

    high_tier_decision(
        HOOK_NAME, SEVERITY,
        f"{reason} To override: write .claude/hooks/.pending_override.json "
        f'with {{"rule": "{HOOK_NAME}", "target": "{file_path}", "reason": '
        '"<reason>", "timestamp": <time.time()>}, then retry immediately.',
        data, target=file_path,
    )


if __name__ == "__main__":
    main()
