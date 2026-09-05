"""
`tools/evaluate_dcp_huesatmap_srgb.py`(hue만 회전, S/V 불변)의 후속 -
DNG HueSatMap이 실제로 담을 수 있는 **세 값 전부**(hueShift, satScale,
valScale)를 학습해서 LOO ΔE00이 어디까지 내려가는지 잰다.

**동기**: 사용자 질문 "1점대는 안되?"(2026-09-04). 현행 챠트 매트릭스의
진짜 LOO ΔE00은 2.5942이고, hue-only HueSatMap은 2.4651(-4.98%)까지만
내렸다. 1점대(<2.0)에 닿으려면 -23% 이상이 필요하니 hue 자유도만으로는
구조적으로 부족하다 - S/V 자유도를 열면 어디까지 가는지가 질문이다.

**방법**: `tools/evaluate_dcp_huesatmap_srgb.py`와 동일한 sRGB
(`ProfileHueSatMapEncoding=1`) HSV 좌표계, 동일한 원형 가우시안 커널
히스토그램, 동일한 진짜 LOO(폴드마다 3x3 매트릭스도 재피팅). 달라진 건
hue division마다 학습하는 값이 1개(hue shift)에서 3개(hue shift,
sat scale, val scale)로 늘어난 것뿐이다. sat/val은 비율이므로 로그
공간에서 가중평균한 뒤 되돌린다(곱셈 보정의 자연스러운 평균).

형제 `evaluate_*.py`를 import하지 않고 헬퍼를 복사했다 -
`tools/CLAUDE.md`의 "copy, don't couple" 컨벤션.

**통계**: 기존 HueSatMap 실험들은 부트스트랩 CI 없이 평균만 봤다. 여기서는
이미지 9장이 페어드 표본이므로 `summarize()`(페어드 부호검정 + 부트스트랩
95% CI 20000회, 고정 시드)를 그대로 복사해 붙였다 - `hybrid_engine/CLAUDE.md`
의 "평균 차이로 승자를 부르지 않는다" 규칙. n=9라 검정력이 낮다는 것 자체가
결과의 일부다.

**과적합 점검**: division 수를 4~24로 스윕한다. hue-only Lab 근사판이
자유도를 늘릴수록 개선폭이 계속 커져서(과적합 패턴) 기각됐던 전례가
있으므로(`hybrid_engine/EVALUATION.md` 2026-09-01절), 포화하는지 계속
커지는지를 같이 본다.

**배포 아님**: 배포된 `hybrid_engine/assets/profiles/hasselblad_x2dii_chart.dcp`
는 Never-list다. 이 스크립트는 측정만 하고 어떤 프로필도 쓰지 않는다.

  ~/.hncs-hybrid-venv312/bin/python3 -m tools.evaluate_dcp_huesatmap_full_srgb
"""
import glob
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import colour
import numpy as np

from hybrid_engine.core import chart_baseline, raw_baseline
from hybrid_engine.utils.io import decode_raw_native
from tools.evaluate_dcp_irls_weighted import _irls_fit

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SET_DIR = os.path.join(BASE, "datasets", "hasselblad", "contributed",
                       "kmichels-x2dii-2026-07")
OUT_REPORT = os.path.join(SET_DIR, "huesatmap_full_srgb_loo_report.json")

D50 = colour.CCS_ILLUMINANTS["CIE 1931 2 Degree Standard Observer"]["D50"]
D65 = colour.CCS_ILLUMINANTS["CIE 1931 2 Degree Standard Observer"]["D65"]
_SRGB = colour.RGB_COLOURSPACES["sRGB"]

KERNEL_SIGMA_DEG = 30.0
DIVISION_SWEEP = [4, 8, 12, 16, 24]
NEUTRAL_S_CUTOFF = 0.08  # 무채색 패치는 hue가 불안정 - hue 학습에서 제외


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
    rgb_linear = colour.cctf_decoding(np.clip(rgb_gamma, 0.0, 1.0), function="sRGB")
    xyz_d65 = colour.RGB_to_XYZ(rgb_linear, _SRGB, D65, apply_cctf_decoding=False)
    return colour.chromatic_adaptation(
        xyz_d65, colour.xy_to_XYZ(D65), colour.xy_to_XYZ(D50),
        method="Von Kries", transform="Bradford")


def _rgb_to_hsv(rgb):
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
    return h * 60.0, s, v


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


def _sign_test_p(wins, losses):
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2.0 ** n)
    return min(1.0, 2.0 * tail)


def summarize(label_a, des_a, label_b, des_b, n_bootstrap=20000, seed=0):
    """페어드 비교 - des_b가 des_a보다 작으면(=더 좋으면) 양수 improvement.
    `hybrid_engine/calibrate_profile_leica.py`의 summarize()와 같은 통계
    (부트스트랩 CI + 부호검정) - 형제 스크립트를 import하지 않는 컨벤션이라
    복붙(`hybrid_engine/CLAUDE.md`)."""
    a = np.asarray(des_a, dtype=np.float64)
    b = np.asarray(des_b, dtype=np.float64)
    n = len(a)
    diff = a - b
    mean_a, mean_b = float(a.mean()), float(b.mean())
    improvement_pct = (mean_a - mean_b) / mean_a * 100.0 if mean_a else float("nan")
    wins = int((diff > 0).sum())
    losses = int((diff < 0).sum())

    rng = np.random.default_rng(seed)
    boot = np.empty(n_bootstrap)
    for i in range(n_bootstrap):
        idx = rng.integers(0, n, n)
        boot[i] = diff[idx].mean()
    ci_lo, ci_hi = (float(v) for v in np.percentile(boot, [2.5, 97.5]))
    p_value = _sign_test_p(wins, losses)
    inconclusive = ci_lo <= 0.0 <= ci_hi

    print(f"\n=== {label_a} vs {label_b} (n={n}) ===")
    print(f"평균 {label_a} ΔE00={mean_a:.4f}  평균 {label_b} ΔE00={mean_b:.4f}  "
          f"{label_b} 개선폭={improvement_pct:+.2f}%")
    print(f"승({label_b} 더 좋음)/패={wins}/{losses}  부호검정 p={p_value:.4f}")
    print(f"부트스트랩 95% CI(평균차)=[{ci_lo:+.4f}, {ci_hi:+.4f}]")
    if inconclusive:
        print("판정: 보류 (CI가 0 포함)")
    elif improvement_pct > 0:
        print(f"판정: {label_b} 우세")
    else:
        print(f"판정: {label_a} 우세")
    return dict(mean_a=mean_a, mean_b=mean_b, improvement_pct=improvement_pct,
                wins=wins, losses=losses, p_value=p_value,
                ci_lo=ci_lo, ci_hi=ci_hi, inconclusive=bool(inconclusive))


def _fit_tables(pred_hsv_list, ref_h, ref_s, ref_v, n_divisions):
    """학습 이미지들에서 division별 (hue shift 도, sat scale, val scale)을
    원형 가우시안 커널 가중평균으로 학습. sat/val은 비율이라 로그공간에서
    평균낸 뒤 exp로 되돌린다. (3, n_divisions) 반환."""
    hue_at, hue_shift = [], []
    ratio_at, log_sat, log_val = [], [], []
    for h, s, v in pred_hsv_list:
        for i in range(24):
            if ref_s[i] >= NEUTRAL_S_CUTOFF:
                hue_at.append(h[i])
                hue_shift.append(_wrap_deg(ref_h[i] - h[i]))
            # sat/val 비율은 무채색 패치에서도 의미가 있다(회색축 밝기 보정).
            # 다만 0 나눗셈을 피하려고 하한을 둔다.
            if s[i] > 1e-3 and v[i] > 1e-3:
                ratio_at.append(h[i])
                log_sat.append(math.log(max(ref_s[i], 1e-3) / s[i]))
                log_val.append(math.log(max(ref_v[i], 1e-3) / v[i]))

    hue_at = np.asarray(hue_at)
    hue_shift = np.asarray(hue_shift)
    ratio_at = np.asarray(ratio_at)
    log_sat = np.asarray(log_sat)
    log_val = np.asarray(log_val)

    centers = np.arange(n_divisions) * (360.0 / n_divisions)
    tables = np.zeros((3, n_divisions))
    tables[1, :] = 1.0
    tables[2, :] = 1.0
    for i, c in enumerate(centers):
        if hue_at.size:
            w = np.exp(-0.5 * (np.abs(_wrap_deg(hue_at - c)) / KERNEL_SIGMA_DEG) ** 2)
            if w.sum() > 1e-6:
                tables[0, i] = np.average(hue_shift, weights=w)
        if ratio_at.size:
            w = np.exp(-0.5 * (np.abs(_wrap_deg(ratio_at - c)) / KERNEL_SIGMA_DEG) ** 2)
            if w.sum() > 1e-6:
                tables[1, i] = math.exp(np.average(log_sat, weights=w))
                tables[2, i] = math.exp(np.average(log_val, weights=w))
    return tables


def _interp_division(h, table, n_divisions, circular_deg=False):
    """hue 위치 h(도)에서 division 테이블을 선형보간. circular_deg면 각도
    wrap을 고려해 보간한다."""
    idx = h / (360.0 / n_divisions)
    i0 = np.floor(idx).astype(int) % n_divisions
    i1 = (i0 + 1) % n_divisions
    frac = idx - np.floor(idx)
    v0, v1 = table[i0], table[i1]
    diff = v1 - v0
    if circular_deg:
        diff = np.where(diff > 180, diff - 360, diff)
        diff = np.where(diff < -180, diff + 360, diff)
    return v0 + frac * diff


def _apply_tables(h, s, v, tables, n_divisions, use_sat, use_val):
    new_h = (h + _interp_division(h, tables[0], n_divisions, circular_deg=True)) % 360.0
    new_s = s
    new_v = v
    if use_sat:
        new_s = np.clip(s * _interp_division(h, tables[1], n_divisions), 0.0, 1.0)
    if use_val:
        new_v = np.clip(v * _interp_division(h, tables[2], n_divisions), 0.0, 1.0)
    return new_h, new_s, new_v


def _load_samples():
    per_image = {}
    for raw_path in sorted(glob.glob(os.path.join(SET_DIR, "raw", "*.3FR"))):
        name = os.path.basename(raw_path)
        print(f"  디코드+검출 중: {name}", flush=True)
        samples = chart_baseline.detect_and_sample(decode_raw_native(raw_path))
        if samples is not None:
            per_image[name] = samples
    return per_image


def _loo(per_image, reference, ref_lab, ref_hsv, n_divisions, use_sat, use_val):
    """진짜 LOO - 폴드마다 3x3 매트릭스도 held-out 없이 재피팅한다."""
    ref_h, ref_s, ref_v = ref_hsv
    names = sorted(per_image.keys())
    init_weights = np.array([1.0 if i in range(18, 24) else 4.0 for i in range(24)])
    init_weights[17] = 2.0

    no_map, with_map = [], []
    for held_out in names:
        train_names = [nm for nm in names if nm != held_out]
        _, fold_m = _irls_fit([per_image[nm] for nm in train_names],
                              [reference] * len(train_names), init_weights)

        def _to_hsv(nm):
            return _rgb_to_hsv(_xyz_d50_to_srgb_gamma(
                raw_baseline.apply_color_matrix(per_image[nm], fold_m)))

        held_xyz = raw_baseline.apply_color_matrix(per_image[held_out], fold_m)
        no_map.append(float(np.mean(_delta_e00_lab(_lab(held_xyz), ref_lab))))

        tables = _fit_tables([_to_hsv(nm) for nm in train_names],
                             ref_h, ref_s, ref_v, n_divisions)
        h, s, v = _to_hsv(held_out)
        corrected = _srgb_gamma_to_xyz_d50(_hsv_to_rgb(
            *_apply_tables(h, s, v, tables, n_divisions, use_sat, use_val)))
        with_map.append(float(np.mean(_delta_e00_lab(_lab(corrected), ref_lab))))
    return names, np.array(no_map), np.array(with_map)


def main():
    reference = chart_baseline.reference_patches_xyz_d50()
    ref_hsv = _rgb_to_hsv(_xyz_d50_to_srgb_gamma(reference))
    ref_lab = _lab(reference)

    per_image = _load_samples()
    print(f"\n검출 성공 {len(per_image)}장\n")
    if len(per_image) < 3:
        raise SystemExit("표본 부족")

    variants = [("hue만", False, False),
                ("hue+sat", True, False),
                ("hue+sat+val", True, True)]

    # 평균만 보면 val까지 연 변형이 제일 좋아 보이는데 그게 실제로 성립하는지는
    # CI가 갈라놓는다 - 그래서 최적 하나가 아니라 15조합 전부에 페어드 통계를
    # 붙인다(`hybrid_engine/CLAUDE.md`: 평균 차이로 승자를 부르지 않는다).
    results = []
    for n_div in DIVISION_SWEEP:
        for label, use_sat, use_val in variants:
            names, no_map, with_map = _loo(
                per_image, reference, ref_lab, ref_hsv, n_div, use_sat, use_val)
            pct = (no_map.mean() - with_map.mean()) / no_map.mean() * 100.0
            stats = summarize("매트릭스만", no_map,
                              f"HueSatMap(N={n_div},{label})", with_map)
            print(f"N={n_div:2d} {label:12s}  매트릭스만 {no_map.mean():.4f} -> "
                  f"{with_map.mean():.4f} ({pct:+.2f}%)  "
                  f"{'판정보류(CI가 0 포함)' if stats['inconclusive'] else '유의'}",
                  flush=True)
            results.append(dict(n_divisions=n_div, variant=label,
                                matrix_only_loo=float(no_map.mean()),
                                with_map_loo=float(with_map.mean()),
                                improvement_pct=float(pct),
                                paired_stats=stats,
                                per_image_matrix_only=no_map.tolist(),
                                per_image_with_map=with_map.tolist(),
                                images=names))

    best_mean = min(results, key=lambda r: r["with_map_loo"])
    established = [r for r in results if not r["paired_stats"]["inconclusive"]
                   and r["improvement_pct"] > 0]
    best_established = (min(established, key=lambda r: r["with_map_loo"])
                        if established else None)

    print(f"\n평균 최저: N={best_mean['n_divisions']} {best_mean['variant']} -> "
          f"{best_mean['with_map_loo']:.4f} "
          f"({'판정보류' if best_mean['paired_stats']['inconclusive'] else '유의'})")
    if best_established:
        s = best_established["paired_stats"]
        print(f"통계적으로 성립하는 최저: N={best_established['n_divisions']} "
              f"{best_established['variant']} -> {best_established['with_map_loo']:.4f} "
              f"(승/패={s['wins']}/{s['losses']}, CI=[{s['ci_lo']:+.4f},{s['ci_hi']:+.4f}])")
    else:
        print("통계적으로 성립하는 개선 없음 - 전부 CI가 0을 포함한다")

    floor = (best_established or best_mean)["with_map_loo"]
    reached_1 = floor < 2.0
    print(f"\n1점대(<2.0) 도달: {'예' if reached_1 else '아니오'} (최저 {floor:.4f})")

    report = {
        "question": "사용자 2026-09-04 '1점대는 안되?' - HueSatMap 3값 전부를 "
                    "열면 챠트 LOO ΔE00이 2.0 아래로 내려가는가",
        "method": "sRGB(ProfileHueSatMapEncoding=1) HSV에서 hue division별 "
                  "(hueShift, satScale, valScale) 학습, 진짜 LOO(폴드마다 3x3 "
                  "매트릭스 재피팅), 원형 가우시안 커널 sigma=30도",
        "kernel_sigma_deg": KERNEL_SIGMA_DEG,
        "neutral_s_cutoff": NEUTRAL_S_CUTOFF,
        "n_images": len(per_image),
        "sweep": results,
        "best_by_mean": {k: v for k, v in best_mean.items()
                         if not k.startswith("per_image")},
        "best_statistically_established": (
            None if best_established is None
            else {k: v for k, v in best_established.items()
                  if not k.startswith("per_image")}),
        "reached_sub_2": bool(reached_1),
        "sub_2_floor_used": float(floor),
        "deployment": "배포 아님 - hasselblad_x2dii_chart.dcp는 Never-list, "
                      "이 스크립트는 어떤 프로필도 쓰지 않는다",
    }
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n리포트: {OUT_REPORT}")


if __name__ == "__main__":
    main()
