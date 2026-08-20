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

# mcp (added for must_hook_server.py) needs a newer pyjwt than the
# apt-provided python3-jwt (2.7.0-1ubuntu0.1) ships - that package has no
# pip RECORD metadata, so `pip install -r requirements.txt` fails trying
# to uninstall it to upgrade ("Cannot uninstall PyJWT 2.7.0, RECORD file
# not found"), aborting the whole install under set -e before mcp ever
# lands. Give pip its own tracked pyjwt first so the requirements.txt
# install sees an already-satisfying, pip-owned version and never
# attempts the conflicting uninstall.
pip install -q --ignore-installed pyjwt

pip install -q -r "$CLAUDE_PROJECT_DIR/requirements.txt"

# 범용(프로젝트 무관) 가드 훅 7개 + must_hook MCP 서버는
# songjiun10-collab/hook 플러그인으로 옮겨졌다(2026-08) - .claude/hooks/의
# protect_never_touch.py/protect_generated_files.py/
# protect_experiment_integrity.py/protect_claim_evidence.py(Hncs 전용
# 4개)만 로컬에 남음. 컨테이너가 새로 뜰 때마다 재설치 필요(pip 패키지와
# 같은 이유 - 플러그인 설치가 컨테이너에 안 남음). 실패해도(예: GitHub
# 장애) 전체 세션 시작을 막지 않도록 set -e 범위 밖에서 처리 - 실패하면
# 그 세션은 4개 프로젝트 전용 훅만 활성인 채로 진행되고, 사람이 나중에
# 알아챌 수 있게 stderr에 남긴다.
if ! claude plugin marketplace add songjiun10-collab/hook 2>&1; then
  echo "[session-start] WARNING: hook 플러그인 마켓플레이스 추가 실패 - 범용 가드 훅 7개 비활성" >&2
elif ! claude plugin install hook@hook 2>&1; then
  echo "[session-start] WARNING: hook 플러그인 설치 실패 - 범용 가드 훅 7개 비활성" >&2
fi
