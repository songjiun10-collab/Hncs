"""
learned LUT + 제한된 파라메트릭 정규화 - leave-one-out 교차검증

learn_tone_curve.py의 순수 경험적 LUT은 원본 10장에 대한 in-sample RMSE만
봤고(15.4), 표본이 10장뿐이라 과적합 여부를 확인 안 했음. 이 스크립트는:

1. neutral_L bin별로 (경험적 중앙값, 표본수)를 구하고
2. apply_hncs(v11)의 파라메트릭 커브값을 "사전(prior)"으로 삼아
   정규화: reg_lut[v] = (count[v]*empirical[v] + lambda*prior[v]) / (count[v]+lambda)
   (표본 많은 bin은 경험치 그대로, 적은 bin은 파라메트릭 쪽으로 수축)
3. hue/a,b는 건드리지 않음 (L채널 LUT이라 자동으로 보존됨 - apply_hncs와 동일 구조)
4. 10장 leave-one-out: 매 fold마다 나머지 9장으로 LUT을 만들고 빠진 1장에서
   평가 -> lambda별 LOO RMSE로 "진짜 일반화 성능" 비교
"""
import csv
import os

import cv2
import numpy as np
import rawpy

from hasselblad_hncs import _film_curve

CACHE_DIR = "raw_calib_cache"
CSV_PATH = "hasselblad_sample_images.csv"

# v11 파라메트릭 기본값 (exposure_gamma 선적용 + film curve) - 정규화 사전으로 사용
_EXPOSURE_GAMMA = 0.7
_TOE_LIFT = 0.001
_SHOULDER_START = 0.78
_WHITE_POINT = 1.0


def parametric_prior():
    x = np.arange(256, dtype=np.float32) / 255.0
    x_lifted = x ** _EXPOSURE_GAMMA
    y = _film_curve(x_lifted, _TOE_LIFT, _SHOULDER_START, _WHITE_POINT)
    return np.clip(y * 255, 0, 255).astype(np.float32)


def collect_pair_pixels():
    rows = list(csv.DictReader(open(CSV_PATH, encoding='utf-8-sig')))
    pairs = [r for r in rows if r.get('raw_url', '').strip() and r.get('jpeg_url', '').strip()
             and not r['raw_url'].lower().endswith('.tif')]

    dataset = []
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
        scale = 1200 / max(h, w)
        target = cv2.resize(target, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

        with rawpy.imread(raw_path) as raw:
            rgb = raw.postprocess(use_camera_wb=True, no_auto_bright=True,
                                   output_bps=8, gamma=(2.222, 4.5))
        neutral = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        if neutral.shape[:2] != target.shape[:2]:
            neutral = cv2.resize(neutral, (target.shape[1], target.shape[0]), interpolation=cv2.INTER_AREA)

        n_l = cv2.cvtColor(neutral, cv2.COLOR_BGR2LAB)[:, :, 0].ravel()
        t_l = cv2.cvtColor(target, cv2.COLOR_BGR2LAB)[:, :, 0].ravel()
        t_gray = cv2.cvtColor(target, cv2.COLOR_BGR2GRAY)
        dark_pct = (t_gray < 40).sum() / t_gray.size * 100

        dataset.append(dict(name=r['filename'], neutral_l=n_l, target_l=t_l,
                             b2=np.percentile(t_gray, 2), w995=np.percentile(t_gray, 99.5),
                             shadow_valid=dark_pct > 5))
        print(f"  {r['filename']} - {n_l.size}px")
    return dataset


def build_lut(neutral_l, target_l, prior, lam):
    # 중앙값 대신 평균 사용 (fold마다 반복 계산해야 해서 속도상 평균으로 근사;
    # learn_tone_curve.py의 최종 학습 LUT은 중앙값 기준이라 약간 다를 수 있음)
    counts = np.bincount(neutral_l, minlength=256).astype(np.float64)
    sums = np.bincount(neutral_l, weights=target_l.astype(np.float64), minlength=256)

    lut = np.where(counts > 0, (sums + lam * prior) / (counts + lam), prior)
    # 단조 증가 보정
    lut = np.maximum.accumulate(lut)
    return lut.astype(np.float32)


def apply_lut_to_pixels(neutral_l, lut):
    return lut[neutral_l.astype(np.int32)]


def stats_from_l(l_values):
    return dict(b2=np.percentile(l_values, 2), w995=np.percentile(l_values, 99.5))


def main():
    dataset = collect_pair_pixels()
    prior = parametric_prior()
    print(f"\n{len(dataset)}장 로드 완료\n")

    lambdas = [0, 50, 200, 500, 1000, 2000, 5000, 20000, 1e9]  # 1e9 ~= 순수 파라메트릭

    print(f"{'lambda':>10s}  {'LOO RMSE':>10s}")
    results = []
    for lam in lambdas:
        sq_err = 0.0
        n = 0
        for i, held_out in enumerate(dataset):
            train = [d for j, d in enumerate(dataset) if j != i]
            neutral_l = np.concatenate([d['neutral_l'] for d in train])
            target_l = np.concatenate([d['target_l'] for d in train])
            lut = build_lut(neutral_l, target_l, prior, lam)

            pred_l = apply_lut_to_pixels(held_out['neutral_l'], lut)
            pred_stats = stats_from_l(pred_l)

            e = (pred_stats['w995'] - held_out['w995']) ** 2
            if held_out['shadow_valid']:
                e += (pred_stats['b2'] - held_out['b2']) ** 2
            sq_err += e
            n += 1
        rmse = (sq_err / n) ** 0.5
        results.append((lam, rmse))
        print(f"{lam:10.0f}  {rmse:10.2f}")

    best_lam, best_rmse = min(results, key=lambda t: t[1])
    print(f"\n최적 lambda={best_lam} (LOO RMSE={best_rmse:.2f})")

    # 최적 lambda로 전체 10장 사용해 최종 LUT 생성
    all_neutral = np.concatenate([d['neutral_l'] for d in dataset])
    all_target = np.concatenate([d['target_l'] for d in dataset])
    final_lut = build_lut(all_neutral, all_target, prior, best_lam)
    np.save("regularized_tone_lut.npy", np.clip(final_lut, 0, 255).astype(np.uint8))
    print("저장: regularized_tone_lut.npy")


if __name__ == "__main__":
    main()
