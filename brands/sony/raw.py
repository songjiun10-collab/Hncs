"""
apply_sony_raw_look - Sony 제네릭 population-fit(`apply_sony_look`,
brands/sony.py)을 raw+jpeg 실측으로 다시 튜닝한 변형. `leica_raw.py`와
같은 패턴(매트릭스 없이 톤커브 4파라미터만 재조정) - `apply_sony_look()`
자체는 건드리지 않는다.

**경위(2026-09, /goal "그냥 있는거 부터 다 돌리셈요")**: `apply_sony_look()`의
`shoulder_start=0.78`/`clahe_clip=1.25`는 population-fit 공통 관례대로
핫셀블라드 값을 검증 없이 차용한 것이었다. Sony는 이전 세션 raw+jpeg 조사
때 "raw 기준선 확보 불가"로 결론 났었지만(같은 파일 docstring 참고), 그
이후 이 프로젝트가 dpreview에서 직접 raw+jpeg 페어를 수집하면서
`datasets/sony/contributed/`에 실측 데이터가 쌓였다 - 그 결론은 낡았다.

`tools/fit_population_body_de00_grid.py sony`로 raw+jpeg 328쌍(288쌍
디코드 성공, 40쌍은 pre-production ARW를 libraw가 못 읽는 알려진 한계)에
ΔE00 직접 목적함수 그리드서치(252콤보) + 5-fold LOO:

| 단계 | ΔE00 | 개선폭 | 부호검정 p | 부트스트랩 95% CI |
|---|---|---|---|---|
| 200px 선택/400px LOO확정(초판) | 14.046→13.444 | +4.29% | <0.0001 | [+0.517,+0.687] |
| 원본 픽셀(max_dim=3000) 재확인 | 14.998→14.615 | +2.56% | <0.0001 | [+0.306,+0.460] |

5/5 폴드 만장일치로 `toe_lift=0.02, shoulder_start=0.82, white_point=1.0,
clahe_clip=2.0`에 수렴. 원본 픽셀에서 개선폭이 줄었지만(이 프로젝트가
반복 확인한 CLAHE 해상도 편향 - `docs/hncs_structural_research.md` "정정"
절 참고) CI는 0에서 명확히 떨어진 채 유지 - 통계적으로 견고한 개선이다.
**절대 개선폭(~0.38 ΔE00)은 leica_raw.py의 SL2-S 사례와 마찬가지로
1 JND(사람이 지각하는 최소 차이)보다 작다** - 통계적으로 실재하고
공짜(추가 매트릭스/코드 복잡도 없이 파라미터만 교체)라서 채택하는
것이지 시각적으로 체감된다는 뜻은 아니다.

**정정(2026-09-01) - fit_population_body_de00_grid.py 베이스라인 버그**:
위 초판(200/400px) 그리드서치가 도는 동안 스크립트가 "기존" 대비값을
어느 브랜드와도 안 맞는 하드코딩(toe=0,ss=0.5,wp=1.0,clip=1.25)으로
비교하고 있던 버그가 발견됐다(그리드가 고른 최적 조합 자체는 무관 -
항상 실측 ΔE00을 최소화하는 콤보를 고름). 실제 shipped
`apply_sony_look()` 대비로 정정해서(수정 후 스크립트로) 재실행한
결과가 위 표의 "200px 선택/400px LOO확정" 행이다 - 정정 전 잘못된
비교값(+5.92%로 오기록됐던 것)은 폐기.

이 그리드서치는 Sony 전체(328쌍, a7V/a7R VI 등 전용 함수가 있는 바디
포함) 풀링 데이터로 돌렸다 - `apply_canon_raw_look()`과 같은 논리:
전용 바디용 함수가 없는 나머지 Sony 바디를 위한 제네릭 함수를 튜닝하는
것이므로, 있는 데이터가 완벽히 균등하게 커버하지 못해도 "차용값보다는
낫다"는 게 이 채택의 근거다.

재현: `python3 -m tools.fit_population_body_de00_grid sony` (200/400px),
`python3 -m tools.evaluate_population_raw_look_native_confirm sony 0.02 0.82 1.0 2.0`
(원본 픽셀 재확인).

**바디별 분해 - a1 II(ILCE-1M2) 격차 확인, 전용 함수는 기각(2026-09-02)**:
`tools/breakdown_sony_by_camera_body.py`로 전용 함수 없는 3바디
(ILCE-7CR/ILCE-9M3/ILCE-1M2)에 현재 `apply_sony_raw_look()`을 그대로
적용해서 바디별로 쪼개봤다 - a1 II(ILCE-1M2, n=55) 평균 ΔE00=14.272로
나머지 두 바디 풀링(n=127) 평균 10.60~10.91 대비 유의미하게 나빴다
(부트스트랩 95% CI [+2.351, +4.701], 0 안 걸침 - 통계적으로 실재하는
격차, `hasselblad_x1d.py`가 발견했던 것과 같은 패턴).

`tools/fit_population_body_de00_grid.py sony ILCE-1M2`로 a1 II 전용
4파라미터 그리드서치+5-fold LOO를 돌렸다(200px 선택, 400px 확정) - 다만
이 스크립트는 구버전 `apply_sony_look()`(`brands/sony.py`) 대비였다.
그 대비로는 +3.18% 개선(승/패=44/11, 부호검정 p<0.0001, CI
[+0.290,+0.636])이 나왔지만, **진짜 baseline인 `apply_sony_raw_look()`
자체와 맞대결**(`tools/evaluate_sony_a1ii_vs_raw_look.py`, n=55,
max_dim=400)한 결과 두 후보 콤보 전부 개선폭이 사실상 0이었다 -
(toe=0.02,ss=0.66,wp=0.85,clip=3.0): +0.13%(CI [-0.092,+0.132], 0
포함), (toe=0.02,ss=0.78,wp=0.85,clip=2.0): +0.02%(CI [-0.013,+0.015],
0 포함) - 둘 다 판정 보류.

**결론**: a1 II와 다른 바디 사이 격차는 통계적으로 실재하지만, 이
톤커브 4파라미터(toe/shoulder/white_point/clahe_clip) 계열로는 못
좁힌다 - `apply_sony_raw_look()`이 이미 이 계열 안에서 a1 II에 대해
거의 최적점(그리드서치가 찾은 최선인 14.11~14.13과 현재값 14.13이
사실상 같음)에 있다는 뜻이다. X1D 사례(같은 계열 재튜닝으로 +18.35%,
121/121 폴드 만장일치)와 근본적으로 다른 결과 - a1 II 격차는 이
파라미터 계열이 못 건드리는 원인(예: 매트릭스 수준의 색 렌더링
차이)일 가능성이 높다. 전용 `apply_sony_a1ii_raw_look()`은 이 데이터로는
근거가 없어 기각, 만들지 않았다.

재현: `python3 -m tools.breakdown_sony_by_camera_body`(바디별 분해),
`python3 -m tools.fit_population_body_de00_grid sony ILCE-1M2`(그리드,
구버전 대비), `python3 -m tools.evaluate_sony_a1ii_vs_raw_look`(진짜
baseline 재확인)."""
from core.engine import make_population_fit_look

_TOE_LIFT = 0.02
_SHOULDER_START = 0.82
_WHITE_POINT = 1.0
_CLAHE_CLIP = 2.0

apply_sony_raw_look = make_population_fit_look(_TOE_LIFT, _SHOULDER_START, _WHITE_POINT, _CLAHE_CLIP)
