"""
apply_sigma_bf_look - Experimental. Sigma BF 전용 `apply_sigma_look()`
(brands/sigma.py) 대체 - 호출부가 카메라 모델을 판별해 Sigma BF일 때만
이 함수를 쓰는 걸 전제로 한다.

**경위(2026-08)**: 로컬 raw+jpeg 라이브러리에 Sigma BF 페어 51장이
새로 들어와서(EXIF Software가 펌웨어 버전 문자열만 있고 Adobe 서명 없음
- 편집 오염 없음 확인) `apply_sigma_look()`(main) 대비 ΔE00을 직접
목적함수로 그리드서치+LOO를 X2D II/X1D-50c/a7R VI와 동일 방식으로
돌렸다(`tools/evaluate_new_body_de00_grid.py` - 저해상도(200px) 폴드별
콤보 선택, 400px 확정, 이어서 `tools/evaluate_native_pixel_confirm.py`로
원본 해상도(max_dim=3000) 재확인).

| 검증 단계 | 개선폭 | 승/패 | 부호검정 p | 부트스트랩 95% CI |
|---|---|---|---|---|
| LOO(200px 선택/400px 평가) | +0.65% | 39/12 | 0.0002 | [+0.023, +0.200] |
| 원본 픽셀(max_dim=3000) | +0.53% | 39/12 | 0.0002 | [+0.007, +0.181] |

51/51 폴드 만장일치로 같은 조합 선택: **`toe_lift=0.09,
shoulder_start=0.82, white_point=1.0`**.

**주의 - 이 배치 중 가장 약한 근거**: 원본 픽셀 CI 하한이 +0.007로
0에 극도로 가까움 - 부트스트랩 표본을 조금만 다르게 뽑아도 CI가 0을
포함할 수 있는 경계선이다. Canon EOS R6 Mark III(+0.06%, 채택 안 함)보다는
낫지만 X1D-50c(+5.96%)나 X2D II(+13.38%)와는 신뢰도 차이가 크다. 사용자가
표본 확장 없이 지금 있는 결과 그대로 반영하기로 결정해서 실었지만,
Sigma BF 페어가 더 늘면 제일 먼저 재검증해야 할 후보다. 재현:
`python3 -m tools.evaluate_new_body_de00_grid --label "Sigma BF"
--manifest datasets/sigma/sigma_new_pairs.csv --raw-dir
"/Users/songjiun/local-work" --baseline brands.sigma.apply_sigma_look`.

**갱신(2026-08, clahe_clip 재검증)**: `clahe_clip=1.25`는 population-fit
기본값을 그대로 차용한 미검증값이었다 - `shoulder_start`와 합동으로
2D 그리드서치(`tools/evaluate_all_brands_clahe_shoulder_grid.py`)를
다시 돌려보니 82/82 폴드 만장일치로 `clahe_clip=3.0`(shoulder_start는
0.82 그대로)이 나왔다. 현재 shipped 함수(clahe_clip=1.25) 대비
+7.04%, 승/패=56/26, 부호검정 p=0.0012, 부트스트랩 95% CI
[+0.670,+1.551](0 미포함) - 위 원본 픽셀 검증(+0.53%, CI 하한 +0.007)
보다 훨씬 견고한 신호라 반영. `toe_lift`/`shoulder_start`/`white_point`는
불변.
"""
from core.engine import make_population_fit_look

_TOE_LIFT = 0.09
_SHOULDER_START = 0.82
_WHITE_POINT = 1.0
_CLAHE_CLIP = 3.0  # 2026-08 shoulder_start x clahe_clip 합동 재검증
# (tools/evaluate_all_brands_clahe_shoulder_grid.py, n=82, +7.04%,
# p=0.0012, CI [+0.670,+1.551] 0 미포함, 82/82 만장일치)으로 1.25->3.0.
# docs/measurements.md 참고.

apply_sigma_bf_look = make_population_fit_look(_TOE_LIFT, _SHOULDER_START, _WHITE_POINT, _CLAHE_CLIP)
