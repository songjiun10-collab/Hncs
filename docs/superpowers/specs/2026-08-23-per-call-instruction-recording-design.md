# HNCS — Per-Call Instruction Recording

**상태 (2026-08-23)**: 스펙. 플랜 아님(root `CLAUDE.md`의 "Workflow":
spec → plan → implement). 코드 변경 없음. 부록 B의 열린 질문 3개가
정해지기 전엔 `superpowers:writing-plans`로 못 넘어감.

**작성자**: 1~7절은 사용자 원문(2026-08-23, 채팅으로 제시)을 거의 그대로
옮김. "부록 A: 구현 제약", "부록 B: 열린 질문"은 이 세션이 추가.

**선행 문서**: `docs/superpowers/specs/2026-08-19-hook-evolution-design.md`
(3절 데이터 스키마의 `instruction` 필드가 여기서 구체화됨),
`docs/superpowers/specs/2026-08-18-hook-framework-extension.md`.

## 1. 목적

`/compact` 때문에 Agent가 어떤 지시를 받고 행동했는지 나중에 재구성하기
어려워지는 문제를 줄인다.

전체 채팅을 통째로 보존하는 게 아니라, Agent 호출(call) 단위로 당시
지시문을 원문 그대로 기록한다.

Compact는 컨텍스트를 압축할 수 있지만, 기록된 call의 원본 instruction은
사라지지 않는다.

## 2. 기록 단위

```
Agent Call
│
├── call_id
├── timestamp
├── parent/session
├── model
├── instruction          ← 원문
├── intended_scope
├── target
├── agent_response
├── tool_actions
├── hook_decisions
└── outcome
```

핵심은 instruction을 요약하지 않는 것.

## 3. 기존 HNCS와 연결

현재:

```
Decision Record
      ↓
Outcome
      ↓
Judgment Eval
```

여기에 instruction을 붙이면:

```
Instruction
     ↓
Agent Judgment
     ↓
Agent Action
     ↓
Hook Decision
     ↓
Outcome
     ↓
Judgment Eval
```

즉 "무슨 지시를 받았는가"와 "실제로 어떻게 행동했는가"를 연결할 수 있음.

## 4. Agent Drift 분석

그러면 이런 데이터가 가능해짐.

```
instruction
intended_scope
actual_action
deviation
hook_decision
outcome
human_judgment
```

예:

```
Instruction:
"README의 Hook 설치 방법만 수정해라"
Intended scope:
README.md
Actual action:
README.md
+ hooks/foo.py
+ settings.json
Deviation:
scope expansion
```

이런 사례가 쌓이면:

```
Agent 행동
    ↓
Drift 발견
    ↓
패턴 분석
    ↓
가설
    ↓
새 Hook
    ↓
실험
    ↓
Outcome
    ↓
다시 데이터
```

HNCS의 Hook Evolution loop에 바로 들어감.

## 5. `/compact`와의 관계

원래 구조:

```
Full conversation ──→ compact ──→ 계속 작업
                         ↓
                    일부 맥락 손실 가능
```

새 구조:

```
                    Agent Call
                        │
             ┌──────────┴──────────┐
             ↓                     ↓
       Context/Chat           Call Record
             ↓                     ↓
          compact             원문 instruction
             ↓                     │
        계속 작업               영구 기록
                                   ↓
                            Learning Dataset
```

따라서 전체 채팅 기록을 저장할 필요가 없음.

## 6. 중요한 설계 원칙

원본과 분석을 분리.

```
RAW
└── instruction 원문
       ↓
DERIVED
├── intended_scope
├── deviation
├── judgment
├── outcome
└── evaluation
```

원본 instruction을 나중에 모델이 요약한 결과로 대체하지 않는다.

그래야 나중에 "당시 Agent에게 실제로 뭐라고 했는가?"를 다시 검증할 수
있음.

## 7. HNCS 최종 구조

```
              User / Controller
                     │
                     ▼
               Agent Call
                     │
          ┌──────────┴──────────┐
          ▼                     ▼
   Original Instruction      Agent Action
          │                     │
          └──────────┬──────────┘
                     ▼
                 Hook Layer
                     │
             ┌───────┴───────┐
             ▼               ▼
          Decision          Outcome
             │               │
             └───────┬───────┘
                     ▼
               Learning Data
                     │
             ┌───────┴───────┐
             ▼               ▼
        Drift Analysis   Judgment Eval
             │               │
             └───────┬───────┘
                     ▼
                 Hook 가설
                     │
                     ▼
                  실험
                     │
                     └──────→ 반복
```

**한 문장**: HNCS는 전체 대화를 보존하는 대신, 각 Agent call의 원본
instruction을 불변 기록으로 남겨 Instruction → Judgment → Action → Hook
→ Outcome을 연결하고, 이 데이터를 Agent Drift 분석과 다음 Hook 설계에
사용하는 구조로 확장한다.

## 부록 A: 구현 제약 (2026-08-23, 이 세션이 추가)

2026-08-19 설계의 "부록: 구현 제약"과 같은 목적 — 나중에 버그로
재발견되지 않도록, 지금 확인 가능한 사실만 근거와 함께 적는다.

### A1. Agent call 단위 캡처는 이미 가능하다 — 새 능력이 아니라 "안 쓰고 버리는 중"

2절 스키마의 `instruction`/`model`/`agent_response`는 기존 훅이 **이미
읽고 있는 필드**다.

- `instruction`: `.claude/hooks/protect_reviewer_prejudging.py`가
  PreToolUse에서 `data["tool_input"]["prompt"]`와 `["description"]`을
  그대로 읽어 정규식을 돌린다(`combined = " ".join(str(ti.get(k, ""))
  for k in ("prompt", "description"))`). 즉 서브에이전트 디스패치
  프롬프트 원문은 훅에 통째로 들어온다.
- `agent_response`/`model`: `.claude/hooks/record_consensus_judgment.py`가
  PostToolUse에서 `tool_response.content[*].text`와
  `tool_response.resolvedModel`을 읽는다. 두 필드가 실제로 존재한다는
  건 2026-08-15 라이브 디스패치 측정으로 확인됨(그 파일 docstring에
  근거 기록됨).

따라서 Agent call 기록은 **새 관측 능력을 뚫는 일이 아니라, 이미 훅에
도착해 있는 값을 버리지 않고 append-only 파일에 쓰는 일**이다. 구현
난이도는 낮다.

### A2. 최상위 사용자 지시는 현재 어떤 훅도 못 본다 — 여기가 진짜 공백

7절 다이어그램 맨 위 `User / Controller → Agent Call` 화살표의 **원문**은
현재 파이프라인 어디에도 안 들어온다.

- `tool_input`은 툴 호출 인자만 담는다. 사용자가 채팅에 친 원문은
  거기 없다.
- 레포 전체 코드 검색 결과 `UserPromptSubmit`, `transcript_path`,
  `tool_use_id` **세 문자열 모두 0건**(`repo:songjiun10-collab/hncs`,
  2026-08-23). 훅 프레임워크가 이 셋을 한 번도 안 쓴다.
- `.claude/settings.json`에 등록된 훅 이벤트는 `SessionStart` /
  `PreToolUse` / `PostToolUse` 3개뿐이다.

즉 1절의 동기(`/compact`로 사라지는 지시 복구)가 **실제로 해결되는
지점은 Agent call이 아니라 사용자 턴이다.** Agent 디스패치 프롬프트는
어차피 컨트롤러가 작성한 것 = 6절 기준으로 이미 DERIVED다. 진짜 RAW는
사용자 원문이고, 그건 `UserPromptSubmit` 훅 이벤트를 `settings.json`에
새로 추가해야만 무손실로 잡힌다.

이 문서를 플랜으로 옮길 때 이 구분이 유지돼야 한다:

| 층 | 원문성 | 현재 관측 가능? |
|---|---|---|
| 사용자 턴 | RAW | ❌ (`UserPromptSubmit` 신규 등록 필요) |
| Agent 디스패치 프롬프트 | 컨트롤러 산출물 | ✅ (A1) |
| Agent 응답 | RAW(에이전트 발화) | ✅ (A1) |

### A3. `intended_scope`/`deviation`은 RAW가 아니다

6절 원칙대로면 이 둘은 RAW 블록에 들어가면 안 된다 — 둘 다 판단이다.
2026-08-19 브레인스토밍 결정 3번이 이미 이 둘(+`human_judgment`)을
`write_decision_record()`(must훅 MCP 툴) 스키마 확장 대상으로 못박아
뒀고, 그건 **에이전트 자기신고**이므로 DERIVED가 맞다. 두 문서가
충돌하진 않지만, 새 스키마에서 이 필드들이 어느 파일에 들어가는지는
플랜에서 명시해야 한다(RAW 로그에 섞으면 6절 원칙이 첫날부터 깨진다).

### A4. instruction record는 sentinel이 아니라 append-only 로그다

기존 sentinel(`sentinel_override`, `medium_approval`, decision record,
consensus verdict)은 전부 **1회 소비형**이다. `_hook_common.py`는 이
때문에 실제로 버그를 한 번 겪었다(두 private 로거가 각자 조회해서 첫
호출이 sentinel을 먹어버림 — 모듈 docstring에 정정 블록으로 남아 있음).

instruction record에 같은 패턴을 쓰면 안 된다. "불변 기록"이 목적이므로
**읽어도 소비되지 않고, 한 번 쓰면 덮어쓰지 않는** append-only 파일이어야
한다. 기존 sentinel 3종과 파일/함수 이름이 비슷해서 다음 구현자가
무심코 소비형으로 만들 위험이 실재한다.

### A5. join key 미정 — 라이브 측정이 선행돼야 한다

2절의 `call_id`가 이 설계의 전제인데, 이걸 뭘로 삼을지 아직 모른다.

- 기존 매칭 규율은 `rule + (target | decision_id)`이고, 이건 "가드된
  액션 1건"을 가리키지 "Agent call 1건"을 가리키지 않는다.
- PostToolUse payload에 `tool_use_id`가 실제로 오는지는 이 레포에서 한
  번도 확인 안 됐다(A2의 0건 검색). `resolvedModel` 존재를 2026-08-15에
  라이브 디스패치로 확인한 것과 **같은 방식의 측정이 먼저** 필요하다.
- PreToolUse 기록과 PostToolUse 기록을 같은 call로 묶는 것도 이 키에
  달려 있다. 키가 없으면 timestamp+prompt 해시 같은 임시방편이 되는데,
  그건 동일 프롬프트 재디스패치에서 깨진다.

**측정 전에는 스키마를 확정하지 않는다.**

## 부록 B: 열린 질문 (사용자 결정 필요)

`superpowers:brainstorming` 자리를 대신하는 블로킹 질문들. 안 정하고
플랜으로 넘어가지 않는다.

1. **원문 로그를 git-tracked로 둘 것인가?** `learning_data.jsonl`은
   tracked다. 그런데 instruction 원문에는 로컬 경로, 사적 맥락, 붙여넣은
   자료가 그대로 들어간다. 이 레포는 public이고, 커밋되면 영구 기록이
   된다. 선택지: (a) tracked — 재현성 우선, (b) `.gitignore` — 로컬
   전용, 대신 컨테이너가 회수되면 사라짐, (c) tracked하되 원문은 해시만
   남기고 본문은 로컬 — 그러면 1절 목적이 반쯤 무너짐.
2. **캡처 범위**: 사용자 턴만 / Agent 디스패치만 / 둘 다. A2에 따르면
   `/compact` 방어라는 원래 동기는 사용자 턴 쪽이 핵심이고, Drift 분석
   (4절)은 Agent 디스패치 쪽이 핵심이다. 둘은 다른 목적이라 하나만 고르면
   나머지 목적이 안 된다.
3. **로그 회전과의 충돌**: `tools/rotate_hook_logs.py`가 로그를
   잘라낸다. 원문 무절단·불변이 이 설계의 핵심인데, 회전 대상에 넣으면
   "영구 기록"이 거짓이 되고, 안 넣으면 파일이 무한 증가한다. 정책이
   필요하다(예: 회전 대신 아카이브 분할).

## 다음 단계

부록 B 3개 확정 → A5의 `tool_use_id` 라이브 측정 →
`superpowers:writing-plans`.
