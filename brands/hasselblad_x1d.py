"""
apply_hncs_x1d - Experimental. X1D 전용 `apply_hncs()`(brands/hasselblad.py)
변형. `hasselblad_x2dii.py`/`hasselblad_x1d50c.py`와 같은 패턴 - 호출부가
카메라 모델을 판별해 X1D일 때만 이 함수를 쓰는 걸 전제로 한다(이 함수
자체엔 모델 판별 로직 없음).

**경위(2026-09, 사용자 지시 "애초에 그러면 X1D만 사용하는 필터 하나
더 만들어")**: `tools/breakdown_hasselblad_by_exposure_iso_portrait.py`가
Hasselblad 세대별 실측(368쌍)에서 **X1D가 세대 중 최악**(평균 ΔE00
13.410, 표준편차도 최대 6.876)임을 확인했다 - `apply_hncs()`(main)가
원래 X1D 13쌍으로 만들어진 함수인데도, population이 커진 지금은
CFV 100C/907X(5.783)/X2D 100C(6.783)에 훨씬 잘 맞고 X1D 자신에는
오히려 제일 안 맞는 역설적 상황.

`tools/evaluate_x1d_de00_grid.py`(신규, `evaluate_x2dii_de00_grid.py`와
동일 방법론 - exposure_gamma 포함 441콤보 ΔE00 직접 그리드서치, 저해상도
200px로 폴드별 콤보 선택 후 3000px로 최종 완전 LOO 평가)를
`tools.calibrate.collect_local_pairs()`의 X1D 121쌍(dedup 반영, 챠트
제외)에 돌렸다:

**결과 - `apply_hncs()`(main) 대비 개선폭 +18.35%**(14.013 -> 11.442,
102승19패, 부호검정 p<0.0001, 부트스트랩 95% CI [+2.164, +2.974], 0
미포함), **121/121 폴드 전원일치**로
`exposure_gamma=0.6, toe_lift=0.0, shoulder_start=0.82, white_point=1.0`에
수렴 - 이 세션의 다른 어떤 바디 실험보다도 만장일치 표본이 크다(n=121
전체 폴드 예외 없음).

`clahe_clip`은 이 그리드에 포함되지 않아 main 기본값(1.25)을 그대로
차용 - `apply_hncs_x2dii()`/`apply_hncs_x1d50c.py`와 같은 관례(clahe_clip
합동 재검증은 별도 세션 작업, 이 함수엔 아직 적용 안 됨).

재현: `python3 -m tools.evaluate_x1d_de00_grid`.
"""
from core.engine import make_hasselblad_body_look


apply_hncs_x1d = make_hasselblad_body_look(
    toe_lift=0.0, shoulder_start=0.82, white_point=1.0, clahe_clip=1.25, exposure_gamma=0.6)
