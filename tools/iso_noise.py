"""
핫셀블라드 공식 샘플을 ISO별로 나열해서 노이즈 수준을 분석한다.

CSV(datasets/hasselblad/hasselblad_sample_images.csv)에는 ISO 컬럼이
없고, downloaded_samples/의 캐시본은 tools/analyze.py의 다운로드 단계에서
cv2로 리사이즈+재인코딩하며 EXIF가 전부 날아간 상태(픽셀 내용은 그대로).
그래서:
1. 각 CSV 행의 jpeg_url에서 앞부분 128KB만 HTTP Range로 받아 exiftool로
   ISO/Make/Model을 뽑는다 (EXIF는 보통 파일 맨 앞 APP1 세그먼트에 있어서
   전체를 다시 받을 필요가 없음 - 실측으로 확인됨).
2. 노이즈는 이미 캐시된 downloaded_samples/의 픽셀로 Immerkär의 전역
   노이즈 추정(라플라시안류 커널 컨볼루션 기반, 별도의 "평평한 영역"을
   수동으로 찾을 필요 없음)을 써서 정량화한다.
3. ISO별로 묶어서 평균 노이즈, 표본 수를 출력하고 추세를 본다.

주의: 이 추정치는 진짜 real detail(질감)이 많은 사진일수록 노이즈로
오판할 수 있는 전역 추정이라 완벽하진 않음 - ISO 그룹 간 "상대적" 비교
용도로 쓰는 게 안전함. 또한 캐시본이 quality=92로 재인코딩된 상태라
절대적 노이즈 값 자체는 원본과 다를 수 있음(JPEG 압축이 고주파 노이즈를
일부 깎아내는 방향이라 재인코딩 전보다는 낮게 나올 가능성이 큼).
"""
import csv
import os
import subprocess
import sys
import urllib.request
from collections import defaultdict

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CSV_PATH = "datasets/hasselblad/hasselblad_sample_images.csv"
CACHE_DIR = "downloaded_samples"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def fetch_exif_head(url, n_bytes=131072):
    # 정정(2026-08 코드리뷰): 고정 임시파일 경로(/tmp/_iso_noise_head.jpg)를
    # 썼었는데, tools/analyze.py의 _check_genuine_bytes()에서 같은 패턴이
    # 동시 실행 시 레이스 컨디션을 일으킨 게 확인된 바 있어(다른 프로세스가
    # exiftool 읽기 전에 파일을 덮어씀) 동일하게 tempfile.NamedTemporaryFile로
    # 호출마다 고유 경로를 쓰도록 수정 - 동시 실행에도 안전.
    req = urllib.request.Request(url, headers={**HEADERS, "Range": f"bytes=0-{n_bytes - 1}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
    except Exception as e:
        return None, None, None
    import json
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=True) as tmp:
        tmp.write(data)
        tmp.flush()
        out = subprocess.run(["exiftool", "-json", "-ISO", "-Make", "-Model", tmp.name],
                              capture_output=True, text=True, timeout=30)
    if out.returncode != 0 or not out.stdout.strip():
        return None, None, None
    d = json.loads(out.stdout)[0]
    return d.get("ISO"), d.get("Make"), d.get("Model")


def estimate_noise_sigma(gray):
    """Immerkaer's fast noise estimation (라플라시안류 커널) - 이미지 전체 기준.
    나뭇잎/자갈처럼 진짜 고주파 디테일이 많은 장면을 노이즈로 오판하기 쉬움
    (02445.jpg 숲 사진에서 확인됨: noise_sigma=11.33으로 나머지보다 5배+
    높았는데 실제로는 노이즈가 아니라 빽빽한 나뭇잎/가지 디테일이었음)."""
    kernel = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], dtype=np.float64)
    conv = cv2.filter2D(gray.astype(np.float64), -1, kernel)
    h, w = gray.shape
    sigma = np.sum(np.abs(conv)) * np.sqrt(np.pi / 2) / (6 * (w - 2) * (h - 2))
    return sigma


def estimate_noise_flat_patch(gray, patch_size=32, flat_fraction=0.1):
    """실제 디테일에 덜 흔들리는 버전: 32x32 패치로 나눠 분산이 가장 낮은
    (=가장 평평한, 텍스처가 적은) 하위 10% 패치에서만 노이즈를 측정한다.
    하늘/벽처럼 진짜 균일한 영역이 있어야 의미 있는 값이 나옴.

    2026-07: 패치 그리드 range()가 h/w를 patch_size로 나눈 나머지만큼만
    돌아서(예: 2400/48처럼 딱 나눠떨어지면) 마지막 행/열 패치가 누락되던
    off-by-one을 수정(+1). datasets/*/texture_signature.json의 noise
    필드 중 이 함수를 쓴 population-fit 브랜드 10개(canon/nikon/olympus/
    panasonic/sigma/sony는 patch_size=48, leica/pentax/phaseone/ricoh_gr은
    함수 기본값 32 추정)를 캐시된 원본 이미지로 재계산해서 반영함(각
    texture_signature.json의 methodology 필드에 재계산 기록, 변화는
    평균 노이즈 기준 1% 이내로 작았음). Hasselblad만 당시 쓴 원본
    캐시가 지금 안 남아있어 재계산 못 함(hasselblad/texture_signature.json
    참고)."""
    h, w = gray.shape
    gray_f = gray.astype(np.float64)
    kernel = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], dtype=np.float64)

    patches, variances = [], []
    for y in range(0, h - patch_size + 1, patch_size):
        for x in range(0, w - patch_size + 1, patch_size):
            p = gray_f[y:y + patch_size, x:x + patch_size]
            variances.append(p.var())
            patches.append(p)
    if not patches:
        return None

    variances = np.array(variances)
    n_flat = max(1, int(len(patches) * flat_fraction))
    flat_idx = np.argsort(variances)[:n_flat]

    sigmas = []
    for i in flat_idx:
        p = patches[i]
        conv = cv2.filter2D(p, -1, kernel)
        ph, pw = p.shape
        sigmas.append(np.sum(np.abs(conv)) * np.sqrt(np.pi / 2) / (6 * (pw - 2) * (ph - 2)))
    return float(np.median(sigmas))


def main():
    rows = list(csv.DictReader(open(CSV_PATH, encoding="utf-8-sig")))
    cached = {f[:3]: f for f in os.listdir(CACHE_DIR)}

    results = []
    for i, row in enumerate(rows):
        idx = f"{i:03d}"
        if idx not in cached:
            continue
        url = row.get("jpeg_url", "").strip()
        if not url:
            continue

        iso, make, model = fetch_exif_head(url)
        if iso is None:
            print(f"[{idx}] ISO 못 읽음: {row['filename']}")
            continue

        path = os.path.join(CACHE_DIR, cached[idx])
        img = cv2.imread(path)
        if img is None:
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        noise = estimate_noise_sigma(gray)
        noise_flat = estimate_noise_flat_patch(gray)

        try:
            iso_val = int(iso)
        except (ValueError, TypeError):
            iso_val = None

        results.append(dict(idx=idx, filename=row["filename"], camera=row.get("camera", ""),
                             iso=iso_val, iso_raw=iso, noise=noise, noise_flat=noise_flat))
        print(f"[{idx}] {row['filename']:30s} ISO={str(iso):6s} noise_global={noise:6.2f} "
              f"noise_flat={noise_flat:6.2f}  {row.get('camera','')}")

    print(f"\n총 {len(results)}장 분석 완료\n")

    # ISO 오름차순 전체 나열
    print("=== ISO 오름차순 전체 목록 ===")
    valid = [r for r in results if r["iso"] is not None]
    for r in sorted(valid, key=lambda r: r["iso"]):
        flat = r["noise_flat"]
        flat_str = f"{flat:6.2f}" if flat is not None else "   N/A"
        print(f"  ISO {r['iso']:6d}  noise_global={r['noise']:6.2f}  noise_flat={flat_str}  "
              f"{r['filename']:30s} {r['camera']}")

    # ISO 구간별 집계 (전역 지표 / 평평한영역 지표 둘 다)
    print("\n=== ISO 구간별 평균 노이즈 ===")
    buckets = defaultdict(list)
    buckets_flat = defaultdict(list)
    for r in valid:
        iso = r["iso"]
        if iso <= 100:
            b = "<=100"
        elif iso <= 200:
            b = "101-200"
        elif iso <= 400:
            b = "201-400"
        elif iso <= 800:
            b = "401-800"
        elif iso <= 1600:
            b = "801-1600"
        elif iso <= 3200:
            b = "1601-3200"
        else:
            b = ">3200"
        buckets[b].append(r["noise"])
        if r["noise_flat"] is not None:
            buckets_flat[b].append(r["noise_flat"])

    order = ["<=100", "101-200", "201-400", "401-800", "801-1600", "1601-3200", ">3200"]
    for b in order:
        if b in buckets:
            vals = buckets[b]
            fvals = buckets_flat.get(b, [])
            fstr = f"{np.mean(fvals):6.2f}" if fvals else "   N/A"
            print(f"  ISO {b:10s}  n={len(vals):2d}  전역평균={np.mean(vals):6.2f}  "
                  f"평평한영역평균={fstr}")

    if len(valid) >= 3:
        isos = np.array([r["iso"] for r in valid], dtype=np.float64)
        noises = np.array([r["noise"] for r in valid])
        corr = np.corrcoef(np.log(isos), noises)[0, 1]
        print(f"\nlog(ISO) vs noise_global 상관계수: {corr:.3f}")

        flat_pairs = [(r["iso"], r["noise_flat"]) for r in valid if r["noise_flat"] is not None]
        if len(flat_pairs) >= 3:
            fisos = np.log(np.array([p[0] for p in flat_pairs], dtype=np.float64))
            fnoises = np.array([p[1] for p in flat_pairs])
            fcorr = np.corrcoef(fisos, fnoises)[0, 1]
            print(f"log(ISO) vs noise_flat 상관계수:   {fcorr:.3f}")


if __name__ == "__main__":
    main()
