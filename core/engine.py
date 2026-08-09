"""
population-fit 브랜드 근사(leica/phaseone/pentax/ricoh_gr)가 공통으로 쓰는
엔진. 네 브랜드 모두 raw 기준선이 없어서 그리드서치 대신 population
타깃(블랙p2/화이트p99.5)을 film_curve의 toe_lift/white_point에 직접
대입하는 동일한 구조라 하나로 합쳤다 - 브랜드별 차이는 그 상수값뿐.

CLAHE(지각보상 대비) + Lab L채널 전용 톤커브 구조는 hasselblad_hncs.py의
apply_hncs와 동일한 원칙(hue/채도 무조작)을 raw 검증 없이 그대로 차용한
것 - 각 브랜드 모듈 docstring에 명시된 미검증 한계.

shoulder_start/clahe_clip 브랜드별 추정 시도(2026-07,
`tools/highlight_rolloff_signal.py`): 각 브랜드의 population 풀링 L
히스토그램(`datasets/<brand>/joint_distribution.npz`)에서 하이라이트
rolloff 완만함을 재는 지표(90th~99.5th percentile L값 폭, 250~255
클리핑 비율)를 계산해보니 브랜드 간 값 자체는 꽤 벌어짐(rolloff_width
35~64) - 하지만 이게 실제 shoulder_start 차이를 반영하는지 브랜드별
스크레이핑 촬영자의 장면/노출 편향인지 구분할 근거가 없다. 검증된
정답값이 핫셀블라드(shoulder_start=0.78, raw+jpeg 그리드서치로 확정)
하나뿐이라 지표->shoulder_start 매핑을 만들 표본이 안 됨(점 하나로
회귀선을 그릴 수 없음) - population 풀링 히스토그램만으로는 raw
기준선 없이 카메라의 실제 하이라이트 렌더링 곡선을 분리해낼 수 없다는
결론. 그래서 이 9개 브랜드의 shoulder_start/clahe_clip 기본값(핫셀블라드
차용값 0.78/1.25)은 바꾸지 않았다.
"""
import cv2
import numpy as np

from core.curve import film_curve


def apply_population_fit_look(img_bgr, toe_lift, shoulder_start, white_point, clahe_clip):
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(8, 8))
    l = clahe.apply(l)

    x = np.arange(256, dtype=np.float32) / 255.0
    lut = np.clip(film_curve(x, toe_lift, shoulder_start, white_point) * 255,
                  0, 255).astype(np.uint8)
    l = cv2.LUT(l, lut)

    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)


def make_population_fit_look(toe_lift, shoulder_start, white_point, clahe_clip):
    """apply_population_fit_look()에 브랜드별 상수를 고정한 apply_*_look()
    함수를 만들어 반환한다. functools.partial이 아니라 진짜 def 클로저를
    쓰는 이유: hybrid_engine/core/preset_inverse.py와 tools/video_engine.py가
    inspect.signature(func).parameters["toe_lift"].default 형태로 이
    함수의 기본값을 직접 읽어가므로(브랜드 상수를 이중 기록하지 않기
    위해), 그 두 소비자가 지금과 동일하게 동작하려면 실제 함수
    시그니처(파라미터명+기본값)가 그대로 보존돼야 한다."""
    def apply(img_bgr, toe_lift=toe_lift, shoulder_start=shoulder_start,
              white_point=white_point, clahe_clip=clahe_clip):
        return apply_population_fit_look(img_bgr, toe_lift, shoulder_start, white_point, clahe_clip)
    return apply


def apply_population_fit_look_video_frame(img_bgr, toe_lift, shoulder_start, white_point):
    """apply_population_fit_look()의 비디오 전용 변형 - CLAHE(프레임별
    적응형 로컬 대비 보정)를 생략하고 톤 LUT만 적용한다. CLAHE는 프레임마다
    로컬 히스토그램을 새로 계산해서 비디오에서 깜빡임을 유발하지만, 이
    함수가 쓰는 film_curve() 기반 톤 LUT는 브랜드 고정 파라미터로만
    계산되고 프레임 내용과 무관해 시간적으로 안정적이다. 사진 모드
    apply_population_fit_look()과 동일한 출력이 아니다(로컬 대비가 약함)."""
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    x = np.arange(256, dtype=np.float32) / 255.0
    lut = np.clip(film_curve(x, toe_lift, shoulder_start, white_point) * 255,
                  0, 255).astype(np.uint8)
    l = cv2.LUT(l, lut)

    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
