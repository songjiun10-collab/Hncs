"""
apply_sony_a7rvi_look - Experimental. Sony a7R VI(ILCE-7RM6) 전용
`apply_sony_look()`(brands/sony.py) 대체 - a7V(brands/sony_a7v.py)와는
별개 바디로 독립 그리드서치. 호출부가 카메라 모델을 판별해 a7R VI일
때만 이 함수를 쓰는 걸 전제로 한다.

**경위(2026-08)**: 로컬 raw+jpeg 라이브러리에 a7R VI 페어 40장이 새로
추가돼서(EXIF Software가 펌웨어 버전 문자열만 있고 Adobe 서명 없음 -
편집 오염 없음 확인, 126장 중 17장은 Sony "Compressed RAW" 포맷을
libraw 0.22.1이 지원 안 해서 디코드 자체가 안 됨 - 애초에 후보에서
제외), `apply_sony_look()`(main) 대비 ΔE00을 직접 목적함수로
그리드서치+LOO를 X2D II/X1D-50c와 동일 방식으로 돌렸다
(`tools/evaluate_new_body_de00_grid.py` - 저해상도(200px) 폴드별 콤보
선택, 400px 확정, 이어서 `tools/evaluate_native_pixel_confirm.py`로
원본 해상도(max_dim=3000) 재확인).

| 검증 단계 | 개선폭 | 승/패 | 부호검정 p | 부트스트랩 95% CI |
|---|---|---|---|---|
| LOO(200px 선택/400px 평가) | +0.52% | 31/9 | 0.0007 | [+0.007, +0.162] |
| 원본 픽셀(max_dim=3000) | +0.57% | 31/9 | 0.0007 | [+0.021, +0.172] |

두 단계가 다운샘플 왜곡 없이 일치. 35/40 폴드가 만장일치로 같은 조합
선택: **`toe_lift=0.09, shoulder_start=0.7, white_point=0.85`** - a7V
(`toe_lift=0.06, shoulder_start=0.82, white_point=1.0`)와는 확실히 다른
값이라 a7V 값을 가져오지 않고 이 40장으로 독립적으로 새로 찾았다.

**주의**: 개선폭 자체는 X1D-50c(+5.96%)보다 훨씬 작다(Sony a7V의
+0.52~0.83%와 비슷한 규모) - CI가 0을 벗어나긴 하지만 하한이
+0.007~0.021로 0에 가깝다. 통계적으로는 유의하지만 효과 크기가 작다는
점은 감안할 것. 표본 40장도 X2D II(70장)보다 작음 - 페어가 더 추가되면
재검증 권장. 재현: `python3 -m tools.evaluate_new_body_de00_grid --label
"Sony a7R VI (ILCE-7RM6)" --manifest datasets/sony/sony_new_pairs.csv
--raw-dir "/Users/songjiun/local-work" --model "ILCE-7RM6" --baseline
brands.sony.apply_sony_look`.
"""
from core.engine import make_population_fit_look

_TOE_LIFT = 0.09
_SHOULDER_START = 0.7
_WHITE_POINT = 0.85
_CLAHE_CLIP = 1.25  # population-fit 값 차용, 미검증

apply_sony_a7rvi_look = make_population_fit_look(_TOE_LIFT, _SHOULDER_START, _WHITE_POINT, _CLAHE_CLIP)
