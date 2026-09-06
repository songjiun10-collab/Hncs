"""
apply_hncs_x1dii50c - Experimental. X1D II 50C 전용 `apply_hncs()`
(brands/hasselblad.py) 변형. `hasselblad_x1d.py`/`hasselblad_x2dii.py`와
같은 패턴 - 호출부가 카메라 모델을 판별해 X1D II 50C일 때만 이 함수를
쓰는 걸 전제로 한다.

**경위(2026-09)**: `apply_hncs_x1d()` 신설(세대별 분해에서 X1D가
최악으로 확인된 데 대한 대응) 다음으로, 2위로 나쁜(11.795, 표준편차
6.124) X1D II 50C도 사용자 지시("만들어")로 같은 방법을 적용.

`tools/evaluate_x1dii50c_de00_grid.py`(신설, `evaluate_x1d_de00_grid.py`와
동일 방법론 - exposure_gamma 포함 441콤보 ΔE00 직접 그리드서치, 저해상도
200px로 폴드별 콤보 선택 후 3000px로 최종 완전 LOO 평가)를
`collect_local_pairs()`의 X1D II 50C 38쌍(dedup 반영, 챠트 제외)에
적용:

**결과 - `apply_hncs()`(main) 대비 개선폭 +9.63%**(12.286 -> 11.102,
34승4패, 부호검정 p<0.0001, 부트스트랩 95% CI [+0.886, +1.482], 0
미포함), **38/38 폴드 전원일치**로
`exposure_gamma=0.7, toe_lift=0.02, shoulder_start=0.82, white_point=1.0`에
수렴.

`clahe_clip`은 이 그리드에 포함되지 않아 main 기본값(1.25) 그대로 -
다른 Hasselblad 전용 바디 함수와 같은 관례.

재현: `python3 -m tools.evaluate_x1dii50c_de00_grid`.
"""
from core.engine import make_hasselblad_body_look


apply_hncs_x1dii50c = make_hasselblad_body_look(
    toe_lift=0.02, shoulder_start=0.82, white_point=1.0, clahe_clip=1.25, exposure_gamma=0.7)
