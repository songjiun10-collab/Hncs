"""
RAW -> HNCS 실제 전/후 피팅

CSV에 raw_url과 jpeg_url이 둘 다 있는 행만 골라서:
1. RAW(.fff/.3FR)를 rawpy로 중립 렌더링(카메라 WB, 오토브라이트 끔,
   표준 감마) - "그레이딩 전" 베이스라인으로 사용
2. 같은 행의 공식 JPEG(그레이딩 후 결과물)를 타깃으로 사용
3. apply_hncs(중립렌더, 후보 파라미터) 결과와 실제 타깃 JPEG의 블랙p2/
   화이트p99.5를 페어 단위로 직접 비교 (v8/v9의 "그레이딩된 이미지의
   모집단 통계"가 아니라 진짜 이미지별 전/후 쌍)
4. toe_lift/shoulder_start/white_point 그리드서치로 오차 최소화
"""
import csv
import os
import urllib.request

import cv2
import numpy as np
import rawpy

from hasselblad_hncs import apply_hncs

CSV_PATH = "hasselblad_sample_images.csv"
CACHE_DIR = "raw_calib_cache"
os.makedirs(CACHE_DIR, exist_ok=True)


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


def load_neutral_render(raw_path, max_dim=2000):
    with rawpy.imread(raw_path) as raw:
        rgb = raw.postprocess(
            use_camera_wb=True,
            no_auto_bright=True,
            output_bps=8,
            gamma=(2.222, 4.5),  # 표준 sRGB형 감마 - "무가공/중립" 베이스라인
        )
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    h, w = bgr.shape[:2]
    scale = max_dim / max(h, w)
    if scale < 1:
        bgr = cv2.resize(bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return bgr


def load_jpeg(url, path, max_dim=2000):
    if not download(url, path):
        return None
    img = cv2.imread(path)
    if img is None:
        return None
    h, w = img.shape[:2]
    scale = max_dim / max(h, w)
    if scale < 1:
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return img


def stats(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    dark_pct = (gray < 40).sum() / gray.size * 100
    return dict(b2=np.percentile(gray, 2), w995=np.percentile(gray, 99.5), dark_pct=dark_pct)


def collect_pairs():
    rows = list(csv.DictReader(open(CSV_PATH, encoding='utf-8-sig')))
    pairs = []
    for r in rows:
        raw_url = r.get('raw_url', '').strip()
        jpeg_url = r.get('jpeg_url', '').strip()
        if not raw_url or not jpeg_url:
            continue
        if raw_url.lower().endswith('.tif'):
            continue  # 이미 렌더링된 TIFF는 raw 아님 - 제외
        pairs.append(r)
    return pairs


def main():
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

        target_stats = stats(target_img)
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
    for exposure_gamma in (1.0, 0.9, 0.8, 0.7, 0.6, 0.5):
        for toe_lift in (0.0, 0.001, 0.005, 0.01, 0.02):
            for shoulder_start in (0.70, 0.74, 0.78, 0.82):
                for white_point in (0.85, 0.88, 0.90, 0.92, 0.95, 1.0):
                    err = 0.0
                    for d in dataset:
                        graded = apply_hncs(d['neutral'], toe_lift=toe_lift,
                                             shoulder_start=shoulder_start, white_point=white_point,
                                             exposure_gamma=exposure_gamma)
                        s = stats(graded)
                        err += pair_error(d, s)
                    err /= len(dataset)
                    if best is None or err < best[0]:
                        best = (err, exposure_gamma, toe_lift, shoulder_start, white_point)

    err, exposure_gamma, toe_lift, shoulder_start, white_point = best
    print(f"\n=== 최적 파라미터 (RMSE={err**0.5:.2f}) ===")
    print(f"exposure_gamma={exposure_gamma}, toe_lift={toe_lift}, "
          f"shoulder_start={shoulder_start}, white_point={white_point}")

    print("\n=== 현재 기본값과 비교 (페어별) ===")
    cur_err = 0.0
    best_err = 0.0
    for d in dataset:
        cur = stats(apply_hncs(d['neutral']))
        new = stats(apply_hncs(d['neutral'], toe_lift=toe_lift, shoulder_start=shoulder_start,
                                white_point=white_point, exposure_gamma=exposure_gamma))
        t = d['target']
        flag = "" if d['shadow_valid'] else "  (그림자무효)"
        print(f"  {d['name']:25s} target b2={t['b2']:5.1f} w995={t['w995']:5.1f}  "
              f"| 기존 b2={cur['b2']:5.1f} w995={cur['w995']:5.1f}  "
              f"| 신규 b2={new['b2']:5.1f} w995={new['w995']:5.1f}{flag}")
        cur_err += pair_error(d, cur)
        best_err += pair_error(d, new)
    print(f"\n기존 파라미터 RMSE={ (cur_err/len(dataset))**0.5:.2f}")
    print(f"신규 파라미터 RMSE={ (best_err/len(dataset))**0.5:.2f}")


if __name__ == "__main__":
    main()
