# HNCS 전체 반증 감사 — 2026-09-08

[English](2026-09-08-falsification-audit.en.md)

대상: develop 43c5ee8d4acdd1883a64356063dc93b557884b47. 로컬 Python 3.12 venv.
판정: 렌더러의 기본 실행은 확인됐지만 NARE Supported/ship 판정을 배포 근거로 신뢰할 수 없다.
이 감사는 구현을 수정하지 않고 재현 반례와 주장 한계를 기록한다.

## 확인한 기반

- 전체 unittest: 1396개, 23.259초, OK.
- driver smoke: 6 pass / 0 fail.
- 56개 shipped photo look × 검정/흰색/난수 32×32 uint8: 168건 출력 형태·dtype·유한성 통과.
- 검정/흰색 같은 극단 입력의 성공이 photographic accuracy를 뜻하지 않는다. Hasselblad night의 흰색 입력에는 divide-by-zero 경고가 있으나 최종 출력은 유효했다.
- GFX100RF registered manifest의 37 RAW + 37 JPEG: SHA-256 74/74 일치, 누락 0.
- compileall 및 git diff --check 통과.
- audit_repo_integrity: exit 1, 도구의 한/영 구조 문서 미등재 2건. DCP 13 + ICC 73 구조 검사는 통과.
- optional darktable-cli, population downloaded_samples, 옛 raw_calib_cache_fuji는 없다.

## 재현된 결함

### F1 — P1: 실패한 registration이 Supported로 승격됨

hybrid_engine/evaluation/nare.py:66–68은 correlation/overlap 키 존재만 확인한다.
실제 값 -1/0을 입력해도 registration_passed=True이며 다른 조건을 충족하면
ship_gate_passed=True, classification=Supported다. 실패 이유·이동량도 평가하지 않는다.
RAW runner의 정상 경로에는 threshold 검사가 있지만 recorded-metrics 평가/CLI 경로는 이를 우회한다.
조치: 유한성, 범위, 사전 고정 threshold, 이동량, 명시적 실패 상태를 report 생성 시 재검증.

### F2 — P1: discovery의 coverage로 평가 다양성 gate를 통과함

nare.py:48,81은 전체 manifest의 summary를 사용한다. evaluation은 daylight/landscape
한 종류뿐이어도 discovery에 다른 두 라벨을 추가하면 3 lighting/3 scene coverage가
통과하고 Supported가 된다. train에 있는 조건이 test에서 검증된 것으로 보고된다.
조치: 평가에 실제 기여한 scene만으로 coverage와 picture style을 산출.

### F3 — P1: 중복 scene metric이 평균되지 않고 마지막 행으로 덮어써짐

nare.py:52의 dict 변환은 같은 scene_id의 반복 측정을 조용히 버린다.
12개 scene의 candidate error=5인 입력에 scene 0의 error=100 반복 행을 붙이면
mean_candidate=12.916666666666666, 그 행을 앞에 두면 5.0이다.
동일한 측정 집합의 순서가 결론을 바꾼다. EAGER에 있는 scene aggregation도 호출 전에
행을 잃어버리므로 구제하지 못한다. subgroup 쪽은 원래 행을 전부 세어 global과 가중치가 다르다.
조치: image ID와 scene ID를 구분해 scene별 집계하거나 중복을 명시적으로 거부.

### F4 — P1: semantic catastrophic gate가 0→100 및 NaN을 통과시킴

nare.py:111–126은 수치의 유한성/음수 검증이 없고 baseline=0이면 개선율을 0으로 지정한다.
모든 semantic group의 ΔE00이 0→100이어도 passed=True다. candidate NaN도 통과한다.
조치: finite/nonnegative 검증, zero baseline 악화의 명시적 실패 규칙, 고정 허용치 필요.

### F5 — P1: 피팅 입력에 lockbox·중복 scene·hash 검증이 없음

tools/fuji/fit_nare_provia_session_holdout.py:27–59는 manifest 전체를 바로 읽고 session만 나눈다.
로드와 점수 계산을 mock한 제어흐름 반례에서 같은 scene_id를 세 session에 넣고
전부 split=lockbox로 지정해도 3 scenes/3 sessions 결과를 반환하며 각 fold에 2개가 train으로 들어간다.
이 반례는 RAW 재현이 아니라 split/중복 방어 부재를 검증한다. 코드상 frozen hash도 검사하지 않는다.
현재 실제 37행은 evaluation이며 hash는 이번 감사에서 일치했으므로,
이번 데이터가 변조됐거나 실제 lockbox가 소비됐다는 주장은 하지 않는다.
조치: fitting 허용 split, scene/session 일관성, 파일 hash, Picture Style을 decode 전 검증하고
별도 최종 lockbox를 보존.

### F6 — P2: Layer A + appearance를 실행하지 않음

hybrid_engine/evaluation/nare_runner.py:85–86은 foundation(neutral)과 candidate(neutral)을
각각 호출한다. 비identity foundation을 넘겨도 candidate에는 foundation 출력이 전달되지 않는다.
따라서 별도 계약 없이 결과를 Layer A 대 Layer A+appearance의 기여도 분해로 읽으면 틀린다.
현재 identity B1 측정은 이 문제로 수치가 바뀌지 않는다.
조치: candidate가 전체 pipeline인지 appearance-only인지 API에 명시하고 실제 합성 경로를 검증.

### F7 — P2: 직전 한국어 재현 명령이 실행 불가

hybrid_engine/EVALUATION.md:5050의 --candidate provia는 fit CLI에 없다.
실행 시 argparse exit 2: unrecognized arguments: --candidate provia.
영문 report의 명령은 이 옵션이 없어 같은 결함이 없다.
조치: 한국어 명령을 실제 --help와 대조하고 문서 CLI를 smoke 검사.

### F8 — P2: 문서 전부 완료라는 이전 응답은 근거 부족

직전 커밋의 tools/fuji/fit_nare_provia_session_holdout.py가 양쪽 project_structure에 없어
integrity audit가 2건 실패했다. docs 재귀 검사에서 .en.md 파일명 짝이 없는 문서가 49개,
새 영문 fit report에는 대응하는 한국어 파일이 없다.
이는 파일명 규칙의 누락 수이며 49개 모두 한국어 본문이라는 뜻은 아니다.
기존 integrity 도구는 docs 최상위 16개만 검사하므로 nested superpowers 누락을 놓친다.
조치: 언어/짝 목록을 재귀적으로 감사하고 본문 언어도 확인해 범위를 확정.

## 현재 과학적 주장의 경계

- 37 pair의 unique RAW hash는 37개이나 이것만으로 독립 physical scene 37개가 증명되지는 않는다.
  manifest는 gfx100rf-000 등의 순번 scene ID와 capture-date session을 쓰며 조명은 daylight,
  scene_type은 natural_scene 하나다. 실제 scene grouping과 strata annotation을 별도 검증해야 한다.
- 직전 fit의 11개 held-out session 중 10개는 현행 파라미터와 완전히 동일하다.
  차이가 발생한 17개 frame은 전부 capture-2025-03-18 한 session이다.
  7승/10패와 scene-bootstrap CI를 여러 session에서 반복 확인한 개선 증거로 읽으면 안 된다.
  현재 음성/보류 결론은 유지된다. session 의존성, CV train overlap을 고려한 불확실성 평가는 추가로 필요하다.
- NARE runner는 mean ΔE00만 생성하며 semantic mask, spatial rendering, 다중 scale 결과 결합은
  자동 생성/강제하지 않는다. Boolean controls/provenance는 독립적인 증거 확인을 대신하지 않는다.
- population-fit 브랜드의 JPEG 분포는 장면·촬영자·노출과 제조사 렌더링을 분리하지 못한다.
  이 한계는 core/engine.py와 brands/README.md에 이미 적혀 있다. 코드 실행 성공은 이를 해소하지 않는다.
- Hasselblad shipped docstring은 과거 13쌍 중 9쌍 편집 오염과 후속 65쌍 재피팅을 모두 기록한다.
  따라서 '오염 때문에 현재 계수가 전부 무효'라고 단정하지 않는다. 이번 감사는 65쌍 전체 RAW
  재렌더나 독립 scene 재분류를 수행하지 않았고, 새 NARE 증거로 전체 Hasselblad를 인증하지도 않는다.
- LUT의 CLAHE 비재현성과 inverse의 local contrast 복원 불가는 이미 명시된 제한이다.
  Adobe 앱 실제 profile import, GUI 상호작용 전체, 비디오 장시간, Linux CI 재실행,
  모든 body/profile의 색도 정확성은 이번 검증 범위 밖이다. 프로필 구조 통과와 색 정확도는 별개다.

## 재현

저장소 root에서 실행:

~~~bash
PYTHONPATH=. ~/.hncs-hybrid-venv312/bin/python3 docs/superpowers/reports/2026-09-08-falsification-probes.py
~/.hncs-hybrid-venv312/bin/python3 -m unittest discover -s tests
~/.hncs-hybrid-venv312/bin/python3 .claude/skills/run-hncs/driver.py smoke
~/.hncs-hybrid-venv312/bin/python3 -m tools.maintenance.audit_repo_integrity
~~~

반례 스크립트는 synthetic/mock 반례, 168개 renderer 계약 검사, 기존 fit artifact의
nonzero session 목록, 문서 파일명 짝 검사를 수행한다. 반례가 잡힌다고 예외로 종료하지 않고
관측 결과를 JSON으로 출력한다. 실제 RAW 피팅을 다시 수행하지 않는다.

권고 순서: F1–F5의 잘못된 합격/누수 방어 → 기록된 artifact 재판정 → F6 pipeline 계약 →
문서 재현/짝 보완 → 독립 scene/lighting/semantic/spatial 증거 추가. 현재 감사에 따라
shipped look을 임의로 변경하거나 새로운 정확도 향상을 주장하지 않는다.

> **정정(2026-09-08, F1–F7 수정 완료)**: 위 반례를 회귀 테스트로 고정하고 NARE
> evaluator의 registration 범위·유한성 검사, evaluation-only coverage, 중복 scene 거부,
> semantic zero-baseline/NaN 방어, foundation→candidate 합성, session-holdout의
> evaluation split·SHA-256·Provia 검사를 추가했다. 한국어 fit 명령의 `--candidate provia`
> 옵션도 CLI에 반영했다. 기존 37-scene fit artifact를 새 입력 검증 경로로 재실행했고
> JSON이 byte-identical하며 개선폭 **-0.06342050230067402%**, CI
> **[-0.02051282700178119, +0.00462789732822533]**, 승/패 **7/10**,
> p **0.629058837890625**가 유지됐다. 이 정정은 기존 감사 결과를 지우지 않고 수정 후
> 상태를 함께 기록한다.
