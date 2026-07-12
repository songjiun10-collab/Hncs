"""
population-fit 브랜드 근사(leica/phaseone/pentax/ricoh_gr)가 공통으로 쓰는
엔진. 네 브랜드 모두 raw 기준선이 없어서 그리드서치 대신 population
타깃(블랙p2/화이트p99.5)을 film_curve의 toe_lift/white_point에 직접
대입하는 동일한 구조라 하나로 합쳤다 - 브랜드별 차이는 그 상수값뿐.

CLAHE(지각보상 대비) + Lab L채널 전용 톤커브 구조는 hasselblad_hncs.py의
apply_hncs와 동일한 원칙(hue/채도 무조작)을 raw 검증 없이 그대로 차용한
것 - 각 브랜드 모듈 docstring에 명시된 미검증 한계.
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
