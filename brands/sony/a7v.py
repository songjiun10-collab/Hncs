"""
apply_sony_a7v_look - Experimental. Sony a7 V(ILCE-7M5) 전용
`apply_sony_look()`(brands/sony.py) 대체 - raw+jpeg 페어 기반 첫 Sony
캘리브레이션. brands/sony.py는 population-fit(raw 기준선 없음, 카메라
JPEG population 통계를 직접 film_curve 파라미터로 대입)뿐이었는데, 처음
확보한 a7 V raw(.ARW)+jpeg 75쌍으로 Hasselblad와 동일 방법론(그레이딩 전
중립 렌더링 -> 베이스라인, 카메라 JPEG -> 타깃, `tools.calibrate`의
b2/w995 percentile RMSE 그리드서치 + LOO)을 적용했다.

`apply_sony_look()`은 이 실험으로 손대지 않는다(brands/CLAUDE.md 원칙) -
호출부가 카메라 모델을 판별해 a7 V일 때만 이 함수를 쓰는 걸 전제로 한다
(apply_hncs_x2dii와 같은 패턴).

**표본**: 75쌍 후보 중 raw 디코드/jpeg 로드 성공 58쌍(17쌍은 rawpy가
".ARW"를 못 읽거나 - "Unsupported file format or not RAW file" - jpeg
로드 실패, 원인 미조사) - EXIF Software 태그 기준 편집 오염은 이미 없음
(75쌍 전부 "ILCE-7M5 v1.00" 펌웨어 문자열만 있고 Adobe 서명 없음 확인
후 매니페스트에 등록).

**그리드서치(toe_lift x shoulder_start x white_point, clahe_clip=1.25
고정 - population-fit 값 그대로 차용, 미검증)**: white_point가 처음
탐색범위 상한(1.0, 이후 1.2)에서 반복해서 잡혀 두 차례 범위를 넓힘
(0.85~2.0) - Hasselblad v10 때(brands/hasselblad.py 이력, raw 베이스
라인이 그레이딩 결과보다 계통적으로 어두웠던 문제)와 같은 패턴으로
보인다. 최종 in-sample 최적값 `toe_lift=0.02, shoulder_start=0.5,
white_point=1.35` - white_point>1.0은 `core/curve.py`의 `film_curve()`
smoothstep 구간이 x=1에서 y=white_point로 수렴하게 설계돼 있어서, 1보다
크면 상단 구간이 조기에(더 어두운 입력값부터) 순백으로 클리핑되는 효과를
낸다 - 사실상 하이라이트 쪽 추가 리프트로 해석 가능.

**LOO 검증(58폴드)**: 평균 오차(RMSE 기여값) 기존(population-fit)
34.534 -> LOO 그리드서치 16.329, 개선폭 52.7%, 50승8패, 부호검정
p<0.001, 부트스트랩 95% CI [+44.2%, +60.4%](0 미포함), drop-one
51.7~54.0%(안정). 49/58 폴드가 white_point=1.35, 나머지 9/58은 인접값
1.2에 수렴 - 둘 다 탐색범위 안쪽이라 경계 포화가 아님.

exposure_gamma 같은 전역 노출 리프트 단계는 아직 없음(Hasselblad
apply_hncs의 v10 단계에 해당 - white_point를 1.35까지 밀어올린 것 자체가
비슷한 역할을 우회적으로 하고 있을 가능성이 있지만 별도 파라미터로
분리해서 검증한 적은 없음). 재현: `python3 -m
tools.evaluate_sony_a7v_grid_search`.

**정정(2026-08, white_point=1.35 기각 - RMSE와 ΔE00이 정반대로 나옴)**:
위 white_point=1.35 채택 직후 `tools/evaluate_sony_a7v_de00.py`(신규)로
실제 ΔE00을 재보니 `apply_sony_look`(기존) 대비 **오히려 유의하게
나빴다** - 평균 ΔE00 16.366(기존) -> 16.534(신규), 개선폭 -1.02%,
5승53패, 부호검정 p<0.0001, 부트스트랩 95% CI [-0.203, -0.126](0
미포함, 기존이 확실히 우세). RMSE(+52.7%, 신규 압승)와 ΔE00(-1.02%,
신규 완패)이 정반대 방향 - white_point>1.0이 b2/w995 percentile이라는
좁은 목적함수만 겨냥한 하이라이트 과다 클리핑이었다는 뜻으로 해석했다
(X2D II 분리감마 실험 때 겪은 것과 같은 종류의 목적함수-실제품질 괴리,
`docs/measurements.md` "콤보A RMSE 악화" 절 참고).

**white_point<=1.0으로 좁혀 재검색** - 최종 채택값
`toe_lift=0.02, shoulder_start=0.5, white_point=1.0`(탐색범위 안쪽
경계, 58/58 폴드 만장일치). LOO: 개선폭 31.4%(RMSE 34.534->23.696),
40승18패, 부호검정 p=0.005, 부트스트랩 95% CI [+21.2%, +41.2%],
drop-one 30.3~32.5%(안정). ΔE00 재확인 결과는 아래 별도 절 참고.

**재정정(2026-08, white_point<=1.0으로도 ΔE00은 여전히 짐 - 목적함수를
ΔE00 자체로 교체)**: white_point를 1.0으로 낮춰도 실제 ΔE00은 여전히
기존보다 유의하게 나빴다(16.550 vs 기존 16.366, 개선폭 -1.12%, 4승54패,
p<0.0001, CI [-0.223,-0.147]) - white_point 값 자체가 아니라 **b2/w995
percentile RMSE를 목적함수로 쓰는 그리드서치 방식 자체**가 ΔE00과 방향이
안 맞는 구조적 문제였다는 뜻. `tools/evaluate_sony_a7v_de00_grid.py`
(신규)로 ΔE00(CIEDE2000)을 직접 목적함수로 삼아 140콤보 그리드를
재검색(저해상도 200px로 그리드 선택, 고해상도 400px로 최종 평가) -
LOO 결과 `toe_lift=0.06, shoulder_start=0.82, white_point=1.0`
(57/58 폴드 수렴)이 기존 대비 **개선폭 +0.53%로 작지만 진짜 유의미하게
이겼다**(47승11패, 부호검정 p<0.0001, 부트스트랩 95% CI [+0.058,+0.114],
0 미포함). RMSE 그리드서치가 냈던 31~53%대 "개선"은 전부 목적함수
자체의 결함이었고, ΔE00 기준 진짜 개선 여력은 1% 미만이라는 게 최종
결론 - 최종 채택값을 이걸로 갱신했다. 재현: `python3 -m
tools.evaluate_sony_a7v_de00_grid`.
"""
from core.engine import make_population_fit_look

_TOE_LIFT = 0.06
_SHOULDER_START = 0.82
_WHITE_POINT = 1.0
_CLAHE_CLIP = 1.25  # population-fit 값 차용, 미검증

apply_sony_a7v_look = make_population_fit_look(_TOE_LIFT, _SHOULDER_START, _WHITE_POINT, _CLAHE_CLIP)
