"""
Protocol 1(Fidelity)/Protocol 2(Cross-camera generalization) 평가에 쓰는
지표 함수 모음. `utils/evaluate.py`의 mean_delta_e()가 이미 하는 "평균 ΔE
하나로 뭉개기"보다 세분화된 진단이 필요해서 분리했다 - 단일 숫자는
국소적 오차나 구간별 편향(그림자만 틀렸다든가)을 가린다.

scikit-image를 새로 추가하지 않고(이 프로젝트의 최소 의존성 원칙) SSIM은
표준 11x11 가우시안 윈도우 공식을 cv2로 직접 구현했다 - skimage.metrics.
structural_similarity와 같은 결과를 내는 표준 정의.
"""
import cv2
import numpy as np
import colour

_SRGB = colour.RGB_COLOURSPACES["sRGB"]


def _to_lab(rgb_linear):
    xyz = colour.RGB_to_XYZ(rgb_linear, _SRGB, apply_cctf_decoding=False)
    return colour.XYZ_to_Lab(xyz)


def delta_e_stats(rgb_a_linear, rgb_b_linear, method="CIE 2000"):
    """픽셀별 ΔE 분포 요약 - 평균만이 아니라 median/p95/max까지. p95/max가
    큰데 평균은 낮으면 국소적으로 심하게 틀린 영역이 있다는 신호."""
    if rgb_a_linear.shape != rgb_b_linear.shape:
        raise ValueError(f"shape mismatch: {rgb_a_linear.shape} vs {rgb_b_linear.shape}")
    lab_a = _to_lab(rgb_a_linear).reshape(-1, 3)
    lab_b = _to_lab(rgb_b_linear).reshape(-1, 3)
    d = np.asarray(colour.delta_E(lab_a, lab_b, method=method))
    return {
        "mean": float(np.mean(d)),
        "median": float(np.median(d)),
        "p95": float(np.percentile(d, 95)),
        "max": float(np.max(d)),
    }


def delta_e_by_zone(rgb_a_linear, rgb_b_linear, method="CIE 2000"):
    """rgb_a(기준/타깃)의 L채널을 기준으로 그림자(L<33)/미드톤/
    하이라이트(L>66) 셋으로 나눠 구간별 평균 ΔE를 계산. 존별 표본이
    없으면 해당 구간은 None."""
    lab_a = _to_lab(rgb_a_linear).reshape(-1, 3)
    lab_b = _to_lab(rgb_b_linear).reshape(-1, 3)
    d = np.asarray(colour.delta_E(lab_a, lab_b, method=method))
    L = lab_a[:, 0]

    zones = {
        "shadow": L < 33,
        "midtone": (L >= 33) & (L <= 66),
        "highlight": L > 66,
    }
    return {name: (float(np.mean(d[mask])) if np.any(mask) else None)
            for name, mask in zones.items()}


def saturation_hue_delta(rgb_a_linear, rgb_b_linear):
    """Lab a/b로 chroma(채도 프록시)와 hue 각도 차이를 계산.
    반환: 평균 |Δchroma|, 평균 |Δhue|(도 단위, wraparound 처리)."""
    lab_a = _to_lab(rgb_a_linear).reshape(-1, 3)
    lab_b = _to_lab(rgb_b_linear).reshape(-1, 3)

    chroma_a = np.hypot(lab_a[:, 1], lab_a[:, 2])
    chroma_b = np.hypot(lab_b[:, 1], lab_b[:, 2])
    mean_abs_dchroma = float(np.mean(np.abs(chroma_a - chroma_b)))

    hue_a = np.degrees(np.arctan2(lab_a[:, 2], lab_a[:, 1]))
    hue_b = np.degrees(np.arctan2(lab_b[:, 2], lab_b[:, 1]))
    dhue = np.abs(hue_a - hue_b)
    dhue = np.minimum(dhue, 360.0 - dhue)  # wraparound(0도=360도)
    # 채도가 거의 없는 픽셀(무채색 근처)은 hue가 노이즈라 큰 가중치를 주면
    # 안 됨 - chroma로 가중평균
    weight = np.clip((chroma_a + chroma_b) / 2.0, 1e-6, None)
    mean_abs_dhue = float(np.average(dhue, weights=weight))

    return {"mean_abs_dchroma": mean_abs_dchroma, "mean_abs_dhue_deg": mean_abs_dhue}


def ssim_L(rgb_a_linear, rgb_b_linear):
    """L채널(지각 균등 명도) 기준 SSIM - 색이 아니라 대비/계조 보존
    여부를 본다. skimage 없이 표준 11x11 가우시안 윈도우 공식을 직접
    구현(skimage.metrics.structural_similarity와 동일 정의)."""
    L_a = _to_lab(rgb_a_linear)[..., 0].astype(np.float64)
    L_b = _to_lab(rgb_b_linear)[..., 0].astype(np.float64)

    data_range = 100.0  # L*는 [0, 100]
    c1 = (0.01 * data_range) ** 2
    c2 = (0.03 * data_range) ** 2

    kernel_1d = cv2.getGaussianKernel(11, 1.5)
    window = kernel_1d @ kernel_1d.T

    mu_a = cv2.filter2D(L_a, -1, window)
    mu_b = cv2.filter2D(L_b, -1, window)
    mu_a_sq, mu_b_sq, mu_ab = mu_a ** 2, mu_b ** 2, mu_a * mu_b

    sigma_a_sq = cv2.filter2D(L_a ** 2, -1, window) - mu_a_sq
    sigma_b_sq = cv2.filter2D(L_b ** 2, -1, window) - mu_b_sq
    sigma_ab = cv2.filter2D(L_a * L_b, -1, window) - mu_ab

    ssim_map = ((2 * mu_ab + c1) * (2 * sigma_ab + c2)) / \
               ((mu_a_sq + mu_b_sq + c1) * (sigma_a_sq + sigma_b_sq + c2))
    return float(np.mean(ssim_map))


def full_report(rgb_a_linear, rgb_b_linear):
    """리포트용 지표 전부를 한 번에 계산해서 dict로 반환."""
    return {
        "delta_e": delta_e_stats(rgb_a_linear, rgb_b_linear),
        "delta_e_by_zone": delta_e_by_zone(rgb_a_linear, rgb_b_linear),
        "saturation_hue": saturation_hue_delta(rgb_a_linear, rgb_b_linear),
        "ssim_L": ssim_L(rgb_a_linear, rgb_b_linear),
    }
