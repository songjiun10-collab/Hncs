"""
raw+jpeg 페어에서 톤커브를 직접 학습 (파라메트릭 커브 가정 없이)

RAW -> camera neutral decode -> [학습 대상] -> Hasselblad 타깃 JPEG

같은 raw에서 나온 중립 렌더링과 공식 JPEG은 같은 장면이라 픽셀 단위로
거의 대응됨. L채널끼리 (neutral_L, target_L) 쌍을 전부 모아서 neutral_L
값별로 target_L의 중앙값을 구하면, toe/shoulder라는 모양을 미리 가정하지
않고 핫셀블라드가 실제로 쓰는 톤커브에 훨씬 가까운 LUT을 얻을 수 있음.
"""
import csv
import os

import cv2
import numpy as np
import rawpy

from hasselblad_hncs import apply_hncs

CACHE_DIR = "raw_calib_cache"
CSV_PATH = "hasselblad_sample_images.csv"


def collect_pairs():
    rows = list(csv.DictReader(open(CSV_PATH, encoding='utf-8-sig')))
    return [r for r in rows if r.get('raw_url', '').strip() and r.get('jpeg_url', '').strip()
            and not r['raw_url'].lower().endswith('.tif')]


def load_neutral(raw_path, shape_hw):
    with rawpy.imread(raw_path) as raw:
        rgb = raw.postprocess(use_camera_wb=True, no_auto_bright=True,
                               output_bps=8, gamma=(2.222, 4.5))
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    if bgr.shape[:2] != shape_hw:
        bgr = cv2.resize(bgr, (shape_hw[1], shape_hw[0]), interpolation=cv2.INTER_AREA)
    return bgr


def main():
    pairs = collect_pairs()
    neutral_l_all = []
    target_l_all = []

    for r in pairs:
        ext = os.path.splitext(r['raw_url'])[1]
        raw_path = os.path.join(CACHE_DIR, r['filename'] + ext)
        jpeg_path = os.path.join(CACHE_DIR, r['filename'] + '.target.jpg')
        if not (os.path.exists(raw_path) and os.path.exists(jpeg_path)):
            continue

        target = cv2.imread(jpeg_path)
        if target is None:
            continue
        h, w = target.shape[:2]
        scale = 1200 / max(h, w)  # 픽셀 대응 통계용이라 해상도는 낮춰도 충분
        target = cv2.resize(target, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

        try:
            neutral = load_neutral(raw_path, target.shape[:2])
        except Exception as e:
            print(f"  {r['filename']} raw 디코드 실패: {e}")
            continue

        n_l = cv2.cvtColor(neutral, cv2.COLOR_BGR2LAB)[:, :, 0]
        t_l = cv2.cvtColor(target, cv2.COLOR_BGR2LAB)[:, :, 0]
        neutral_l_all.append(n_l.ravel())
        target_l_all.append(t_l.ravel())
        print(f"  {r['filename']} - {n_l.size}px 수집")

    neutral_l_all = np.concatenate(neutral_l_all)
    target_l_all = np.concatenate(target_l_all)
    print(f"\n총 {len(neutral_l_all)}픽셀 쌍으로 LUT 학습")

    # neutral_L 값(0~255)별로 target_L의 중앙값 -> 경험적 톤커브
    lut = np.zeros(256, dtype=np.float32)
    counts = np.zeros(256, dtype=np.int64)
    for v in range(256):
        mask = neutral_l_all == v
        counts[v] = mask.sum()
        if counts[v] > 0:
            lut[v] = np.median(target_l_all[mask])

    # 빈 bin은 이웃값으로 보간
    valid = counts > 20  # 표본이 너무 적은 bin은 신뢰 안 함
    xs = np.arange(256)
    lut_filled = np.interp(xs, xs[valid], lut[valid])

    # 단조 증가 강제 (isotonic-ish: 누적 최댓값)
    lut_mono = np.maximum.accumulate(lut_filled)

    np.save("learned_tone_lut.npy", lut_mono.astype(np.uint8))
    print("저장: learned_tone_lut.npy")

    print("\nneutral_L -> target_L (학습된 커브, 16단계 샘플):")
    for v in range(0, 256, 16):
        print(f"  {v:3d} -> {lut_mono[v]:6.1f}  (표본 {counts[v]})")

    # --- 비교: 학습 LUT vs 현재 파라메트릭 apply_hncs ---
    def stats(gray):
        return dict(b2=np.percentile(gray, 2), w995=np.percentile(gray, 99.5))

    cur_err = 0.0
    learned_err = 0.0
    n = 0
    for r in pairs:
        ext = os.path.splitext(r['raw_url'])[1]
        raw_path = os.path.join(CACHE_DIR, r['filename'] + ext)
        jpeg_path = os.path.join(CACHE_DIR, r['filename'] + '.target.jpg')
        if not (os.path.exists(raw_path) and os.path.exists(jpeg_path)):
            continue
        target = cv2.imread(jpeg_path)
        h, w = target.shape[:2]
        scale = 2000 / max(h, w)
        if scale < 1:
            target = cv2.resize(target, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        neutral = load_neutral(raw_path, target.shape[:2])

        t_gray = cv2.cvtColor(target, cv2.COLOR_BGR2GRAY)
        t_stats = stats(t_gray)
        dark_pct = (t_gray < 40).sum() / t_gray.size * 100

        cur_gray = cv2.cvtColor(apply_hncs(neutral), cv2.COLOR_BGR2GRAY)
        cur_stats = stats(cur_gray)

        lab = cv2.cvtColor(neutral, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        l_learned = cv2.LUT(l, lut_mono.astype(np.uint8))
        learned_bgr = cv2.cvtColor(cv2.merge((l_learned, a, b)), cv2.COLOR_LAB2BGR)
        learned_gray = cv2.cvtColor(learned_bgr, cv2.COLOR_BGR2GRAY)
        learned_stats = stats(learned_gray)

        w_err = lambda s: (s['w995'] - t_stats['w995']) ** 2
        b_err = lambda s: (s['b2'] - t_stats['b2']) ** 2 if dark_pct > 5 else 0.0

        cur_err += w_err(cur_stats) + b_err(cur_stats)
        learned_err += w_err(learned_stats) + b_err(learned_stats)
        n += 1

        flag = "" if dark_pct > 5 else "  (그림자무효)"
        print(f"  {r['filename']:25s} target b2={t_stats['b2']:5.1f} w995={t_stats['w995']:5.1f}  "
              f"| 파라메트릭 b2={cur_stats['b2']:5.1f} w995={cur_stats['w995']:5.1f}  "
              f"| 학습LUT b2={learned_stats['b2']:5.1f} w995={learned_stats['w995']:5.1f}{flag}")

    print(f"\n파라메트릭(v11) RMSE={ (cur_err/n)**0.5:.2f}")
    print(f"학습 LUT RMSE={ (learned_err/n)**0.5:.2f}")


if __name__ == "__main__":
    main()
