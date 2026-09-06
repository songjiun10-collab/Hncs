"""
HNCS(Hasselblad Natural Colour Solution) 근사 - X 시스템 통합
(X1D + X1D II + X2D + X2D II 혼합 풀). ⭐ 공식 Stable - `apply_hncs`
하나만 담는다. 원래 이 파일 하나에 apply_hncs/apply_hncs_learned/
apply_hasselblad_day/apply_hasselblad_night 4개 함수가 다 있었는데,
"공식 채택(파라메트릭)" vs "실험/레거시"를 명확히 가르려고 다시 분리했다:
  brands/hasselblad.py         - apply_hncs (이 파일, Stable)
  brands/hasselblad_learned.py - apply_hncs_learned (Experimental)
  brands/hasselblad_day.py     - apply_hasselblad_day (Legacy)
  brands/hasselblad_night.py   - apply_hasselblad_night (Legacy)
day/night가 "Legacy"인 이유: v3 재보정(2026-07) 결과 day/night 타깃 둘 다
apply_hncs의 전체 population 타깃에 거의 수렴해서, 별도 프리셋으로 유지할
근거가 계속 약해지는 중이기 때문 (아직 apply_hncs로 통합은 안 함 - 각
파일 docstring 참고).

문서화된 HNCS 설계 원칙 (hasselblad.com):
1. "Hasselblad Film Curve" - toe + 리니어 미드 + shoulder의 필름형 톤커브
2. "정확한 색값만 복원하면 monotonous - 눈은 대비를 강화해 본다"
   -> 지각 보상: 약한 마이크로 콘트라스트
3. "rich saturation" - 채도 무조작
4. 스킨톤이 전 명도 구간에서 부드러움 -> hue/채도 무조작으로 달성
5. HNCS는 X 시스템 전체(X1D~X2D II)에 걸쳐 일관 적용되는 색철학 -> 바디
   세대를 섞어서 풀링하는 것이 오히려 "카메라 개체차"를 노이즈로 상쇄시켜
   "X 시스템 공통 색과학"을 더 안정적으로 드러냄 (설계 판단, 2026-07)

정정(2026-08-05, hasselblad.com 원문 직접 대조): 위 3/4번의 "채도/
hue 무조작"은 원문과 안 맞는다. 원문(hasselblad.com/learn/
hasselblad-natural-colour-solution/): "The colour data undergoes a
series of transformations that remap the captured values. This ensures
true contrast, rich saturation, and tricky subtle tones – like skin
tones – are kept smooth" - rich saturation은 안 건드려서 나오는 게
아니라 변환이 만들어내는 결과라고 명시돼 있다. 스킨톤 문구도 "커브/
대비 편집 후에도 덜 흔들림"(Phocus 후처리 절)이지 초기 렌더링에서
hue/채도를 아예 안 건드린다는 뜻이 아니다. 자세한 대조는
docs/hncs_structural_research.md 참고. 다만 이 프로젝트가 직접 측정한
"hue가 거의 안 변한다"(v8/v9, 아래 이력)는 결과 자체는 이 정정과
무관하게 유효 - 근거로 삼은 인용이 부정확했을 뿐, apply_hncs()의
실측 검증과 계수는 이 정정으로 바뀌지 않는다.

=== apply_hncs 실측 검증 이력 ===

v8 (공식 샘플 19~20장): 인물 6장 서브셋 재검증 결과 타깃 전체(13.5/222.1)
vs 인물전용(10.0/211.7)이 갈렸지만 피팅 파라미터는 거의 동일(toe_lift
0.001 동일, white_point 0.92->0.90). 스킨톤 hue 3장 검증 - 전부 완전
불변(51->51, 9->9, 11->11).

v9 (공식 샘플 풀 확대 124장, CSV 139행 중 다운로드 성공분): 얼굴 검출
(YuNet)로 인물 서브셋 43장 자동 추출 - 타깃 전체(11.3/223.9) vs 인물전용
(10.2/226.3), v8과 거의 동일선상. 표준편차 큼(화이트 std~27) - 낮/밤/
역광 샘플이 안 갈리고 섞여서 그런 것으로 보이나 커브 파라미터를 흔들
정도는 아니라고 판단해 유지. 스킨톤 hue 43장 자동 검증: 평균 |delta|=
0.21, 최대 2.0 (hue 0~179 기준) - L채널만 건드리는 구조상 나오는 반올림
잡음 수준, 실질적 hue 불변 확인.

v10 (rawpy 설치 후 raw+jpeg 페어 10장으로 진짜 전/후 그리드서치, raw를
카메라WB+오토브라이트끔+표준감마로 중립 렌더링 -> 베이스라인, 같은 행의
공식 JPEG -> 타깃): RMSE 43.8->37.8로 소폭 개선됐지만 최적값이
white_point=1.0(탐색범위 상한)에서 잡힘 - 원인은 중립 렌더링이 실제
그레이딩 결과보다 블랙p2/화이트p99.5가 계통적으로 낮게 나오는데(전역
노출/감마 리프트 단계가 아예 없는 구조), 그 격차를 그리드서치가
white_point를 밀어붙여서 메우려 한 것으로 판단 - 채택 안 하고
toe_lift/shoulder_start/white_point 유지.

v11 (v10 후속): x1d-II-sample-09(오큘러스 실내, 사실상 전체가 흰색이라
그림자 없음)를 그림자무효로 블랙포인트 피팅에서 제외, exposure_gamma
파라미터를 그리드서치에 추가. exposure_gamma=0.7, white_point=1.0만 반영
(toe_lift/shoulder_start는 원안 0.001/0.78 유지) - RMSE 36.3->23.3
(그림자유효 8장+화이트포인트 10장 기준). shoulder_start를 0.5까지
낮추면 RMSE 16.5까지 더 떨어지지만 그림자유효 샘플 8장뿐이라 커브 모양
자체를 바꾸는 건 과적합 위험 커서 채택 안 함.

실험 기록 (음성 결과): calibrate_from_raw.py의 rawpy 베이스라인을
gamma=(2.222,4.5)(sRGB형) 대신 gamma=(1,1)(linear)로 바꿔서 "디모자이크+
컬러매트릭스 직후, 톤커브 적용 전" 상태에 더 가깝게 만들어봄(파이프라인상
이론적으론 더 정확해야 함). 그런데 RMSE 오히려 악화(23.3->28.2) - rawpy의
디모자이크/컬러매트릭스가 핫셀블라드 자체 파이프라인과 다른 알고리즘이라
"센서에 더 가깝게" 만든다고 실제 camera profile 출력과 더 비슷해지는 게
아니었음. gamma=(2.222,4.5) 베이스라인 유지, linear 실험은 되돌림.

v12: raw+jpeg 페어(10장)를 픽셀 단위로 대응시켜 직접 LUT을 학습하는
데이터기반 버전을 시도, RMSE=15.4로 이 파일의 파라메트릭(23.3)보다
낮게 나옴 - 별도 파일 `brands/hasselblad_learned.py`의
apply_hncs_learned()로 분리 제공 (원본이 10장뿐이라 표본이 작다고 판단해
이 파일의 apply_hncs 기본값은 안 건드리고 나란히 유지, 자세한 이력은
그 파일 docstring 참고).

재검증(2026-07, brands/core/tools 리팩토링 후): `tools.calibrate
grid_search`/`learn_curve`로 다시 돌려서 RMSE가 리팩토링 전과 완전히
동일하게 재현됨을 확인(23.31->16.51 grid_search, 23.31->15.41
learn_curve) - raw+jpeg 페어가 여전히 10장뿐이라(나머지는 죽은 링크) 더
재보정할 새 데이터는 없음.

파이프라인 시그니처 분석(2026-07, 공식 샘플 124장 전량 진짜 원본
재다운로드로 샤프닝/미세대비/노이즈/에지헤일로/JPEG 특성 측정): 어느
지표도 확실하고 비혼재된 신호가 아니어서 이 파일에 새 파라미터를
반영하지 않기로 결정 (자세한 근거는 README.md 참고).

세대 간 pooling 재검증(2026-08, local-mixed-2026-07 기여 데이터셋):
raw+jpeg 페어가 X1D 13장(공식)에서 X2D/907X·CFV 실사진 61장이 추가돼
총 74장(4세대)으로 늘었다. 이 파라메트릭 커브(v11, RMSE 19.94)가
`hasselblad_learned.py`의 학습 LUT(v12, RMSE 22.20)보다 전체/세대별
모두 대등하거나 더 나음 - 특히 CFV 100C/907X에서 거의 2배 차이
(10.82 vs 19.11). v12가 X1D 10장 표본에서만 우세했던 건 과적합이었던
것으로 확인됨. `apply_hncs`가 기본값으로 유지되는 근거가 더 튼튼해짐.
자세한 세대별 표는 `docs/measurements.md` 참고.

원 캘리브레이션 데이터(공식 X1D 13쌍) 편집 오염 발견(2026-08): 이
13쌍의 `target.jpg` EXIF Software 태그를 이번에 처음 확인했다 -
**13개 중 9개가 Adobe Photoshop/Lightroom Classic 편집 태그를 갖고
있음**(순정 추정은 4쌍뿐: 00378/02709/x1d-ii-xcd45p-01/02). 이 v11
커브(및 v12 학습 LUT)는 이 13쌍(그중 9쌍이 편집됐을 수 있는) 전체로
피팅됐다. 클린 4쌍만으로 다시 잰 ΔE(target vs 실제 Phocus 렌더 기준
`docs/measurements.md` 참고)는 방향은 안 바뀌지만 n=4라 통계적 의미는
없음 - 재캘리브레이션 여부는 아직 결정하지 않았고 이 함수는 이번에
손대지 않았다.

v11 파라미터 재보정(2026-08, 65쌍 - 공식 오염제외 4 + 로컬 기여
61 - `tools.calibrate grid_search`/`grid_search_loo`): 이번엔 실제로
채택했다. 그리드서치 최적값이 **exposure_gamma=0.7->0.8, toe_lift=
0.001->0.0, shoulder_start=0.78->0.5**(white_point=1.0은 그대로)로
나왔는데, 바로 이 shoulder_start~0.5 값은 v11 원래 이력(위 문단)에서
그림자유효 8장 표본에 과적합 위험으로 채택 안 했던 바로 그 값이라 -
이번엔 leave-one-out(폴드마다 파라미터를 다시 피팅해 안 본 1쌍에만
평가, `grid_search_loo` 모드)으로 먼저 검증했다: 기존 파라미터(이
65쌍으로 피팅된 적 없어 이미 out-of-sample) 평균오차 14.948 ->
LOO최적화 9.960(33.4% 개선), 폴드 55승8패, 부호검정 p<0.001, 부트스트랩
95% CI [+26.0%,+40.5%](0 안 걸침), drop-one 32.5~35.3%(부호 안 뒤집힘),
65폴드 중 64폴드가 정확히 같은 조합에 수렴(나머지 1폴드도
exposure_gamma만 0.9로 거의 동일) - 표본이 8장->65장(4세대)으로 커지면서
그때의 과적합 우려가 실제로 해소됐다고 판단해 채택. `apply_hncs_video_frame()`
도 동일하게 갱신(두 함수는 원래 같은 기본값을 공유하는 설계).

v11 재보정 - 독립 검증 두 갈래(2026-08): 위 33.4%는 grid_search_loo가
쓰는 b2/w995 percentile 오차(그리드서치 목적함수)라 이 프로젝트 표준
지표인 ΔE00(CIEDE2000)은 아니다. 그래서 신구 파라미터를 apply_hncs()에
직접 통과시켜 실측 두 번 더 함: (1) 65쌍 실사진 target.jpg 대비 ΔE00
7.457->6.861(8.0% 개선, 53승12패, 부호검정 p<0.001, CI[+3.9%,+12.2%]).
(2) kmichels ColorChecker Classic 차트(X2D II 100C raw 9장, 장면 내용
편차 없이 순수 톤커브 영향만 격리) 24패치 대비 ΔE00 7.927->6.563(17.2%
개선, 9전9승, 부호검정 p=0.004, CI[+12.6%,+21.4%]). 세 지표(33.4%/
8.0%/17.2%) 전부 같은 방향이지만 스케일이 다르다 - 그리드서치 목적함수가
실제 지각적 개선폭을 과대추정한다는 뜻으로 해석. 패치별로는 균일하게
좋아진 게 아니라는 것도 확인: 대다수 패치(dark skin/foliage/orange/
green/cyan 등)는 크게 개선됐지만 **black 2(가장 어두운 패치)는 오히려
악화**(4.964->6.425), neutral 6.5/8·bluish green·blue·orange yellow도
소폭 악화 - exposure_gamma 0.7->0.8(중간톤 리프트 감소)이 일부 어둡거나
무채색에 가까운 패치를 반대 방향으로 밀어낸 것으로 보인다. 채택 결정은
그대로 유지(평균/폴드 단위로는 확실히, 일관되게 이김), 다만 "모든
톤/색상에서 고르게 나아졌다"는 아님을 기록해둠.
"""
import cv2
import numpy as np

from core.curve import film_curve


def apply_hncs(img_bgr, toe_lift=0.0, shoulder_start=0.5,
               white_point=1.0, clahe_clip=1.25, exposure_gamma=0.8):
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    # 0. 전역 노출 리프트 (v10: 중립 렌더링과 그레이딩 결과 사이 밝기
    #    격차가 toe/shoulder만으론 안 메꿔져서 추가. exposure_gamma=1.0이면
    #    기존 동작과 동일 - no-op)
    if exposure_gamma != 1.0:
        x = np.arange(256, dtype=np.float32) / 255.0
        exp_lut = np.clip((x ** exposure_gamma) * 255, 0, 255).astype(np.uint8)
        l = cv2.LUT(l, exp_lut)

    # 1. 지각 보상 대비 (커브보다 먼저 - 순서 중요)
    clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(8, 8))
    l = clahe.apply(l)

    # 2. Film Curve (L채널, 색 보존)
    x = np.arange(256, dtype=np.float32) / 255.0
    lut = np.clip(film_curve(x, toe_lift, shoulder_start, white_point) * 255,
                  0, 255).astype(np.uint8)
    l = cv2.LUT(l, lut)

    # 3. 채도/hue 무조작 (rich saturation은 "안 건드림"으로 달성)
    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)


def apply_hncs_video_frame(img_bgr, toe_lift=0.0, shoulder_start=0.5,
                            white_point=1.0, exposure_gamma=0.8):
    """apply_hncs()의 비디오 전용 변형 - CLAHE를 생략해 프레임 간
    깜빡임을 피한다. 사진 모드와 동일한 출력이 아니다."""
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    if exposure_gamma != 1.0:
        x = np.arange(256, dtype=np.float32) / 255.0
        exp_lut = np.clip((x ** exposure_gamma) * 255, 0, 255).astype(np.uint8)
        l = cv2.LUT(l, exp_lut)

    x = np.arange(256, dtype=np.float32) / 255.0
    lut = np.clip(film_curve(x, toe_lift, shoulder_start, white_point) * 255,
                  0, 255).astype(np.uint8)
    l = cv2.LUT(l, lut)

    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
