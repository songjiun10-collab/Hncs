"""
[GitHub 이슈 #4 대응] raw 베이스라인(rawpy/libraw 기본 디코드) 자체를
색차트 없이 실측 raw+jpeg 페어로 특성화한다.

이슈 #4 지적: "raw 베이스라인이 색차트 최소자승 매트릭스로 특성화된 적이
없다" - hybrid_engine의 ΔE≈15 병목이 톤/채도/hue 등 hybrid_engine
자체의 처리 문제인지, 아니면 애초에 rawpy의 기본 디코드(카메라 고유
CFA 분광감도를 sRGB 프라이머리로 근사하는 기본 색공간 변환)가 실제
카메라(Phocus)와 다른 색공간에서 출발하기 때문인지 이 둘을 분리해서
보지 못했다는 뜻. 실제 ColorChecker 촬영이 이 프로젝트엔 없어서, 대신
13쌍의 실사진 픽셀 대응 자체를 거대한 "차트"로 써서 전역 3x3 선형
컬러 매트릭스 하나를 최소자승으로 맞춘다 - hybrid_engine의 Phase 0-2를
전혀 거치지 않은 순수 rawpy 디코드 결과에 대해서.
"""
import numpy as np


def fit_color_matrix(sources, targets):
    """sources/targets: linear RGB 배열 리스트(각 (H, W, 3), 페어별로
    shape 동일). 전부 이어붙여서 Y ≈ X @ M 최소자승으로 (3, 3) 행렬을
    구한다. bias(상수항)는 넣지 않음 - linear RGB는 물리적으로 원점을
    지나야 한다(검은색 -> 검은색)."""
    X = np.concatenate([s.reshape(-1, 3) for s in sources], axis=0)
    Y = np.concatenate([t.reshape(-1, 3) for t in targets], axis=0)
    matrix, _, _, _ = np.linalg.lstsq(X, Y, rcond=None)
    return matrix


def apply_color_matrix(rgb_linear, matrix):
    """rgb_linear: (H, W, 3). matrix: (3, 3), fit_color_matrix()가 만든
    것. 반환: 보정된 (H, W, 3), 음수는 0으로 clip(물리적으로 불가능한
    음의 광량은 없음)."""
    out = rgb_linear @ matrix
    return np.clip(out, 0.0, None)
