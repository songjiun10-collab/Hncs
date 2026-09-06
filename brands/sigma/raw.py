"""
apply_sigma_raw_look - Sigma 제네릭 population-fit(`apply_sigma_look`,
brands/sigma.py)을 raw+jpeg 실측으로 다시 튜닝한 변형. `leica_raw.py`/
`sony_raw.py`와 같은 패턴(매트릭스 없이 톤커브 4파라미터만 재조정) -
`apply_sigma_look()` 자체는 건드리지 않는다.

**경위(2026-09, /goal "그냥 있는거 부터 다 돌리셈요")**: `apply_sigma_look()`의
`shoulder_start=0.78`/`clahe_clip=1.25`는 population-fit 공통 관례대로
핫셀블라드 값을 검증 없이 차용한 것이었다. `datasets/sigma/contributed/`의
83쌍(전량 디코드 성공, Sigma BF/fp L 등 전용 함수가 있는 바디 포함
풀링)에 `tools/fit_population_body_de00_grid.py sigma`로 ΔE00 직접
목적함수 그리드서치(252콤보) + 5-fold LOO:

| 단계 | ΔE00 | 개선폭 | 부호검정 p | 부트스트랩 95% CI |
|---|---|---|---|---|
| 200px 선택/400px LOO확정(초판) | 15.872→14.647 | +7.72% | 0.0009 | [+0.784,+1.654] |
| 원본 픽셀(max_dim=3000) 재확인 | 16.716→15.742 | +5.82% | 0.0080 | [+0.522,+1.419] |

5/5 폴드 만장일치로 `toe_lift=0.02, shoulder_start=0.82, white_point=1.0,
clahe_clip=3.0`에 수렴. 원본 픽셀에서 개선폭이 줄었지만(이 프로젝트가
반복 확인한 CLAHE 해상도 편향) CI는 0에서 명확히 떨어진 채 유지 -
통계적으로 견고한 개선이다. Sony(`sony_raw.py`)와 나란히, 있는 데이터로
할 수 있는 최선이라는 논리로 채택 - 전용 함수가 없는 나머지 Sigma
바디를 위한 제네릭 함수 튜닝.

**Sigma fp L 단독 재시도는 기각됐던 것과 별개**: `tools/fit_sigma_fpl_deployable_pipeline.py`
(매트릭스+톤+채도, fp L 32쌍 단독)는 통계적으로 무의미해서(-2.81%,
p=0.86, CI[-1.390,+0.302]) 기각·삭제됐다(이 세션 앞부분 기록) - 이건
매트릭스 없는 순수 톤커브를, fp L 단독이 아니라 Sigma 전체 83쌍
풀링으로 다시 물은 별개 실험이고, 여기서는 신호가 있었다.

재현: `python3 -m tools.fit_population_body_de00_grid sigma` (200/400px),
`python3 -m tools.evaluate_population_raw_look_native_confirm sigma 0.02 0.82 1.0 3.0`
(원본 픽셀 재확인).
"""
from core.engine import make_population_fit_look

_TOE_LIFT = 0.02
_SHOULDER_START = 0.82
_WHITE_POINT = 1.0
_CLAHE_CLIP = 3.0

apply_sigma_raw_look = make_population_fit_look(_TOE_LIFT, _SHOULDER_START, _WHITE_POINT, _CLAHE_CLIP)
