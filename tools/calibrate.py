"""
핫셀블라드 raw+jpeg 페어 기반 캘리브레이션 스크립트 모음 - CLI로 모드를
골라 실행한다.

  python3 -m tools.calibrate grid_search   # apply_hncs 파라미터 그리드서치 (원래 calibrate_from_raw.py, v10/v11)
  python3 -m tools.calibrate learn_curve   # 파라메트릭 가정 없이 LUT 직접 학습 (원래 learn_tone_curve.py, v12)
  python3 -m tools.calibrate regularize    # 학습 LUT 정규화 + leave-one-out 교차검증 (원래 regularized_lut_loocv.py, 음성 결과)

raw_url+jpeg_url이 둘 다 있는 CSV 행을 rawpy로 중립 렌더링해서 "그레이딩
전" 베이스라인으로 쓰고, 같은 행의 공식 JPEG을 타깃으로 삼는 진짜 전/후
페어 방식 - v8/v9의 "이미 그레이딩된 이미지들의 population 통계"보다 한
단계 더 정밀한 검증. 세 스크립트 모두 이 raw+jpeg 페어 수집 로직을
거의 그대로 중복해서 갖고 있던 걸 collect_pairs()로 합쳤다.
"""
import csv
import os
import sys
import urllib.request

import cv2
import numpy as np
import rawpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brands.hasselblad import apply_hncs
from core.curve import film_curve
from core.validation import is_image_array_usable

CACHE_DIR = "raw_calib_cache"
CSV_PATH = "datasets/hasselblad/hasselblad_sample_images.csv"

_GENERATION_MAP = {
    "Hasselblad X1D II 50C": "X1D II 50C",
    "Hasselblad X1D": "X1D",
}


def _generation_for(camera):
    """로컬 기여 manifest.csv의 camera 필드를 docs/measurements.md의
    기존 세대 버킷 라벨로 정규화. 이미 그 라벨 형태인 값(CFV 100C/907X,
    X2D 100C)은 그대로 통과."""
    return _GENERATION_MAP.get(camera, camera)


def download(url, path):
    if os.path.exists(path):
        return True
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
        with open(path, 'wb') as f:
            f.write(data)
        return True
    except Exception as e:
        print(f"  실패: {url} -> {e}")
        return False


def collect_pairs():
    """raw_url+jpeg_url이 둘 다 있는 행만 (TIFF는 이미 렌더링된 결과물이라
    raw가 아니므로 제외)."""
    rows = list(csv.DictReader(open(CSV_PATH, encoding='utf-8-sig')))
    return [r for r in rows if r.get('raw_url', '').strip() and r.get('jpeg_url', '').strip()
            and not r['raw_url'].lower().endswith('.tif')]


def collect_local_pairs():
    """datasets/hasselblad/contributed/<세트>/manifest.csv의 로컬 raw+jpeg
    페어 수집 (tools.verify_contributed_pairs 통과 전제 - 여기선 파일 존재만
    재확인). 공식 샘플(collect_pairs, 원격 URL)과 별개 출처라 함수를 분리."""
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "datasets", "hasselblad", "contributed")
    pairs = []
    if not os.path.isdir(base):
        return pairs
    for set_name in sorted(os.listdir(base)):
        manifest = os.path.join(base, set_name, "manifest.csv")
        if not os.path.exists(manifest):
            continue
        for row in csv.DictReader(open(manifest, encoding='utf-8-sig')):
            raw_path = os.path.join(base, set_name, "raw", row["filename_raw"])
            jpeg_path = os.path.join(base, set_name, "jpeg", row["filename_jpeg"])
            if os.path.exists(raw_path) and os.path.exists(jpeg_path):
                pairs.append(dict(
                    filename=f"{set_name}__{os.path.splitext(row['filename_raw'])[0]}",
                    raw_path=raw_path, jpeg_path=jpeg_path,
                    generation=_generation_for(row["camera"])))
    return pairs


def _resize_to_max_dim(img, max_dim):
    """긴 변이 max_dim을 넘으면 비율 유지 축소 (5군데서 각자 반복하던 걸 통합)."""
    h, w = img.shape[:2]
    scale = max_dim / max(h, w)
    if scale < 1:
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return img


def load_neutral_render(raw_path, shape_hw=None, max_dim=2000):
    with rawpy.imread(raw_path) as raw:
        rgb = raw.postprocess(
            use_camera_wb=True,
            no_auto_bright=True,
            output_bps=8,
            gamma=(2.222, 4.5),  # 표준 sRGB형 감마 - "무가공/중립" 베이스라인
        )
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    if shape_hw is not None:
        if bgr.shape[:2] != shape_hw:
            bgr = cv2.resize(bgr, (shape_hw[1], shape_hw[0]), interpolation=cv2.INTER_AREA)
        return bgr
    return _resize_to_max_dim(bgr, max_dim)


def load_jpeg(url, path, max_dim=2000):
    if not download(url, path):
        return None
    img = cv2.imread(path)
    if img is None or not is_image_array_usable(img):
        return None
    return _resize_to_max_dim(img, max_dim)


def gray_stats(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    dark_pct = (gray < 40).sum() / gray.size * 100
    return dict(b2=np.percentile(gray, 2), w995=np.percentile(gray, 99.5), dark_pct=dark_pct)


# ============================================================
# grid_search: apply_hncs 파라미터 그리드서치 (v10/v11)
# ============================================================
def run_grid_search():
    pairs = collect_pairs()
    print(f"raw+jpeg 페어 후보: {len(pairs)}개")

    dataset = []
    for r in pairs:
        raw_url = r['raw_url'].strip()
        jpeg_url = r['jpeg_url'].strip()
        ext = os.path.splitext(raw_url)[1]
        raw_path = os.path.join(CACHE_DIR, r['filename'] + ext)
        jpeg_path = os.path.join(CACHE_DIR, r['filename'] + '.target.jpg')

        print(f"[{r['filename']}] raw 다운로드중...")
        if not download(raw_url, raw_path):
            continue
        try:
            neutral = load_neutral_render(raw_path)
        except Exception as e:
            print(f"  raw 디코드 실패: {e}")
            continue

        target_img = load_jpeg(jpeg_url, jpeg_path)
        if target_img is None:
            continue

        target_stats = gray_stats(target_img)
        shadow_valid = target_stats['dark_pct'] > 5
        dataset.append(dict(name=r['filename'], neutral=neutral, target=target_stats,
                             shadow_valid=shadow_valid))
        flag = "" if shadow_valid else "  (그림자무효 - 블랙포인트 피팅 제외)"
        print(f"  OK - 타깃 b2={target_stats['b2']:.1f} w995={target_stats['w995']:.1f}{flag}")

    print(f"\n사용 가능한 페어: {len(dataset)}개 "
          f"(그림자유효 {sum(d['shadow_valid'] for d in dataset)}개)")
    if not dataset:
        return

    def pair_error(d, s):
        err = (s['w995'] - d['target']['w995']) ** 2
        if d['shadow_valid']:
            err += (s['b2'] - d['target']['b2']) ** 2
        return err

    # --- 그리드서치 (전역 노출 리프트 포함) ---
    best = None
    for exposure_gamma in (0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3):
        for toe_lift in (0.0, 0.005, 0.02):
            for shoulder_start in (0.50, 0.58, 0.66, 0.70, 0.74, 0.78, 0.82):
                for white_point in (0.90, 0.95, 1.0):
                    err = 0.0
                    for d in dataset:
                        graded = apply_hncs(d['neutral'], toe_lift=toe_lift,
                                             shoulder_start=shoulder_start, white_point=white_point,
                                             exposure_gamma=exposure_gamma)
                        s = gray_stats(graded)
                        err += pair_error(d, s)
                    err /= len(dataset)
                    if best is None or err < best[0]:
                        best = (err, exposure_gamma, toe_lift, shoulder_start, white_point)

    err, exposure_gamma, toe_lift, shoulder_start, white_point = best
    print(f"\n=== 최적 파라미터 (RMSE={err ** 0.5:.2f}) ===")
    print(f"exposure_gamma={exposure_gamma}, toe_lift={toe_lift}, "
          f"shoulder_start={shoulder_start}, white_point={white_point}")

    print("\n=== 현재 기본값과 비교 (페어별) ===")
    cur_err = 0.0
    best_err = 0.0
    for d in dataset:
        cur = gray_stats(apply_hncs(d['neutral']))
        new = gray_stats(apply_hncs(d['neutral'], toe_lift=toe_lift, shoulder_start=shoulder_start,
                                     white_point=white_point, exposure_gamma=exposure_gamma))
        t = d['target']
        flag = "" if d['shadow_valid'] else "  (그림자무효)"
        print(f"  {d['name']:25s} target b2={t['b2']:5.1f} w995={t['w995']:5.1f}  "
              f"| 기존 b2={cur['b2']:5.1f} w995={cur['w995']:5.1f}  "
              f"| 신규 b2={new['b2']:5.1f} w995={new['w995']:5.1f}{flag}")
        cur_err += pair_error(d, cur)
        best_err += pair_error(d, new)
    print(f"\n기존 파라미터 RMSE={(cur_err / len(dataset)) ** 0.5:.2f}")
    print(f"신규 파라미터 RMSE={(best_err / len(dataset)) ** 0.5:.2f}")


# ============================================================
# learn_curve: 파라메트릭 가정 없이 LUT 직접 학습 (v12)
# ============================================================
def _resolve_pairs():
    """공식 샘플(collect_pairs, 원격 URL - 다운로드해서 캐시에 확보) + 로컬
    기여 페어(collect_local_pairs, 이미 로컬에 있음)를 raw_path/jpeg_path가
    바로 붙은 공통 포맷으로 합친다. generation 필드도 붙여 반환(공식은
    한 버킷 "공식 샘플(X1D 계열)", 로컬은 카메라별)."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    resolved = []
    for r in collect_pairs():
        ext = os.path.splitext(r['raw_url'])[1]
        raw_path = os.path.join(CACHE_DIR, r['filename'] + ext)
        jpeg_path = os.path.join(CACHE_DIR, r['filename'] + '.target.jpg')
        if download(r['raw_url'].strip(), raw_path) and download(r['jpeg_url'].strip(), jpeg_path):
            resolved.append(dict(filename=r['filename'], raw_path=raw_path, jpeg_path=jpeg_path,
                                  generation="공식 샘플(X1D 계열)"))
    n_official = len(resolved)
    local_pairs = collect_local_pairs()
    resolved.extend(local_pairs)
    print(f"공식 샘플 페어 {n_official}개 + 로컬 기여 페어 {len(local_pairs)}개 = 총 {len(resolved)}개")
    return resolved


def run_learn_curve():
    pairs = _resolve_pairs()
    neutral_l_all = []
    target_l_all = []

    for r in pairs:
        raw_path = r['raw_path']
        jpeg_path = r['jpeg_path']
        if not (os.path.exists(raw_path) and os.path.exists(jpeg_path)):
            continue

        target = cv2.imread(jpeg_path)
        if target is None:
            continue
        target = _resize_to_max_dim(target, 1200)  # 픽셀 대응 통계용이라 해상도는 낮춰도 충분

        try:
            neutral = load_neutral_render(raw_path, shape_hw=target.shape[:2])
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
    cur_err = 0.0
    learned_err = 0.0
    n = 0
    for r in pairs:
        raw_path = r['raw_path']
        jpeg_path = r['jpeg_path']
        if not (os.path.exists(raw_path) and os.path.exists(jpeg_path)):
            continue
        target = _resize_to_max_dim(cv2.imread(jpeg_path), 2000)
        neutral = load_neutral_render(raw_path, shape_hw=target.shape[:2])

        t_stats = gray_stats(target)
        dark_pct = t_stats['dark_pct']

        cur_stats = gray_stats(apply_hncs(neutral))

        lab = cv2.cvtColor(neutral, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        l_learned = cv2.LUT(l, lut_mono.astype(np.uint8))
        learned_bgr = cv2.cvtColor(cv2.merge((l_learned, a, b)), cv2.COLOR_LAB2BGR)
        learned_stats = gray_stats(learned_bgr)

        w_err = lambda s: (s['w995'] - t_stats['w995']) ** 2
        b_err = lambda s: (s['b2'] - t_stats['b2']) ** 2 if dark_pct > 5 else 0.0

        cur_err += w_err(cur_stats) + b_err(cur_stats)
        learned_err += w_err(learned_stats) + b_err(learned_stats)
        n += 1

        flag = "" if dark_pct > 5 else "  (그림자무효)"
        print(f"  {r['filename']:25s} target b2={t_stats['b2']:5.1f} w995={t_stats['w995']:5.1f}  "
              f"| 파라메트릭 b2={cur_stats['b2']:5.1f} w995={cur_stats['w995']:5.1f}  "
              f"| 학습LUT b2={learned_stats['b2']:5.1f} w995={learned_stats['w995']:5.1f}{flag}")

    print(f"\n파라메트릭(v11) RMSE={(cur_err / n) ** 0.5:.2f}")
    print(f"학습 LUT RMSE={(learned_err / n) ** 0.5:.2f}")


# ============================================================
# regularize: 학습 LUT 정규화 + leave-one-out 교차검증 (음성 결과)
# ============================================================
# v11 파라메트릭 기본값 (exposure_gamma 선적용 + film curve) - 정규화 사전으로 사용
_EXPOSURE_GAMMA = 0.7
_TOE_LIFT = 0.001
_SHOULDER_START = 0.78
_WHITE_POINT = 1.0


def _parametric_prior():
    x = np.arange(256, dtype=np.float32) / 255.0
    x_lifted = x ** _EXPOSURE_GAMMA
    y = film_curve(x_lifted, _TOE_LIFT, _SHOULDER_START, _WHITE_POINT)
    return np.clip(y * 255, 0, 255).astype(np.float32)


def _collect_pair_pixels():
    dataset = []
    for r in _resolve_pairs():
        raw_path = r['raw_path']
        jpeg_path = r['jpeg_path']
        if not (os.path.exists(raw_path) and os.path.exists(jpeg_path)):
            continue

        target = cv2.imread(jpeg_path)
        if target is None:
            continue
        target = _resize_to_max_dim(target, 1200)

        with rawpy.imread(raw_path) as raw:
            rgb = raw.postprocess(use_camera_wb=True, no_auto_bright=True,
                                   output_bps=8, gamma=(2.222, 4.5))
        neutral = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        if neutral.shape[:2] != target.shape[:2]:
            neutral = cv2.resize(neutral, (target.shape[1], target.shape[0]), interpolation=cv2.INTER_AREA)

        n_l = cv2.cvtColor(neutral, cv2.COLOR_BGR2LAB)[:, :, 0].ravel()
        t_l = cv2.cvtColor(target, cv2.COLOR_BGR2LAB)[:, :, 0].ravel()
        t_stats = gray_stats(target)

        dataset.append(dict(name=r['filename'], neutral_l=n_l, target_l=t_l,
                             generation=r['generation'],
                             b2=t_stats['b2'], w995=t_stats['w995'],
                             shadow_valid=t_stats['dark_pct'] > 5))
        print(f"  {r['filename']} ({r['generation']}) - {n_l.size}px")
    return dataset


def _pair_counts_sums(neutral_l, target_l):
    """페어 한 장의 neutral_L->target_L 픽셀 대응을 bincount로 집계.
    LOO 뺄셈에 쓰기 위해 페어별로 한 번만 계산해둔다."""
    counts = np.bincount(neutral_l, minlength=256).astype(np.float64)
    sums = np.bincount(neutral_l, weights=target_l.astype(np.float64), minlength=256)
    return counts, sums


def _build_lut_from_counts(counts, sums, prior, lam):
    """counts/sums(여러 페어를 이미 합친 것이든, 전체에서 한 페어를 뺀
    것이든 상관없이)로부터 ridge-정규화 LUT을 만든다. lam=0이면 순수
    경험적 평균(빈 bin은 prior로 대체), lam이 크면 prior에 수렴."""
    lut = np.where(counts > 0, (sums + lam * prior) / (counts + lam), prior)
    lut = np.maximum.accumulate(lut)  # 단조 증가 보정
    return lut.astype(np.float32)


def run_regularize():
    dataset = _collect_pair_pixels()
    prior = _parametric_prior()
    print(f"\n{len(dataset)}장 로드 완료\n")

    for d in dataset:
        d['counts'], d['sums'] = _pair_counts_sums(d['neutral_l'], d['target_l'])

    counts_all = sum(d['counts'] for d in dataset)
    sums_all = sum(d['sums'] for d in dataset)

    lambdas = [0, 50, 200, 500, 1000, 2000, 5000, 20000, 1e9]  # 1e9 ~= 순수 파라메트릭

    print(f"{'lambda':>10s}  {'LOO RMSE':>10s}")
    results = []
    per_fold_by_lambda = {}
    for lam in lambdas:
        sq_err = 0.0
        n = 0
        per_fold = []
        for held_out in dataset:
            train_counts = counts_all - held_out['counts']
            train_sums = sums_all - held_out['sums']
            lut = _build_lut_from_counts(train_counts, train_sums, prior, lam)

            pred_l = lut[held_out['neutral_l'].astype(np.int32)]
            pred_stats = dict(b2=np.percentile(pred_l, 2), w995=np.percentile(pred_l, 99.5))

            e = (pred_stats['w995'] - held_out['w995']) ** 2
            if held_out['shadow_valid']:
                e += (pred_stats['b2'] - held_out['b2']) ** 2
            sq_err += e
            n += 1
            per_fold.append((held_out['name'], held_out['generation'], e ** 0.5))
        rmse = (sq_err / n) ** 0.5
        results.append((lam, rmse))
        per_fold_by_lambda[lam] = per_fold
        print(f"{lam:10.0f}  {rmse:10.2f}")

    best_lam, best_rmse = min(results, key=lambda t: t[1])
    print(f"\n최적 lambda={best_lam} (LOO RMSE={best_rmse:.2f})")

    # 최적 lambda로 전체 74쌍 사용해 최종 LUT 생성
    final_lut = _build_lut_from_counts(counts_all, sums_all, prior, best_lam)
    np.save("regularized_tone_lut.npy", np.clip(final_lut, 0, 255).astype(np.uint8))
    print("저장: regularized_tone_lut.npy")

    return per_fold_by_lambda, best_lam


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "grid_search":
        run_grid_search()
    elif mode == "learn_curve":
        run_learn_curve()
    elif mode == "regularize":
        run_regularize()
    else:
        print("usage: python3 -m tools.calibrate [grid_search|learn_curve|regularize]")
