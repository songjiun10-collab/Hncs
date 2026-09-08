"""Shared subprocess runner for `.claude/hooks/*.py` PreToolUse end-to-end
tests - `test_hooks_test_coverage.py`, `test_hooks_branch.py`, and
`test_hooks_push_safety.py` each carried an identical `_run_hook` method
before this was extracted (byte-identical bodies, confirmed via
ast.dump comparison)."""
import json
import subprocess
import sys


def run_hook(hook_module, repo, env, command, agent_id=None):
    payload = {"tool_name": "Bash", "tool_input": {"command": command}}
    if agent_id:
        payload["agent_id"] = agent_id
        payload["agent_type"] = "general-purpose"
    proc = subprocess.run(
        [sys.executable, hook_module.__file__], cwd=repo, input=json.dumps(payload),
        env=env, capture_output=True, text=True, timeout=15,
    )
    out = json.loads(proc.stdout)
    return out["hookSpecificOutput"]["permissionDecision"]
