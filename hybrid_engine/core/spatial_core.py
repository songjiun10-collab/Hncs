"""
[Phase 2] 공간(spatial) 연산 - 주변 픽셀을 참조하는 로컬 콘트라스트
("Clarity") 보정. tone_core/color_core/hue_core/lab2d_core/lab3d_core는
전부 픽셀별(pointwise) 연산이라 이웃 픽셀 정보를 못 쓰는데, evaluate_fidelity의
SSIM(L) 0.74가 절대색만이 아니라 구조/대비 자체도 실제 카메라 JPEG와
다르다는 신호였다 - 이 모듈이 메우려는 자리.

L채널에 언샤프 마스크(unsharp mask) 방식 로컬 콘트라스트를 적용한다:
가우시안 블러로 "저주파(전체적인 밝기 흐름)"를 뽑고, 원본에서 그걸 뺀
"디테일(고주파)" 성분을 amount만큼 증폭해서 다시 더한다. threshold 이하의
미세한 디테일(주로 노이즈)은 증폭하지 않는다.

L/a/b 결합 잔차 LUT들(2D/3D)이 표본 13장에서 전부 교차검증 기준
음성이었던 것과 달리(assets/luts/README.md), 이건 파라미터가 3개뿐인
파라메트릭 모델이라 과적합 위험이 훨씬 낮다 - Phase 1의 tone_core
파라미터 캘리브레이션과 같은 성격.
"""
import cv2
import numpy as np


def apply_local_contrast(L, radius=30.0, amount=0.0, threshold=0.0):
    """L: (H, W) LAB L채널([0, 100]). amount=0이면 완전 항등(무보정) -
    Phase 2를 켜도 캘리브레이션 전에는 아무 효과가 없도록 안전한 기본값.
    radius: 가우시안 블러 sigma(픽셀) - 클수록 더 넓은 영역의 콘트라스트를
    다룸("Clarity"에 가까움), 작을수록 좁은 영역(선명화에 가까움).
    threshold: 이 값보다 작은 절대 디테일은 증폭하지 않음(평탄한 영역의
    노이즈를 증폭시키지 않기 위함)."""
    if amount == 0.0:
        return L
    L64 = L.astype(np.float64)
    blurred = cv2.GaussianBlur(L64, (0, 0), sigmaX=radius)
    detail = L64 - blurred
    mask = np.abs(detail) >= threshold
    boosted = L64 + amount * detail * mask
    return np.clip(boosted, 0.0, 100.0)
