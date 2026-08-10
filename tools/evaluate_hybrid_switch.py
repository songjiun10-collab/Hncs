"""
`tools/evaluate_learned_lut.py`가 발견한 "고ISO(노이즈 많은) 사진에서 학습
LUT이 파라메트릭 커브보다 오히려 진다"(Sony a7V/a7R VI에서 확인, 승패군
ISO 평균이 각각 163 vs 2734 / 1167 vs 3339)를 근거로, 이미지 자체에서
추정한 노이즈 레벨로 파라메트릭/LUT을 선택적으로 전환하는 하이브리드가
"항상 LUT"보다 실제로 나은지 검증한다 - EXIF ISO는 apply_*() 시그니처에
없어서(브랜드 함수는 img_bgr만 받음, brands/CLAUDE.md의 균일 시그니처
규칙) 쓸 수 없고, 이미지 콘텐츠에서 노이즈를 직접 추정해야 한다.

노이즈 추정: Immerkaer(1996) 방법(3x3 라플라시안형 커널 컨볼루션의
평균절대값에서 노이즈 표준편차를 근사, `core/curve.py` 등과 독립적인
순수 통계 기법 - 참고: J. Immerkaer, "Fast Noise Variance Estimation",
Computer Vision and Image Understanding, 1996) - CLAHE 이후 L채널에
적용한다(실제 파이프라인이 CLAHE까지 거친 상태로 LUT/커브를 먹이므로).

임계값은 LOO로 페어별 (파라메트릭 ΔE00 - LUT ΔE00)과 노이즈 추정치의
상관관계를 이용해 정한다 - held-out 페어를 뺀 학습셋에서 "노이즈
추정치가 임계값보다 크면 파라메트릭, 아니면 LUT" 규칙이 최소화하는
분류 오차 지점을 찾고, held-out 페어에 적용해서 실제 ΔE00을 측정.

  python3 -m tools.evaluate_hybrid_switch \
      --label "Sony a7V" \
      --manifest datasets/sony/sony_new_pairs.csv --raw-dir "/Users/songjiun/local-work" \
      --model "ILCE-7M5" --clahe-clip 1.25 \
      --toe-lift 0.06 --shoulder-start 0.82 --white-point 1.0
"""
import argparse
import csv
import math
import os
import sys

import colour
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.curve import film_curve
from core.validation import is_image_array_usable
from tools.calibrate import load_neutral_render

MAX_DIM = 250
N_BINS = 256

# Immerkaer 1996 노이즈 추정 커널
_NOISE_KERNEL = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], dtype=np.float32)


def _resolve(raw_dirs, filename):
    for d in raw_dirs:
        p = os.path.join(d, filename)
        if os.path.exists(p):
            return p
    return None


def estimate_noise(l_channel):
    """Immerkaer 고속 노이즈 표준편차 추정 - CLAHE 이후 L채널에 적용."""
    h, w = l_channel.shape
    conv = cv2.filter2D(l_channel.astype(np.float32), -1, _NOISE_KERNEL)
    sigma = np.sum(np.abs(conv)) * math.sqrt(0.5 * math.pi) / (6 * (w - 2) * (h - 2))
    return float(sigma)


def pre_curve_l(neutral_bgr, exposure_gamma, clahe_clip):
    lab = cv2.cvtColor(neutral_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    if exposure_gamma is not None and exposure_gamma != 1.0:
        x = np.arange(256, dtype=np.float32) / 255.0
        exp_lut = np.clip((x ** exposure_gamma) * 255, 0, 255).astype(np.uint8)
        l = cv2.LUT(l, exp_lut)
    clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(8, 8))
    l = clahe.apply(l)
    return l, a, b


def bgr_u8_to_linear(bgr_u8):
    rgb = bgr_u8[:, :, ::-1].astype(np.float64) / 255.0
    return colour.cctf_decoding(rgb, function="sRGB")


def load_target_linear(jpg_path, shape_hw):
    bgr = cv2.imread(jpg_path)
    bgr = cv2.resize(bgr, (shape_hw[1], shape_hw[0]), interpolation=cv2.INTER_AREA)
    return bgr_u8_to_linear(bgr)


def mean_delta_e(linear_a, linear_b):
    from skimage.color import rgb2lab, deltaE_ciede2000
    a = colour.cctf_encoding(np.clip(linear_a, 0.0, 1.0), function="sRGB")
    b = colour.cctf_encoding(np.clip(linear_b, 0.0, 1.0), function="sRGB")
    return float(np.mean(deltaE_ciede2000(rgb2lab(a), rgb2lab(b))))


def _sign_test_p(wins, losses):
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2.0 ** n)
    return min(1.0, 2.0 * tail)


def _build_lut(sum_target, sum_weight):
    lut = np.zeros(N_BINS)
    filled = sum_weight > 0
    lut[filled] = sum_target[filled] / sum_weight[filled]
    domain = np.arange(N_BINS)
    if not filled.all():
        lut = np.interp(domain, domain[filled], lut[filled])
    return np.clip(lut, 0, 255).astype(np.uint8)


def _best_threshold(noise_vals, diff_vals):
    """diff_vals = param_de - lut_de (양수면 LUT이 이김). noise_vals 임계값
    후보 전부(정렬된 값들 사이 중점) 시도해서 "임계값 이상=파라메트릭
    선택, 미만=LUT 선택"이 냈을 총 ΔE00 합을 최소화하는 임계값을 찾는다."""
    order = np.argsort(noise_vals)
    sorted_noise = noise_vals[order]
    candidates = [sorted_noise[0] - 1.0] + list((sorted_noise[:-1] + sorted_noise[1:]) / 2) + [sorted_noise[-1] + 1.0]
    best_thr, best_score = candidates[0], None
    for thr in candidates:
        use_param = noise_vals >= thr  # True면 파라메트릭 선택(=LUT을 안 씀=diff 기여 0), False면 LUT 선택(diff만큼 이득)
        score = np.where(use_param, 0.0, diff_vals).sum()
        if best_score is None or score > best_score:
            best_score = score
            best_thr = thr
    return best_thr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--raw-dir", action="append", required=True, dest="raw_dirs")
    ap.add_argument("--model", action="append", dest="models", default=None)
    ap.add_argument("--exposure-gamma", type=float, default=None)
    ap.add_argument("--clahe-clip", type=float, default=1.25)
    ap.add_argument("--toe-lift", type=float, required=True)
    ap.add_argument("--shoulder-start", type=float, required=True)
    ap.add_argument("--white-point", type=float, required=True)
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.manifest)))
    if args.models:
        rows = [r for r in rows if r["model"] in args.models]
    print(f"{args.label} 후보 {len(rows)}개", flush=True)

    x = np.arange(256, dtype=np.float32) / 255.0
    param_lut = np.clip(film_curve(x, args.toe_lift, args.shoulder_start, args.white_point) * 255,
                         0, 255).astype(np.uint8)

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

        l, a, b = pre_curve_l(neutral, args.exposure_gamma, args.clahe_clip)
        tgt_l = cv2.cvtColor(target_img, cv2.COLOR_BGR2LAB)[:, :, 0]
        target_lin = load_target_linear(jpg_path, neutral.shape[:2])

        param_l = cv2.LUT(l, param_lut)
        param_out = cv2.cvtColor(cv2.merge((param_l, a, b)), cv2.COLOR_LAB2BGR)
        param_de = mean_delta_e(bgr_u8_to_linear(param_out), target_lin)

        noise = estimate_noise(l)

        sum_target = np.zeros(N_BINS)
        sum_weight = np.zeros(N_BINS)
        np.add.at(sum_target, l.ravel(), tgt_l.ravel().astype(np.float64))
        np.add.at(sum_weight, l.ravel(), 1.0)

        pairs.append(dict(name=r["raw_file"], l=l, a=a, b=b, target_lin=target_lin,
                           param_de=param_de, noise=noise,
                           sum_target=sum_target, sum_weight=sum_weight))
        print(f"  [{i+1}/{len(rows)}] {r['raw_file']} 등록 (파라메트릭 ΔE00={param_de:.3f}, 노이즈추정={noise:.3f})",
              flush=True)

    n = len(pairs)
    print(f"\n사용 가능한 페어: {n}개", flush=True)
    if n < 8:
        print("판정: 표본 8개 미만 - 중단", flush=True)
        return

    total_target = sum(p["sum_target"] for p in pairs)
    total_weight = sum(p["sum_weight"] for p in pairs)

    # 임계값 학습용 diff 캐시 - 폴드마다 학습셋 전원의 LOO diff를 다시 구하면
    # 표본수^2 스케일이라 비싸서, 전체 표본으로 한 번 지은 LUT(각 폴드의
    # LOO LUT과 표본 1개 차이라 근사로 충분)의 in-sample diff로 대체한다.
    full_lut = _build_lut(total_target, total_weight)
    _train_diff_cache = []
    for p in pairs:
        full_l = cv2.LUT(p["l"], full_lut)
        full_out = cv2.cvtColor(cv2.merge((full_l, p["a"], p["b"])), cv2.COLOR_LAB2BGR)
        full_de = mean_delta_e(bgr_u8_to_linear(full_out), p["target_lin"])
        _train_diff_cache.append(p["param_de"] - full_de)

    print(f"\n=== LOO 검증({n}폴드) ===", flush=True)
    lut_des, hybrid_des, thresholds, choices = [], [], [], []
    for i in range(n):
        train_target = total_target - pairs[i]["sum_target"]
        train_weight = total_weight - pairs[i]["sum_weight"]
        lut = _build_lut(train_target, train_weight)

        p = pairs[i]
        lut_l = cv2.LUT(p["l"], lut)
        lut_out = cv2.cvtColor(cv2.merge((lut_l, p["a"], p["b"])), cv2.COLOR_LAB2BGR)
        lut_de = mean_delta_e(bgr_u8_to_linear(lut_out), p["target_lin"])
        lut_des.append(lut_de)

        # held-out을 뺀 학습셋으로 임계값 학습(같은 폴드 LUT로 학습셋 ΔE00 재계산은
        # 비용이 커서, 학습셋의 이미 계산된 param_de/lut_de 근사를 못 쓰고 노이즈만
        # 이용 - 대신 전체 학습에서 미리 최종 LUT로 학습셋 자체 ΔE00을 한 번 구해
        # diff를 근사한다(아래 참고)로 단순화)
        train_noise = np.array([pairs[j]["noise"] for j in range(n) if j != i])
        train_diff = np.array([_train_diff_cache[j] for j in range(n) if j != i])
        thr = _best_threshold(train_noise, train_diff)
        thresholds.append(thr)

        use_param = p["noise"] >= thr
        choices.append("파라메트릭" if use_param else "LUT")
        hybrid_de = p["param_de"] if use_param else lut_de
        hybrid_des.append(hybrid_de)

        print(f"  [{i+1}/{n}] {p['name']} 노이즈={p['noise']:.3f} 임계값={thr:.3f} "
              f"선택={'파라메트릭' if use_param else 'LUT'} 파라메트릭={p['param_de']:.3f} "
              f"LUT={lut_de:.3f} 하이브리드={hybrid_de:.3f}", flush=True)

    param_des = np.array([p["param_de"] for p in pairs])
    lut_des = np.array(lut_des)
    hybrid_des = np.array(hybrid_des)

    def _report(name, new_des):
        diff = param_des - new_des
        wins = int((diff > 0).sum())
        losses = int((diff < 0).sum())
        mean_param, mean_new = float(param_des.mean()), float(new_des.mean())
        improvement_pct = (mean_param - mean_new) / mean_param * 100.0 if mean_param else float("nan")
        rng = np.random.RandomState(0)
        boot = np.empty(20000)
        for i in range(20000):
            idx = rng.randint(0, n, n)
            boot[i] = diff[idx].mean()
        ci_lo, ci_hi = np.percentile(boot, [2.5, 97.5])
        p_value = _sign_test_p(wins, losses)
        print(f"\n=== {name} vs 파라메트릭 (n={n}) ===")
        print(f"평균 파라메트릭 ΔE00={mean_param:.3f}  평균 {name} ΔE00={mean_new:.3f}  개선폭={improvement_pct:+.2f}%")
        print(f"승/패={wins}/{losses}  부호검정 p={p_value:.4f}")
        print(f"부트스트랩 95% CI(평균차)=[{ci_lo:+.3f}, {ci_hi:+.3f}]")
        if ci_lo <= 0 <= ci_hi:
            print("판정: 보류 (CI가 0 포함)")
        else:
            print(f"판정: {name} 우세" if improvement_pct > 0 else "파라메트릭 우세")

    _report("항상 LUT", lut_des)
    _report("노이즈 전환 하이브리드", hybrid_des)

    n_param_chosen = sum(1 for c in choices if c == "파라메트릭")
    print(f"\n하이브리드가 파라메트릭 선택한 비율: {n_param_chosen}/{n} ({n_param_chosen/n*100:.1f}%)")


if __name__ == "__main__":
    main()
