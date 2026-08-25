# Senior Engineer Mindset — 스킬 번들

코드를 쓰기 전에 시니어처럼 사고하도록 만드는 스킬 모음. 하나의 거대한 스킬 대신 **작고 조합 가능한 규율**로 쪼개져 있다.

## 구조

호출 축으로 나뉜다:

- **user-invoked (라우터)** — 사람이 직접 부르는 것. 오케스트레이션이 역할이다. 하위(model-invoked)를 부를 수 있지만, **다른 라우터는 부르지 않는다**
- **model-invoked (규율)** — 사람이 부를 수도 있고, 작업이 맞으면 에이전트가 알아서 꺼내 쓴다. 재사용 가능한 규율이 여기 담긴다

## 목록

### 라우터 (user-invoked)

| 스킬 | 역할 |
|---|---|
| `senior-engineer-mindset` | 작업에 맞는 규율을 골라 하위 스킬로 라우팅. 규모 조절과 출력 형식도 여기 |

### 규율 (model-invoked)

| 단계 | 스킬 | 역할 |
|---|---|---|
| 확인 | `search-first` | 외부 API·라이브러리는 기억이 아니라 문서로 |
| 확인 | `context-economy` | 컨텍스트에 올릴 것과 파일에 둘 것을 가른다 |
| 이해 | `clarify-the-real-problem` | 요청 뒤의 진짜 목적을 캐낸다 |
| 탐색 | `widen-the-solution-space` | 후보 접근법을 12축으로 넓히고 2~3개로 추린다 |
| 결정 | `weigh-tradeoffs` | 대안 비교 + 결정의 무게(되돌릴 수 있는가) |
| 결정 | `record-the-why` | 결정과 기각한 대안을 영구 기록으로 남긴다(ADR) |
| 설계 | `premortem` | 실패 시나리오와 실패 감지 |
| 설계 | `simplicity-budget` | YAGNI + 복잡도 예산 |
| 설계 | `design-for-the-next-reader` | 인터페이스 먼저 + 6개월 후 독자 |
| 설계 | `interface-contracts` | Hyrum의 법칙 — 노출한 건 전부 약속이 된다 |
| 설계 | `threat-and-scale-check` | 신뢰 경계 · 규모 · 다층 방어 |
| 검증 | `verifiability-first` | 성공 기준 선언 + 테스트 가능한 설계 |
| 계획 | `bite-sized-plan` | 파일 구조 → 작업 쪼개기 → 2~5분 단계 |
| 위임 | `delegate-to-subagents` | 서브에이전트 위임 판단·브리핑·검증 (+ 선택형 PreToolUse/PostToolUse 훅 번들) |
| 디버깅 | `root-cause-discipline` | 이미 풀렸는지 확인 → 근본 원인 → 증거 |
| 실행 | `chestertons-fence` | 지우거나 단순화하기 전에 왜 있는지부터 이해한다 |
| 실행 | `surgical-change` | 요청에 추적되지 않는 줄은 넣지 않는다 (+ 변경 크기 · 심각도 라벨) |
| 실행 | `measure-before-optimizing` | 성능은 증거(측정) 먼저 — 추측으로 최적화하지 않는다 |
| 실행 | `honest-artifacts` | 미검증 라벨 · 재현 가능성 · 지표의 함정 |
| 되돌아보기 | `fresh-context-review` | 쓴 맥락을 벗고 스펙 준수 · 코드 품질 두 축으로 |
| 되돌아보기 | `verify-before-claiming` | 증거 없이 완료를 말하지 않는다 |
| 되돌아보기 | `adversarial-review` | 되돌리기 싼 시점에 반박 편향으로 미리 심문 |

## 쓰는 법

셋 다 유효하다:

1. **전부 설치하고 놔둔다** — 라우터가 상황을 보고 알아서 고른다
2. **필요한 규율만 골라 설치한다** — 각 규율은 독립적으로 동작한다. 예를 들어 디버깅 규율만 원하면 `root-cause-discipline`만 가져간다
3. **고쳐서 쓴다** — 팀 컨벤션에 맞게 문구를 바꾸는 걸 전제로 썼다

## 설계 원칙

- 하나의 1100줄 스킬보다 **22개의 30~70줄 스킬**이 낫다. 필요한 것만 컨텍스트에 올라오고, 필요 없는 부분만 지울 수 있다
- 각 스킬의 `description`은 **언제 발동할지**를 담는다. 본문은 **무엇을 할지**만 담는다
- 규모 조절은 라우터의 책임이다. 함수 하나 짜는 데 설계 메모를 쓰면 실패한 것이다

## 출처

이 번들은 열 곳에서 아이디어를 가져와 재구성했다.

| 출처 | 링크 | 가져온 것 |
|---|---|---|
| addyosmani/agent-skills | https://github.com/addyosmani/agent-skills | Hyrum의 법칙(API 설계), 체스터턴의 울타리(단순화 전 이해), 반박 편향 리뷰(적대적 프레이밍), 변경 크기 기준(~100/300/1000줄), 심각도 라벨(Critical/Nit/Optional/FYI), "나중에 정리" 거부, 측정→지목→고치기→재측정(성능 최적화), ADR·왜를 남기는 문서화 |
| obra/superpowers | https://github.com/obra/superpowers | **가장 많이 참고** — 4단계 체계적 디버깅과 3회 실패 규칙, 완료 전 검증 게이트, 스파이크/한정/구조적 3경로 분류와 일방향 래칫, 잘게 쪼갠 계획, 위험 신호·합리화 차단 표 형식, YAGNI·복잡도 감소·증거 우선, 서브에이전트 위임(브리핑 전 기준점 기록, 보고/리뷰는 파일로, 고침→재리뷰 루프에 상한+판정 기록, 컨트롤러는 직접 안 고침 — subagent-driven-development) |
| songjiun10-collab/Hncs | https://github.com/songjiun10-collab/Hncs | 미검증 값 라벨링, 재현 가능성 감사, 지표 과적합 회피(보수적 선택), 수술적 변경, 깊게 파기 전 기존 해답 확인, 위험 등급별 게이트, 서브에이전트 위임 원칙(브리핑 최소화·한 번에 하나·보고 직접 검증 — CLAUDE.md "Controller/Implementer" 절) |
| mattpocock/skills | https://github.com/mattpocock/skills | **구조 전체** — user-invoked 라우터 / model-invoked 규율 이원화, 작고 조합 가능한 스킬, 스펙·표준 두 축 리뷰 분리 |
| affaan-m/ECC | https://github.com/affaan-m/ECC | 코딩 전 문서 확인(research-first), 새 컨텍스트 리뷰, 컨텍스트 경제("컨텍스트는 최적화하고 나머지는 영속화"), 작업 흐름 루프 |
| shinpr/sub-agents-skills | https://github.com/shinpr/sub-agents-skills | 서브에이전트 역할별 권한 분리(리뷰·구현·테스트는 지시뿐 아니라 권한도 갈라야 한다) |
| WenyuChiou/agent-collab-skills | https://github.com/WenyuChiou/agent-collab-skills | 반박 편향 논쟁(consequential한 결정에 에이전트 둘을 반대 입장으로 붙이기), 경쟁 탐색 결과 조정(reconciler) |
| rohitg00/awesome-claude-code-toolkit | https://github.com/rohitg00/awesome-claude-code-toolkit | 같은 문제를 여러 에이전트가 격리된 워크스페이스에서 경쟁적으로 탐색 후 비교·선택 |
| obra/superpowers (dispatching-parallel-agents) | https://github.com/obra/superpowers/blob/main/skills/dispatching-parallel-agents/SKILL.md | 독립 도메인 병렬 디스패치 기준(관련 없는 실패 여러 개 vs 관련 있는 실패), 병렬 브리핑 구조(좁은 범위+제약+산출물), 합치기 전 조정 절차(요약 개별 확인→겹침 확인→전체 테스트) |
| affaan-m/ECC (dmux-workflows) | https://github.com/affaan-m/ECC/blob/main/skills/dmux-workflows/SKILL.md | git worktree 격리 시 커밋 안 된 파일은 안 보인다는 것, 그걸 명시적으로 넣어줘야 한다는 것(seedPaths) |

### 스킬별 유래

| 스킬 | 주 출처 |
|---|---|
| `senior-engineer-mindset` (라우터) | mattpocock (구조) + ECC (흐름) |
| `search-first` | ECC |
| `context-economy` | ECC + Hncs |
| `clarify-the-real-problem` | superpowers + Hncs |
| `widen-the-solution-space` | 자체 구성 |
| `weigh-tradeoffs` | 자체 구성 + Hncs (위험 등급별 게이트) |
| `record-the-why` | addyosmani (documentation-and-adrs) |
| `premortem` | 자체 구성 |
| `simplicity-budget` | superpowers + Hncs |
| `design-for-the-next-reader` | superpowers + mattpocock (deep modules) |
| `interface-contracts` | addyosmani (Hyrum's Law) |
| `chestertons-fence` | addyosmani |
| `adversarial-review` | addyosmani (doubt-driven-development) |
| `threat-and-scale-check` | Hncs (다층 방어) |
| `verifiability-first` | superpowers (TDD) + Hncs (성공 기준 선언) |
| `bite-sized-plan` | superpowers |
| `delegate-to-subagents` | superpowers (subagent-driven-development + dispatching-parallel-agents) + Hncs (CLAUDE.md "Controller/Implementer" 절) + shinpr/sub-agents-skills(역할별 권한 분리) + WenyuChiou/agent-collab-skills·rohitg00/awesome-claude-code-toolkit(경쟁 탐색·반박 편향 논쟁) + ECC(dmux-workflows, worktree 격리 시 미커밋 파일 처리) |
| `verify-before-claiming` | superpowers |
| `root-cause-discipline` | superpowers (4단계·3회 규칙) + Hncs |
| `surgical-change` | Hncs + addyosmani (변경 크기 · 심각도 라벨) |
| `measure-before-optimizing` | addyosmani (performance-optimization) |
| `honest-artifacts` | Hncs |
| `fresh-context-review` | ECC + mattpocock |

### 안 가져온 것

의도적으로 뺐다 — 스킬 문서만으로는 구현되지 않고, 넣으면 "동작하는 척하는 문서"가 되기 때문이다.

- ECC의 instincts / continuous-learning (세션에서 패턴 자동 추출), 메모리 볼트, AgentShield — 하네스 런타임 기능
- Hncs의 훅 기반 강제(PreToolUse/PostToolUse 게이트) — 실행 환경이 필요하다
- mattpocock의 이슈 트래커 연동 스킬 (`triage`, `to-tickets`) — 이 번들의 범위(코드 쓰기 전 사고) 밖

각 원본은 각자의 라이선스를 따른다. 이 번들은 그 아이디어를 한국어로 재구성한 것이지 코드 복제가 아니다.

## 업데이트 로그

- 2026-08-24: `measure-before-optimizing`, `record-the-why` 추가(둘 다 addyosmani/agent-skills — 각각 performance-optimization, documentation-and-adrs 재구성). GitHub 재검색으로 기존 20개에 없던 갭(성능 최적화 전 측정, 결정 이유의 영구 기록)을 찾아 채움. 같은 저장소의 나머지 스킬(ci-cd, git-workflow, browser-testing, frontend-ui 등)은 툴링/도메인 특화라 "코드 쓰기 전 사고"라는 이 번들의 범위 밖이라 계속 제외.
- 2026-08-24(같은 날, 이후): 다른 4개 소스(superpowers·mattpocock·ECC·Hncs) 재훑음 — 갭 없음 확인만(추가 없음). superpowers `brainstorming`(스파이크/한정/구조적 3경로+하드 게이트)은 이미 라우터 자체가 그 구조이고, mattpocock `code-review`(스펙·표준 두 축 병렬 리뷰)는 이미 `fresh-context-review` 유래에 있고, ECC `security-review`는 Next.js/Supabase/Solana 스택 특화라 범위 밖이자 이 세션 환경의 별도 시스템 스킬과 중복. GitHub 전체로 넓혀도(가장 화제였던 forrestchang/andrej-karpathy-skills의 4원칙 포함) 마찬가지 — 그 4원칙은 오히려 이미 Hncs CLAUDE.md의 "Working principles" 제목 그대로라 새로울 게 없었음.
- 2026-08-24(같은 날, 세 번째): `delegate-to-subagents` 추가(Hncs CLAUDE.md의 Controller/Implementer 절 재구성 — 언제 위임할지, 브리핑을 뭘 주고 뭘 안 줄지, 보고를 어떻게 검증할지). 이 번들 최초로 `scripts/`를 들고 있는 스킬 — `check_dispatch_brief.py`가 Task 호출 전후(PreToolUse/PostToolUse)에 겹치는 dispatch와 대화-요약형 브리핑을 감지한다. 기본은 advisory(사람에게만 보이는 경고, Claude 행동엔 영향 없음), `DELEGATE_HOOK_STRICT=1`이면 실제로 막고 이유를 Claude에 돌려준다. 격리된 stdin으로 6개 케이스(비-Task 통과, 정상 브리핑 통과, 긴 페이스트 감지, PostToolUse로 카운트 닫힘, STRICT 모드 exit 2, 깨진 입력 fail-open) 직접 실행해 확인 — Hncs 실제 훅(`_hook_common.py`, CRITICAL·deny-by-default)과는 설계 등급이 다르다는 걸 SKILL.md에 명시.
- 2026-08-25: `delegate-to-subagents` 보강 — Hncs만 보고 썼던 초판이 이 저장소 CLAUDE.md가 실제로 가리키는 `superpowers:subagent-driven-development`(obra/superpowers)를 안 보고 지나쳤다는 지적을 받고 그 SKILL.md를 실제로 읽어서 반영. 추가된 것: 위임 직전 기준점(`git rev-parse HEAD`) 기록 — 나중에 `HEAD~1` 대신 이 기준점으로 diff 범위를 잡는다(안 그러면 그 사이 낀 커밋이 범위를 조용히 틀리게 만든다), 보고·리뷰는 파일로 받기(압축 생존), 고침→재리뷰 루프에 상한을 두고 상한 넘으면 컨트롤러가 직접 판정 후 기록(조용히 버리지 않음), 리뷰 지적은 지적 하나당이 아니라 한 서브에이전트가 한 번에 받아 고침, 컨트롤러는 리뷰를 건너뛰게 되므로 직접 안 고침, 촘촘한 폴링 대신 완료 신호까지 기다림. superpowers의 전체 장치(git worktree 격리, ledger 파일, `scripts/task-brief`·`scripts/review-package`)는 이 번들의 30~70줄 압축 규율 스타일과 안 맞아서 원리만 가져오고 스크립트 인프라는 안 가져옴.
- 2026-08-25(같은 날, 이후): "다른 프로젝트도 참고" 지시로 서브에이전트 오케스트레이션 쪽을 더 넓게 훑음 — shinpr/sub-agents-skills, WenyuChiou/agent-collab-skills, rohitg00/awesome-claude-code-toolkit 실제 README 확인. 3개 반영: (1) 역할별 권한 분리(리뷰어에 쓰기 권한 안 줌 — shinpr), (2) "한 번에 하나만"의 예외로 격리된 워크스페이스에서 접근법을 일부러 경쟁시켜 비교하는 경우 명시(rohitg00 + WenyuChiou의 task-splitter/reconciler), (3) 되돌리기 어려운 결정에서 판단이 갈릴 때 에이전트 둘을 반대 입장으로 붙이는 반박 편향 논쟁(WenyuChiou의 adversarial-debate). WenyuChiou의 shared-memory(`.coord/memory.yml` 크로스세션 블랙보드)는 이미 반영된 superpowers 쪽 기준점·판정 기록 원리와 상당 부분 겹쳐서 따로 안 뺌.
- 2026-08-25(같은 날, 세 번째): "ECC하고 매트 뭐시기도" 지시로 나머지 두 소스를 이 주제로 재확인. **mattpocock**은 관련 있는 걸 못 찾음(`/implement-spec`이 서브에이전트 최대 동시성으로 티켓을 구현한다는 X 게시물은 있었지만 유지되는 SKILL.md가 아니라 트윗이라 근거로 안 씀). **ECC**의 `dmux-workflows`(tmux 기반 병렬 에이전트 오케스트레이션)에서 git worktree 격리 시 커밋 안 된 로컬 파일은 워커에 안 보인다는 것과 그걸 명시적으로 넣어줘야 한다는 `seedPaths` 개념을 가져옴. 이 과정에서 **superpowers 자체의 전용 스킬 `dispatching-parallel-agents`**를 놓쳤던 걸 발견해서 같이 반영 — 독립 도메인 병렬 디스패치(관련 없는 실패 여러 개를 한 응답 안에서 동시에 dispatch)와 순차 디스패치를 구분하는 기준, 합치기 전 조정 절차(요약 개별 확인 → 겹침 확인 → 전체 테스트)를 추가. 이걸 반영하면서 `check_dispatch_brief.py`의 "겹치는 dispatch면 경고" 로직이 문제였다는 것도 알게 됨 — 2~3개 독립 도메인 병렬은 스킬이 직접 권장하는 정상 패턴인데 그걸 전부 걸고 있었음. 임계값을 1개 이상 → **4개 이상 열려 있을 때만**으로 올리고 문구도 "잘못됐다"가 아니라 "정말 독립적인지 확인하라"로 순화. 격리된 stdin으로 재검증(3개 열 때까지 조용, 4번째 열 때 경고) 확인.
