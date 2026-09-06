"""배포된 룩 LUT을 굽는 방식 두 가지를 held-out 실사진에서 비교한다.

**왜**: `hybrid_engine/assets/profiles/capture_one_look_iccs_report.json`은
발급된 52장 중 **30장이 `faithful=false`** 라고 기록한다 - LUT 경유 결과와
룩 직접 호출 결과의 차이가 그 룩이 만드는 효과보다 크다는 뜻이다. 리포트는
이걸 "CLAHE 등 적응형 연산은 점별 LUT에 담을 수 없다"는 포맷의 구조적
한계로 설명한다. 한계 자체는 사실이지만, 현재 굽는 방식이 그 한계 안에서
최선인지는 측정된 적이 없다.

**현재 방식**(`core.lut_export.bake_lut_from_function`): 33^3 격자를
1089x33짜리 합성 "이미지" 하나로 펴서 룩에 통과시킨다. CLAHE 입장에서 이
합성 이미지의 이웃 픽셀 분포는 무지개 격자이고, 실사진의 이웃 분포와
아무 관계가 없다. 즉 적응형 성분이 **임의의** 값으로 구워진다.

**비교 대상**: 같은 격자를 학습 사진의 조건부 평균으로 채운다. 점별 함수로
공간 적응형 연산자를 근사할 때 MSE를 최소화하는 것은 입력값이 주어졌을 때의
출력 기대값이므로, 실사진 분포에서 추정한 조건부 평균이 그 분포에 대한
점별 최적이다. 여기서는 각 픽셀의 출력을 삼선형 가중치로 이웃 8개 격자점에
splat해서 누적하고 가중치 합으로 나눈다(정규방정식의 대각 근사 - 정확한
최소제곱해가 아니라 그 근사임을 밝혀둔다). 학습 사진이 닿지 않은 격자점은
현재 방식의 값을 그대로 둔다.

**평가**: 학습에 쓰지 않은 held-out 사진에서, LUT 경유 결과와 룩 직접
호출 결과 사이의 ΔE00(CIEDE2000)을 잰다. 적용은 **삼선형 보간** - 캡처원/
포토샵이 실제로 하는 방식이다(기존 리포트의 `_measure_fidelity`는 64x64
난수 이미지에 **최근접** 보간이라 실사용과 두 겹으로 다르다).

**성공 기준(결과 보기 전에 고정)**: 룩별 held-out 평균 ΔE00을 페어드로
비교해서 부트스트랩 95% CI가 0을 제외하고 부호검정이 같은 방향일 때만
개선으로 판정한다. CI가 0을 걸치면 판정 보류다(`hybrid_engine/CLAUDE.md`).

**양성 대조**: CLAHE를 안 쓰는 순수 점별 룩에서는 두 방식이 같은 LUT에
수렴해야 한다(조건부 평균 = 그 점의 정확한 상). 차이가 0 근처로 나오는지
확인해서 측정 자체가 무의미한 잡음이 아님을 본다.

> **정정(2026-09-05, 첫 실행 결과로 확인)**: 위 양성 대조 예상은 틀렸다.
> 실제로는 점별 룩에서 두 방식 차이가 **더** 벌어진다(두 방식 차이를 룩
> 효과로 나눈 평균: CLAHE 미사용 25개 0.2513 vs CLAHE 사용 29개 0.0686).
> 삼선형 splat은 각 격자점에 이웃 색공간의 출력을 가중 평균해 넣으므로,
> 참 매핑이 정확히 점별인 곳에서도 평활 편향이 남는다 - 조건부 평균
> 자체는 MSE 최적이지만 splat 추정량은 그 평활된 근사다. 이 실험이 진
> 이유가 바로 이것이다(`hybrid_engine/EVALUATION.md` 같은 절).

**데이터**: `datasets/hasselblad/hasselblad_raw_jpeg_pairs.csv`의 공식 13장
JPEG(cdn.hasselblad.com, 공개 CDN). 이 실험은 raw가 필요 없다 - 비교
대상이 "룩 직접 호출"이지 카메라 JPEG이 아니기 때문이다.

  python3 -m tools.evaluate_lut_bake_conditional_mean <이미지폴더> <리포트.json>
"""
import json
import math
import os
import sys

import colour
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tests"))

from core.lut_export import bake_lut_from_function

LUT_SIZE = 33
# CLAHE의 지역 적응성은 해상도에 따라 달라진다. 두 방식을 같은 해상도에서
# 재므로 비교 자체는 공정하지만, 절대값은 이 해상도에 묶인 수치다.
WORK_MAX_DIM = 1024
N_TRAIN = 7  # 앞 7장 학습 / 나머지 held-out - 파일명 정렬 기준 고정 분할


def _load_images(folder):
    paths = sorted(os.path.join(folder, f) for f in os.listdir(folder)
                   if f.lower().endswith((".jpg", ".jpeg")))
    imgs = []
    for p in paths:
        img = cv2.imread(p)
        if img is None:
            raise RuntimeError(f"디코드 실패: {p}")
        h, w = img.shape[:2]
        scale = WORK_MAX_DIM / max(h, w)
        if scale < 1.0:
            img = cv2.resize(img, (int(round(w * scale)), int(round(h * scale))),
                             interpolation=cv2.INTER_AREA)
        imgs.append((os.path.basename(p), img))
    return imgs


def _to_linear(bgr_u8):
    rgb = np.clip(bgr_u8[:, :, ::-1].astype(np.float64) / 255.0, 0.0, 1.0)
    return colour.cctf_decoding(rgb, function="sRGB")


def _mean_delta_e(lin_a, lin_b):
    from skimage.color import deltaE_ciede2000, rgb2lab
    a = colour.cctf_encoding(np.clip(lin_a, 0.0, 1.0), function="sRGB")
    b = colour.cctf_encoding(np.clip(lin_b, 0.0, 1.0), function="sRGB")
    return float(np.mean(deltaE_ciede2000(rgb2lab(a), rgb2lab(b))))


def _sign_test_p(wins, losses):
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1))
    return min(1.0, 2.0 * tail / (2 ** n))


def _trilinear_weights(bgr_u8, size=LUT_SIZE):
    """입력 BGR uint8 픽셀들을 격자 좌표로 바꾸고, 이웃 8개 격자점의
    인덱스와 삼선형 가중치를 돌려준다. 격자 인덱스 규약은
    `core.lut_export.write_cube_file`과 같은 [b, g, r] 순서다."""
    x = bgr_u8.astype(np.float64).reshape(-1, 3) / 255.0 * (size - 1)
    lo = np.floor(x).astype(np.int64)
    lo = np.clip(lo, 0, size - 2)
    frac = x - lo
    corners = []
    for db in (0, 1):
        for dg in (0, 1):
            for dr in (0, 1):
                w = ((frac[:, 0] if db else 1.0 - frac[:, 0])
                     * (frac[:, 1] if dg else 1.0 - frac[:, 1])
                     * (frac[:, 2] if dr else 1.0 - frac[:, 2]))
                idx = ((lo[:, 0] + db) * size * size
                       + (lo[:, 1] + dg) * size
                       + (lo[:, 2] + dr))
                corners.append((idx, w))
    return corners


def apply_lut_trilinear(bgr_u8, lut, size=LUT_SIZE):
    """LUT을 삼선형 보간으로 적용해 BGR uint8을 돌려준다 - 캡처원/포토샵이
    실제로 하는 적용 방식."""
    flat_lut = lut.reshape(-1, 3)
    out = np.zeros((bgr_u8.size // 3, 3), dtype=np.float64)
    for idx, w in _trilinear_weights(bgr_u8, size):
        out += flat_lut[idx] * w[:, None]
    rgb = np.clip(out, 0.0, 1.0).reshape(bgr_u8.shape)
    return np.clip(rgb[:, :, ::-1] * 255.0 + 0.5, 0, 255).astype(np.uint8)


def bake_lut_conditional_mean(func, train_imgs, fallback_lut, size=LUT_SIZE):
    """학습 사진에서 입력색 -> 룩 출력색의 조건부 평균을 격자에 splat한다.
    닿지 않은 격자점은 fallback_lut(현재 방식) 값을 그대로 쓴다."""
    acc = np.zeros((size ** 3, 3), dtype=np.float64)
    wsum = np.zeros(size ** 3, dtype=np.float64)
    for _, img in train_imgs:
        out = func(img.copy())
        if out.ndim == 2:
            raise ValueError("그레이스케일 반환 룩은 3D LUT 대상이 아님")
        out_rgb = out[:, :, ::-1].astype(np.float64).reshape(-1, 3) / 255.0
        for idx, w in _trilinear_weights(img, size):
            np.add.at(acc, idx, out_rgb * w[:, None])
            np.add.at(wsum, idx, w)
    lut = fallback_lut.reshape(-1, 3).copy()
    hit = wsum > 1e-9
    lut[hit] = acc[hit] / wsum[hit, None]
    return lut.reshape(size, size, size, 3), int(hit.sum())


def _collect_looks():
    from test_brands import BRAND_LOOKS, FUJI_COLOR_PRESETS
    return list(BRAND_LOOKS) + [("brands.fuji", fn) for fn in FUJI_COLOR_PRESETS]


def summarize(per_look, n_bootstrap=20000, seed=0):
    """페어드 비교 - 각 행은 (name, value_a, value_b). value_a가 기준(현재
    방식), value_b가 비교 대상(조건부 평균)이고 ΔE는 낮을수록 좋다."""
    a = np.array([r[1] for r in per_look], dtype=np.float64)
    b = np.array([r[2] for r in per_look], dtype=np.float64)
    n = len(per_look)
    diff = a - b
    mean_a, mean_b = float(a.mean()), float(b.mean())
    improvement_pct = (mean_a - mean_b) / mean_a * 100.0
    wins, losses = int((diff > 0).sum()), int((diff < 0).sum())
    rng = np.random.default_rng(seed)
    boot = [float(diff[rng.integers(0, n, n)].mean()) for _ in range(n_bootstrap)]
    ci = tuple(float(v) for v in np.percentile(boot, [2.5, 97.5]))
    dropone = []
    for i in range(n):
        keep = np.ones(n, dtype=bool)
        keep[i] = False
        dropone.append(float((a[keep].mean() - b[keep].mean()) / a[keep].mean() * 100.0))
    inconclusive = ci[0] <= 0.0 <= ci[1]
    return {
        "n": n, "mean_a": mean_a, "mean_b": mean_b,
        "mean_diff": float(diff.mean()), "median_diff": float(np.median(diff)),
        "improvement_pct": improvement_pct,
        "b_wins": wins, "a_wins": losses,
        "sign_test_p": _sign_test_p(wins, losses),
        "ci_diff": ci,
        "dropone_pct_min": min(dropone), "dropone_pct_max": max(dropone),
        "inconclusive": inconclusive,
        "verdict": ("판정 보류 - 95% 부트스트랩 CI가 0을 포함"
                    if inconclusive else
                    ("조건부 평균이 이겼다" if improvement_pct > 0
                     else "현재 방식이 더 낫다")),
    }


def main():
    folder, out_path = sys.argv[1:3]
    imgs = _load_images(folder)
    train, test = imgs[:N_TRAIN], imgs[N_TRAIN:]
    print(f"이미지 {len(imgs)}장 (학습 {len(train)} / held-out {len(test)}), "
          f"작업 해상도 최대 {WORK_MAX_DIM}px")

    import importlib
    rows, per_look = [], []
    for module_name, func_name in _collect_looks():
        func = getattr(importlib.import_module(module_name), func_name)
        try:
            base_lut = bake_lut_from_function(func, size=LUT_SIZE)
        except ValueError as e:
            print(f"  건너뜀 {module_name}.{func_name}: {e}")
            continue
        cond_lut, n_hit = bake_lut_conditional_mean(func, train, base_lut)

        de_base, de_cond, effects = [], [], []
        for _, img in test:
            direct = func(img.copy())
            if direct.ndim == 2:
                break
            d_lin = _to_linear(direct)
            de_base.append(_mean_delta_e(_to_linear(apply_lut_trilinear(img, base_lut)), d_lin))
            de_cond.append(_mean_delta_e(_to_linear(apply_lut_trilinear(img, cond_lut)), d_lin))
            effects.append(_mean_delta_e(_to_linear(img), d_lin))
        if not de_base:
            print(f"  건너뜀 {module_name}.{func_name}: 그레이스케일 반환")
            continue

        m_base, m_cond, m_eff = (float(np.mean(de_base)), float(np.mean(de_cond)),
                                 float(np.mean(effects)))
        name = f"{module_name.split('.')[1]}.{func_name}"
        rows.append({"look": name, "delta_e00_base": m_base,
                     "delta_e00_conditional_mean": m_cond,
                     "look_effect_delta_e00": m_eff,
                     "grid_cells_hit": n_hit, "grid_cells_total": LUT_SIZE ** 3,
                     "faithful_base": m_base < m_eff,
                     "faithful_conditional_mean": m_cond < m_eff,
                     "per_test_image_base": de_base,
                     "per_test_image_conditional_mean": de_cond})
        per_look.append((name, m_base, m_cond))
        print(f"  {name:34s} 현재 {m_base:7.3f}  조건부평균 {m_cond:7.3f}  "
              f"효과 {m_eff:7.3f}  격자적중 {n_hit}/{LUT_SIZE**3}", flush=True)

    stats = summarize(per_look)
    faithful_base = sum(r["faithful_base"] for r in rows)
    faithful_cond = sum(r["faithful_conditional_mean"] for r in rows)
    report = {
        "purpose": "룩 LUT 굽는 방식 비교 - 현재(합성 격자) vs 조건부 평균(실사진)",
        "metric": "held-out 사진에서 LUT 경유 vs 룩 직접 호출의 평균 ΔE00 "
                  "(CIEDE2000, 삼선형 보간 적용)",
        "lut_size": LUT_SIZE, "work_max_dim": WORK_MAX_DIM,
        "n_train_images": len(train), "n_test_images": len(test),
        "train_images": [n for n, _ in train], "test_images": [n for n, _ in test],
        "n_looks": len(rows),
        "faithful_base": faithful_base,
        "faithful_conditional_mean": faithful_cond,
        "stats_paired_over_looks": stats,
        "looks": rows,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print()
    print(f"룩 {stats['n']}개 페어드 (held-out {len(test)}장 평균)")
    print(f"  현재 방식     평균 ΔE00 {stats['mean_a']:.4f}")
    print(f"  조건부 평균   평균 ΔE00 {stats['mean_b']:.4f}")
    print(f"  개선폭 {stats['improvement_pct']:.1f}%  "
          f"승패 {stats['b_wins']}승 {stats['a_wins']}패  "
          f"부호검정 p={stats['sign_test_p']:.4g}")
    print(f"  페어드 차이 평균 {stats['mean_diff']:+.4f} / 중앙값 {stats['median_diff']:+.4f}")
    print(f"  부트스트랩 95% CI [{stats['ci_diff'][0]:+.4f}, {stats['ci_diff'][1]:+.4f}]")
    print(f"  drop-one {stats['dropone_pct_min']:.1f}% ~ {stats['dropone_pct_max']:.1f}%")
    print(f"  판정: {stats['verdict']}")
    print(f"  오차<효과(faithful): 현재 {faithful_base}/{len(rows)} -> "
          f"조건부평균 {faithful_cond}/{len(rows)}")
    print(f"리포트: {out_path}")


if __name__ == "__main__":
    main()
