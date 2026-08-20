"""
apply_sigma_fpl_look - Experimental. Sigma fp L 전용 `apply_sigma_look()`
(brands/sigma.py) 대체 - 호출부가 카메라 모델을 판별해 Sigma fp L일 때만
이 함수를 쓰는 걸 전제로 한다. Sigma BF(brands/sigma_bf.py)와는 별개
바디로 독립 그리드서치.

**경위(2026-08)**: 로컬 raw+jpeg 라이브러리에 Sigma fp L 페어 32장이
새로 들어와서(EXIF Software가 펌웨어 버전 문자열만 있고 Adobe 서명 없음
- 편집 오염 없음 확인) `apply_sigma_look()`(main) 대비 ΔE00을 직접
목적함수로 그리드서치+LOO를 Sigma BF와 동일 방식으로 돌렸다
(`tools/evaluate_new_body_de00_grid.py` - 저해상도(200px) 폴드별 콤보
선택, 400px 확정, 이어서 `tools/evaluate_native_pixel_confirm.py`로
원본 해상도(max_dim=3000) 재확인).

| 검증 단계 | 개선폭 | 승/패 | 부호검정 p | 부트스트랩 95% CI |
|---|---|---|---|---|
| LOO(200px 선택/400px 평가) | +0.63% | 23/9 | 0.0201 | [+0.044, +0.129] |
| 원본 픽셀(max_dim=3000) | +0.55% | 23/9 | 0.0201 | [+0.038, +0.124] |

두 단계가 다운샘플 왜곡 없이 일치. 32/32 폴드 만장일치로 같은 조합
선택: **`toe_lift=0.02, shoulder_start=0.82, white_point=1.0`** - Sigma
BF(`toe_lift=0.09, shoulder_start=0.82, white_point=1.0`)와는 toe_lift만
다르다.

**주의**: Sigma BF와 마찬가지로 개선폭 자체는 작다(X1D-50c/X2D II
급이 아니라 Sony a7V/Sigma BF와 비슷한 규모) - CI는 0을 벗어나지만
Sigma BF(CI 하한 +0.007)보다는 하한이 조금 더 멀다(+0.038). 표본
32장도 X2D II(70장)보다 작음 - 페어가 더 추가되면 재검증 권장. 재현:
`python3 -m tools.evaluate_new_body_de00_grid --label "Sigma fp L"
--manifest datasets/sigma/sigma_new_pairs.csv --raw-dir
"/Users/songjiun/local-work" --model "SIGMA fp L" --baseline
brands.sigma.apply_sigma_look`.
"""
from core.engine import make_population_fit_look

_TOE_LIFT = 0.02
_SHOULDER_START = 0.82
_WHITE_POINT = 1.0
_CLAHE_CLIP = 1.25  # population-fit 값 차용, 미검증

apply_sigma_fpl_look = make_population_fit_look(_TOE_LIFT, _SHOULDER_START, _WHITE_POINT, _CLAHE_CLIP)
