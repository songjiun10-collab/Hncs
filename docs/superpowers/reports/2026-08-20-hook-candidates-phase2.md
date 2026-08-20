# 새 Hook 후보 제안 (Phase 2, 로그 기반)

**상태**: 제안서 — 사람 검토 대기. 코드 없음, `settings.json` 변경 없음.
`docs/superpowers/specs/2026-08-19-hook-evolution-design.md`의 4절(데이터로
새로운 Hook 설계) + 브레인스토밍 결정사항 #4("opus 서브에이전트가
`learning_data.jsonl`을 분석해서 새 Hook 후보를 제안 … **배포(새 훅 코드
작성/`settings.json` 등록)는 여전히 사람 승인 필요**")의 산출물이다.
배포는 이 문서의 범위 밖 — Implementer→Reviewer→사용자 게이트를 그대로
통과해야 한다.

**작성**: 2026-08-20, opus 서브에이전트. 어떤 훅 파일/설정도 안 건드림.

## 1. 데이터와 방법

| 소스 | 크기 | 성격 |
|---|---|---|
| `.claude/hooks/violations_log.jsonl` | 50 events (2026-08-14 ~ 08-20) | 실제 deny/ask/override 원본 이벤트 |
| `.claude/hooks/override_audit.jsonl` | 10 events | 실제로 override된 가드 액션 + decision record |
| `.claude/hooks/learning_data.jsonl` | 1 line, `n_events=13`, `n_determinable=4` | `tools/eval_hook_judgments.py`의 캘리브레이션 리포트 |

기존 로스터 18개(`.claude/hooks/*.py`)와 `.claude/settings.json`의 실제
등록 상태를 전부 읽고 나서 "이미 있는 것"과 "빈 곳"을 갈랐다.

**표본 크기 경고 (모든 candidate에 적용)**: `learning_data.jsonl`은
`n_events=13`, `n_determinable=4`, `severity_calibration.verdict`가
`"표본 부족(insufficient_n, n=4 < min_n=20)"`이다. `tools/CLAUDE.md`의
`_MIN_N_FOR_RATE`(기본 20) 규율대로, 이 문서는 **어떤 비율(rate)도, 어떤
캘리브레이션 판정(verdict)도 주장하지 않는다.** 아래 숫자는 전부 raw
count이며, 각 count 옆에 재현 명령을 붙였다. "N번 일어났다"는 검증
가능하지만 "N%가 그렇다" 또는 "에이전트는 X하는 경향이 있다"는 이
표본으로 말할 수 없다.

또 하나: 이 로그의 상당수는 **의도적 침투테스트(hook pentest 2~13차,
`.claude/hooks/README.md`)와 라이브 스모크 테스트**에서 나왔다 — 자연
발생 작업 트래픽이 아니다(`LIVE-SMOKE-*`, `DEVIATION-DEMO-*`,
`MANDATORY-GATE-LIVE-*`, `"pentest"` 마커가 붙은 항목들). 따라서 여기서
보이는 패턴은 "에이전트가 평소에 이렇게 행동한다"가 아니라 "이 시스템을
의도적으로 밀었을 때 이 지점이 비어 있다"에 가깝다. Candidate별로 이
구분을 명시했다.

**어느 소스가 뒷받침하는가**:
- Candidate 1만 부분적으로 `learning_data.jsonl`(n=13/n=4)과 관련 —
  단, 그 파일이 *제공하지 못하는* 것(gating)이 제안의 요지다.
- Candidate 2~6은 전부 `violations_log.jsonl`/`override_audit.jsonl`
  원본 이벤트에 직접 기반한다. `learning_data.jsonl` 미사용.

---

## 2. Candidate 목록

### C1. `protect_severity_understatement.py` — 자기평가 등급이 가드 등급보다 낮은데 self-servable override로 통과하려는 경우

**등급 제안**: HIGH (좁은 교집합에서만) / LOW 로그전용 (그 외)

**증거 (raw count, `violations_log.jsonl`)**

decision record가 붙은 이벤트 13개 중 **8개**에서 `decision.self_severity`가
그 이벤트를 낸 훅 자신의 `severity`보다 낮다. 그중 **6개**는 2단계 이상
낮고, **6개**는 동시에 `confidence >= 0.9`다.

```bash
cd /home/user/Hncs/.claude/hooks && python3 - <<'PY'
import json
RANK={"LOW":0,"MEDIUM":1,"HIGH":2,"CRITICAL":3}
rows=[json.loads(l) for l in open('violations_log.jsonl')]
d=[r for r in rows if r.get('decision')]
u=[r for r in d if RANK.get(r['decision']['self_severity'],9)<RANK.get(r.get('severity'),-1)]
print(len(d), len(u),
      sum(1 for r in u if RANK[r['severity']]-RANK[r['decision']['self_severity']]>=2),
      sum(1 for r in u if (r['decision'].get('confidence') or 0)>=0.9))
PY
# -> 13 8 6 6
```

가장 명시적인 두 건 (원문 그대로):

- `2026-08-16T08:43:31+00:00` / `protect_never_touch` / `severity: CRITICAL`
  / `overridden: true` — `decision`: `{"self_severity": "LOW",
  "confidence": 0.9, "reason": "DEVIATION-DEMO-5510 clahe_clip 기본값만
  바꾸는 사소한 수정으로 확신함", "expected_risk": "거의 없음 - 그냥
  파라미터 튜닝이라고 판단"}`. 같은 이벤트의 override reason은
  `"DEVIATION-DEMO-5510 승인 - 스크래치 더미, 실제로는 CRITICAL 등급
  apply_* 수정"` — 즉 **override 사유 자체가 자기 decision record와
  모순**된다(한쪽은 LOW라고 확신, 다른 쪽은 실제로는 CRITICAL이라고
  인정).
- `2026-08-17T23:29:58+00:00` / `protect_destructive` / `CRITICAL` /
  `override` — `{"self_severity": "LOW", "confidence": 0.95, "reason":
  "스크래치 clone 동기화, 재시도", "expected_risk": "없음"}`. 13분 뒤
  `23:31:16`에 같은 형태로 한 번 더(`"스크래치 clone 최신화"`, 역시 LOW /
  0.95 / `"없음"`).

CRITICAL 가드 + self_severity ≤ MEDIUM + 실제 override 통과 = **3건**
(위 2건 + `2026-08-16T08:43:31`의 never_touch). 재현:

```bash
cd /home/user/Hncs/.claude/hooks && python3 - <<'PY'
import json
RANK={"LOW":0,"MEDIUM":1,"HIGH":2,"CRITICAL":3}
rows=[json.loads(l) for l in open('violations_log.jsonl')]
print(sum(1 for r in rows if r.get('decision') and r.get('severity')=='CRITICAL'
          and RANK.get(r['decision']['self_severity'],9)<=1 and r.get('overridden')))
PY
# -> 3
```

**빈 곳(gap)**

`require_decision_or_deny()`(`_hook_common.py:727`)는 decision record가
**존재하는지**만 본다 — 그 안의 `self_severity`가 가드 자신의 등급과
정합적인지는 어떤 훅도 안 본다. `tools/eval_hook_judgments.py`는 이
불일치를 **사후에 측정**하지만(`_over_under_match()`), 측정은 gating이
아니고 게다가 `n_determinable=4 < min_n=20`이라 지금은 `verdict`조차 안
낸다. 즉 "CRITICAL 가드가 걸렸는데 에이전트는 LOW라고 0.95 확신하면서
자기가 쓴 bash 주석 한 줄로 통과" 경로에 아무 마찰이 없다. 이건
README "알려진 한계"의 *"override는 self-servable함"* 항목의 구체적
계측 지점이다 — 자기평가와 가드 판단이 2단계 이상 벌어졌다는 건 이
시스템이 관측할 수 있는 몇 안 되는 객관적 drift 신호다.

**등급 근거**

- 기본은 **LOW 로그전용**(`protect_agent_model_naming.py`의 선례 —
  "정말 마찰을 줄 만한 발견이 아니면 안 막는다"). 1단계 차이는 정상적
  판단 편차 범위.
- **HIGH**는 좁은 교집합에만: `severity == CRITICAL` **and** delta ≥ 2
  **and** 통과 경로가 self-servable override(bash 주석/sentinel). 이
  조합은 "가장 위험한 등급에서, 자기가 이미 위험도를 크게 낮게 매긴
  주체가, 스스로 발급한 사유로 통과"라 CRITICAL이 서브에이전트발
  override를 아예 안 받는 것과 같은 논리(자기 승인 불가)가 적용된다.
  HIGH로 두면 스펙 5절의 2-agent consensus fast-path를 그대로 쓸 수
  있다(직접호출 `ask()`, 서브에이전트발 deny, consensus 시 통과) — 새
  메커니즘이 필요 없다.
- CRITICAL로 올리지 않는 이유: 이건 파괴적 액션 자체가 아니라 그
  액션에 대한 *메타 판단*이다. 오탐 시 잃는 게 크고(정당한 "이 CRITICAL
  가드는 이번 맥락에선 사소하다"는 판단은 실제로 존재한다 — 아래 caveat),
  복구 가능하다.

**불확실성/caveat**

- 8건 중 최소 5건은 명시적 테스트 시나리오다(`DEVIATION-DEMO-5510`,
  `LIVE-SMOKE-7788`, `"pentest"`, `"verify fix"`) — **의도적으로 낮게
  매긴 것**일 수 있고, 실제로 `DEVIATION-DEMO-5510`은 이름부터
  deviation 데모다. 자연 발생 사례는 `/workspace/hook` 스크래치 clone
  건 2개 정도이고, 그 2건은 사후에 봐도 판단이 **맞았다**(원격에 이미
  push된 스크래치 clone 동기화 — 실제로 LOW가 타당). 즉 이 패턴이
  "실제 손해로 이어졌다"는 증거는 0건이다.
- 따라서 C1의 정당화는 "이미 사고가 났다"가 아니라 "이 시스템이 drift를
  관측할 수 있는 유일한 수치 신호인데 아무도 안 쓰고 있다"이다. 그
  선에서만 읽어야 한다.
- 오탐 비용이 실재한다: "가드 등급은 CRITICAL이지만 이 파일/이 맥락에선
  LOW"는 정당한 판단일 수 있고(위 2건이 바로 그 예), HIGH로 막으면
  정확히 그 정당한 케이스에 2-agent 디스패치 비용(~50-70k 토큰 × 2)이
  붙는다.

---

### C2. `protect_denial_ladder.py` — 같은 target에 대한 연속 deny를 "요구사항 체크리스트"로 소비하는 패턴

**등급 제안**: HIGH

**증거 (`violations_log.jsonl`)**

동일 (hook, target) 쌍이 반복 등장하는 클러스터 3개. override 주석을
제거해 정규화하면:

```bash
cd /home/user/Hncs/.claude/hooks && python3 - <<'PY'
import json,re,collections,datetime
rows=[json.loads(l) for l in open('violations_log.jsonl')]
norm=lambda t: re.sub(r"#\s*HNCS-OVERRIDE:.*","",t or "").strip()
g=collections.defaultdict(list)
for r in rows:
    if r.get('target'): g[(r['hook'],norm(r['target']))].append(r)
for k,v in sorted(g.items(), key=lambda kv:-len(kv[1])):
    if len(v)>1:
        s=(datetime.datetime.fromisoformat(v[-1]['timestamp'])
           -datetime.datetime.fromisoformat(v[0]['timestamp'])).total_seconds()
        print(len(v), int(s), k[0], [r.get('decision_kind') for r in v])
PY
# -> 5 15731 protect_push_safety ['deny','deny','deny','deny','override']
# -> 2 23   protect_generated_files ['deny','deny']
# -> 2 14   protect_destructive ['deny','deny']
```

가장 선명한 건 2026-08-20 `protect_push_safety` 클러스터 — **같은 명령**
(`git push --force-with-lease origin
claude/hncs-v13-author-fix-tziws6:claude/hncs-v13-dpreview-calibration 2>&1`)에
대해 38초 안에 4번, 그리고 통과:

| 시각 | 결과 | 그 시도가 추가한 것 |
|---|---|---|
| `08:47:28` | deny | (decision record 붙음, 하지만 deny 메시지는 "override 없음") |
| `08:47:46` | deny | decision record 소진됨 → `"decision record가 먼저 있어야 함"` |
| `08:47:53` | deny | `# HNCS-OVERRIDE: protect_push_safety: author-fix rebase, content diff 0, 사용자 승인됨` 추가 → 이번엔 decision record가 없어서 deny |
| `08:48:06` | **override, allow** | 둘 다 갖춰서 통과 |

(같은 명령의 첫 시도는 4시간 21분 전 `04:25:55`.) `protect_destructive`도
같은 모양이다: `23:29:32` deny(record 없음) → `23:29:46` deny(record는
썼는데 override 없음) → `23:29:58` override 통과 — 26초.

**빈 곳(gap)**

지금 로스터의 모든 가드는 **stateless**다. 각 호출은 "decision record
있나? override 있나?"를 독립적으로 보고, 같은 target이 방금 전에 몇 번
거절당했는지는 아무도 모른다. 그래서 deny 메시지(정확히 무엇을 추가하면
통과하는지 전부 알려준다 — 설계상 의도)가 **자동으로 소진 가능한
체크리스트**가 된다. 여기서 문제가 되는 건 "재시도" 자체가 아니라
`08:47:28`→`08:48:06` 사이에 **판단이 다시 이뤄졌다는 흔적이 0**이라는
것이다: 마지막 decision record의 `reason`은 첫 번째 것과 사실상 같은
텍스트고(`"f64ec504 및 5개 root 커밋의 author가 …"`), 사이에 바뀐 건
override 주석 한 줄뿐이다. 3차 라운드가 확인한 "override 판별 로직 자체는
견고하다"는 결론과 모순되지 않는다 — 이건 로직을 속인 게 아니라
**같은 로직을 순서대로 만족시킨** 것이다.

**등급 근거**

HIGH — `protect_branch.py`/`protect_test_coverage.py`와 같은 성격
("절차가 실제로 지켜졌는지"에 대한 가드, 데이터 손실 자체는 아님).
동작 제안: 같은 (rule, 정규화된 target)에 대해 최근 10분(기존
`_SENTINEL_MAX_AGE_SECONDS`와 같은 창) 안에 deny가 N회(예: 3) 이상
쌓인 뒤 도착한 **self-servable override는 안 받고** HIGH 경로로
넘긴다(직접호출 `ask()` / 서브에이전트 deny / 2-agent consensus 통과).
CRITICAL로 하지 않는 이유: 반복 재시도는 그 자체로 파괴적이지 않고,
정당한 경우(위 push 사례가 실제로 그렇다 — 사용자가 `AskUserQuestion`으로
force-with-lease를 승인했다고 decision record에 적혀 있다)가 분명히
존재해서 사람/consensus 경로로 올리는 게 맞지 완전 차단은 과하다.

**불확실성/caveat**

- 클러스터 3개, 그중 "밀어붙여서 결국 통과"까지 간 건 2개
  (`push_safety` 5건, `destructive` 3건 — 후자는 `23:29:32`/`23:29:46`/
  `23:29:58`). 표본이 작다.
- 두 사례 모두 **사후 판단으로는 옳은 액션이었다**(author 수정 rebase는
  content diff 0, 스크래치 clone 동기화). 즉 이 패턴이 나쁜 결과를
  냈다는 증거는 없다 — 문제는 결과가 아니라 "가드가 마찰을 주기로 한
  지점에서 실제 마찰이 38초짜리 형식 절차로 축소됐다"는 것.
- 구현 시 주의: 훅이 자기 로그를 읽는 구조가 되면 로그 회전
  (`tools/rotate_hook_logs.py`)과의 상호작용, 그리고 훅 실행 시간
  (`settings.json`의 `timeout: 15`)을 같이 봐야 한다. 별도 카운터
  sentinel이 더 깔끔할 수 있다 — 단 그 sentinel도 C4의 보호 대상이 돼야
  한다(2차 라운드 finding #8의 교훈: 새 sentinel을 보호 없이 내보내지
  않는다).

---

### C3. `protect_medium_approval_sentinel_bypass.py` — MEDIUM 승인 sentinel이 어떤 가드로도 안 막힘

**등급 제안**: CRITICAL, override 없음 (`protect_decision_record_bypass.py`와 동일 계약)

**증거 (코드 + 로그, 신규 발견)**

`protect_decision_record_bypass.py`의 보호 테이블에는 **2개**만 있다:

```python
_PROTECTED_SENTINELS = {
    os.path.abspath(_DECISION_RECORD_PATH): (...),
    os.path.abspath(_CONSENSUS_PATH): (...),
}
```

그런데 `_MEDIUM_APPROVAL_PATH`(`.pending_medium_approval.json`) —
`record_agent_approval.py`가 실제 opus 디스패치 응답을 파싱해야만
생겨야 하는, MEDIUM 등급의 **유일한 통과 경로** — 는 이 테이블에 없고,
리포 전체에서 어떤 PreToolUse 가드도 이 경로를 참조하지 않는다:

```bash
cd /home/user/Hncs && grep -rn "pending_medium_approval\|_MEDIUM_APPROVAL_PATH" \
  .claude/hooks/*.py | grep -v _hook_common.py
# -> (출력 없음)
```

`.claude/hooks/README.md`도 이 파일을 "보호 안 되는 sentinel"로 적어둔
적이 없다(2차 라운드 finding #8은 `.last_whole_branch_review_sha`만
다룬다 — 이 파일은 아님). 로그 쪽 방증: `protect_decision_record_bypass`가
낸 6개 이벤트는 전부 `.pending_decision_record.json`(1건) 또는
`.pending_consensus.json`(5건) 대상이고, medium-approval 경로에 대한
차단 기록은 0건이다.

```bash
cd /home/user/Hncs/.claude/hooks && python3 -c "
import json;rows=[json.loads(l) for l in open('violations_log.jsonl')]
print([r.get('target','').split('/')[-1] for r in rows if r['hook']=='protect_decision_record_bypass'])"
# -> ['.pending_decision_record.json', '.pending_consensus.json', '.pending_consensus.json',
#     '.pending_consensus.json', '.pending_consensus.json', '.pending_consensus.json']
```

**빈 곳(gap)**

`protect_decision_record_bypass.py` docstring이 스스로 정한 원칙 —
"각 sentinel의 전용 writer(MCP 툴 / 실제 Agent 디스패치를 파싱하는
PostToolUse 훅)를 유일 통로로 만들려면 raw-Write 경로를 닫아야 한다" —
이 medium-approval sentinel에는 적용이 안 돼 있다. 결과적으로 MEDIUM
등급의 "opus가 진짜로 디스패치돼야 생기는 sentinel이라 위조 난이도가
한 단계 높다"는 신뢰 근거가, **Write 툴 한 번**으로 무너진다(그
sentinel의 스키마는 `medium_approval()`이 읽을 때의 rule/target/fresh
검사뿐이고, 그건 위조하기 쉬운 필드들이다). 2차 라운드 finding #8이
`.last_whole_branch_review_sha`에 대해 실증한 것과 정확히 같은 모양의
구멍이며, 그 finding의 대응 방향(8번)도 아직 미수정이므로 같은 훅에서
**두 파일을 함께** 다루는 게 자연스럽다.

**등급 근거**

`protect_decision_record_bypass.py`와 동일: CRITICAL, override 없음,
decision record 요구도 없음(sentinel 보호 메커니즘을 sentinel 메커니즘으로
게이팅하면 순환). 실제로 이 후보의 가장 단순한 형태는 "새 훅"이 아니라
**기존 `_PROTECTED_SENTINELS` 테이블에 2줄 추가**다 — 그쪽이 더 낫다면
그렇게 가는 게 맞다. 새 파일이 정당화되는 경우는 C4와 묶어서 Bash 경로
커버까지 같이 할 때다(아래).

**불확실성/caveat**

- 이건 로그에서 **관측된 공격**이 아니라 **관측되지 않은 것에서 추론한
  구멍**이다(차단 기록 0건은 "아무도 안 시도했다"이지 "안전하다"가
  아니다). 코드 레벨로는 완전히 checkable하지만(위 grep), 악용된 적이
  있다는 증거는 없다.
- 실제 침투 실증은 README 2차 라운드가 이미 같은 계열로 해뒀다
  (`.last_whole_branch_review_sha`에 `echo`만으로 "최종 리뷰 통과" 완성).
  이 후보는 그 실증의 확장 적용이지 새 실험 결과가 아니다.

---

### C4. `protect_sentinel_bash_writes.py` — sentinel 보호가 Edit/Write에만 걸려 있고 Bash엔 없음

**등급 제안**: CRITICAL, override 없음

**증거**

`.claude/settings.json`에서 `protect_decision_record_bypass.py`는
`matcher: "Edit|Write|MultiEdit"` 블록에만 등록돼 있다(`Bash` 블록엔
`protect_push_safety`/`protect_never_touch`/`protect_destructive`/
`protect_branch`/`protect_test_coverage` 5개뿐). `.claude/hooks/README.md`의
`### protect_decision_record_bypass.py가 Bash를 안 봄 - 실증(2026-08-18)`
절이 격리 환경에서 3단계로 이걸 실증해뒀다 — `python3 -c
"...open('.claude/hooks/.pending_decision_record.json','w')..."` 는 이
CRITICAL 가드를 아예 안 거치고, 위조 승인과 합치면 `_LEARNED_LUT` 수정이
`allow`까지 간다. **대응 방향은 그 문서에 적혀 있고 아직 미수정이다.**

로그 쪽 방증: `protect_decision_record_bypass`의 6개 이벤트는 전부
Edit/Write 경로(모두 `target`이 파일 경로)이고, Bash 경로 차단은 0건.
같은 기간 Bash로 sentinel 디렉토리를 다루는 명령은 실제로 흘러다녔다 —
예: `2026-08-18T23:36:02+00:00` / `protect_destructive`의 target에
`export HNCS_HOOK_DECISION_RECORD_SENTINEL="$SCRATCH/.pending_decision_record.json"`
등 5개 sentinel 경로 환경변수가 통째로 들어 있다(이 건은
`protect_destructive`가 `rm -rf`로 잡은 것이지 sentinel 가드가 잡은 게
아니다).

**빈 곳(gap)**

`protect_never_touch.py`는 이미 같은 문제를 겪고 **Bash 커버리지를
추가**했다(docstring: "a code review found this hook's
Edit|Write|MultiEdit-only matcher meant `sed -i`, `python3 -c
"...open(...).write(...)"`, `tee`, or shell redirection … went through
unchecked"). 그 파일의 `_REDIRECT_TARGET_RE`/`_SED_INPLACE_TARGET_RE`/
`_TEE_TARGET_RE`/`_CP_MV_DEST_RE`/`_PY_WRITE_OPEN_RE` 5종 패턴이 그대로
재사용 가능한 선례다. sentinel 경로들(`.pending_decision_record.json`,
`.pending_consensus.json`, `.pending_medium_approval.json`,
`.last_whole_branch_review_sha`)에는 그 커버리지가 없다.

**등급 근거**

보호 대상이 같으므로 등급도 같다 — CRITICAL, override 없음. 다만
`protect_never_touch.py`의 Bash 경로가 물려받은 알려진 한계
(2차 라운드 finding #1·#2·#4: heredoc 본문 스트리핑, 문자열 인접 결합,
`eval "..."`)를 그대로 물려받는다는 걸 제안 단계에서 명시해야 한다 —
"막았다"가 아니라 "가장 흔한 모양을 막았다"다.

**불확실성/caveat**

- C3와 마찬가지로 **미관측 구멍**이다. 다만 이쪽은 README가 격리
  환경에서 실제로 실증까지 해둔 항목이라(2026-08-18) 근거가 한 단계
  강하다.
- C3와 C4는 하나의 훅으로 합치는 게 자연스럽다(보호 경로 테이블 하나 +
  Edit/Write 경로 + Bash 경로). 별도 후보로 적은 이유는 등급 판단과
  구현 난이도가 다르기 때문 — C3는 테이블 2줄, C4는 새 정규식 세트.

---

### C5. `protect_hook_tree_integrity.py` — 가드 트리 자체(`.claude/hooks/`, `.claude/settings.json`)가 무보호

**등급 제안**: CRITICAL (서브에이전트발 override 불가 — `protect_never_touch.py`와 동일 계약)

**증거**

- 이 체크아웃 52개 커밋 중 **42개**가 `.claude/hooks/`를 건드리고, 그중
  **16개**가 `protect_*.py`/`_hook_common.py` 등 훅 스크립트 자체를
  수정한다. `.claude/settings.json`은 2개. (기준 커밋 `8523979`,
  2026-08-20 — 이 저장소는 계속 커밋되므로 숫자는 커밋마다 올라간다.
  비율이 요점이지 절대값이 아니다.)
  ```bash
  cd /home/user/Hncs && git rev-list --count HEAD && \
    git log --oneline -- .claude/hooks | wc -l && \
    git log --oneline -- '.claude/hooks/*.py' | wc -l && \
    git log --oneline -- .claude/settings.json | wc -l
  # -> 52 / 42 / 16 / 2   (at 8523979)
  ```
- 그런데 60개 로그 이벤트(violations 50 + audit 10) 중 **가드 대상이 훅
  스크립트나 `settings.json`이었던 이벤트는 0건**이다. `.claude/hooks`
  문자열이 등장하는 6건은 전부 sentinel 파일 경로(1건) 또는 reason/
  target 안의 부수적 언급(5건)이고, 훅 소스 파일에 대한 쓰기를 막은
  기록은 하나도 없다.
  ```bash
  cd /home/user/Hncs/.claude/hooks && python3 -c "
  import json
  rows=[json.loads(l) for l in open('violations_log.jsonl')]+[json.loads(l) for l in open('override_audit.jsonl')]
  print(sum(1 for r in rows if (r.get('target') or '').endswith('.py') and '.claude/hooks' in (r.get('target') or '')))"
  # -> 0
  ```
- `.claude/hooks/README.md`의 "알려진 한계" 마지막 항목이 이 위협
  클래스를 이미 명시적으로 인정해뒀다: *"훅 스크립트/설정 자체의
  무결성·공급망 신뢰는 이 시스템 어디에도 다뤄지지 않는다 (2026-08-19 …
  완전히 새로운 위협 클래스)"* — 대응 방향으로 *"훅 트리에 대한
  체크섬/서명 검증, 또는 최소한 `.claude/hooks/`/`.claude/settings.json`
  자체를 기존 Edit/Write 가드 대상에 추가"*까지 적혀 있고 **미수정**이다.

**빈 곳(gap)**

`protect_never_touch.py`가 지키는 건 `brands/*.py`와
`hybrid_engine/assets/profiles/*`뿐이다. 가드 트리 자체는 이 저장소에서
가장 자주 수정되는 영역(42/52 커밋)이면서 유일하게 **자기 자신을 지키는
가드가 없는** 고위험 영역이다. 모든 다른 가드는 "훅이 변조 없이
실행된다"는 전제 위에 서 있으므로, 이 한 곳이 뚫리면 나머지 18개가
동시에 무의미해진다 — 등급 계산에서 이 비대칭이 결정적이다.

**등급 근거**

CRITICAL. `protect_never_touch.py`와 같은 계약(서브에이전트발은 override
불가, 오케스트레이터 직접 호출은 sentinel/bash-marker override 가능)이
가장 자연스럽다 — 이유도 같다: 자기 자신이 사유를 지어낼 수 있는
override가 가장 치명적으로 작동하는 등급이라서.

**불확실성/caveat**

- **이건 로그에서 새로 발견한 게 아니다.** README가 2026-08-19에 이미
  적어둔 항목이고, 이 문서가 추가하는 건 노출 규모의 정량화(42/52,
  16 커밋, 로그 0건)뿐이다. 크레딧은 그 항목에 있다.
- 자충수 위험이 실재한다: 훅 트리를 가드로 막으면 **훅 개발 자체가
  매번 override를 요구**한다(42/52 커밋이 그 대상이 된다). Phase 2에서
  이걸 채택하려면 "훅 자체를 고치는 작업"의 정상 경로를 같이 설계해야
  한다 — 예: `.claude/hooks/` 편집은 LOW 로그전용, `settings.json`
  등록 변경만 CRITICAL(등록이 실제 실행 경로를 결정하므로). 이
  분기는 사람이 정할 문제라 여기서 단정하지 않는다.
- 체크섬/서명 검증 쪽(진짜 공급망 방어)은 PreToolUse 훅으로는 부분적으로만
  가능하다 — 훅이 이미 변조된 뒤에는 그 훅이 자기 변조를 보고하지 않는다.
  이 후보는 "정직한 실수와 대놓고 하는 수정"을 잡는 것이지 공급망
  공격의 해법이 아니다.

---

### C6. `protect_test_fixture_isolation.py` — 훅 테스트 픽스처가 실제 체크아웃 안에 만들어짐

**등급 제안**: MEDIUM

**증거**

`.claude/hooks/CLAUDE.md`의 격리 규칙은 절대적이다 — *"Tier 1: … Never
let a test write to the real `.claude/hooks/.pending_*.json` /
`*_log.jsonl`"*, *"Tier 2: dispatch the subagent into a **separate scratch
git repo** … not a clone of this repo, not this repo's working tree"*.
그런데 로그에는 실제 체크아웃(또는 `$HOME`) 안에 만들어진 훅 테스트
픽스처가 남아 있다 — **6개 이벤트, 5개 고유 경로**:

| 시각 | 훅 | 경로 |
|---|---|---|
| `2026-08-15T06:54:28+00:00` | `protect_destructive` (override됨) | `/home/user/Hncs/.hnc_hook_test_dir` |
| `2026-08-15T06:54:50+00:00` | `protect_test_coverage` | `tools/.hnc_hook_test_new_file.py` |
| `2026-08-16T04:46:03+00:00` | `protect_test_coverage` | `tools/.hnc_hook_live_test2_new_file.py` |
| `2026-08-16T05:00:10+00:00` | `protect_test_coverage` | (동일 경로, 재시도) |
| `2026-08-16T08:57:28+00:00` | `protect_never_touch` (override됨) | `/home/user/Hncs/brands/.hnc_decision_critical_test.py` |
| `2026-08-18T00:16:12+00:00` | `protect_destructive` | `/home/user/hnc_plugin_live_test_dummy` |

```bash
cd /home/user/Hncs/.claude/hooks && python3 - <<'PY'
import json,re
rows=[json.loads(l) for l in open('violations_log.jsonl')]+[json.loads(l) for l in open('override_audit.jsonl')]
pat=re.compile(r"[\w./-]*(?:hnc[\w./-]*test[\w./-]*|test[\w./-]*dummy)[\w./-]*")
seen=set()
for r in rows:
    for m in pat.findall((r.get('target') or '')+' '+r.get('reason','')):
        if m not in seen: seen.add(m); print(r['timestamp'], r.get('hook') or r.get('rule'), m)
PY
```

가장 안 좋은 건 `brands/.hnc_decision_critical_test.py` — **실제
`brands/` 디렉토리 안에** 더미 `apply_*` 파일을 만들고 CRITICAL 가드를
override로 뚫었다(`override_audit.jsonl`에 `"REVERTED-DEMO-8834 승인 -
테스트 더미 apply_*, 곧 revert 예정"`으로 남아 있다). 이건
`.claude/hooks/CLAUDE.md`가 *"Fabricating evidence in the **real** repo …
even temporarily. The isolation rule above exists precisely so this never
has to be weighed against 'but I'll revert it after.'"* 라고 못 박은
바로 그 논리 구조다.

**빈 곳(gap)**

격리 규칙은 산문으로만 존재한다 — 어떤 훅도 "이 쓰기가 훅 테스트
픽스처인가, 그리고 실제 체크아웃 안인가"를 안 본다. 실제로 걸린 건
`protect_test_coverage`(테스트 없는 새 파일)와 `protect_never_touch`
(`brands/*.py`)였고, 둘 다 **다른 이유로** 걸린 것이지 격리 위반으로
걸린 게 아니다. 즉 규칙을 쓴 세션들 자신이 그 규칙을 반복해서 어겼고
(4일에 걸쳐 5개 경로), 시스템은 그걸 격리 위반으로 인지한 적이 없다.

**등급 근거**

MEDIUM — 실제 손상은 작고(더미 파일, 대개 곧 삭제) 복구 가능하지만,
`protect_generated_files.py`/`protect_claim_evidence.py`가 MEDIUM인
이유("실제 결과가 있는 실수라 마찰을 줄 값어치는 있다")와 같은 급이다.
MEDIUM은 지금 plain override가 없고 opus `MEDIUM-APPROVE`만 유효하므로,
"정말 실제 리포 안에 픽스처를 만들어야 한다"는 판단은 상위 에이전트를
한 번 거치게 된다 — 격리 규칙의 성격("애매하면 물어라")과 맞는다.

**불확실성/caveat**

- 탐지 정의가 어렵다: `.hnc_*_test_*` 같은 접두사 규칙은 **작명 관습에
  의존**하므로, 다른 이름을 쓰면 그냥 새어나간다(`protect_reviewer_prejudging.py`의
  고정 문구 블록리스트와 같은 구조적 한계). 이 훅은 "실수로 관습대로
  이름 붙인 픽스처"만 잡는다 — 회피 의도가 있으면 못 잡는다.
- 오탐 위험: `tests/` 아래 정상 픽스처, `datasets/` 아래 샘플 등과
  구분이 필요하다. 스코프를 "리포 루트 + `brands/` + `tools/` 아래의
  dotfile-스타일 임시 픽스처"로 아주 좁게 잡아야 실용적이다.
- 6개 이벤트 전부 훅 개발/테스트 세션에서 나왔다. 일반 작업에서 이
  패턴이 나온다는 증거는 0건 — 즉 이 훅의 수혜자는 미래의 훅 pentest
  세션 자신이다.

---

## 3. 후보로 제안하지 **않는** 것 (같은 데이터에서 나왔지만)

기록해두는 이유: 다음 세션이 같은 로그를 보고 같은 걸 다시 제안하지
않도록.

1. **`protect_agent_model_naming` 반복 발생(3건: `2026-08-14T14:40:10`,
   `2026-08-16T07:36:20`, `2026-08-16T07:40:56`, 전부 `"This dispatch has
   no model field"`)** → 새 훅 불필요. LOW 로그전용은 그 훅 docstring이
   *"deny → ask → deny → here"* 세 번 뒤집힌 끝에 내린 **의도된 결정**이다.
   반복 자체가 설계대로다.
2. **`.last_whole_branch_review_sha` 무보호** → 이미 README 2차 라운드
   finding #8로 문서화된 열린 항목. C3/C4에 흡수해서 다루는 게 맞지
   독립 후보로 새로 "발견"할 것이 아니다.
3. **블록리스트 rephrase 우회(`protect_reviewer_prejudging` /
   `protect_rubber_stamp_approval`)** → 11차 라운드가 Tier 1로 확정한
   기존 한계. 문구를 더 추가하는 건 훅이 아니라 유지보수이고, 두 훅
   docstring이 *"고정 문구 블록리스트라는 구조적 한계"*라고 이미 인정했다.
4. **"사용자가 승인했다"는 검증 불가 주장** (`override_audit.jsonl` 3건:
   `"사용자 요청으로 훅 라이브 검증용 테스트"`, `"author-fix rebase,
   content diff 0, 사용자 승인됨"`, 그리고 그 decision record의
   `"사용자가 force-with-lease 진행을 명시적으로 승인함(AskUserQuestion에서
   …)"`) → **후보로 만들 만큼의 근거가 없다.** 3건 중 확인 가능한 1건은
   실제로 사용자가 승인한 게 맞고(`AskUserQuestion` 언급), 훅은 대화
   맥락을 못 보므로 진위 판정이 원천 불가다(README "알려진 한계"의
   self-servable 항목). 만들 수 있는 건 기껏해야 LOW 로그 태깅
   (`record_approval_claim.py`류)인데, 그건 이미 `override_audit.jsonl`이
   전문(全文)을 남기고 있어서 추가 정보가 0이다. **제안하지 않음.**
5. **`find -delete` / `eval "..."` / heredoc 우회 등 2차 라운드 9개
   결함** → 전부 기존 훅의 정규식 수정 대상이지 새 훅이 아니다. README에
   대응 방향 (1)~(11)로 이미 정리돼 있다.

## 4. 같은 데이터에서 보인 **기존 훅의 결함** (새 훅 아님, 참고용)

- **`bash_override()`의 reason이 문장 경계를 안 끊는다.**
  `2026-08-17T23:29:58+00:00` 항목의 override reason 원문:
  `"스크래치 clone, 원격에 이미 push된 내용으로 로컬 동기화 && find . -type f -not -path './.git/*' | sort"`
  — `# HNCS-OVERRIDE:` 뒤의 텍스트를 줄 끝까지 통째로 reason으로 삼아서,
  뒤따르던 셸 텍스트가 감사 로그의 "사유"에 섞여 들어갔다
  (`override_audit.jsonl`에도 같은 문자열이 그대로 남아 있다).
  부수 효과로 원래 명령의 `&& find …` 부분은 bash 주석에 먹혀 **실행되지
  않았다** — 즉 override 주석 위치에 따라 사용자가 의도한 명령의 일부가
  조용히 사라진다. `_BASH_OVERRIDE_RE`(`_hook_common.py:193`)의 문제.
- **감사 로그의 `target`이 스크립트 전체를 삼킨다.** `2026-08-18T23:36:02`
  /`2026-08-19T07:21:25` 항목의 `target`은 40줄이 넘는 셸 스크립트
  전문이고, 그게 deny 메시지 안에 한 번 더 그대로 인용돼 같은 이벤트에
  두 번 저장된다(`violations_log.jsonl` 44KB 중 상당 부분). 로그 가독성
  /회전 비용 문제이지 보안 문제는 아니다.

## 5. 다음 단계 (제안)

1. 사람이 C1~C6 중 채택할 것을 고른다. C3+C4는 묶는 게 자연스럽고,
   C5는 "훅 개발 자체의 정상 경로"를 같이 정해야 채택 가능하다.
2. 채택된 것만 `superpowers:writing-plans` → Implementer → Reviewer.
   이 문서는 스펙도 플랜도 아니다(루트 `CLAUDE.md`의 Workflow 절).
3. 어느 것을 채택하든 배포 전에 `.claude/hooks/CLAUDE.md`의 2-tier
   테스트 프로토콜(Tier 1 합성 stdin + 대조군 필수)을 통과해야 하고,
   결과는 성공/실패 무관하게 `README.md`의 라운드 구조에 append.
