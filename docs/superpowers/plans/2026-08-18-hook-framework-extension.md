# 훅 프레임워크 확장 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development가
> 이 세션엔 로드 안 되므로, 동일한 원칙(태스크당 fresh 서브에이전트 dispatch,
> 태스크마다 spec/quality 2단 리뷰, 마지막 whole-branch 리뷰)을 컨트롤러가
> 수동으로 따른다. Steps는 체크박스(`- [ ]`)로 추적.

**Goal:** 스펙(`docs/superpowers/specs/2026-08-18-hook-framework-extension.md`,
커밋 e7d276c)의 4개 항목을 `songjiun10-collab/hook`(범용 코어)에 먼저
구현+검증하고, 동일 diff를 `songjiun10-collab/Hncs`의 로컬 복사본에 포팅.

**Architecture:** 두 레포가 `_hook_common.py`/가드 훅을 독립적으로
유지(라이브 크로스레포 의존 금지, 기존 설계 원칙)하므로 모든 코드
변경은 "hook 레포에서 구현+테스트 그린" → "Hncs에 동일 diff 포팅+테스트
그린" 두 단계로 반복된다. 항목 2(ask() 관측)만 예외 - 조사 작업이라
코드 diff가 조사 결과에 따라 갈림.

**Tech Stack:** Python 3, `unittest`(pytest 아님), `pyotp`(신규 의존성),
기존 `mcp==2.0.0`.

## Global Constraints

- 커밋 전 항상 `python3 -m unittest discover -s tests` 전체 그린 (양쪽
  레포 각자).
- 각 훅 테스트는 `HNCS_HOOK_*` 환경변수로 로그/sentinel 경로 격리 -
  실제 `.claude/hooks/violations_log.jsonl`/`hooks/violations_log.jsonl`을
  절대 오염시키지 않음.
- 기존 로그 항목/함수 시그니처는 전부 하위 호환 유지 - 새 파라미터는
  옵션(기본값 있음), 새 로그 필드는 값이 있을 때만 추가.
- CRITICAL 등급 훅에서 서브에이전트발 호출은 override조차 안 받는
  기존 규칙 변경 없음 - TOTP는 오케스트레이터 직접 호출 경로에만 추가
  레이어로 얹는다.
- override는 여전히 `git_sha`와 함께 `override_audit.jsonl`에 기록 -
  TOTP 검증 결과(`totp_verified`/`totp_configured`)도 같은 항목에 추가.

---

## Task 1: `protect_secret_exposure.py` (hook 레포)

**Files:**
- Create: `hooks/protect_secret_exposure.py`
- Create: `tests/test_hooks_secret_exposure.py`
- Modify: `hooks/hooks.json` (PreToolUse에 두 매처 추가 - 기존
  `Edit|Write|MultiEdit`/`Bash` 그룹에 이 훅 커맨드 추가)
- Modify: `README.md`, `README.ko.md` (가드 훅 목록 7→8, 새 훅 설명 추가)
- Modify: `CLAUDE.md` ("새 가드 훅 추가하기" 예시로 언급 가능)

**Interfaces:**
- Consumes: `_hook_common.allow`/`deny`/`allow_with_override`/
  `bash_override`/`sentinel_override`/`is_subagent_call`/
  `require_decision_or_deny`/`high_tier_decision` (기존 훅들과 동일 패턴).
- Produces: `HOOK_NAME = "protect_secret_exposure"`, `SEVERITY = "HIGH"`,
  `find_secret_pattern(text) -> Optional[str]` (매칭된 패턴 이름 문자열
  반환, 없으면 None) - Task 3/5에서도 동일 이름으로 참조.

- [ ] **Step 1: 실패하는 테스트부터 작성**

```python
# tests/test_hooks_secret_exposure.py 일부
import protect_secret_exposure as hook

def test_aws_access_key_detected(self):
    self.assertIsNotNone(hook.find_secret_pattern("AKIAABCDEFGHIJKLMNOP"))

def test_github_token_detected(self):
    self.assertIsNotNone(hook.find_secret_pattern("ghp_" + "a" * 36))

def test_private_key_header_detected(self):
    self.assertIsNotNone(
        hook.find_secret_pattern("-----BEGIN RSA PRIVATE KEY-----"))

def test_slack_token_detected(self):
    self.assertIsNotNone(hook.find_secret_pattern("xoxb-123456-abcdefghij"))

def test_normal_code_not_flagged(self):
    self.assertIsNone(hook.find_secret_pattern("def foo():\n    return 1"))
```

동일 파일에 `TestProtectSecretExposureEndToEnd`로 Edit/Write/Bash 세
경로 subprocess end-to-end 테스트 추가 - `test_hooks_destructive.py`의
`TestProtectDestructiveEndToEnd` 구조를 그대로 따른다(decision record
선행 작성, override 테스트, 서브에이전트 경로 없음 - HIGH는
`is_subagent_call` 분기만 있고 override 자체는 서브에이전트도 가능).

- [ ] **Step 2: 테스트 실행 - 실패 확인**

Run: `python3 -m unittest tests.test_hooks_secret_exposure -v`
Expected: FAIL (모듈 없음)

- [ ] **Step 3: `hooks/protect_secret_exposure.py` 구현**

정규식 4개(스펙 문서에 정확한 패턴 있음: AWS `AKIA[0-9A-Z]{16}`, GitHub
`gh[pousr]_[A-Za-z0-9]{36,}`, private key
`-----BEGIN (RSA |EC |OPENSSH |)?PRIVATE KEY-----`, Slack
`xox[baprs]-[0-9A-Za-z-]{10,48}`). `main()`은 `tool_name`이
Edit/Write/MultiEdit면 `content`(Write) 또는 `new_string`(Edit/MultiEdit)을,
Bash면 `command`를 스캔 - `protect_test_coverage.py`가 이미 `tool_input`
분기하는 것과 같은 패턴.

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m unittest tests.test_hooks_secret_exposure -v`
Expected: PASS

- [ ] **Step 5: `hooks/hooks.json`/README/CLAUDE.md 갱신, 전체 스위트 확인**

Run: `python3 -m unittest discover -s tests`
Expected: 전체 그린 (기존 182개 + 신규)

- [ ] **Step 6: 커밋**

```bash
git add hooks/protect_secret_exposure.py tests/test_hooks_secret_exposure.py hooks/hooks.json README.md README.ko.md CLAUDE.md
git commit -m "feat: protect_secret_exposure.py 추가 - AWS/GitHub/Slack 토큰 + private key 헤더 탐지"
```

---

## Task 2: TOTP override key (hook 레포)

**Files:**
- Modify: `hooks/_hook_common.py`
- Modify: `hooks/protect_destructive.py`, `hooks/protect_push_safety.py`
  (force-push 분기만)
- Modify: `requirements.txt` (`pyotp` 추가)
- Create/Modify: `tests/test_hook_common_totp.py` (신규) +
  `tests/test_hooks_destructive.py`/`test_hooks_push_safety.py`에 TOTP
  케이스 추가

**Interfaces:**
- Consumes: Task 1 없음(독립).
- Produces: `_hook_common.verify_totp_override_key(code) -> bool`,
  `bash_override(rule, command, require_totp_key=False) -> reason_or_None`
  (요구했는데 코드가 없거나 틀리면 None 반환 - 기존 호출부는 시그니처
  그대로라 하위 호환).

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_hook_common_totp.py
import pyotp

def test_correct_code_verifies(self):
    secret = pyotp.random_base32()
    os.environ["HNCS_HOOK_OVERRIDE_TOTP_SECRET"] = secret
    code = pyotp.TOTP(secret).now()
    self.assertTrue(_hook_common.verify_totp_override_key(code))

def test_wrong_code_rejected(self):
    os.environ["HNCS_HOOK_OVERRIDE_TOTP_SECRET"] = pyotp.random_base32()
    self.assertFalse(_hook_common.verify_totp_override_key("000000"))

def test_no_secret_configured_returns_none(self):
    os.environ.pop("HNCS_HOOK_OVERRIDE_TOTP_SECRET", None)
    self.assertIsNone(_hook_common.verify_totp_override_key("123456"))
```

`verify_totp_override_key`는 3-state 반환: `True`(검증됨)/`False`(틀림)/
`None`(secret 미설정 - 폴백 케이스와 "틀림"을 구분해야 감사 로그에
`totp_configured` 플래그를 정확히 남길 수 있음).

- [ ] **Step 2: 테스트 실행 - 실패 확인**

Run: `python3 -m unittest tests.test_hook_common_totp -v`
Expected: FAIL

- [ ] **Step 3: `_hook_common.py`에 `verify_totp_override_key()` 추가 +
  `bash_override()` 확장**

`bash_override(rule, command, require_totp_key=False)`: 기존처럼 룰+사유
파싱한 뒤, `require_totp_key`가 True면 커맨드 문자열에서
`key=(\d{6})` 추가 파싱 - 없으면 `(reason, totp_configured=False,
totp_verified=False)`, 있는데 `verify_totp_override_key()`가 `None`이면
동일(secret 미설정), `False`면 override 자체 무효(함수가 `None` 반환 -
호출부는 override 없음으로 처리), `True`면 `(reason, totp_configured=True,
totp_verified=True)`. 반환 타입이 문자열에서 튜플로 바뀌므로 **기존
`bash_override()` 호출부 전부(`protect_never_touch.py` 포함, Hncs
쪽까지) 시그니처 변경에 맞춰 같이 고쳐야 함** - `require_totp_key`
기본값 `False`인 호출은 `(reason, False, False)` 튜플을 받되 기존
로직은 `reason` 부분만 쓰면 되므로 각 훅에서 `reason, *_ =
bash_override(...)` 형태로 최소 수정.

- [ ] **Step 4: `protect_destructive.py`/`protect_push_safety.py`
  force-push 분기에 `require_totp_key=True` 적용, `allow_with_override()`
  호출에 `totp_verified`/`totp_configured` 전달**

`allow_with_override()`/`_record_override()`에 `totp_verified=None,
totp_configured=None` 옵션 파라미터 추가 - 값이 있을 때만
`override_audit.jsonl` 항목에 키 추가(기존 항목 하위 호환).

- [ ] **Step 5: 테스트 통과 확인**

Run: `python3 -m unittest discover -s tests`
Expected: 전체 그린

- [ ] **Step 6: `requirements.txt`에 `pyotp` 추가, 커밋**

```bash
git commit -m "feat: CRITICAL override에 TOTP 물리적 키 검증 레이어 추가"
```

---

## Task 3: TOTP override key 포팅 (Hncs 레포)

**Files:**
- Modify (Hncs): `.claude/hooks/_hook_common.py`,
  `.claude/hooks/protect_never_touch.py`,
  `.claude/hooks/protect_destructive.py`,
  `.claude/hooks/protect_push_safety.py`, `requirements.txt`
- Modify (Hncs): `tests/test_hooks_never_touch.py`(기존 파일명 확인 필요),
  `tests/test_hooks_destructive.py`, `tests/test_hooks_push_safety.py`
- Create (Hncs): `tests/test_hook_common_totp.py`

**Interfaces:**
- Consumes: Task 2의 완성/검증된 diff 그대로.
- Produces: 없음(포팅 태스크).

- [ ] **Step 1:** Task 2에서 그린 확인된 `_hook_common.py`/
  `protect_destructive.py`/`protect_push_safety.py`/
  `tests/test_hook_common_totp.py` diff를 Hncs의 동일 경로에 적용.
  **추가로 Hncs 전용** `protect_never_touch.py`의 Bash 경로에도
  `require_totp_key=True` 적용(hook 레포엔 이 훅이 없음 - Hncs
  전용이므로 Task 2엔 없던 신규 적용).
- [ ] **Step 2:** `requirements.txt`에 `pyotp` 추가.
- [ ] **Step 3:** `python3 -m unittest discover -s tests` (Hncs) 전체 그린
  확인.
- [ ] **Step 4:** 커밋.

```bash
git commit -m "feat: Hncs 로컬 훅에도 TOTP override 검증 포팅 (hook 레포 Task 2 동일 diff)"
```

---

## Task 4: 관측성 로깅 + glob override (hook 레포)

**Files:**
- Modify: `hooks/_hook_common.py` (`_log_event`/`_record_override`에
  `agent_type`/`tool_name` 옵션 파라미터; `sentinel_override`/
  `decision_record`에 glob 매칭)
- Modify: 8개 가드 훅 전부(호출부에 `data.get("agent_type")`/
  `data.get("tool_name")` 전달 - 기계적 diff, `target=` 추가할 때와 같은
  자리)
- Modify/Create: 관련 테스트 파일들, `tests/test_hook_common_glob_override.py`(신규)

**Interfaces:**
- Consumes: Task 1/2와 독립적으로 병행 가능(같은 파일 `_hook_common.py`를
  건드리므로 머지 순서만 주의 - Task 2 이후에 진행 권장, 이 플랜의
  순서 그대로).
- Produces: `_log_event(..., agent_type=None, tool_name=None)`,
  `sentinel_override(rule, target)`/`decision_record(rule, target=...)`가
  저장된 sentinel의 `target`에 `*`/`?`가 있으면 `fnmatch.fnmatch(target,
  stored_target)`로, 없으면 기존 완전 일치로 매칭(하위 호환 - glob
  문자 없는 기존 target은 동작 100% 동일).

- [ ] **Step 1: 실패하는 테스트 작성** - `_log_event`가 `agent_type`/
  `tool_name` 값이 있을 때만 항목에 포함하는지, glob target
  (`"tests/*.py"`)이 실제 파일(`"tests/foo.py"`)과 매칭되는지, 기존
  완전-일치 target(`"main"` 같은 glob-문자-없는 문자열)이 여전히
  정확히 일치할 때만 매칭되는지(`"main2"`와는 매칭 안 됨을 회귀
  테스트로 lock-in).

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m unittest tests.test_hook_common_glob_override -v`

- [ ] **Step 3: `_hook_common.py` 구현** - `import fnmatch` 추가,
  `sentinel_override`/`decision_record`의 target 비교 라인만
  `fnmatch.fnmatch(target, data.get("target"))
  if any(c in (data.get("target") or "") for c in "*?")
  else target == data.get("target")` 형태로 교체(기존 완전-일치 분기
  보존).

- [ ] **Step 4: 8개 가드 훅에 `agent_type=data.get("agent_type")`,
  `tool_name=data.get("tool_name")` 전달** - 각 훅의 `deny()`/`ask()`/
  `allow_with_override()`/`high_tier_decision()` 호출부에 인자 추가.
  기계적이라 파일마다 diff 1~2줄.

- [ ] **Step 5: 테스트 통과 확인**

Run: `python3 -m unittest discover -s tests`

- [ ] **Step 6: 커밋**

```bash
git commit -m "feat: 로그에 agent_type/tool_name 추가, override target에 glob 매칭 지원"
```

---

## Task 5: 관측성 로깅 + glob override 포팅 (Hncs 레포)

**Files:** Hncs의 `.claude/hooks/_hook_common.py` + 12개 훅(4개 프로젝트
전용 + Task 3까지 반영된 8개) + 대응 테스트 전부.

**Interfaces:** Task 4의 완성/검증된 diff 그대로 포팅.

- [ ] **Step 1~4:** Task 3과 동일한 방식(diff 적용 → 전체 스위트 그린
  → 커밋). Hncs 전용 4개 훅(`protect_never_touch.py` 등)에도
  `agent_type`/`tool_name` 전달 추가 - hook 레포엔 없는 신규 적용분.

```bash
git commit -m "feat: Hncs 로컬 훅에도 agent_type/tool_name 로깅 + glob override 포팅"
```

---

## Task 6: ask() 결과 관측성 재조사

**Files:**
- Create (임시, 커밋 안 함 또는 조사 후 삭제): 진단용 PostToolUse 훅
- Modify (조사 결과에 따라 갈림): `_hook_common.py`의 `ask()` docstring
  최소 날짜 갱신, 가능하면 `deliver_caution.py` 패턴처럼 실제 결과
  연결하는 신규 코드 - **이 태스크는 사전에 코드를 명세할 수 없음**
  (조사 선행 태스크).

- [ ] **Step 1:** 진단용 임시 PostToolUse 훅 작성 - 매처는 실제 HIGH
  등급 훅(`protect_branch.py` 등)이 `ask()`를 발동시키는 툴과 동일하게
  맞추고, hook input 전체를 raw JSON으로 파일에 덤프.
- [ ] **Step 2:** 라이브로 실제 HIGH 등급 액션을 오케스트레이터 직접
  호출로 트리거 - 사람이 실제로 승인 또는 거부.
- [ ] **Step 3:** 덤프된 PostToolUse 입력에서 사람의 실제 답변을
  가리키는 필드가 있는지 확인.
- [ ] **Step 4a (관측 가능으로 확인됨):** `_hook_common.py`에
  `write_pending_ask_target()`/대응 PostToolUse 훅 추가해서
  `eval_hook_judgments.py`가 `ask_unknown` 대신 실제
  `approved`/`denied`를 쓰도록 확장 - 새 서브태스크로 분리해서 이
  플랜에 Task 7로 추가.
- [ ] **Step 4b (여전히 관측 불가로 재확인됨):** `_hook_common.py`
  `ask()` docstring에 "2026-08-18 재확인, 여전히 관측 불가"만 날짜
  붙여 추가 - 코드 변경 없음.
- [ ] **Step 5:** 진단용 임시 훅 제거(커밋했다면), 결과를 이 플랜
  문서에 추가 기록.

---

## 실행 순서

Task 1 → Task 2 → Task 3 → Task 4 → Task 5 → Task 6 (스펙의 우선순위
3→1→4→2와 동일, Task 3/5는 각각 2/4의 포팅이라 번호가 밀림).

## 검증 (전체)

1. 매 태스크 커밋 전 `python3 -m unittest discover -s tests` 그린
   (해당 레포).
2. Task 3/5(포팅) 완료 후 양쪽 레포 전체 스위트 그린 재확인.
3. TOTP 라이브 스모크: 실제 `pyotp.TOTP(secret).now()` 코드로 override
   시도해서 통과하는지, secret 미설정 상태에서 폴백 감사 플래그가
   실제로 남는지 subprocess 시뮬레이션이 아니라 실제 훅 실행으로 확인.
4. `protect_secret_exposure.py` 라이브 스모크: 실제 AWS 키 모양
   문자열을 담은 파일 Edit 시도해서 막히는지 확인.
5. 이 프로젝트 관례대로 작성자 정정(`git config user.email/name` →
   `rebase --exec` → 재시도 push) 후 최종 커밋.
