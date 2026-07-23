"""
[GitHub 이슈 #4 대응, Phase 0] raw 베이스라인(rawpy/libraw 기본 디코드)
자체를 색차트 없이 실측 raw+jpeg 페어로 특성화한다.

이슈 #4 지적: "raw 베이스라인이 색차트 최소자승 매트릭스로 특성화된 적이
없다" - hybrid_engine의 ΔE≈15 병목이 톤/채도/hue 등 hybrid_engine
자체의 처리 문제인지, 아니면 애초에 rawpy의 기본 디코드(카메라 고유
CFA 분광감도를 sRGB 프라이머리로 근사하는 기본 색공간 변환)가 실제
카메라(Phocus)와 다른 색공간에서 출발하기 때문인지 이 둘을 분리해서
보지 못했다는 뜻. 실제 ColorChecker 촬영이 이 프로젝트엔 없어서, 대신
13쌍의 실사진 픽셀 대응 자체를 거대한 "차트"로 써서 전역 3x3 선형
컬러 매트릭스 하나를 최소자승으로 맞춘다 - hybrid_engine의 다른 처리를
전혀 거치지 않은 순수 rawpy 디코드 결과에 대해서.

**2026-07 실측(EVALUATION.md 후속 실측 5)**: 이 매트릭스 하나가
교차검증 기준 32.6% 개선을 냈다(다른 LUT 실험들과 달리 유일한 양성
결과) - 자유도 9개뿐이라 표본 13장에서도 과적합이 덜 되는 게 이유로
보인다. 그 결과로 이 모듈은 단순 진단 도구를 넘어 pipeline/engine.py의
정식 **Phase 0** 단계가 됐다(`raw_baseline_matrix` profile 파라미터,
calibrate_profile.py --mode raw_baseline_pipeline으로 캘리브레이션) -
tone_core(Phase 1)/color_core(Phase 2)는 삭제하지 않고 이 매트릭스
위에서 재학습한다(사용자 지시).

**2026-07 확장(docs/superpowers/specs/2026-07-23-matrix-features-design.md,
후속 실측 20)**: 자유도를 통제된 방식으로만 늘리는 두 축을 추가.
(1) root-polynomial feature(Finlayson et al. 2015) - 선형 3항 대신
[r,g,b,sqrt(rg),sqrt(rb),sqrt(gb)] 6항을 써서 노출 불변성을 유지하면서
자유도를 9->18로 늘림. (2) 가중 최소자승(WLS) - 밀도 기반(과대표집된
색 영역 다운웨이트)과 채도 기반(무채색 픽셀 다운웨이트) 두 가중치
스킴. 둘 다 기본값(feature_fn=None, weights=None, ridge=0.0)에서는
기존 동작과 완전히 동일하다.
"""
import numpy as np


def root_polynomial_features(rgb):
    """rgb: (..., 3) linear RGB. 반환: (..., 6) =
    [r, g, b, sqrt(r*g), sqrt(r*b), sqrt(g*b)].

    Finlayson et al. 2015 "Color Correction Using Root-Polynomial
    Regression" 방식 - 제곱항(r^2 등)이 아니라 제곱근 교차항을 쓰는
    이유는 전역 노출(밝기) 스케일 불변성 때문이다: 이미지 전체가 k배
    밝아지면 선형항도 제곱근 교차항도 똑같이 k배로 스케일되어(제곱근
    안의 곱이 k^2배가 되고 제곱근을 취하면 k배), 이 feature로 피팅한
    매트릭스는 노출이 다른 사진에도 그대로 유효하다. 일반 2차 다항식의
    순수 제곱항(r^2)은 k^2배로 스케일되어 이 불변성이 깨진다.

    음수(라인어 RGB 클리핑 이전의 미세한 음수)는 제곱근 전에 0으로
    clip해서 NaN을 막는다 - 최종 feature 값 자체는 clip 안 된 원본
    r/g/b를 그대로 쓴다(선형항은 clip 불필요)."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    r_c = np.clip(r, 0.0, None)
    g_c = np.clip(g, 0.0, None)
    b_c = np.clip(b, 0.0, None)
    return np.stack([
        r, g, b,
        np.sqrt(r_c * g_c),
        np.sqrt(r_c * b_c),
        np.sqrt(g_c * b_c),
    ], axis=-1)


def fit_color_matrix(sources, targets, feature_fn=None, weights=None, ridge=0.0):
    """sources/targets: linear RGB 배열 리스트(각 (H, W, 3), 페어별로
    shape 동일). 전부 이어붙여서 Y ≈ features(X) @ M 최소자승으로
    (K, 3) 행렬을 구한다(K=3이면 feature_fn=None일 때의 기존 동작).
    bias(상수항)는 넣지 않음 - linear RGB는 물리적으로 원점을 지나야
    한다(검은색 -> 검은색).

    feature_fn: None(기존 선형 3항)이거나 (H,W,3)->(H,W,K) 변환 함수
    (예: root_polynomial_features).
    weights: None(균등 가중치)이거나 sources와 길이가 같은 리스트 -
    각 원소는 해당 source와 같은 (H, W) shape의 픽셀별 가중치. 가중
    최소자승은 sqrt(weight)를 X/Y 양쪽에 곱하는 표준 트릭으로 구현.
    ridge: L2 정규화 강도(기본 0 = 정규화 없음, 기존 동작과 동일).
    feature_fn으로 자유도가 늘어날 때 과적합을 억제하는 용도."""
    if feature_fn is None:
        feats = [s.reshape(-1, 3) for s in sources]
    else:
        feats = []
        for s in sources:
            f = feature_fn(s)
            feats.append(f.reshape(-1, f.shape[-1]))
    X = np.concatenate(feats, axis=0)
    Y = np.concatenate([t.reshape(-1, 3) for t in targets], axis=0)

    if weights is not None:
        w = np.concatenate([wi.reshape(-1) for wi in weights], axis=0)
        sqrt_w = np.sqrt(w)[:, None]
        X = X * sqrt_w
        Y = Y * sqrt_w

    if ridge == 0.0:
        matrix, _, _, _ = np.linalg.lstsq(X, Y, rcond=None)
    else:
        k = X.shape[1]
        matrix = np.linalg.solve(X.T @ X + ridge * np.eye(k), X.T @ Y)
    return matrix


def apply_color_matrix(rgb_linear, matrix, feature_fn=None):
    """rgb_linear: (H, W, 3). matrix: (K, 3), fit_color_matrix()가 만든
    것(K=3이면 feature_fn=None, K=6이면 feature_fn=root_polynomial_features
    등). feature_fn은 fit_color_matrix()에 쓴 것과 반드시 같아야 한다.
    반환: 보정된 (H, W, 3), 음수는 0으로 clip(물리적으로 불가능한 음의
    광량은 없음)."""
    features = rgb_linear if feature_fn is None else feature_fn(rgb_linear)
    out = features @ matrix
    return np.clip(out, 0.0, None)
