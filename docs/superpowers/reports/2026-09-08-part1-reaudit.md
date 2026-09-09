# Part 1 반증 재감사 — 2026-09-08

[English](2026-09-08-part1-reaudit.en.md) · [최초 감사](2026-09-08-falsification-audit.md)

감사 기준: develop `b9a14043cf49b9b4f113938027cad582d3844c45`.
판정: Part 1은 불완전했다. 잘못된 기록 증거가 NARE **Supported**, EAGER
**Verified**로 승격될 수 있었다. 아래에서 재현한 경로는 이제 입력을 거절하거나
gate를 실패시킨다. 모든 가능한 잘못된 데이터·조작을 검출한다는 증명은 아니다.

## Part 1 항목별 재검증

| 최초 항목 | 재감사 결과와 수정 |
|---|---|
| F1: registration | 유한한 10,000px 이동도 통과했다. 이동량·해상도 누락 및 숫자/문자열 실패 표기도 허용됐다. 상관·overlap·양축 이동·`long_edge_px`를 요구하고 기존 5% 이동 제한과 명시적 실패를 검사한다. 주입한 NaN/Inf ECC 결과도 renderer 비교문을 통과했으므로 비유한 ECC 결과를 거절한다. |
| F2: 평가 coverage | discovery coverage 차단은 유지됐다. 대신 동일 scene의 manifest 반복 행에 다른 평가 label을 넣을 수 있었다. scene metadata 충돌을 거절하고 대소문자·공백을 정규화하며 unknown placeholder는 gate에서 세지 않는다. null metadata를 문자열 `None`으로 바꾸어 허용하지 않는다. |
| F3: 반복 scene | 중복 metric 거절은 유지됐다. 동일 RAW/JPEG hash를 다른 scene ID로 바꾸면 표본 수를 늘리고 피팅 session을 넘을 수 있었다. 평가·피팅 전 동일 hash의 다른 scene 할당을 거절한다. |
| F4: subgroup 퇴행 | 기존 NaN 및 0→100 차단은 유지됐다. 유한한 1e308→1.7e308도 평균 overflow로 퇴행을 숨겼다. 먼저 나누는 임시 수정은 5e-324→1e-323 underflow 재검증에서 실패했다. subgroup 평균에 `statistics.mean`을 사용하고 빈 subgroup 계약·비유한 threshold를 거절한다. RAW baseline 0은 예외 대신 보류, foundation 파생 개선율의 비유한 값은 거절한다. |
| F5: 피팅 경계 | 완전한 lockbox 입력, 중복 scene, 뒤쪽 RAW/JPEG hash 변경, 잘못된 style 모두 `_load_frame` 호출 전에 실패한다. 이름만 바꾼 파일 재사용은 F3으로 차단된다. 실제 파일 hash 검사 후 synthetic score matrix로 각 held-out session이 선택용 학습에서 제외됨을 확인했다. 피팅 알고리즘 추가 수정은 필요 없었다. |
| F6: 파이프라인 합성 | neutral 40에 in-place Layer A가 40, appearance가 40을 더한다. 실제 JPEG decode와 ΔE00 계산에서 target 120 대비 candidate 오차는 0, B0/B1은 양수이고 순서가 맞으며 neutral 입력도 보존됐다. 합성 수정은 유지됐다. 이 테스트에서는 RAW decode와 registration만 mock한다. |
| F7: 문서 CLI | `--candidate provia` 회귀 테스트가 통과한다. parser/output 테스트의 fitting mock은 실제 RAW 피팅 증거가 아니다. |
| F8: 문서 | 양쪽 tool index 항목이 존재하고 무결성 감사도 통과한다. 재귀 probe에는 영어 filename 짝 누락 **49개**가 남는다. 이전의 전체 문서 완료 주장은 여전히 뒷받침되지 않으며 이번에 번역 완료를 주장하지 않는다. |

## Supported / Verified에 도달한 상호작용

- NARE는 false 의미 문자열 등 truthy 비불리언을 controls·subgroup 승인·provenance로
  받아들였다. 이제 각 gate는 실제 `True`만 허용한다.
- 직접 classifier는 역순/비유한 CI 끝점, 음수 부호검정 p, 무한대 개선율을 받아들였다.
  양끝점·순서·유한성을 검사하고 NARE scene 수는 정수를 요구한다. EAGER의
  replication/validation/lockbox flag도 엄격한 불리언이다.
- 직접 classifier를 고친 뒤에도 **서로 다른 EAGER JSON report 네 경우가 Verified**였다:
  robustness `0`, 음수 neutral candidate 오차, 음수 chromatic candidate 오차,
  tier-E manifest에 tier A 요청. 숫자 robustness를 거절하고 optional 오차를 집계 전
  검사하며 요청 tier가 평가 manifest의 최약 tier보다 강할 수 없게 했다.
  discovery 행은 평가 tier를 결정하지 않는다.
- 직접 paired 집계도 음수 optional 오차를 허용했다. 반복 관측 평균으로 숨기기 전에
  개별 metric 값을 검사한다.

정상 synthetic NARE는 Supported, 필요한 attestation을 모두 제공한 정상 synthetic
EAGER는 Verified로 유지된다. 모든 입력을 실패시키는 방식으로 테스트를 통과하지 않는다.

## 재현 증거

최초 adversarial 모듈 11개 테스트는 production 수정 전에 **실패 subtest 46개와
zero-baseline 오류 1개**를 냈다. 추가 red test에서 EAGER report 승격 네 경우,
비유한 ECC 주입 두 경우, 직접 paired 음수 오차, 평균 계산 문제 두 경우도 재현했다.
겹치는 테스트 사례 수이며 독립 root cause 수가 아니다.

저장소 루트의 Python 3.12 환경에서:

```bash
~/.hncs-hybrid-venv312/bin/python3 -m unittest tests.test_nare_part1_reaudit tests.test_nare_session_holdout tests.test_nare_runner tests.test_nare_registration tests.test_nare tests.test_nare_cli tests.test_eager
~/.hncs-hybrid-venv312/bin/python3 -m unittest discover -s tests
PYTHONPATH=. ~/.hncs-hybrid-venv312/bin/python3 docs/superpowers/reports/2026-09-08-falsification-probes.py
~/.hncs-hybrid-venv312/bin/python3 .claude/skills/run-hncs/driver.py smoke
~/.hncs-hybrid-venv312/bin/python3 -m tools.maintenance.audit_repo_integrity
git diff --check
```

adversarial 모듈은 15개 테스트이고 피팅·합성·ECC 테스트를 추가했다. 기존 probe도
정상 control, 독립 discovery hash, 필수 필드를 갖춘 lockbox fixture를 사용한다.
무관한 필드 누락을 lockbox 방어 성공으로 오해하지 않게 했다.

최종 전체 discovery: **1,424개, 23.041초, OK**. Part 1의 1,404개 대비
20개 테스트를 추가했다. `compileall`, `git diff --check`도 통과했다.

## 기록 데이터와 호환성

- 현재 Fuji 피팅 manifest 37행의 RAW/JPEG frozen hash **74/74**가 일치한다.
  이번 재감사는 RAW corpus를 다시 decode/피팅하지 않았고 피팅 수치를 바꾸지 않았다.
- 기록된 512px/1024px registered metric 모두 gate probe용 bootstrap 100회에서
  **Inconclusive**다. diversity·semantic·control gate가 실패한다. 과거 diagnostic에
  `long_edge_px`가 없어 registration도 실패한다. 원래 artifact는 보존했다.
  실제 평가 해상도로 registration을 재생성해야 하며 통과용 해상도를 임의로 넣으면 안 된다.
- 기록 피팅의 비영(非零) 차이는 여전히 `capture-2025-03-18` 하나에만 있다.
  hash 고유성은 독립 물리 장면을 입증하지 않는다.
- Driver smoke **6 pass / 0 fail**, shipped-look contract probe **168 pass**.
  실행 검증이며 appearance 검증은 아니다. 기존 Hasselblad night의 흰 입력
  divide-by-zero 경고는 계속 표시된다.
- 저장소 무결성은 DCP 13개·ICC 73개 검사를 포함해 통과했다. 문서 짝 검사는
  최상위 16개만 보므로 위의 재귀 누락은 남는다.

## 분류 결과가 여전히 증명하지 못하는 것

JSON API는 사전 계산한 오차·label·hash와 명시적 attestation을 받는다.
controls를 실제 실행했는지, semantic mask가 맞는지, 물리 장면을 정직하게 묶었는지,
JPEG가 SOOC인지, 독립 재현이 실제 있었는지를 인증하지 않는다. 내부적으로 일관된
유한 수치와 실제 `True`를 조작하면 여전히 긍정 분류를 받을 수 있다.
이 신뢰 경계를 닫으려면 실행 결과와 provenance를 결합하는 설계가 필요하며,
이번에 재현한 validator 결함 수정의 범위를 넘는다.

shipped look/profile·기록된 피팅 artifact는 수정하지 않았다.
Supported/Verified는 제공된 증거의 진실성을 전제로 하며, 이번 재감사가
사진 정확도 또는 release 주장을 허가하지 않는다.
