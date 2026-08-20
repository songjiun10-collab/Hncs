# 훅 프레임워크 확장 스펙 - Override 강화 / ask() 관측 / 신규 가드 / 권한 세분화

## 배경

`songjiun10-collab/hook` 플러그인 추출(2026-08-18) 이후, 사용자가 "훅 설계
추가"를 요청. 대화로 스코프를 좁힌 결과 독립적인 4개 항목으로 확정됨(모두
README.md "알려진 한계" 절과 직접 연결됨). 대상은 `songjiun10-collab/hook`
(범용 부분)과 `songjiun10-collab/Hncs`(프로젝트 전용 4개 훅, 방금 자체
로컬 복사본을 되살림 - "훅은 냅둬" 지시) 양쪽 - 각 레포가 `_hook_common.py`를
독립적으로 유지하므로 구현은 양쪽에 동일한 diff를 각자 적용하는 형태가 됨.

## 스코프

### 1. CRITICAL override용 TOTP 추가 확인 단계

**정정(2026-08-18, "설계 굿?" 리뷰)**: 최초 안은 이걸 "물리적 키"로,
"override self-servable 문제를 완화"한다고 프레이밍했는데 과장이었다.
TOTP secret을 `HNCS_HOOK_OVERRIDE_TOTP_SECRET` env var에 두면, 에이전트가
Bash로 `echo $HNCS_HOOK_OVERRIDE_TOTP_SECRET` 한 줄이면 secret을 그대로
읽고 `python3 -c "import pyotp; print(pyotp.TOTP('<secret>').now())"`로
코드 자체를 스스로 계산할 수 있다 - 악의적이거나 판단이 틀린 에이전트를
막는 방어력은 사실상 0. 이 메커니즘이 실제로 막는 건 "에이전트가 사용자
승인 없이 무의식적으로/일상적으로 CRITICAL override를 남발하는 것"뿐 -
그건 이 프로젝트의 훅 철학("훅은 개발자를 대신해 판단하지 않는다 - 훅은
위험한 행동을 무의식적으로 해버리는 것만 막는다")과 정확히 일치하는
수준이라 여전히 가치는 있지만, "물리적 키"/"self-servable 완화"라는
이름은 실제보다 강한 보장을 암시하므로 버린다.

**문제(정정된 프레이밍)**: 현재 override는 순수 self-declared임 -
`bash_override()`가 커맨드 텍스트의 `# HNCS-OVERRIDE: <rule>: <reason>`
주석을 파싱할 뿐, 최소한의 "이건 그냥 지나가듯 쓴 게 아니라 이번 건
때문에 일부러 쓴 것"이라는 마찰조차 없음. CRITICAL 등급에 코드 하나
더 요구하는 건 완전한 검증이 아니라 **부주의 방지용 추가 확인
단계(added friction)** - override를 쓸 때 "진짜 이걸 할 건가"를 한 번
더 확인시키는 정도로 기대치를 낮춘다.

**설계**: CRITICAL 등급 override에, TOTP 코드 첨부를 요구.

- 포맷: `# HNCS-OVERRIDE: <rule>: <reason> key=<6자리 코드>`
- 신규 env var `HNCS_HOOK_OVERRIDE_TOTP_SECRET` (base32 secret, 저장소에
  커밋하지 않음 - 사용자가 환경변수로 직접 설정, 인증 앱과 동일한
  secret 공유해서 코드는 대화창에서 사용자가 직접 불러주는 방식을
  전제로 함 - 에이전트가 스스로 env를 읽어서 계산하지 않는다는 신뢰가
  전제라는 걸 문서에도 명시).
- `_hook_common.py`에 `verify_totp_override_key(code)` 추가
  (`pyotp.TOTP(secret).verify(code, valid_window=1)`) - `requirements.txt`에
  `pyotp` 추가.
- **`bash_override()` 자체는 안 건드림** - 대신 신규 함수
  `bash_override_with_totp(rule, command)`을 추가해서 CRITICAL 전용
  3개 훅(`protect_never_touch.py`의 Bash 경로, `protect_destructive.py`,
  `protect_push_safety.py`의 force-push 분기)만 이걸 쓰게 한다. 기존
  `bash_override()`를 쓰는 나머지 8개 훅은 시그니처/리턴 타입 전혀
  안 바뀜(surgical changes 원칙 - 3개 훅에만 필요한 기능 때문에 11개
  전부의 호출부를 고치지 않는다).
- **Secret 미설정 시 폴백**: 하드 실패(CRITICAL 작업 전체 봉쇄) 대신,
  기존 방식대로 통과시키되 `override_audit.jsonl` 항목에
  `"totp_verified": false, "totp_configured": false`를 남겨 감사 시
  "코드 확인 없이 통과"가 눈에 띄게 함. 코드가 설정은 됐는데 틀리면
  override 자체를 무효 처리(deny 유지).
- HIGH/MEDIUM은 대상 아님.

**테스트**: 올바른 코드 통과, 틀린 코드 거부, replay(같은 코드 재사용-
`valid_window`로 시간 윈도 제한 확인), secret 미설정 시 폴백 + 감사
플래그, 기존 `bash_override()` 쓰는 다른 8개 훅은 이 변경과 무관하게
전혀 안 건드려짐(회귀 테스트로 lock-in).

### 2. ask() 결과 관측성 재조사

**문제**: `_hook_common.py`의 2026-08-15 조사 결과 "PostToolUse에서
ask()의 실제 사람 답변을 관측할 수 없다"고 확정돼 있지만, 이후 Claude
Code 버전이 바뀌었을 가능성이 있고 재확인 안 됨.

**이건 코드 변경이 아니라 조사 작업**: 실제 스펙 산출물은 (a) 조사
결과 문서(가능/불가능 여부, 가능하면 어떤 필드로), (b) 결과에 따른
후속 설계 - 가능하면 `deliver_caution.py` 패턴처럼 `tool_use_id`로
연결해 `eval_hook_judgments.py`가 `ask_unknown` 대신 실제 값을 쓰게
확장; 불가능이 재확인되면 문서에 "재확인 날짜"만 갱신.

**방법**: 임시 진단 훅(PostToolUse, ask()를 트리거하는 훅과 동일
matcher)을 만들어 hook input 전체를 raw로 파일에 덤프 - 실제로 HIGH
등급 훅을 오케스트레이터 직접 호출로 트리거해서 사람이 승인/거부하고
그 뒤 덤프 내용 확인. 라이브 검증 필수(과거에도 이 프로젝트가 organic
테스트로만 진짜 동작을 확인해온 방식과 동일).

### 3. 신규 가드 `protect_secret_exposure.py`

**설계**: PreToolUse, matcher `Edit|Write|MultiEdit|Bash`, HIGH 등급.
Edit/Write는 `content`/`new_string`을, Bash는 `command`를 스캔.

확실한 패턴만(고엔트로피 휴리스틱은 false positive가 많아 v1에서
제외 - `protect_push_safety.py`가 정규식 오탐/우회를 놓고 이미 두 차례
고친 전례를 반복하지 않기 위함):

- AWS Access Key ID: `AKIA[0-9A-Z]{16}`
- GitHub 토큰: `gh[pousr]_[A-Za-z0-9]{36,}`
- Private key 헤더: `-----BEGIN (RSA |EC |OPENSSH |)?PRIVATE KEY-----`
- Slack 토큰: `xox[baprs]-[0-9A-Za-z-]{10,48}`

override: 기존 bash-comment/sentinel 메커니즘 그대로(HIGH 등급이라
TOTP 요구 대상 아님).

**알려진 한계 명시(README 톤 유지)**: placeholder 값(`<your-key>`,
`xxx...`, `sk-...REDACTED...` 류)과 진짜 키를 구분 못 할 수 있음 - v1은
정규식 매칭만 하고 값의 "진짜같음"은 판단 안 함(엔트로피 체크 배제와
같은 이유).

**테스트**: 패턴별 positive/negative 케이스, Edit/Write/Bash 세 경로
모두 subprocess end-to-end.

### 4. 접근 권한 세분화 (3축)

재검토 결과 세 축 중 상당 부분이 이미 존재함:
- "규칙별 override 범위"는 이미 `target` 문자열 매칭이라 사실상
  파일/커맨드 단위로 이미 부분적임 - 다만 **완전 일치만** 지원해서
  디렉토리 전체를 한 번에 override할 방법이 없음.
- "도구별 게이트 강도"는 이미 훅마다 자기 matcher + 고정 SEVERITY로
  사실상 도구별로 다름.

그래서 진짜 새로 필요한 건 셋 다 무거운 ACL 시스템이 아니라 **관측성
먼저, 제한은 나중**(YAGNI - 지금 실제로 이 축으로 제한해야 할 구체적
케이스가 없음):

- **(a) 호출자 신원 로깅**: hook input의 `agent_type` 필드(이미
  존재 확인됨 - `record_agent_approval.py`가 `resolvedModel` 체크하듯)를
  모든 로그 항목에 `agent_type` 키로 추가. 제한 로직은 아직 안 만듦 -
  나중에 실제 필요가 생기면 이 데이터로 설계.
- **(b) glob 패턴 override**: `sentinel_override()`/`decision_record()`의
  `target` 매칭에 정확히 일치 외에 `fnmatch` 기반 glob도 지원(저장된
  sentinel의 `target`이 `*`/`?`를 포함하면 glob으로, 아니면 기존처럼
  완전 일치). 디렉토리 하나를 한 번에 override 가능해짐 - 단
  `write_sentinel_override()` 호출부(에이전트 자신)가 명시적으로 glob
  패턴을 target으로 써야만 발동하므로 기존 동작은 완전 하위 호환.
- **(c) 도구명 로깅**: 모든 로그 항목에 `tool_name`(Bash/Edit/Write/
  MultiEdit/Agent/mcp__...) 키 추가 - `eval_hook_judgments.py`가 나중에
  도구축으로도 calibration을 낼 수 있게.

**테스트**: `agent_type`/`tool_name`이 있을 때/없을 때 로그 항목 형태,
glob override 매칭(디렉토리 prefix, `*.py` 패턴)과 완전 일치 override의
하위 호환 회귀 테스트.

## 우선순위 제안

사용자 확정 필요. 초안 제안: 3(신규 가드, 독립적이고 가장 작음) →
1(TOTP 추가 확인 단계) → 4(관측성 로깅, 다른 항목들과 겹치지 않음) →
2(조사 작업, 결과 불확실이라 별도 트랙으로 아무 때나 가능).

## 검증

각 항목 구현 후 `python3 -m unittest discover -s tests` 전체 그린,
`songjiun10-collab/hook` 쪽도 `python3 -m unittest discover -s tests`
동일하게 그린 - 두 레포 모두. 라이브 스모크 테스트(실제 TOTP 코드로
override, 실제 secret 패턴이 담긴 커밋 시도해서 막히는지) 필수 -
subprocess 시뮬레이션만으로 끝내지 않음(이 프로젝트 관례).
