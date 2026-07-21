"""
[핵심] Delta E (CIEDE2000) 오차 측정 루프. 엔진 출력과 타깃 이미지(실제
카메라 JPEG 또는 완성 그레이딩본)를 같은 Lab 도메인으로 변환해서 픽셀별
색차를 계산한다. 인간 눈이 구별하기 힘든 수준은 대략 ΔE < 2.0.
"""
import numpy as np
import colour

_SRGB = colour.RGB_COLOURSPACES["sRGB"]


def _linear_rgb_to_lab(rgb_linear):
    xyz = colour.RGB_to_XYZ(rgb_linear, _SRGB, apply_cctf_decoding=False)
    return colour.XYZ_to_Lab(xyz)


def mean_delta_e(rgb_a_linear, rgb_b_linear, method="CIE 2000"):
    """두 linear RGB 이미지(shape 동일) 사이 픽셀별 ΔE 평균."""
    if rgb_a_linear.shape != rgb_b_linear.shape:
        raise ValueError(f"shape mismatch: {rgb_a_linear.shape} vs {rgb_b_linear.shape}")
    lab_a = _linear_rgb_to_lab(rgb_a_linear).reshape(-1, 3)
    lab_b = _linear_rgb_to_lab(rgb_b_linear).reshape(-1, 3)
    delta = colour.delta_E(lab_a, lab_b, method=method)
    return float(np.mean(delta))


def delta_e_map(rgb_a_linear, rgb_b_linear, method="CIE 2000"):
    """픽셀별 ΔE 맵 (H, W) - 오차가 큰 영역을 시각화할 때 사용."""
    if rgb_a_linear.shape != rgb_b_linear.shape:
        raise ValueError(f"shape mismatch: {rgb_a_linear.shape} vs {rgb_b_linear.shape}")
    h, w = rgb_a_linear.shape[:2]
    lab_a = _linear_rgb_to_lab(rgb_a_linear).reshape(-1, 3)
    lab_b = _linear_rgb_to_lab(rgb_b_linear).reshape(-1, 3)
    delta = colour.delta_E(lab_a, lab_b, method=method)
    return np.asarray(delta).reshape(h, w)


def load_image_linear_for_evaluate(target_path, result_shape, resize_to_match=True):
    """타깃 이미지를 읽어서 result_shape((H, W, 3))에 맞춘 Linear RGB로
    반환. resize_to_match=True(기본)면 shape이 다를 때 같은 장면/구도라는
    전제 하에 리사이즈해서 맞춘다 - 아직 정수인 상태에서 먼저 리사이즈
    하고 나서 float64/cctf_decoding으로 변환한다(load_image_linear의
    resize_to 참고) - 큰 타깃을 원본 해상도로 먼저 부풀렸다가 버리면
    다운샘플된 엔진 출력과 비교하는 경우에도 불필요하게 OOM 위험이
    생긴다."""
    from hybrid_engine.utils.io import load_image_linear

    if not resize_to_match:
        target = load_image_linear(target_path)
        if target.shape != result_shape:
            raise ValueError(f"shape mismatch: {result_shape} vs {target.shape}")
        return target
    return load_image_linear(target_path, resize_to=result_shape[:2])


def evaluate(engine, raw_path, target_path, resize_to_match=True):
    """RAW를 engine에 통과시킨 결과와 target_path(실제 카메라 JPEG 등
    완성본) 사이 평균 ΔE를 계산하는 검증 루프 진입점."""
    from hybrid_engine.utils.io import decode_raw

    src = decode_raw(raw_path)
    result = engine.process(src)
    target = load_image_linear_for_evaluate(target_path, result.shape,
                                             resize_to_match=resize_to_match)
    return mean_delta_e(result, target)
