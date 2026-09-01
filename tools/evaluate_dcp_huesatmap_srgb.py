"""
`tools/evaluate_dcp_huesatmap.py`(Lab 평면 회전 근사)의 후속 - 실제
DNG `ProfileHueSatMapEncoding=1`이 명시하는 "sRGB 좌표계"에서 hue
테이블을 학습/적용해서 그 근사 격차를 메운다. `encoding=1`을 쓰는 이유:
Adobe의 내부 선형 참조공간(encoding=0)은 스펙 문서 없이 정확히
재현하기 어렵지만, sRGB(D65, IEC 61966-2-1 감마)는 이 프로젝트가 이미
`chart_baseline.detect_and_sample()`에서 쓰는 표준 변환이라 정확히
재현 가능 - `ProfileHueSatMapEncoding` 태그가 정확히 이 상황(프로필
저자가 익숙한 sRGB에서 작업하고 싶을 때)을 위해 존재한다.

파이프라인: 챠트 매트릭스로 native RGB -> XYZ(D50) -> Bradford D50->D65
색순응 -> sRGB 선형 -> sRGB 감마 인코딩 -> [0,1] 클립 -> HSV. Hue만
회전(S/V 불변), 다시 역변환해서 XYZ(D50)로 되돌려 표준 ΔE00으로 평가.
`tools/evaluate_dcp_huesatmap.py`와 같은 원형 가우시안 커널 히스토그램
방식, 같은 진짜 LOO(폴드마다 매트릭스도 재피팅) 방식을 그대로 씀.

  python3 -m tools.evaluate_dcp_huesatmap_srgb
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import colour
import numpy as np

from hybrid_engine.core import chart_baseline, raw_baseline
from hybrid_engine.utils.io import decode_raw_native
from tools.evaluate_dcp_irls_weighted import _irls_fit

SET_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "datasets", "hasselblad", "contributed", "kmichels-x2dii-2026-07")

D50 = colour.CCS_ILLUMINANTS["CIE 1931 2 Degree Standard Observer"]["D50"]
D65 = colour.CCS_ILLUMINANTS["CIE 1931 2 Degree Standard Observer"]["D65"]
_SRGB = colour.RGB_COLOURSPACES["sRGB"]

N_DIVISIONS = 8
KERNEL_SIGMA_DEG = 30.0


def _wrap_deg(x):
    return (x + 180.0) % 360.0 - 180.0


def _xyz_d50_to_srgb_gamma(xyz_d50):
    """(N,3) XYZ(D50) -> (N,3) sRGB 감마 인코딩, [0,1] 클립."""
    xyz_d65 = colour.chromatic_adaptation(
        xyz_d50, colour.xy_to_XYZ(D50), colour.xy_to_XYZ(D65),
        method="Von Kries", transform="Bradford")
    rgb_linear = colour.XYZ_to_RGB(xyz_d65, _SRGB, D65, apply_cctf_encoding=False)
    rgb_linear = np.clip(rgb_linear, 0.0, None)
    return np.clip(colour.cctf_encoding(rgb_linear, function="sRGB"), 0.0, 1.0)


def _srgb_gamma_to_xyz_d50(rgb_gamma):
    """역변환: sRGB 감마 [0,1] -> XYZ(D50)."""
    rgb_linear = colour.cctf_decoding(np.clip(rgb_gamma, 0.0, 1.0), function="sRGB")
    xyz_d65 = colour.RGB_to_XYZ(rgb_linear, _SRGB, D65, apply_cctf_decoding=False)
    return colour.chromatic_adaptation(
        xyz_d65, colour.xy_to_XYZ(D65), colour.xy_to_XYZ(D50),
        method="Von Kries", transform="Bradford")


def _rgb_to_hsv(rgb):
    """(N,3) [0,1] RGB -> H(도, 0-360)/S/V. numpy 벡터화, colorsys 안 씀."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    maxc = np.max(rgb, axis=-1)
    minc = np.min(rgb, axis=-1)
    v = maxc
    delta = maxc - minc
    s = np.where(maxc > 1e-8, delta / np.maximum(maxc, 1e-8), 0.0)

    h = np.zeros_like(maxc)
    is_r = (maxc == r) & (delta > 1e-8)
    is_g = (maxc == g) & (delta > 1e-8) & ~is_r
    is_b = (maxc == b) & (delta > 1e-8) & ~is_r & ~is_g
    h = np.where(is_r, ((g - b) / np.maximum(delta, 1e-8)) % 6.0, h)
    h = np.where(is_g, ((b - r) / np.maximum(delta, 1e-8)) + 2.0, h)
    h = np.where(is_b, ((r - g) / np.maximum(delta, 1e-8)) + 4.0, h)
    h = h * 60.0
    return h, s, v


def _hsv_to_rgb(h_deg, s, v):
    h = (h_deg % 360.0) / 60.0
    c = v * s
    x = c * (1 - np.abs(h % 2 - 1))
    m = v - c
    r = np.zeros_like(h)
    g = np.zeros_like(h)
    b = np.zeros_like(h)
    for lo, hi, rr, gg, bb in [
        (0, 1, c, x, 0), (1, 2, x, c, 0), (2, 3, 0, c, x),
        (3, 4, 0, x, c), (4, 5, x, 0, c), (5, 6, c, 0, x),
    ]:
        mask = (h >= lo) & (h < hi)
        r = np.where(mask, rr if np.isscalar(rr) else rr, r)
        g = np.where(mask, gg if np.isscalar(gg) else gg, g)
        b = np.where(mask, bb if np.isscalar(bb) else bb, b)
    return np.stack([r + m, g + m, b + m], axis=-1)


def _lab(xyz):
    return colour.XYZ_to_Lab(xyz, illuminant=D50)


def _delta_e00_lab(lab_a, lab_b):
    return np.asarray(colour.delta_E(lab_a, lab_b, method="CIE 2000"))


def _fit_hue_table(pred_hsv_list, ref_h, ref_s):
    all_pred_hue, all_shift = [], []
    for h, s, v in pred_hsv_list:
        for i in range(24):
            if ref_s[i] < 0.08:  # 무채색 패치는 hue 정의가 불안정
                continue
            all_pred_hue.append(h[i])
            all_shift.append(_wrap_deg(ref_h[i] - h[i]))
    all_pred_hue = np.array(all_pred_hue)
    all_shift = np.array(all_shift)

    centers = np.arange(N_DIVISIONS) * (360.0 / N_DIVISIONS)
    table = np.zeros(N_DIVISIONS)
    for i, c in enumerate(centers):
        d = np.abs(_wrap_deg(all_pred_hue - c))
        w = np.exp(-0.5 * (d / KERNEL_SIGMA_DEG) ** 2)
        table[i] = 0.0 if w.sum() < 1e-6 else np.average(all_shift, weights=w)
    return table


def _apply_hue_table(h, s, v, table):
    centers = np.arange(N_DIVISIONS) * (360.0 / N_DIVISIONS)
    idx = h / (360.0 / N_DIVISIONS)
    i0 = np.floor(idx).astype(int) % N_DIVISIONS
    i1 = (i0 + 1) % N_DIVISIONS
    frac = idx - np.floor(idx)
    shift0, shift1 = table[i0], table[i1]
    diff = shift1 - shift0
    diff = np.where(diff > 180, diff - 360, diff)
    diff = np.where(diff < -180, diff + 360, diff)
    shift = shift0 + frac * diff
    new_h = (h + shift) % 360.0
    return new_h, s, v


def main():
    reference = chart_baseline.reference_patches_xyz_d50()
    ref_rgb_gamma = _xyz_d50_to_srgb_gamma(reference)
    ref_h, ref_s, ref_v = _rgb_to_hsv(ref_rgb_gamma)
    ref_lab = _lab(reference)

    raw_paths = sorted(glob.glob(os.path.join(SET_DIR, "raw", "*.3FR")))
    per_image = {}
    for raw_path in raw_paths:
        name = os.path.basename(raw_path)
        print(f"  디코드+검출 중: {name}", flush=True)
        native = decode_raw_native(raw_path)
        samples = chart_baseline.detect_and_sample(native)
        if samples is None:
            continue
        per_image[name] = samples
    names = sorted(per_image.keys())
    print(f"\n검출 성공 {len(names)}장: {names}")

    init_weights = np.array([1.0 if i in range(18, 24) else 4.0 for i in range(24)])
    init_weights[17] = 2.0

    no_map_de, with_map_de = {}, {}
    for held_out in names:
        train_names = [nm for nm in names if nm != held_out]
        train_sources = [per_image[nm] for nm in train_names]
        _, fold_m = _irls_fit(train_sources, [reference] * len(train_names), init_weights)

        def _to_hsv(nm):
            xyz_pred = raw_baseline.apply_color_matrix(per_image[nm], fold_m)
            rgb_gamma = _xyz_d50_to_srgb_gamma(xyz_pred)
            return _rgb_to_hsv(rgb_gamma)

        held_h, held_s, held_v = _to_hsv(held_out)
        held_xyz_pred = raw_baseline.apply_color_matrix(per_image[held_out], fold_m)
        no_map_de[held_out] = float(np.mean(_delta_e00_lab(_lab(held_xyz_pred), ref_lab)))

        train_hsv = [_to_hsv(nm) for nm in train_names]
        table = _fit_hue_table(train_hsv, ref_h, ref_s)
        new_h, new_s, new_v = _apply_hue_table(held_h, held_s, held_v, table)
        corrected_rgb_gamma = _hsv_to_rgb(new_h, new_s, new_v)
        corrected_xyz = _srgb_gamma_to_xyz_d50(corrected_rgb_gamma)
        with_map_de[held_out] = float(np.mean(_delta_e00_lab(_lab(corrected_xyz), ref_lab)))

    no_mean = np.mean(list(no_map_de.values()))
    with_mean = np.mean(list(with_map_de.values()))
    print(f"\nhue map 없음(sRGB 경로, 진짜 LOO) LOO ΔE00 = {no_mean:.4f}")
    print(f"hue map 적용(sRGB HSV, {N_DIVISIONS}division, 진짜 LOO) LOO ΔE00 = {with_mean:.4f}")
    print(f"개선폭 = {(with_mean - no_mean) / no_mean * 100:+.2f}%")
    print("\n장별 비교:")
    for nm in names:
        print(f"  {nm}: 없음={no_map_de[nm]:.4f}  적용={with_map_de[nm]:.4f}  "
              f"차이={with_map_de[nm] - no_map_de[nm]:+.4f}")


if __name__ == "__main__":
    main()
