"""
Claude Code용 전수분석 스크립트
사용법: 이 폴더에서 claude 실행 후 이 파일 돌려달라고 하면 됨
(settings.json이 같은 폴더에 있으면 자동으로 네트워크 허용됨)

1. hasselblad_sample_images.csv 읽기
2. 전체 jpeg_url 다운로드 (원본 대신 리사이즈해서 저장 - 용량 절약)
3. 통계 추출 (블랙p2/화이트p99.5/채도, 그림자유효 판정)
4. hasselblad_hncs.py의 toe_lift/white_point 재보정
5. 결과를 csv_stats_result.csv로 저장
"""
import csv
import os
import urllib.request
import cv2
import numpy as np

CSV_PATH = "hasselblad_sample_images.csv"
CACHE_DIR = "downloaded_samples"
os.makedirs(CACHE_DIR, exist_ok=True)

def download(url, path, max_dim=2000):
    """원본이 1억화소급이라 다운로드 후 리사이즈해서 저장 (용량/속도 절약)"""
    if os.path.exists(path):
        return True
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        arr = np.frombuffer(data, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return False
        h, w = img.shape[:2]
        scale = max_dim / max(h, w)
        if scale < 1:
            img = cv2.resize(img, (int(w*scale), int(h*scale)), interpolation=cv2.INTER_AREA)
        cv2.imwrite(path, img, [cv2.IMWRITE_JPEG_QUALITY, 92])
        return True
    except Exception as e:
        print(f"  실패: {url} -> {e}")
        return False


def stats(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    s = hsv[:, :, 1].astype(np.float32)
    p = np.percentile
    dark = (gray < 40).sum() / gray.size * 100
    return dict(
        b2=p(gray, 2), w995=p(gray, 99.5), med=np.median(gray),
        sat=s[s > 20].mean() if (s > 20).any() else 0, dark_pct=dark,
    )


def main():
    with open(CSV_PATH, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))

    results = []
    for i, row in enumerate(rows):
        url = row.get('jpeg_url', '').strip()
        if not url:
            continue
        fname = f"{i:03d}_{row['filename']}"
        path = os.path.join(CACHE_DIR, fname)
        print(f"[{i+1}/{len(rows)}] {row['camera']} - {row['photographer']}")
        if not download(url, path):
            continue
        img = cv2.imread(path)
        if img is None:
            continue
        st = stats(img)
        results.append(dict(row, **st, local_path=path))

    # 결과 저장
    if results:
        keys = list(results[0].keys())
        with open("csv_stats_result.csv", "w", newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(results)

    # 그림자유효 서브셋으로 블랙포인트 타깃, 전체로 화이트포인트 타깃 계산
    shadow_valid = [r for r in results if r['dark_pct'] > 5]
    b2_target = np.mean([r['b2'] for r in shadow_valid]) if shadow_valid else None
    w995_target = np.mean([r['w995'] for r in results]) if results else None

    print(f"\n=== 전수분석 결과 ===")
    print(f"총 다운로드 성공: {len(results)}장")
    print(f"그림자유효(블랙포인트 계산용): {len(shadow_valid)}장")
    if b2_target:
        print(f"블랙p2 타깃: {b2_target:.1f}  (std={np.std([r['b2'] for r in shadow_valid]):.1f})")
    if w995_target:
        print(f"화이트p99.5 타깃: {w995_target:.1f}  (std={np.std([r['w995'] for r in results]):.1f})")

    # 바디별 분리 (X1D vs X2D vs H vs V) - camera 컬럼 문자열 기준
    print(f"\n=== 바디별 그룹 ===")
    from collections import defaultdict
    groups = defaultdict(list)
    for r in results:
        cam = r['camera']
        key = 'X1D' if 'X1D' in cam else ('X2D' if 'X2D' in cam else ('H6D' if 'H6D' in cam else '907X/CFV'))
        groups[key].append(r)
    for k, v in groups.items():
        sv = [r for r in v if r['dark_pct'] > 5]
        b2 = np.mean([r['b2'] for r in sv]) if sv else float('nan')
        w995 = np.mean([r['w995'] for r in v])
        print(f"{k:10s} n={len(v):3d}  블랙p2={b2:.1f}  화이트p99.5={w995:.1f}")

    print("\n결과 저장: csv_stats_result.csv")
    print("이 데이터로 hasselblad_hncs.py 재보정하려면 grid search 스크립트 추가 요청하세요.")


if __name__ == "__main__":
    main()
