"""
imaging-resource.com의 Ricoh GR III/GR IIIx 리뷰 갤러리에서 population
통계를 뽑는다. analyze_pentax_samples.py와 완전히 같은 스크래핑 구조
(리코이미징이 펜탁스 브랜드 소유사라 EXIF Make/Software 패턴도 동일 -
"RICOH IMAGING COMPANY, LTD." / "RICOH GR III Ver. 1.00").

GR은 빠른 실험용으로 우선순위가 낮게 잡혀서(사이즈가 작고 갤러리도
적당히 있어 스크래핑 자체는 가장 간단함) 두 모델만 확인.
"""
import csv
import os
import re
import subprocess
import time
import urllib.request
from collections import defaultdict

import cv2
import numpy as np

CACHE_DIR = "downloaded_samples_ricoh_gr"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

GALLERIES = [
    ("Ricoh GR III", "https://www.imaging-resource.com/cameras/ricoh-gr-iii-review/gallery/"),
    ("Ricoh GR IIIx", "https://www.imaging-resource.com/cameras/ricoh-gr-iiix-review/gallery/"),
]

MAX_PER_CAMERA = 20

DETAIL_LINK_RE = re.compile(
    r'href="(/cameras/[^"]+/image/\d+\?section=gallery)"[^>]*>\s*<img([^>]*)>'
)
FULL_IMG_RE = re.compile(r'<a href="([^"]+)" target="_blank"><img([^>]*)class="attachment-full size-full"')

EDIT_KEYWORDS = ("edit", "-mod", "unsharpmask", "nosharp", "stack")
# "-iso-"는 Phase One 때 겪은 ISO 노이즈 테스트 차트(같은 장면 반복)용,
# f값 정규식은 GR IIIx에서 발견한 조리개 브라케팅 테스트(-f2.8/-f4.0 등,
# 역시 같은 장면 반복) 제외용 - 둘 다 population 통계용으로는 대표성 없는
# 기술 테스트샷이라 뺀다
SKIP_KEYWORDS = ("-iso-",)
SKIP_PATTERN = re.compile(r"-f\d")


def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def _img_url(img_attrs):
    m = re.search(r'data-lazy-src="([^"]+)"', img_attrs)
    if m:
        return m.group(1)
    m = re.search(r'src="([^"]+)"', img_attrs)
    return m.group(1) if m else ""


def list_gallery_images(gallery_url):
    html = fetch(gallery_url)
    seen = set()
    results = []
    for detail_path, img_attrs in DETAIL_LINK_RE.findall(html):
        if detail_path in seen:
            continue
        seen.add(detail_path)
        thumb_url = _img_url(img_attrs)
        low = thumb_url.lower()
        if any(k in low for k in EDIT_KEYWORDS + SKIP_KEYWORDS) or SKIP_PATTERN.search(low):
            continue
        results.append(detail_path)
    return results


def resolve_full_image(detail_path):
    detail_url = "https://www.imaging-resource.com" + detail_path
    html = fetch(detail_url)
    m = FULL_IMG_RE.search(html)
    if not m:
        return None
    original_url = m.group(1)
    scaled_url = _img_url(m.group(2))
    return original_url, scaled_url


def download(url, path):
    if os.path.exists(path):
        return True
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        with open(path, "wb") as f:
            f.write(data)
        return True
    except Exception as e:
        print(f"    실패: {url} -> {e}")
        return False


def exif_check(path):
    out = subprocess.run(["exiftool", "-Make", "-Software", path], capture_output=True, timeout=30)
    text = out.stdout.decode("utf-8", errors="ignore").lower()
    make_ok = "ricoh" in text or "pentax" in text
    edited = any(s in text for s in ["photoshop", "lightroom", "capture one", "camera raw"])
    return make_ok, edited


def stats(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    s = hsv[:, :, 1].astype(np.float32)
    p = np.percentile
    dark = (gray < 40).sum() / gray.size * 100
    return dict(b2=p(gray, 2), w995=p(gray, 99.5), med=np.median(gray),
                sat=s[s > 20].mean() if (s > 20).any() else 0, dark_pct=dark)


def main():
    os.makedirs(CACHE_DIR, exist_ok=True)
    results = []

    for camera, gallery_url in GALLERIES:
        print(f"\n=== {camera} ===")
        try:
            detail_paths = list_gallery_images(gallery_url)
        except Exception as e:
            print(f"  갤러리 목록 실패: {e}")
            continue
        print(f"  후보 {len(detail_paths)}장 (MOD/EDIT/ISO 제외)")

        n_ok = 0
        for detail_path in detail_paths:
            if n_ok >= MAX_PER_CAMERA:
                break
            try:
                resolved = resolve_full_image(detail_path)
            except Exception:
                continue
            if not resolved:
                continue
            original_url, scaled_url = resolved

            fname = f"{camera.replace(' ', '_')}_{os.path.basename(original_url)}"
            path = os.path.join(CACHE_DIR, fname)
            if not download(original_url, path):
                fname = f"{camera.replace(' ', '_')}_{os.path.basename(scaled_url)}"
                path = os.path.join(CACHE_DIR, fname)
                if not download(scaled_url, path):
                    continue

            make_ok, edited = exif_check(path)
            if not make_ok or edited:
                print(f"  스킵 ({'리코 아님' if not make_ok else '편집된 파일'}): {fname}")
                os.remove(path)
                continue

            img = cv2.imread(path)
            if img is None:
                continue
            st = stats(img)
            results.append(dict(camera=camera, filename=fname, url=original_url, **st))
            n_ok += 1
            print(f"  [{n_ok}/{MAX_PER_CAMERA}] {fname}  b2={st['b2']:.0f} w995={st['w995']:.0f} sat={st['sat']:.0f}")
            time.sleep(0.3)

    if not results:
        print("\n결과 없음")
        return

    with open("ricoh_gr_stats_result.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)

    print(f"\n=== 전체 population 통계 (n={len(results)}) ===")
    shadow_valid = [r for r in results if r["dark_pct"] > 5]
    print(f"그림자유효: {len(shadow_valid)}장")
    if shadow_valid:
        print(f"블랙p2 타깃: {np.mean([r['b2'] for r in shadow_valid]):.1f}")
    print(f"화이트p99.5 타깃: {np.mean([r['w995'] for r in results]):.1f}")
    print(f"채도 평균: {np.mean([r['sat'] for r in results]):.1f}")

    print(f"\n=== 카메라별 ===")
    groups = defaultdict(list)
    for r in results:
        groups[r["camera"]].append(r)
    for cam, rows in groups.items():
        sv = [r for r in rows if r["dark_pct"] > 5]
        b2 = np.mean([r["b2"] for r in sv]) if sv else float("nan")
        w995 = np.mean([r["w995"] for r in rows])
        sat = np.mean([r["sat"] for r in rows])
        print(f"{cam:15s} n={len(rows):2d}  b2={b2:5.1f}  w995={w995:5.1f}  sat={sat:5.1f}")

    print("\n저장: ricoh_gr_stats_result.csv")


if __name__ == "__main__":
    main()
