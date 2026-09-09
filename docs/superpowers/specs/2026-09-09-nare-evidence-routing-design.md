# NARE 보정안: 데이터 유형별 측정과 주장

[English](2026-09-09-nare-evidence-routing-design.en.md)

상태: 검토용 방법론 설계. 아래 계약은 아직 validator에 구현되지 않았다.
기존 [NARE](2026-09-08-nare-natural-scene-protocol.md)의 appearance 기준을 유지하며,
불완전한 로컬 데이터를 측정할 수 있는 범위와 승격할 수 없는 범위를 명시한다.

## 선택

NARE 기준 완화, 완전한 새 방법론, NARE 유지 및 보조 평가 분리 중 세 번째를 선택한다.
기준 완화는 누락된 target을 증거로 바꾸고, 전면 교체는 기존 회귀 검증을 중복한다.
12개 브랜드를 모두 조사하는 것과 12개 브랜드 모두에서 appearance 오차를 측정하는
것은 별개의 완료 조건이다. 결측 target의 ΔE00는 0이 아니라 null이다.

## 측정 경로

| 경로 | 입력 | 허용되는 결과 | NARE appearance 등급 |
|---|---|---|---|
| NARE | 같은 capture의 RAW와 확인된 SOOC JPEG, 확인된 style | 고정 candidate의 target 재현 오차 | 기존 gate 및 receipt 요건 충족 시에만 승격 |
| Preview comparison | RAW와 그 RAW에서 추출한 내장 preview | 해당 preview에 대한 재현 오차 | Exploratory 상한, SOOC 대체 금지 |
| Colorimetric | chart RAW와 유효한 chart reference/ROI | chart 색도학 오차 | 별도 colorimetric claim, NARE 승격 금지 |
| Diagnostic | target provenance/style가 불명확한 pair 또는 단독 이미지 | pair 오차의 기술통계 또는 실행 성공/실패 | Exploratory 상한; target 없으면 ΔE00 없음 |

RAW 내 preview가 실제 존재하고 추출·색공간·해상도를 검증한 경우에만 preview 경로를
사용한다. 추출 불가, 저해상도, 색공간 불명은 제외 사유로 기록한다. RAW decoder로
새 JPEG를 만든 뒤 독립적인 제조사 target이라고 부를 수 없다. 경로 간 평균은 합치지 않는다.

## Identity와 provenance

- 파일 탐색은 선언한 로컬 roots 전체에서 수행하고 접근 실패도 기록한다. 한 repo의
  `datasets/` 검사만으로 컴퓨터 전체에 파일이 없다고 결론 내리지 않는다.
- SHA-256은 동일 바이트 중복을 찾는 수단이다. 다른 encoding/crop의 같은 사진은
  별도 중복 후보 검사와 검토가 필요하다. 경로·파일명 변경은 새 capture를 만들지 않는다.
- capture_id는 검증된 pair identity, scene_id는 검토된 실제 장면 그룹이다. 순번은
  record_id로만 사용한다. EXIF 시각/모델/ISO 일치는 pairing 후보 근거이며 SOOC 인증이 아니다.
- scene/session/contributor/lighting/style는 근거와 상태를 함께 기록한다. 추론 값은
  verified로 표시하지 않는다. `LOCAL_SOOC`, 폴더명, `natural_scene` 같은 대체값을
  실제 style, 촬영 session, 검토된 taxonomy로 취급하지 않는다.
- target_kind, 원본 hash, preview 추출 명령/버전, decoder 버전/옵션, 색공간 처리,
  candidate 함수/commit/config, split, 모든 산출물 hash를 보존한다. receipt는 입력과
  실행의 연결을 인증하며 피사체의 진실성이나 scene 독립성을 인증하지 않는다.

## 비교와 측정

실행 전에 `(brand, body/model, target_kind, style, candidate, scale)` 평가 셀과
제외 규칙을 고정한다. candidate는 명시적인 registry에서 선택하며 style 불일치 시
NARE 비교를 중단한다. body 전용 look과 brand 기본 look은 별도 candidate다.

B0는 고정 RAW decoder, B1은 독립적인 colorimetric foundation이 있을 때만 별도
단계, C는 실제 appearance transform이다. identity 후보는 baseline 실행 점검이다.
B1이 identity이면 B0와 동일하다고 기록하며 sensor correction 기여를 주장하지 않는다.
fit과 evaluation은 scene/session 분리 후 수행하며 평가 데이터를 보고 임계값을 바꾸지 않는다.

색공간/ICC/전달함수/백색점 처리 계약을 고정한 뒤 registration, overlap 및 exclusion
mask를 계산한다. B0/B1/C에 같은 geometry와 mask를 쓴다. candidate 점수를 높이기
위한 재정렬이나 유리한 pixel 선택을 금지한다. clipping, shadow, highlight의 분모와
제외 수를 기록한다. 등록 실패를 null 및 failure로 보존하고 색 오차에 섞지 않는다.

512px는 실행 탐색 scale이다. 성능 결론은 사전 지정한 두 scale 이상에서 평가하며
1024px/2048px도 native 해상도를 뜻하지 않는다. 공통 유효 capture 집합의 scale 비교와
각 scale의 전체 통과 집합을 함께 보고해 선택 효과를 드러낸다.

## 통계 및 주장

scene 그룹 검토 전에는 n_captures와 capture별 mean/median/p90만 기술한다.
독립 scene 수, bootstrap CI, sign-test 유의성, generalization을 주장하지 않는다.
등록 성공 사진 수를 독립 scene 수로 바꾸지 않는다.

그룹 검토 후 image 값을 scene 안에서 평균하고 scene에 동일 가중치를 준다.
scene별 B0-C paired 차이로 20,000회 bootstrap(seed=0), exact sign test 및
drop-one sensitivity를 계산한다. session 의존성이 있으면 session cluster 분석도
보고하며 scene-only CI를 충분한 근거로 취급하지 않는다. 여러 candidate를 선택하는
실험은 holdout과 다중 비교 정책을 사전 지정한다.

서로 다른 장면을 촬영한 브랜드 간 원시 ΔE00 순위는 브랜드 품질 순위가 아니다.
브랜드별 paired 개선량과 관측 coverage를 보고하고, 직접 cross-camera 비교는
Protocol 2R의 같은 물리 장면 조건에서 수행한다.

NARE의 기존 최소 scene 수, 개선율, CI/sign test, subgroup, coverage, control,
provenance gate를 낮추지 않는다. Supported는 재현 가능한 전체 hash chain과 실제
evaluator 실행을 요구한다. Verified는 별도 trusted runner 서명과 replay를 추가로
요구하며, 해당 경로가 구현되지 않았으면 Verified는 발급하지 않는다.

## Accounting과 재현

단계별 분모를 분리한다: 발견 파일 → capture 후보 → pairing/provenance 적격 →
decode 성공 → registration 성공 → 평가 적격 → 검토된 scene 그룹.
한 단계에서 capture는 통과 또는 하나의 primary failure로 분류하고 부가 원인은
별도 배열에 둔다. 파일 수, pair 수, scene 수를 서로 더하지 않는다.

run bundle은 입력 inventory, pair/scene manifest, per-capture/per-scene metrics,
failure records, 설정/환경, 실행 가능한 명령과 코드, receipt 및 요약을 포함한다.
`/tmp`의 결과에만 의존하는 요약은 durable evidence가 아니다. 모든 12개 브랜드에
결과 또는 정확한 미측정 이유를 출력하되 missing을 pass로 세지 않는다.

## 이전 실행 정정 및 구현 수락 조건

2026-09-09 로컬 audit의 Fuji 207, Hasselblad 17, Leica 15 통과는 **capture record 수**다.
독립 scene 수는 미확인이다. identity candidate 평균은 RAW decoder와 선택된 JPEG의
기술적 차이이며 HNCS appearance 성능이 아니다. `LOCAL_SOOC`와 임의 metadata를
넣은 manifest는 NARE 적격 증거가 아니다. Sony decode/geometry failure는 이 실행
환경과 입력에서 관찰된 결과이며 다른 decoder에서도 불가능하다는 뜻이 아니다.

후속 구현은 최소 다음을 회귀 검증한다: (1) unknown style 승격 거부,
(2) preview의 SOOC 승격 거부, (3) 파일명 변경 중복 제거,
(4) 미검토 scene의 추론통계 거부, (5) identity 후보의 appearance 개선 주장 거부,
(6) target 없는 ΔE00 null, (7) failure accounting 보존,
(8) candidate/style 불일치 거부, (9) receipt artifact 변조 거부,
(10) 같은 geometry/mask로 baseline과 candidate 비교.
