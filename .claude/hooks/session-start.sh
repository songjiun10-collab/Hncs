#!/bin/bash
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# tests/CLAUDE.md documents 12 pre-existing sandbox errors from missing
# gdown/torch/tkinter - this installs them so the full suite can run.
#
# tkinter needs a version-matched package, not the generic python3-tk -
# this environment's `python3` is a non-system build (/usr/local/bin,
# deadsnakes-provisioned), and Ubuntu's python3-tk attaches to the
# system Python (3.12 here) rather than whatever `python3` resolves to,
# so `import tkinter` still fails after installing the generic package.
PYVER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
apt-get update -qq && apt-get install -y -qq "python${PYVER}-tk" >/dev/null

pip install -q -r "$CLAUDE_PROJECT_DIR/requirements.txt"
