"""
apply_leica_raw_look - Experimental. Leica SL3-P/Q3 43 전용
`apply_leica_look()`(brands/leica.py) 대체 - raw+jpeg 페어 기반 첫 Leica
캘리브레이션. brands/leica.py는 population-fit(raw 기준선 없음, M9/X
Vario/SL2 population 통계를 직접 대입)뿐이었는데, 처음 확보한
SL3-P(41쌍)+Q3 43(44쌍) raw(.dng)+jpeg로 Sony a7V와 동일 방법론(ΔE00을
직접 목적함수로 삼는 그리드서치 - b2/w995 percentile RMSE를 쓰면 실제
ΔE00과 반대로 갈 수 있다는 걸 Sony a7V에서 겪음, brands/sony_a7v.py
이력 참고)을 적용했다.

`apply_leica_look()`은 이 실험으로 손대지 않는다(brands/CLAUDE.md 원칙) -
호출부가 카메라 모델을 판별해 SL3-P/Q3 43일 때만 이 함수를 쓰는 걸
전제로 한다.

**표본**: SL3-P 55매칭 중 41쌍 클린(14쌍 Adobe Camera Raw 편집 오염),
Q3 43 50매칭 중 44쌍 클린(6쌍 오염) - EXIF Software 태그 기준(순정은
버전 문자열만: SL3-P "4.2.0-t-alpha.11"/"4.2.0-t-beta.4", Q3 43
"2.0.4"). 두 바디를 따로 그리드서치했다(Hasselblad X2D II처럼 센서/
렌즈 시스템이 다른 바디를 하나로 묶을 근거가 없어서).

**결과 - 두 바디가 정확히 같은 조합에 수렴**(우연인지 진짜 "라이카
하우스 룩"인지는 미확인, 표본이 2바디뿐이라 판단 근거 부족):
`toe_lift=0.0, shoulder_start=0.82, white_point=1.0` (SL3-P 41/41,
Q3 43 44/44 폴드 만장일치) - 그래서 두 바디를 이 파일 하나의 함수로
같이 커버한다.

| 바디 | n | 개선폭 | 승/패 | 부호검정 p | 부트스트랩 95% CI |
|---|---|---|---|---|---|
| SL3-P | 41 | +2.77% | 40/1 | <0.0001 | [+0.173, +0.330] |
| Q3 43 | 44 | +0.80% | 34/10 | 0.0004 | [+0.044, +0.136] |

둘 다 CI가 0을 안 낀 채 양수 - 통계적으로 견고하지만 개선폭 자체는
작다(Sony a7V의 +0.53%와 비슷한 규모 - ΔE00을 직접 목적함수로 쓰면
percentile RMSE 그리드서치가 냈던 것 같은 큰 숫자는 안 나온다는 게
이번 세션에서 반복 확인된 패턴).

clahe_clip=1.25는 population-fit 값 그대로 차용(미검증, 이번 실험
범위 밖). 재현: `python3 -m tools.evaluate_leica_de00_grid sl3p` /
`python3 -m tools.evaluate_leica_de00_grid q343`.

**적용 범위 확장 - SL2/M10 추가 (2026-08)**: 로컬 raw+jpeg 라이브러리에
SL2(55쌍)·M10(32쌍)이 새로 추가돼서 같은 방법론(ΔE00 직접 그리드서치+
LOO, `tools/evaluate_new_body_de00_grid.py` 저해상도 선택 -> 400px
확정, `tools/evaluate_native_pixel_confirm.py`로 원본 픽셀(max_dim=3000)
재확인)으로 `apply_leica_look()`(brands/leica.py) 대비 검증했다.

| 바디 | n | 개선폭(LOO, 400px) | 개선폭(원본 픽셀) | 부호검정 p | 부트스트랩 95% CI(픽셀) |
|---|---|---|---|---|---|
| SL2 | 55 | +2.29% | +1.89% | <0.0001 | [+0.138, +0.274] |
| M10 | 32 | +2.03% | +1.53% | 0.0005 | [+0.079, +0.226] |

**두 바디 모두 SL3-P/Q3 43과 완전히 같은 조합에 수렴**(SL2 55/55,
M10 32/32 폴드 만장일치: `toe_lift=0.0, shoulder_start=0.82,
white_point=1.0`) - 이제 4개 바디(SL3-P/Q3 43/SL2/M10)가 전부 같은
값이라 우연이 아니라 "라이카 하우스 룩"에 가깝다는 근거가 됨. 호출부는
이 4개 모델 중 하나일 때 이 함수를 쓰면 된다 - M11은 편집 오염(Adobe
Camera Raw)으로 이번 배치에 클린 페어가 0장이라 검증 불가, 아직
미포함. 재현: `python3 -m tools.evaluate_new_body_de00_grid --label
"Leica SL2" --manifest datasets/leica/leica_new_pairs.csv --raw-dir
"/Users/songjiun/local-work" --model "LEICA SL2" --baseline
brands.leica.apply_leica_look` (M10은 --model만 교체).

**적용 범위 확장 - SL2-S 추가 (2026-08)**: 같은 라이브러리에 SL2-S
43쌍이 추가돼서 동일 방법론으로 검증: 개선폭 +1.21%, 38승5패, 부호검정
p<0.0001, 부트스트랩 95% CI [+0.080, +0.173]. 43/43 폴드 만장일치로
역시 같은 조합(`toe_lift=0.0, shoulder_start=0.82, white_point=1.0`)에
수렴 - 5개 바디(SL3-P/Q3 43/SL2/M10/SL2-S) 전부 동일한 값. 5패 전부
diff 0.002~0.041 ΔE00로 편향 신호 없음(렌즈/ISO/F값/촬영일 확인,
전부 승 그룹과 분포 동일). 재현: 위 명령의 `--model`만 "LEICA SL2-S"로
교체.

**독립 재확인 - SL2-S(2026-08, /goal "다른 브랜드 ΔE00<10" 조사 중)**:
같은 SL2-S 43쌍으로 별도 스크립트(`tools/confirm_leica_raw_look_extension.py`)로
원본 픽셀(max_dim=3000)에서 다시 재확인 - +0.93%, 34승9패, 부호검정
p=0.0002, 부트스트랩 95% CI [+0.070, +0.157](0 미포함) - 위 +1.21%와
소폭 다르지만(다른 스크립트/다른 시점 파이프라인) 방향·유의성 모두
동일, 채택 유지. **참고**: 절대 개선폭(~0.11 ΔE00)은 사람이 지각하는
최소 차이(~1 JND)보다 한 자릿수 작다 - 통계적으로 실재하고 공짜(코드
변경 없음)라서 유지하는 것이지 시각적으로 체감된다는 뜻은 아니다.
같은 조사에서 **CL(28쌍)은 기각**: +0.36%, 13승15패, 부호검정 p=0.85,
부트스트랩 95% CI [-0.005, +0.126](0 포함) - 근거 없음, 이 함수
적용 범위에 추가 안 함(`apply_leica_look()`(brands/leica.py) 그대로 사용).
"""
from core.engine import make_population_fit_look

_TOE_LIFT = 0.0
_SHOULDER_START = 0.82
_WHITE_POINT = 1.0
_CLAHE_CLIP = 1.25  # population-fit 값 차용, 미검증

apply_leica_raw_look = make_population_fit_look(_TOE_LIFT, _SHOULDER_START, _WHITE_POINT, _CLAHE_CLIP)
