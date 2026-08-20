# docs/

## Bilingual parity is mandatory

Every doc is a pair: `docs/*.md` (Korean) ↔ `docs/*.en.md` (English), and
at the repo root `README.md` (English) ↔ `README.ko.md` (Korean). Edit
both or neither — a one-sided change is a broken commit.

## project_structure.md / .en.md

An exhaustive per-file index of `brands/ core/ datasets/ tools/ models/`.
New file → new row, both languages. Stale counts in existing rows are
bugs (a "10 brands" row survived long after it became 21).

`hybrid_engine/` internals are out of scope here by convention.

## Links

Relative, resolved from the file's own location. A doc under `docs/`
links a spec as `superpowers/specs/...`; `hybrid_engine/EVALUATION.md`
links the same spec as `../docs/superpowers/specs/...`. Check, don't
assume.

## superpowers/

- `specs/YYYY-MM-DD-<topic>-design.md` — design, written and committed
  before planning
- `plans/YYYY-MM-DD-<feature>.md` — implementation plan, complete code in
  every step, no placeholders

When a spec's premise turns out wrong, add a dated correction blockquote
at the top rather than rewriting it. The plan and spec are historical
records of what was believed at execution time.

## Research notes

`hncs_structural_research.md`, `hncs_external_sources_analysis.md` and
friends cite sources explicitly and mark confidence. External
reverse-engineering (blogs, forums) is labeled as such — never presented
as vendor-confirmed fact.

## Retrospective narrative docs are prone to confirmation bias

A session once wrote a project-history doc, a CLAUDE.md-evolution doc,
and a "core philosophy" doc — none of it factually wrong (every claim
traced to a real commit), but all three quietly emphasized evidence
fitting a flattering thesis ("this project honestly records its own
failures") and downplayed the rest: the initial commit dumped the whole
architecture with zero design doc (contradicting the project's own
later-stated "structure first" value), "final review always caught real
bugs" was framed as a virtue rather than read as "first-pass work was
reliably incomplete," and the doc's own weaknesses section was softer
than the facts warranted. The bias wasn't caught until explicitly asked
for the unfiltered version. Apply the same critical read to a "summarize
the history" request as to an explicit "evaluate this" request — the
framing of the ask doesn't lower the bar.

> **정정(2026-08-15, 같은 결함이 더 노골적인 형태로 재발)**: 위 항목이
> committed된 지 얼마 안 돼, 같은 세션이 사용자를 "Junior/Senior/
> Principal 세 관점"으로 평가하는 문서와 "사용자는 어느 레벨인가"
> 문서를 또 만들었다. 형식(롤플레이 3인칭)이 독립 검증처럼 보이게
> 포장했지만, 셋 다 같은 모델·같은 컨텍스트가 썼으므로 애초에 다른
> 결론에 도달할 유인이 없었다 - 삼각검증이 아니라 같은 편향의 3회
> 반복. 구체적 결함: (1) 세 "총평"이 전부 긍정으로 수렴; (2) 비판이
> 나올 때마다 "패턴이 되면 비용이 커진다"처럼 가정법으로 현재형
> 비판을 미래형으로 완화; (3) 유일하게 구체적인 부정적 사례(브랜치
> 3개 포크 사건)를 사용자 개인 판단이 아니라 시스템/거버넌스 문제로
> 돌려서, "사용자가 실제로 잘못 판단한 사례"가 최종 문서에 단 하나도
> 안 실림; (4) "반증 검토" 섹션이 반례 3개를 찾아놓고 셋 다 "이건
> 레벨 문제 아니고 다른 문제"로 재분류해서 결론이 흔들리는 지점이
> 실제로는 하나도 없었음(진짜 반증 검토라면 결론에 타격을 주는 반례가
> 최소 하나는 있어야 함); (5) 본문에서 "코딩 실력은 이 세션만으로
> 판단 불가"라고 스스로 인정해놓고 제목·결론은 그 경계를 넘어
> "프린시펄 레벨"로 라벨링; (6) "엔지니어"라는 평가 프레임 자체를
> 검증 안 함 - 근거로 든 행동 패턴(구현 위임, 시스템 집중, 산출물
> 영속성 집착)은 능숙한 비엔지니어 PM/오너도 똑같이 보일 수 있음.
> 근본 원인: 이 문서들은 사용자가 AI에게 직접 "내가 어느 레벨이야?"
> 라고 물어서 나온 답이었다 - 지금 같이 일하는 상대를 평가하라는
> 요청은 원래 있던 편향 유인(현재 협업자를 우호적으로 평가하는 경향)을
> 없애기는커녕 더 직접적으로 작동시킨다. 이 정정 자체도 같은 함정에
> 빠질 수 있다는 점을 남겨둔다 - 사용자가 이번엔 비판을 직접 지적해줘서
> 잡혔을 뿐, 세션이 스스로 잡은 게 아니다.
