# CLAUDE.md

이 리포에서 작업할 때 지켜야 하는 규칙. Claude Code가 세션 시작 시
자동으로 읽는다.

> 이 파일은 한국어 단일 파일이다 - 아래 "문서 규칙"의 이중언어 병행
> 규칙은 `README.md`/`README.ko.md`와 `docs/*.md`에만 적용되고, 이
> 파일은 `CLAUDE.md`라는 고정 파일명을 도구가 읽어가는 구조라 짝
> 파일(`CLAUDE.ko.md` 등)을 만들지 않는다.

## 프로젝트 한 줄 요약

카메라/디지털백 제조사의 공식 샘플 이미지를 실측해서 브랜드별 색과학을
코드로 근사하는 프로젝트(12개 브랜드). Hasselblad HNCS가 원점이고,
`brands/*.py`의 `apply_*` 함수들이 배포 결과물이다.

---

## 1. 절대 건드리지 않는 것

**연구/실험 작업은 배포 아티팩트를 절대 수정하지 않는다.** 실험은
새 파일에서 하고, 배포물은 별도의 명시적 결정으로만 바꾼다.

- `brands/hasselblad.py`의 `apply_hncs()` - **어떤 실험도 이 함수를
  수정하지 않는다.** 실험이 이겼다고 나와도 자동 반영 금지, 별도 논의.
- `hybrid_engine/assets/profiles/hasselblad.json`, `*.dcp` -
  캘리브레이션 아티팩트. 연구 스크립트가 절대 안 건드린다.
- `brands/*.py`의 기존 `apply_*` 프리셋 함수들 - 새 함수 추가는
  OK(순수 추가), 기존 함수 수정은 별도 결정.
- 기존 연구 모듈의 함수를 "개선"하지 않는다 - 예: `hncs_structural.py`의
  하드클러스터 함수들은 블렌딩 실험이 추가돼도 그대로 남긴다(향후
  비교 기준선으로 계속 쓰인다).

작업 전에 `git diff`로 위 파일들이 안 바뀌었는지 확인하고, 최종 리뷰
때도 blob hash로 재확인한다.

## 2. 통계 규칙 (이 프로젝트에서 가장 비싸게 배운 것)

**평균 차이 하나로 승패를 선언하지 않는다.** 이 세션에서만 "결정적
승리"로 보였던 결과가 3번 뒤집혔다(노이즈, 스레딩 논디터미니즘,
환경변수 누수로 인한 렌더 손상).

새 비교 실험을 만들 때 `summarize()`에 반드시 포함:

- 대응표본 t-검정
- 부호검정(`math.comb` 기반 정확 이항, scipy 의존 없음)
- 부트스트랩 95% 신뢰구간(기본 20000회, 시드 고정)
- drop-one 민감도(한 쌍 빼면 부호가 뒤집히는지)

**95% CI가 0을 포함하면 "판정 보류"로 보고한다.** 평균이 몇 % 좋아
보여도 마찬가지. 기존 구현을 그대로 복사해 쓰면 된다:
`tools/evaluate_hncs_structural.py`, `tools/evaluate_darktable_vs_rawpy.py`,
`tools/evaluate_chromatic_aberration.py`, `tools/evaluate_hncs_blend.py`.

**무신호(null) 결과가 나오면 포지티브 컨트롤을 반드시 확인한다.**
"파라미터가 조용히 안 먹혀서" 나온 무신호인지, "먹히는데 도움이 안
돼서" 나온 무신호인지 구분해야 한다. 실제로 이 프로젝트에서 두 번
후자로 착각할 뻔했다(X-Trans 데모자이크 경로 붕괴, darktable OMP
스레드 누수).

## 3. 결과 기록 규칙

- 모든 실험 결과는 **이기든 지든 애매하든** `hybrid_engine/EVALUATION.md`에
  기록한다. 실패/무신호 기록이 이 프로젝트의 핵심 자산이다.
- 페어별 원자료 표를 같이 실어서, 스크립트를 재실행하지 않고도 문서의
  통계 수치를 검증할 수 있게 한다. 그 표를 그대로 하드코딩해서
  `summarize()`가 재현하는지 확인하는 회귀 테스트도 같이 만든다
  (`TestSummarizeRecordedRun` 패턴).
- 나중에 전제나 결과가 틀린 것으로 밝혀지면 **조용히 고쳐쓰지 않고**
  해당 위치에 날짜 붙은 정정 블록쿼트를 단다:
  `> **정정(YYYY-MM-DD, 재검증 경위)**: ...` 원문은 역사 기록으로 남긴다.
- 수치는 실행 로그에서 그대로 옮긴다. 손으로 반올림하거나 추정하지
  않는다.

## 4. 문서 규칙

- **이중언어 병행 필수**: `README.md`(영문) ↔ `README.ko.md`(국문),
  `docs/*.md`(국문) ↔ `docs/*.en.md`(영문). 한쪽만 고치면 안 된다.
- `docs/project_structure.md`/`.en.md`는 `brands/`/`core/`/`datasets/`/
  `tools/`/`models/`의 **파일별 전수 인덱스**다. 새 파일 추가하면 여기도
  갱신. (`hybrid_engine/` 내부는 관례상 범위 밖)
- 문서 내 상대 링크는 파일 위치 기준으로 검증한다 -
  `hybrid_engine/EVALUATION.md`에서 스펙을 링크하면
  `../docs/superpowers/specs/...`가 맞다.

## 5. git / 커밋 규칙

**커밋할 때마다 authorship을 고쳐야 한다.** 안 하면 GitHub에서
Unverified로 뜨고 stop hook이 잡는다. 서브에이전트가 커밋한 뒤에도
컨트롤러가 이걸 처리한다:

```bash
git config user.email noreply@anthropic.com && git config user.name Claude
git rebase --exec "git commit --amend --no-edit --reset-author" origin/<branch>
for i in 1 2 3 4; do git push -u origin <branch> && break; sleep $((2**i)); done
```

- 푸시는 항상 `git push -u origin <branch>`, 네트워크 실패 시에만
  지수 백오프로 최대 4회 재시도.
- 푸시가 거부되면(다른 세션이 같은 브랜치에 푸시) 강제 푸시하지 말고
  `git fetch` 후 `git rebase origin/<branch>`로 그 위에 얹는다.
- 커밋 메시지에 모델 식별자(claude-opus-5 등)를 넣지 않는다.

## 6. 개발 워크플로우 (superpowers)

새 기능/실험은 이 순서를 탄다. 사용자가 "ㄱ"/"ㄱㄱ"로 각 게이트를
승인한다.

1. `superpowers:brainstorming` - 질문 하나씩, 접근법 2-3개 제시 후
   설계 승인
2. 스펙을 `docs/superpowers/specs/YYYY-MM-DD-<주제>-design.md`에 작성,
   커밋
3. `superpowers:writing-plans` - 계획을
   `docs/superpowers/plans/YYYY-MM-DD-<기능>.md`에 작성, 커밋
4. `superpowers:subagent-driven-development` - 태스크당 구현 서브에이전트
   1개 + 리뷰어 1개, 마지막에 전체 브랜치 리뷰(가장 강한 모델로)
5. 진행 상황은 `.superpowers/sdd/progress.md` 원장에 기록(컨텍스트가
   날아가도 여기서 복구). **원장에 complete로 적힌 태스크는 절대
   재실행하지 않는다.**

최종 전체 리뷰는 생략하지 않는다 - 이 프로젝트에서 치명적 버그를 세 번
잡아냈다(DCP transpose, OMP 누수, 데모자이크 경로 붕괴).

## 7. 연구 스크립트 관례 (`tools/evaluate_*.py`)

- **독립 실행 스크립트로 유지한다.** 다른 `evaluate_*.py`에서 import
  하지 말고 필요한 로더/헬퍼는 복사한다(실험 간 결합 방지).
- 데이터 로드 패턴은 기존 스크립트에서 복사:
  `datasets/hasselblad/hasselblad_raw_jpeg_pairs.csv` + `raw_calib_cache/`,
  파일명 규칙은 `{jpeg_basename}.{raw_ext}` / `{jpeg_basename}.target.jpg`.
- **디코드 직후 축소한다** - `_resize_max_dim(img, DOWNSAMPLE_MAX_DIM)`.
  100MP 핫셀블라드 float64를 그대로 들면 OOM으로 죽는다(실제로 죽었다).
  전역 통계 기반 ΔE는 축소로 왜곡되지 않는다.
- ΔE는 항상 `hybrid_engine.utils.evaluate.mean_delta_e`(CIEDE2000).
- 서브프로세스를 쓸 때는 `env=`를 명시적으로 구성한다 - 부모의
  `OMP_NUM_THREADS`가 새어 들어가서 렌더의 75%가 검게 나온 적 있다.
  그리고 exit code만 믿지 말고 출력 자체의 타당성을 검사한다.

## 8. 오래 걸리는 실행

RAW 디코드가 걸리는 실험은 몇 시간까지 갈 수 있다(실측: 색수차 실험
~2시간).

- 동기 실행으로 붙잡고 있지 말고 `nohup ... > /tmp/<이름>.log 2>&1 &`로
  띄운다.
- `Monitor` 도구로 로그를 감시한다. 필터는 진행 신호 **와 실패 신호를
  전부** 잡게 만든다(`ΔE=|판정:|Traceback|Error|Killed|OOM`) - 성공
  신호만 보면 크래시가 침묵과 구별되지 않는다.
- 턴이 끝날 것 같으면 결과를 **지어내지 말고** 로그 경로와 함께
  "진행 중"으로 보고한다. 컨트롤러가 이어받는다.

## 9. 테스트

```bash
python3 -m unittest discover -s tests
```

커밋 전에 전체 스위트를 돌리고 전부 통과하는지 확인한다. 실제 RAW
캐시에 의존하는 코드는 커밋되는 자동 테스트를 만들지 않는다(CI에
데이터가 없다) - 순수 함수/파싱 로직만 단위 테스트하고, 실측은 수동
실행 + 보고서에 결과 기록.

## 10. 데이터

- 커밋되는 것: manifest CSV, 시그니처 JSON, 분석 결과 문서
- 커밋 안 되는 것(`.gitignore`): `raw_calib_cache*/`,
  `downloaded_samples*/`, `datasets/hasselblad/contributed/*/raw|jpeg/`,
  `*_stats_result.csv`, `eval_reports/`
- 즉 **다른 세션이 만든 manifest가 있어도 이 컨테이너에 실제 이미지가
  없을 수 있다.** 실험 전에 파일 존재를 확인한다.

---

## 자주 쓰는 명령어

### `/goal <조건>`

세션 종료 게이트를 건다. 조건이 충족될 때까지 세션이 끝나지 않는다.

- **"하겠다"는 충족이 아니다.** "이제 찾아보겠다"고 말하고 끝내면 hook이
  0/N으로 되돌린다. 실제로 찾아서 **완료**해야 한다.
- 개수가 명시되면(예: "5개 이상") 그 개수만큼 **구체적이고 검증된**
  작업을 끝내고, 각각 뭘 했는지 결과와 함께 보고한다.
- "할 일 없으면 찾아서"류는 이 순서로 뒤진다: 진행 중인 PR(리뷰 코멘트,
  CI 실패) → 대화에서 하다 만 것 → TODO/FIXME → 문서와 코드의 불일치
  (stale 카운트, 빠진 인덱스 행, 깨진 링크) → 배포물 무결성 검증.
- 새 프로젝트를 발명하지는 않는다. 이미 시작된 것을 끝내는 쪽이다.

### `/loop [간격] [프롬프트]`

주기 실행. 간격 없이 부르면 스스로 페이싱한다.

- **하네스가 추적하는 작업을 폴링하지 않는다.** 백그라운드 태스크는
  끝나면 알림이 오므로 짧은 간격으로 깨우는 건 낭비다. 대신 긴
  폴백(1200초 이상)만 건다.
- 이벤트를 기다리는 거라면 `Monitor`를 걸고, `/loop`은 그게 실패했을
  때를 위한 보조 신호로만 쓴다.
- 외부 상태(CI, 배포)를 폴링할 때만 그 상태의 실제 변화 주기에 맞춰
  간격을 정한다(8분짜리 CI면 480초 한 번이지 60초 여덟 번이 아니다).
- 조용하면 한 줄로 보고하고 끝낸다. "확인했고 할 게 없다"를 세 번
  반복하면 스코프를 줄이거나 루프를 멈춘다.
- 되돌릴 수 있는 것(로컬 편집, 테스트 실행)은 판단해서 진행하고,
  되돌리기 어려운 것(푸시, 삭제, 외부 전송)은 확인을 기다린다.

### `/compact`

컨텍스트가 길어지면 사용자가 직접 부른다. 요약 후에는 **원장
(`.superpowers/sdd/progress.md`)과 `git log`를 자기 기억보다 신뢰**한다.
