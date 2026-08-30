"""
apply_hncs_x2dii()의 clahe_clip=1.25는 brands/hasselblad.py(main)의
기본값을 그대로 물려받은 것으로, X2D II 전용 그리드서치
(tools/evaluate_x2dii_de00_grid.py)가 exposure_gamma/toe_lift/
shoulder_start/white_point 4개만 훑고 clahe_clip은 한 번도 변수로
넣은 적이 없었다(사용자 지적). shoulder_start=0.58도 같은 그리드에서
확정된 값이라, clahe_clip과 상호작용이 있는지 shoulder_start와 함께
다시 훑어본다 - exposure_gamma=0.6/toe_lift=0.02/white_point=0.95는
이미 별도로 견고하게 검증된 값이라 고정.

`/Users/songjiun/Documents/raw pair`(evaluate_x2dii_de00_grid.py가 쓰던
경로)가 이번 세션엔 로컬에 없어서(옮겨진 `~/local-work`에도 없음),
같은 manifest(datasets/hasselblad/dpreview_raw_jpeg_pairs_clean.csv)의
124개 파일이 전부 datasets/hasselblad/contributed/*/raw|jpeg/에 이미
있는 걸 확인하고 그쪽에서 읽는다(중복 세트 dedup은 여기선 무관 -
manifest 자체가 이미 브랜드 쪽에서 정리된 124개 페어).

  python3 -m tools.evaluate_x2dii_clahe_shoulder_grid
"""
import csv
import math
import os
import sys

import colour
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brands.hasselblad import apply_hncs
from brands.hasselblad_x2dii import apply_hncs_x2dii
from tools.calibrate import load_neutral_render

CONTRIB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "datasets", "hasselblad", "contributed")
MANIFEST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "datasets", "hasselblad", "dpreview_raw_jpeg_pairs_clean.csv")

GRID_MAX_DIM = 200
CONFIRM_MAX_DIM = 400  # 200px 선택 -> 400px 확정의 기존 2단계 패턴(X1D-50c 등)과 동일 -
                       # 3000px는 70쌍x2해상도 디코드+140회 고해상도 CLAHE라 너무 느려서
                       # (10분+에도 3000px confirm 단계 진행 안 됨) 이번엔 400으로 낮춤,
                       # 원본 픽셀 최종 재확인은 채택 콤보 1개만 나중에 별도로

_GS_SHOULDER_STARTS = (0.50, 0.58, 0.66, 0.70, 0.74, 0.78, 0.82)  # tools/calibrate.py 기존 그리드 재사용
_GS_CLAHE_CLIPS = (0.5, 1.0, 1.25, 1.5, 2.0, 3.0)


def _build_filename_index():
    index = {}
    for base, _dirs, files in os.walk(CONTRIB_DIR):
        for f in files:
            index.setdefault(f, os.path.join(base, f))
    return index


def load_target_linear(jpg_path, shape_hw):
    bgr = cv2.imread(jpg_path)
    bgr = cv2.resize(bgr, (shape_hw[1], shape_hw[0]), interpolation=cv2.INTER_AREA)
    rgb = bgr[:, :, ::-1].astype(np.float64) / 255.0
    return colour.cctf_decoding(rgb, function="sRGB")


def bgr_u8_to_linear(bgr_u8):
    rgb = bgr_u8[:, :, ::-1].astype(np.float64) / 255.0
    return colour.cctf_decoding(rgb, function="sRGB")


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


def main():
    rows = [r for r in csv.DictReader(open(MANIFEST)) if r['model'] == 'X2D II 100C']
    print(f"X2D II 페어 {len(rows)}개 (manifest 기준)", flush=True)

    index = _build_filename_index()
    pairs = []
    for i, r in enumerate(rows):
        raw_path = index.get(r['raw_file'])
        jpg_path = index.get(r['jpeg_file'])
        if not (raw_path and jpg_path):
            print(f"  [{i+1}/{len(rows)}] {r['raw_file']} 로컬에 없음, 스킵", flush=True)
            continue
        try:
            neutral_grid = load_neutral_render(raw_path, max_dim=GRID_MAX_DIM)
            neutral_confirm = load_neutral_render(raw_path, max_dim=CONFIRM_MAX_DIM)
        except Exception as e:
            print(f"  [{i+1}/{len(rows)}] {r['raw_file']} 디코드 실패: {e}", flush=True)
            continue
        target_grid = load_target_linear(jpg_path, neutral_grid.shape[:2])
        target_confirm = load_target_linear(jpg_path, neutral_confirm.shape[:2])
        pairs.append(dict(name=r['raw_file'], neutral_grid=neutral_grid, target_grid=target_grid,
                           neutral_confirm=neutral_confirm, target_confirm=target_confirm))
        print(f"  [{i+1}/{len(rows)}] {r['raw_file']} 등록", flush=True)

    n = len(pairs)
    print(f"\n사용 가능한 페어: {n}개", flush=True)

    combos = [(ss, cc) for ss in _GS_SHOULDER_STARTS for cc in _GS_CLAHE_CLIPS]
    print(f"\n{len(combos)}개 조합(shoulder_start x clahe_clip) x {n}쌍 - "
          f"ΔE00 행렬 계산중(저해상도, exposure_gamma=0.6/toe_lift=0.02/white_point=0.95 고정)...",
          flush=True)
    de00 = np.zeros((len(combos), n))
    for ci, (ss, cc) in enumerate(combos):
        for pi, p in enumerate(pairs):
            out = apply_hncs_x2dii(p['neutral_grid'], shoulder_start=ss, clahe_clip=cc)
            de00[ci, pi] = mean_delta_e(bgr_u8_to_linear(out), p['target_grid'])
        if ci % 10 == 0:
            print(f"  콤보 {ci}/{len(combos)}", flush=True)

    print(f"\n{CONFIRM_MAX_DIM}px에서 main/현재 apply_hncs_x2dii 기준선 계산중...", flush=True)
    main_des, current_x2dii_des = [], []
    for pi, p in enumerate(pairs):
        main_des.append(mean_delta_e(
            bgr_u8_to_linear(apply_hncs(p['neutral_confirm'])), p['target_confirm']))
        current_x2dii_des.append(mean_delta_e(
            bgr_u8_to_linear(apply_hncs_x2dii(p['neutral_confirm'])), p['target_confirm']))
        if pi % 10 == 0:
            print(f"  {pi}/{n}", flush=True)
    main_des = np.array(main_des)
    current_x2dii_des = np.array(current_x2dii_des)

    print(f"\n=== LOO 검증({n}폴드, 선택은 저해상도 / 평가는 {CONFIRM_MAX_DIM}px) ===", flush=True)
    loo_des = []
    chosen_counts = {}
    for i in range(n):
        train_mask = np.ones(n, dtype=bool)
        train_mask[i] = False
        best_ci = int(np.argmin(de00[:, train_mask].mean(axis=1)))
        chosen_counts[combos[best_ci]] = chosen_counts.get(combos[best_ci], 0) + 1
        ss, cc = combos[best_ci]
        out = apply_hncs_x2dii(pairs[i]['neutral_confirm'], shoulder_start=ss, clahe_clip=cc)
        de = mean_delta_e(bgr_u8_to_linear(out), pairs[i]['target_confirm'])
        loo_des.append(de)
        print(f"  [{i+1}/{n}] {pairs[i]['name']} ΔE00={de:.3f} "
              f"(현재 apply_hncs_x2dii={current_x2dii_des[i]:.3f}, main={main_des[i]:.3f})", flush=True)

    loo_des = np.array(loo_des)

    def _report(label, old, new):
        diff = old - new
        wins = int((diff > 0).sum())
        losses = int((diff < 0).sum())
        mean_old, mean_new = float(old.mean()), float(new.mean())
        improvement_pct = (mean_old - mean_new) / mean_old * 100.0
        rng = np.random.RandomState(0)
        boot = np.empty(20000)
        for i in range(20000):
            idx = rng.randint(0, n, n)
            boot[i] = diff[idx].mean()
        ci_lo, ci_hi = np.percentile(boot, [2.5, 97.5])
        p_value = _sign_test_p(wins, losses)
        print(f"\n=== {label} (n={n}) ===")
        print(f"평균 old={mean_old:.3f}  평균 new={mean_new:.3f}  개선폭={improvement_pct:+.2f}%")
        print(f"승/패={wins}/{losses}  부호검정 p={p_value:.4f}")
        print(f"부트스트랩 95% CI(평균차)=[{ci_lo:+.3f}, {ci_hi:+.3f}]")
        if ci_lo <= 0 <= ci_hi:
            print("판정: 보류 (CI가 0 포함)")
        else:
            print(f"판정: {'new 우세' if improvement_pct > 0 else 'old 우세'}")

    _report("LOO 그리드서치 vs apply_hncs(main)", main_des, loo_des)
    _report("LOO 그리드서치 vs 현재 apply_hncs_x2dii(shoulder_start=0.58, clahe_clip=1.25)",
            current_x2dii_des, loo_des)

    print("\n폴드별 선택 조합 상위:")
    for combo, cnt in sorted(chosen_counts.items(), key=lambda kv: -kv[1])[:8]:
        print(f"  {cnt:3d}/{n}  shoulder_start={combo[0]}, clahe_clip={combo[1]}")


if __name__ == "__main__":
    main()
