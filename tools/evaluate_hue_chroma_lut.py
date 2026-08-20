"""
Hue/채도(chroma) 보정 LUT 실험 - 이 세션에서 채택한 apply_*_look() 톤커브
함수들은 Lab L채널만 건드리고 a/b(hue+chroma)는 완전히 무조작인데(예:
apply_hncs()의 "채도/hue 무조작 (rich saturation은 '안 건드림'으로
달성)"), 톤커브 보정 후에도 hue/chroma에 잔차가 남는지, 남는다면
hybrid_engine/core/hue_core.py의 순환(circular) 1D LUT으로 더 줄일 수
있는지 검증한다.

hybrid_engine/calibrate_profile.py의 learn_hue_lut()/learn_hue_chroma_lut()
과 같은 알고리즘(hue는 chroma가중 순환평균, chroma는 에너지비율)을
그대로 재구현했다 - 원본은 HybridCameraEngine(profile 기반)에 강결합돼
있고 hybrid_engine/utils/evaluate.py가 이 환경의 colour-science 0.4.4에서
`intermediate_attributes_CIE2000` import 실패로 아예 안 돌아가서
(`ImportError` - 구버전 colour-science 전용 API가 이번 버전에서 사라짐,
hybrid_engine 쪽 별도 이슈), 이 세션의 apply_*_look() 함수 + skimage 기반
ΔE00 측정 스택에 맞게 독립적으로 새로 짰다. hue_core.py의
apply_hue_lut/apply_hue_chroma_lut(순수 numpy, colour-science 의존 없음)은
그대로 재사용.

LOO는 톤커브 그리드서치 때와 같은 방식(폴드마다 전체를 다시 안 돌고,
페어별로 미리 계산해둔 hue-bin 집계에서 held-out 페어의 기여분만 빼는
O(n) 뺄셈)으로 처리한다.

  python3 -m tools.evaluate_hue_chroma_lut \
      --label "X2D II 100C" \
      --manifest datasets/hasselblad/dpreview_raw_jpeg_pairs_clean.csv \
      --raw-dir "/Users/songjiun/local-work" \
      --model "X2D II 100C" \
      --tone-fn brands.hasselblad_x2dii.apply_hncs_x2dii
"""
import argparse
import csv
import importlib
import math
import os
import sys

import colour
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.validation import is_image_array_usable
from hybrid_engine.core.hue_core import apply_hue_chroma_lut, apply_hue_lut
from tools.calibrate import load_neutral_render

MAX_DIM = 250  # hue LUT 피팅은 페어당 픽셀 수가 많이 필요해서 톤커브
                # 그리드서치(200px)보다 살짝 크게, 그래도 메모리/속도 안전권
N_BINS = 36  # 10도 간격 - learn_hue_lut()과 동일


def _resolve(raw_dirs, filename):
    for d in raw_dirs:
        p = os.path.join(d, filename)
        if os.path.exists(p):
            return p
    return None


def bgr_u8_to_lab(bgr_u8):
    rgb = bgr_u8[:, :, ::-1].astype(np.float64) / 255.0
    linear = colour.cctf_decoding(rgb, function="sRGB")
    srgb = colour.cctf_encoding(np.clip(linear, 0.0, 1.0), function="sRGB")
    from skimage.color import rgb2lab
    return rgb2lab(srgb)


def mean_delta_e_lab(lab_a, lab_b):
    from skimage.color import deltaE_ciede2000
    return float(np.mean(deltaE_ciede2000(lab_a, lab_b)))


def _sign_test_p(wins, losses):
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2.0 ** n)
    return min(1.0, 2.0 * tail)


def _hue_chroma_bins(source_a, source_b, target_a, target_b):
    """한 페어의 (hue delta, chroma 비율) bin별 집계를 반환 - LOO에서
    페어별로 캐시해뒀다가 뺄셈만 하기 위함."""
    bin_width = 360.0 / N_BINS
    source_hue = np.degrees(np.arctan2(source_b, source_a)) % 360.0
    target_hue = np.degrees(np.arctan2(target_b, target_a)) % 360.0
    delta = (target_hue - source_hue + 180.0) % 360.0 - 180.0

    chroma_source = np.hypot(source_a, source_b)
    chroma_target = np.hypot(target_a, target_b)
    weight = np.clip((chroma_source + chroma_target) / 2.0, 0.0, None)

    bins = np.minimum((source_hue.ravel() / bin_width).astype(int), N_BINS - 1)
    w = weight.ravel()
    delta_rad = np.radians(delta.ravel())

    sum_re = np.zeros(N_BINS)
    sum_im = np.zeros(N_BINS)
    weight_sum = np.zeros(N_BINS)
    np.add.at(sum_re, bins, w * np.cos(delta_rad))
    np.add.at(sum_im, bins, w * np.sin(delta_rad))
    np.add.at(weight_sum, bins, w)

    sum_chroma_source = np.zeros(N_BINS)
    sum_chroma_target = np.zeros(N_BINS)
    np.add.at(sum_chroma_source, bins, chroma_source.ravel())
    np.add.at(sum_chroma_target, bins, chroma_target.ravel())

    return sum_re, sum_im, weight_sum, sum_chroma_source, sum_chroma_target


def _build_hue_lut(sum_re, sum_im, weight_sum):
    lut = np.zeros(N_BINS)
    filled = weight_sum > 1e-6
    lut[filled] = np.degrees(np.arctan2(sum_im[filled], sum_re[filled]))
    if filled.any() and not filled.all():
        bin_width = 360.0 / N_BINS
        centers = (np.arange(N_BINS) + 0.5) * bin_width
        src_centers, src_vals = centers[filled], lut[filled]
        domain = np.concatenate([src_centers - 360.0, src_centers, src_centers + 360.0])
        values = np.tile(src_vals, 3)
        order = np.argsort(domain)
        lut = np.interp(centers, domain[order], values[order])
    return lut


def _build_chroma_lut(sum_chroma_source, sum_chroma_target):
    lut = np.ones(N_BINS)
    filled = sum_chroma_source > 1e-6
    lut[filled] = sum_chroma_target[filled] / sum_chroma_source[filled]
    if filled.any() and not filled.all():
        bin_width = 360.0 / N_BINS
        centers = (np.arange(N_BINS) + 0.5) * bin_width
        src_centers, src_vals = centers[filled], lut[filled]
        domain = np.concatenate([src_centers - 360.0, src_centers, src_centers + 360.0])
        values = np.tile(src_vals, 3)
        order = np.argsort(domain)
        lut = np.interp(centers, domain[order], values[order])
    return lut


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--raw-dir", action="append", required=True, dest="raw_dirs")
    ap.add_argument("--model", action="append", dest="models", default=None)
    ap.add_argument("--film-mode", default=None,
                     help="fuji_new_pairs.csv 전용 film_mode 컬럼 필터(예: 'F0/Standard (Provia)')")
    ap.add_argument("--tone-fn", required=True, help="이미 채택된 톤커브 apply_* 함수 (module.path.fn)")
    args = ap.parse_args()

    mod_path, fn_name = args.tone_fn.rsplit(".", 1)
    tone_fn = getattr(importlib.import_module(mod_path), fn_name)

    rows = list(csv.DictReader(open(args.manifest)))
    if args.models:
        rows = [r for r in rows if r["model"] in args.models]
    if args.film_mode:
        rows = [r for r in rows if r.get("film_mode") == args.film_mode]
    print(f"{args.label} 후보 {len(rows)}개 (tone_fn={args.tone_fn})", flush=True)

    pairs = []
    for i, r in enumerate(rows):
        raw_path = _resolve(args.raw_dirs, r["raw_file"])
        jpg_path = _resolve(args.raw_dirs, r["jpeg_file"])
        if raw_path is None or jpg_path is None:
            continue
        try:
            neutral = load_neutral_render(raw_path, max_dim=MAX_DIM)
        except Exception as e:
            print(f"  [{i+1}/{len(rows)}] {r['raw_file']} 디코드 실패: {e}", flush=True)
            continue
        target_img = cv2.imread(jpg_path)
        if target_img is None or not is_image_array_usable(target_img):
            continue
        target_img = cv2.resize(target_img, (neutral.shape[1], neutral.shape[0]),
                                 interpolation=cv2.INTER_AREA)

        candidate = tone_fn(neutral)
        cand_lab = bgr_u8_to_lab(candidate)
        target_lab = bgr_u8_to_lab(target_img)

        baseline_de = mean_delta_e_lab(cand_lab, target_lab)
        agg = _hue_chroma_bins(cand_lab[..., 1], cand_lab[..., 2],
                                target_lab[..., 1], target_lab[..., 2])
        pairs.append(dict(name=r["raw_file"], cand_lab=cand_lab, target_lab=target_lab,
                           baseline_de=baseline_de, agg=agg))
        print(f"  [{i+1}/{len(rows)}] {r['raw_file']} 등록 (톤커브만 ΔE00={baseline_de:.3f})",
              flush=True)

    n = len(pairs)
    print(f"\n사용 가능한 페어: {n}개", flush=True)
    if n < 8:
        print("판정: 표본 8개 미만 - 통계적으로 의미 없음, 중단", flush=True)
        return

    # 전체 bin 집계 합 (LOO에서 held-out 페어분만 빼는 O(n) 방식)
    total = [np.zeros(N_BINS) for _ in range(5)]
    for p in pairs:
        for t, part in zip(total, p["agg"]):
            t += part

    baseline_des = np.array([p["baseline_de"] for p in pairs])

    print(f"\n=== LOO 검증({n}폴드) ===", flush=True)
    hue_only_des, hue_chroma_des = [], []
    for i in range(n):
        train_re = total[0] - pairs[i]["agg"][0]
        train_im = total[1] - pairs[i]["agg"][1]
        train_w = total[2] - pairs[i]["agg"][2]
        train_cs = total[3] - pairs[i]["agg"][3]
        train_ct = total[4] - pairs[i]["agg"][4]

        hue_lut = _build_hue_lut(train_re, train_im, train_w)
        chroma_lut = _build_chroma_lut(train_cs, train_ct)

        cand_a, cand_b = pairs[i]["cand_lab"][..., 1], pairs[i]["cand_lab"][..., 2]
        hue_a, hue_b = apply_hue_lut(cand_a, cand_b, hue_lut)
        hue_chroma_a, hue_chroma_b = apply_hue_chroma_lut(hue_a, hue_b, chroma_lut)

        lab_hue_only = pairs[i]["cand_lab"].copy()
        lab_hue_only[..., 1], lab_hue_only[..., 2] = hue_a, hue_b
        lab_hue_chroma = pairs[i]["cand_lab"].copy()
        lab_hue_chroma[..., 1], lab_hue_chroma[..., 2] = hue_chroma_a, hue_chroma_b

        de_hue = mean_delta_e_lab(lab_hue_only, pairs[i]["target_lab"])
        de_hue_chroma = mean_delta_e_lab(lab_hue_chroma, pairs[i]["target_lab"])
        hue_only_des.append(de_hue)
        hue_chroma_des.append(de_hue_chroma)
        print(f"  [{i+1}/{n}] {pairs[i]['name']} 톤커브만={pairs[i]['baseline_de']:.3f} "
              f"+hue={de_hue:.3f} +hue+chroma={de_hue_chroma:.3f}", flush=True)

    hue_only_des = np.array(hue_only_des)
    hue_chroma_des = np.array(hue_chroma_des)

    def _report(label, new_des):
        diff = baseline_des - new_des
        wins = int((diff > 0).sum())
        losses = int((diff < 0).sum())
        mean_base, mean_new = float(baseline_des.mean()), float(new_des.mean())
        improvement_pct = (mean_base - mean_new) / mean_base * 100.0 if mean_base else float("nan")
        rng = np.random.RandomState(0)
        boot = np.empty(20000)
        for i in range(20000):
            idx = rng.randint(0, n, n)
            boot[i] = diff[idx].mean()
        ci_lo, ci_hi = np.percentile(boot, [2.5, 97.5])
        p_value = _sign_test_p(wins, losses)
        print(f"\n=== {label} vs 톤커브만 (n={n}) ===")
        print(f"평균 톤커브만 ΔE00={mean_base:.3f}  평균 {label} ΔE00={mean_new:.3f}  개선폭={improvement_pct:+.2f}%")
        print(f"승/패={wins}/{losses}  부호검정 p={p_value:.4f}")
        print(f"부트스트랩 95% CI(평균차)=[{ci_lo:+.3f}, {ci_hi:+.3f}]")
        if ci_lo <= 0 <= ci_hi:
            print("판정: 보류 (CI가 0 포함)")
        else:
            print(f"판정: {'LOO hue LUT 우세' if improvement_pct > 0 else '톤커브만 우세'}")

    _report("+hue LUT", hue_only_des)
    _report("+hue+chroma LUT", hue_chroma_des)


if __name__ == "__main__":
    main()
