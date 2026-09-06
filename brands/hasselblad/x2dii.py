"""
apply_hncs_x2dii - Experimental. X2D II 100C 전용 `apply_hncs()`
(brands/hasselblad.py) 변형. exposure_gamma 하나만 0.8->0.7로 바꾼다 -
호출부가 카메라 모델을 판별해 X2D II일 때만 이 함수를 쓰는 걸 전제로
한다(이 함수 자체엔 모델 판별 로직 없음, apply_hncs_learned/
apply_hasselblad_day·night와 같은 패턴).

**경위**: docs/measurements.md "exposure_gamma 세대별 직접 맞대결"
절에서, exposure_gamma=0.8(main)과 0.7(candidate, 별도 브랜치였다가
폐기됨)을 X2D II 41장 실사진 포함 dpreview 95쌍에 직접 맞대결시켰더니
CFV/X2D는 0.8이(p<0.001), X2D II는 0.7이(p<0.001) 통계적으로 확실히
이겼다 - 두 값 다 사전에 존재하던 고정 상수라 이 비교엔 표본 부족으로
인한 과적합 위험이 없다.

**의도적으로 안 가져온 것**:
- shoulder_start=0.82/toe_lift=0.02/white_point=0.95(X2D II 41쌍 자체
  그리드서치 결과) - LOO 부호검정 p=0.060, 학습셋을 5-fold로 줄이면
  p=0.349로 유의성 소실(같은 문서 "X2D II 전용 파라미터 LOO/5-fold"
  절). 41쌍·441콤보 그리드라 과적합 위험이 실제로 있다고 판단해 제외
  - shoulder_start/white_point는 main과 동일하게 유지
- 3x3 컬러 매트릭스 단계 - X2D II 41쌍 자체로 새로 피팅해도
  apply_hncs(main) 톤커브 단독보다 유의하게 나쁨(-13.9%, CI가 0
  안 낀 채 음수, `tools/evaluate_x2dii_color_matrix.py`) - 매트릭스
  경로는 시도했으나 기각

즉 이 함수가 담는 건 "여러 독립 신호(8가설 조사, main-vs-candidate,
LOO)가 공통으로 가리키는 방향 중, **표본 크기에 안정적으로 버티는
부분만**"이다 - 41쌍 전용 그리드서치 최적값 전체를 그대로 옮기지
않았다. `apply_hncs()`(main) 자체는 이 실험으로 바뀌지 않는다.

재현: `python3 -m tools.evaluate_exposure_gamma_x2dii` (95쌍, X2D II
세대만 골라 읽으면 이 함수의 exposure_gamma=0.7 쪽 결과).

**갱신(2026-08, 사용자 명시적 지시로 풀그리드 최적값 전체 채택)**:
위에서 통계적 견고함 부족으로 일부러 뺐던
`shoulder_start=0.82/toe_lift=0.02/white_point=0.95`를 이번엔 그대로
반영했다 - 통계가 바뀐 게 아니라(LOO 부호검정 p=0.060, 5-fold에서
p=0.349로 유의성 소실이라는 판정은 그대로 유효, 41쌍 전용 in-sample
최적값에 불과함), 사용자가 그 트레이드오프를 알고도 "필름 커브,
노출 다 따로 X2D II를 위한 모델로"라고 명시적으로 지시해서 반영한
것이다. 재현: `python3 -m tools.evaluate_x2dii_generation_loo`
("전체 41쌍으로 피팅한 in-sample 최적 조합" 줄).

**갱신(2026-08, 표본 41->70쌍으로 확장 후 shoulder_start 정정)**:
사용자가 X2D II raw+jpeg 페어를 두 차례 더 추가해서(같은 dpreview
갤러리의 나머지 분량으로 보임, 전부 Software=펌웨어 버전 문자열만
있고 Adobe 서명 없음 - 편집 오염 없음 확인) 41->63->70쌍으로 커졌다.
재검증 결과 **`shoulder_start=0.82`는 41쌍짜리 작은 표본의
아티팩트였다** - 표본이 늘어날수록 다른 4세대와 같은 `0.5`로
수렴했다:

| n | LOO 부호검정 p | 5-fold 부호검정 p | 지배적 shoulder_start |
|---|---|---|---|
| 41 | 0.060 | 0.349(유의성 소실) | 0.82 (39/41) |
| 63 | 0.011 | 0.005 | 0.5 (61/63) |
| 70 | 0.003 | 0.003(LOO와 완전 동일) | **0.5 (70/70, 만장일치)** |

70쌍에서는 LOO와 5-fold 결과가 소수점까지 완전히 일치하고(개선폭
44.1%, CI [+31.9%,+53.6%]), drop-one도 42.3~45.7%로 안정적 - 위
"통계적 견고함 부족" 문제 자체가 해소됐다. `exposure_gamma=0.3`/
`toe_lift=0.02`/`white_point=0.95`는 그대로, **`shoulder_start`만
0.82->0.5로 정정**한다. 재현: `python3 -m
tools.evaluate_x2dii_generation_loo`(70쌍 기준 매니페스트로 재실행).

**재정정(2026-08, exposure_gamma=0.3 기각 - percentile RMSE와 ΔE00이
정반대로 나옴, Sony a7V와 같은 패턴)**: 위 모든 검증은 b2/w995
percentile RMSE를 목적함수로 삼은 그리드서치였다 - `apply_hncs()`
(main) 대 `apply_hncs_x2dii()`를 실제 ΔE00으로 직접 맞대결시킨 적은
없었다. `tools/evaluate_full_pixel_de00_confirm.py`(3000px, 다운샘플
최소화)로 처음 직접 비교해보니 **-5.13%로 오히려 main이 근소 우세,
CI가 0을 포함해 판정 보류**(승/패 34/36) - 이전까지의 모든 "44.1%
개선" 등은 percentile RMSE 목적함수 자체의 결함이었다. 사용자가 눈으로
직접 확인한 시각적 문제(exposure_gamma=0.3 렌더가 "너무 밝고 노이즈
있고 뿌옇다")와도 일치하는 결과 - 그리드서치가 실제 지각 품질과 무관한
좁은 지표만 맞추고 있었다는 뜻.

**ΔE00을 직접 목적함수로 441콤보 그리드서치 재실행**
(`tools/evaluate_x2dii_de00_grid.py`, 신규 - 저해상도(200px)로 폴드별
콤보 선택, 3000px로 최종 LOO 평가) - `apply_hncs()`(main) 대비
**개선폭 +12.99%, 61승9패, 부호검정 p<0.0001, 부트스트랩 95% CI
[+1.421, +2.065]**(0 미포함, 이번엔 진짜 유의미) - 최적 조합
**`exposure_gamma=0.6, toe_lift=0.02, shoulder_start=0.58,
white_point=0.95`**(58/70 폴드 지배, 나머지는 shoulder_start만
0.5/0.66로 인접). exposure_gamma가 0.3에서 0.6으로 훨씬 덜 극단적으로
바뀐 게 시각적 피드백과 정확히 들어맞는다 - **최종 채택값을 이걸로
갱신**. 재현: `python3 -m tools.evaluate_x2dii_de00_grid`.
"""
from core.engine import make_hasselblad_body_look


apply_hncs_x2dii = make_hasselblad_body_look(
    toe_lift=0.02, shoulder_start=0.58, white_point=0.95, clahe_clip=1.25, exposure_gamma=0.6)
