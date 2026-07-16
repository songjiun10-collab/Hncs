"""
population 통계/검증 스크립트 모음 - CLI로 브랜드를 골라 실행한다.

  python3 -m tools.analyze hasselblad     # 공식 CSV 전수분석 (원래 analyze_all_samples.py)
  python3 -m tools.analyze leica          # imaging-resource.com population (원래 analyze_leica_samples.py)
  python3 -m tools.analyze phaseone       # 〃 (원래 analyze_phaseone_samples.py)
  python3 -m tools.analyze pentax         # 〃 (원래 analyze_pentax_samples.py)
  python3 -m tools.analyze ricoh_gr       # 〃 (원래 analyze_ricoh_gr_samples.py)
  python3 -m tools.analyze fuji_film_modes  # Film Mode별 population + 프리셋 방향 검증 (원래 analyze_fuji_film_modes.py)
  python3 -m tools.analyze portrait       # 인물 서브셋 + 피부톤 hue 불변성 검증 (원래 portrait_skin_analysis.py)

라이카/Phase One/Pentax/Ricoh GR 네 브랜드는 전부 imaging-resource.com
카메라 리뷰 갤러리를 스크레이핑하는 동일한 구조였던 걸(원래 analyze_*.py
4개 파일에 거의 그대로 중복돼 있었음) BRAND_CONFIGS 딕셔너리 + 공용
run_imaging_resource_brand()로 합쳤다. 브랜드별 차이는 어떤 EXIF 키워드가
"기대하는 렌더러"인지(Phase One은 Capture One이 기대값, 나머지는
거절값), 어떤 파일명 패턴이 "대표성 없는 기술 테스트샷"인지뿐이다.
"""
import csv
import glob
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from collections import defaultdict

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.stats import image_stats
from core.validation import genuine_render_check, is_image_array_usable, is_image_usable, region_hue
from tools.download import list_gallery_images, resolve_full_image, download_file


# ============================================================
# 핫셀블라드: 공식 CSV 전수분석 (원래 analyze_all_samples.py)
# ============================================================
HASSELBLAD_CSV_PATH = "datasets/hasselblad/hasselblad_sample_images.csv"
HASSELBLAD_CACHE_DIR = "downloaded_samples"


def _hasselblad_download(url, path, max_dim=2000):
    """원본이 1억화소급이라 다운로드 후 리사이즈해서 저장 (용량/속도 절약)"""
    if os.path.exists(path):
        if is_image_usable(path):
            return True
        os.remove(path)  # 이전 실행에서 손상된 채로 캐시된 파일 - 재다운로드
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        arr = np.frombuffer(data, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None or not is_image_array_usable(img):
            return False
        h, w = img.shape[:2]
        scale = max_dim / max(h, w)
        if scale < 1:
            img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        cv2.imwrite(path, img, [cv2.IMWRITE_JPEG_QUALITY, 92])
        return True
    except Exception as e:
        print(f"  실패: {url} -> {e}")
        return False


def run_hasselblad():
    os.makedirs(HASSELBLAD_CACHE_DIR, exist_ok=True)
    with open(HASSELBLAD_CSV_PATH, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))

    results = []
    for i, row in enumerate(rows):
        url = row.get('jpeg_url', '').strip()
        if not url:
            continue
        fname = f"{i:03d}_{row['filename']}"
        path = os.path.join(HASSELBLAD_CACHE_DIR, fname)
        print(f"[{i + 1}/{len(rows)}] {row['camera']} - {row['photographer']}")
        if not _hasselblad_download(url, path):
            continue
        img = cv2.imread(path)
        if img is None:
            continue
        st = image_stats(img)
        results.append(dict(row, **st, local_path=path))

    if results:
        keys = list(results[0].keys())
        with open("csv_stats_result.csv", "w", newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(results)

    shadow_valid = [r for r in results if r['dark_pct'] > 5]
    b2_target = np.mean([r['b2'] for r in shadow_valid]) if shadow_valid else None
    w995_target = np.mean([r['w995'] for r in results]) if results else None

    print("\n=== 전수분석 결과 ===")
    print(f"총 다운로드 성공: {len(results)}장")
    print(f"그림자유효(블랙포인트 계산용): {len(shadow_valid)}장")
    if b2_target is not None:
        print(f"블랙p2 타깃: {b2_target:.1f}  (std={np.std([r['b2'] for r in shadow_valid]):.1f})")
    if w995_target is not None:
        print(f"화이트p99.5 타깃: {w995_target:.1f}  (std={np.std([r['w995'] for r in results]):.1f})")

    print("\n=== 바디별 그룹 ===")
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


# ============================================================
# 라이카/Phase One/Pentax/Ricoh GR: imaging-resource.com population
# ============================================================
BRAND_CONFIGS = {
    "leica": dict(
        galleries=[
            ("Leica M9", "https://www.imaging-resource.com/PRODS/M9/M9GALLERY.HTM"),
            ("Leica X Vario", "https://www.imaging-resource.com/PRODS/leica-x-vario/leica-x-varioGALLERY.HTM"),
            ("Leica SL2", "https://www.imaging-resource.com/PRODS/leica-sl2/leica-sl2GALLERY.HTM"),
            # "Leica T (Typ 701)" URL은 추측이었는데 존재하지 않는 슬러그라
            # 사이트가 엉뚱한(후지 GFX100) 갤러리로 리다이렉트시켰음 -
            # 검증된 URL을 못 찾아서 제외.
        ],
        max_per_camera=15,
        expected_keywords=("leica",),
        reject_keywords=("photoshop", "lightroom", "camera raw", "capture one"),
        skip_keywords=("edit",),
        skip_patterns=(),
        cache_dir="downloaded_samples_leica",
        result_csv="leica_stats_result.csv",
    ),
    "phaseone": dict(
        galleries=[
            ("Phase One XF 100MP", "https://www.imaging-resource.com/PRODS/phase-one-xf-100mp/phase-one-xf-100mpGALLERY.HTM"),
            # "Phase One XT" 갤러리(imaging-resource.com/cameras/
            # phase-one-xt-review/gallery/, 218장 후보)를 표본 확대용으로
            # 시도했다가 뺐음 - 무결성 검증 통과분 13장이 전부 "-ACHROMATIC-"
            # 파일명의 흑백 전용 백(채도=0)이었음. 컬러 population
            # 타깃(toe_lift/white_point 피팅용)에 흑백 전용 카메라를
            # 섞으면 안 되므로 제외.
        ],
        max_per_camera=30,
        # Phase One은 스튜디오/테더링 중심이라 인카메라 JPEG 엔진이
        # 사실상 없음 - EXIF Software가 전부 "Capture One"(자체 RAW
        # 컨버터)이라 이게 오히려 "기대하는" 렌더러
        expected_keywords=("capture one",),
        reject_keywords=("photoshop", "lightroom"),
        # ISO 노이즈 테스트 차트(같은 장면, ISO만 다름)가 population을
        # 왜곡시켜서 제외 (1차 실행 n=20에서 8장 중 6장이 이거였고, 빼고
        # 나니 채도 평균이 76.9 -> 118.6으로 크게 달라졌음)
        skip_keywords=("edit", "-mod", "unsharpmask", "nosharp", "stack", "-iso-"),
        skip_patterns=(),
        cache_dir="downloaded_samples_phaseone",
        result_csv="phaseone_stats_result.csv",
    ),
    "pentax": dict(
        galleries=[
            ("Pentax 645Z", "https://www.imaging-resource.com/cameras/pentax-645z-review/gallery/"),
            ("Pentax K-1", "https://www.imaging-resource.com/cameras/pentax-k-1-review/gallery/"),
        ],
        max_per_camera=20,
        expected_keywords=("ricoh", "pentax"),
        reject_keywords=("photoshop", "lightroom", "capture one", "camera raw"),
        skip_keywords=("edit", "-mod", "unsharpmask", "nosharp", "stack", "-iso-"),
        skip_patterns=(),
        cache_dir="downloaded_samples_pentax",
        result_csv="pentax_stats_result.csv",
    ),
    "ricoh_gr": dict(
        galleries=[
            ("Ricoh GR III", "https://www.imaging-resource.com/cameras/ricoh-gr-iii-review/gallery/"),
            ("Ricoh GR IIIx", "https://www.imaging-resource.com/cameras/ricoh-gr-iiix-review/gallery/"),
            # 표본 확대(2026-07) - GR(1세대, 2013)과 GR II(2015)도 같은
            # 회사/같은 EXIF 검증 패턴이라 추가. Phase One XT 때처럼 흑백
            # 전용 백 같은 이종 카메라가 섞일 위험은 없음(GR 라인은 전부
            # 컬러 APS-C 콤팩트).
            ("Ricoh GR", "https://www.imaging-resource.com/cameras/ricoh-gr-review/gallery/"),
            ("Ricoh GR II", "https://www.imaging-resource.com/cameras/ricoh-gr-ii-review/gallery/"),
        ],
        max_per_camera=20,
        expected_keywords=("ricoh", "pentax"),
        reject_keywords=("photoshop", "lightroom", "capture one", "camera raw"),
        # "-f\d"는 GR IIIx의 조리개 브라케팅 테스트샷(-f2.8/-f4.0/-f8.0,
        # 같은 장면 반복) 제외용 - ISO 차트와 같은 종류 문제. "-effect"/
        # "-no-effect"는 GR II의 HDR 효과 on/off 비교샷(같은 장면 반복,
        # 2026-07 표본확대 때 발견) 제외용.
        skip_keywords=("edit", "-mod", "unsharpmask", "nosharp", "stack", "-iso-", "-effect"),
        skip_patterns=(re.compile(r"-f\d"),),
        cache_dir="downloaded_samples_ricoh_gr",
        result_csv="ricoh_gr_stats_result.csv",
    ),
    # 핫셀블라드 표본 확대(2026-07) - 기존 124장은 전부 cdn.hasselblad.com
    # 공식 갤러리(hasselblad.com/learn/sample-images/) 단일 소스였음. 다른
    # 소스(하셀 공식 인스타그램, explorecams.com/500px)는 EXIF Software
    # 검증 결과 대부분 편집/재인코딩이라 못 씀(docs/methodology.md 참고).
    # imaging-resource.com에 X2D 100C 리뷰 갤러리(자체 카메라 테스트샷,
    # 다른 4개 브랜드와 동일 소스)가 있는 걸 확인 - 각 장면마다 원본과
    # "-MOD"(리뷰어 보정본) 페어로 올라와 있어서 원본만 골라 쓰면 됨. 키는
    # "hasselblad_ir"로 분리 - CLI의 "hasselblad" mode는 이미 공식 CSV
    # 전수분석(run_hasselblad)이 선점하고 있어서 겹치지 않게 함.
    "hasselblad_ir": dict(
        galleries=[
            ("Hasselblad X2D 100C", "https://www.imaging-resource.com/cameras/hasselblad-x2d-100c-review/gallery/"),
        ],
        max_per_camera=50,
        expected_keywords=("hasselblad",),
        reject_keywords=("photoshop", "lightroom", "capture one", "camera raw"),
        skip_keywords=("edit", "-mod", "unsharpmask", "nosharp", "stack", "-iso-"),
        skip_patterns=(),
        cache_dir="downloaded_samples_hasselblad_ir",
        result_csv="hasselblad_ir_stats_result.csv",
    ),
}


def run_imaging_resource_brand(brand):
    cfg = BRAND_CONFIGS[brand]
    os.makedirs(cfg["cache_dir"], exist_ok=True)
    results = []

    for camera, gallery_url in cfg["galleries"]:
        print(f"\n=== {camera} ===")
        try:
            detail_paths = list_gallery_images(gallery_url, cfg["skip_keywords"], cfg["skip_patterns"])
        except Exception as e:
            print(f"  갤러리 목록 실패: {e}")
            continue
        print(f"  후보 {len(detail_paths)}장 (편집/테스트샷 제외)")

        n_ok = 0
        for detail_path in detail_paths:
            if n_ok >= cfg["max_per_camera"]:
                break
            try:
                resolved = resolve_full_image(detail_path)
            except Exception:
                continue
            if not resolved:
                continue
            original_url, scaled_url = resolved

            fname = f"{camera.replace(' ', '_')}_{os.path.basename(original_url)}"
            path = os.path.join(cfg["cache_dir"], fname)
            img = cv2.imread(path) if download_file(original_url, path) else None
            ok = img is not None and is_image_array_usable(img)
            if not ok:
                # 원본(href)이 404거나 media.imaging-resource.com에 손상된
                # 채로 저장돼 있는 경우가 종종 있어서 scaled로 폴백
                # (2026-07 실측: 사이트 자체 CDN 손상 - core/validation.py
                # is_image_usable() docstring 참고)
                if os.path.exists(path):
                    os.remove(path)
                fname = f"{camera.replace(' ', '_')}_{os.path.basename(scaled_url)}"
                path = os.path.join(cfg["cache_dir"], fname)
                img = cv2.imread(path) if download_file(scaled_url, path) else None
                ok = img is not None and is_image_array_usable(img)
                if not ok:
                    if os.path.exists(path):
                        os.remove(path)
                    print(f"  스킵 (손상된 원본/scaled, imaging-resource.com CDN 문제): {fname}")
                    continue

            try:
                expected_ok, rejected = genuine_render_check(path, cfg["expected_keywords"], cfg["reject_keywords"])
            except Exception as e:
                # exiftool이 이 한 장에서만 실패해도 지금까지 모은 나머지
                # 결과는 살리기 위해 이 파일만 스킵하고 계속 진행
                print(f"  스킵 (exiftool 실패: {e}): {fname}")
                continue
            if not expected_ok or rejected:
                print(f"  스킵 ({'기대 렌더러 아님' if not expected_ok else '편집된 파일'}): {fname}")
                os.remove(path)
                continue

            st = image_stats(img)
            results.append(dict(camera=camera, filename=fname, url=original_url, **st))
            n_ok += 1
            print(f"  [{n_ok}/{cfg['max_per_camera']}] {fname}  b2={st['b2']:.0f} w995={st['w995']:.0f} sat={st['sat']:.0f}")
            time.sleep(0.3)

    if not results:
        print("\n결과 없음")
        return

    with open(cfg["result_csv"], "w", newline="", encoding="utf-8") as f:
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

    print("\n=== 카메라별 ===")
    groups = defaultdict(list)
    for r in results:
        groups[r["camera"]].append(r)
    for cam, rows in groups.items():
        sv = [r for r in rows if r["dark_pct"] > 5]
        b2 = np.mean([r["b2"] for r in sv]) if sv else float("nan")
        w995 = np.mean([r["w995"] for r in rows])
        sat = np.mean([r["sat"] for r in rows])
        print(f"{cam:15s} n={len(rows):2d}  b2={b2:5.1f}  w995={w995:5.1f}  sat={sat:5.1f}")

    print(f"\n저장: {cfg['result_csv']}")


# ============================================================
# 후지: Film Mode별 population + 프리셋 방향 검증 (원래 analyze_fuji_film_modes.py)
# ============================================================
FUJI_FILM_MODE_CACHE_DIR = "raw_calib_cache_fuji"

FUJI_MODE_MAP = {
    "F0/Standard (Provia)": "Provia",
    "F1b/Studio Portrait Smooth Skin Tone (Astia)": "Astia",
    "F2/Fujichrome (Velvia)": "Velvia",
    "Classic Chrome": "Classic Chrome",
    "Pro Neg. Std": "Pro Neg Std",
}


def _read_fuji_film_modes(paths):
    out = subprocess.run(
        ["exiftool", "-json", "-FilmMode"] + paths,
        capture_output=True, text=True, timeout=120,
    )
    data = json.loads(out.stdout) if out.stdout.strip() else []
    return {d["SourceFile"]: d.get("FilmMode") for d in data}


def run_fuji_film_modes():
    from brands.fuji import apply_astia, apply_pro_neg_std

    jpeg_paths = sorted(glob.glob(os.path.join(FUJI_FILM_MODE_CACHE_DIR, "*", "jpeg", "*.jpg")) +
                         glob.glob(os.path.join(FUJI_FILM_MODE_CACHE_DIR, "*", "jpeg", "*.JPG")))
    film_modes = _read_fuji_film_modes(jpeg_paths)

    groups = defaultdict(list)
    for path in jpeg_paths:
        raw_mode = film_modes.get(path)
        label = FUJI_MODE_MAP.get(raw_mode)
        if not label:
            continue
        img = cv2.imread(path)
        if img is None:
            continue
        groups[label].append(image_stats(img))

    print("=== 실측 필름모드별 population 통계 ===")
    agg = {}
    for label, rows in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        b2 = np.mean([r['b2'] for r in rows])
        w995 = np.mean([r['w995'] for r in rows])
        sat = np.mean([r['sat'] for r in rows])
        agg[label] = dict(b2=b2, w995=w995, sat=sat, n=len(rows))
        print(f"{label:15s} n={len(rows):2d}  b2={b2:5.1f}  w995={w995:5.1f}  sat={sat:5.1f}")

    if "Provia" not in agg:
        print("\nProvia 기준 그룹이 없어서 프리셋 방향성 비교를 건너뜀")
        return

    print("\n=== 실측 델타 (필름모드 - Provia) vs 프리셋 델타 (프리셋(Provia사진) - Provia사진) ===")
    provia_paths = [p for p in jpeg_paths if FUJI_MODE_MAP.get(film_modes.get(p)) == "Provia"]

    # Provia 원본은 어느 프리셋을 적용하든 베이스 통계가 동일하므로 한
    # 번만 디코드+계산해서 재사용 (예전엔 프리셋마다, 게다가 필드마다
    # 따로 cv2.imread+image_stats를 다시 불러 최대 8배 중복 계산했음)
    provia_imgs = [img for img in (cv2.imread(p) for p in provia_paths) if img is not None]
    base_stats = [image_stats(img) for img in provia_imgs]
    base_sats = [s['sat'] for s in base_stats]
    base_b2s = [s['b2'] for s in base_stats]
    base_w995s = [s['w995'] for s in base_stats]

    preset_fns = {"Astia": apply_astia, "Pro Neg Std": apply_pro_neg_std}
    for label, fn in preset_fns.items():
        if label not in agg:
            print(f"{label}: 실측 표본 없어서 비교 불가")
            continue
        real_delta_sat = agg[label]['sat'] - agg['Provia']['sat']
        real_delta_b2 = agg[label]['b2'] - agg['Provia']['b2']
        real_delta_w995 = agg[label]['w995'] - agg['Provia']['w995']

        preset_stats = [image_stats(fn(img)) for img in provia_imgs]
        preset_sats = [s['sat'] for s in preset_stats]
        preset_b2s = [s['b2'] for s in preset_stats]
        preset_w995s = [s['w995'] for s in preset_stats]

        preset_delta_sat = np.mean(preset_sats) - np.mean(base_sats)
        preset_delta_b2 = np.mean(preset_b2s) - np.mean(base_b2s)
        preset_delta_w995 = np.mean(preset_w995s) - np.mean(base_w995s)

        def arrow(v):
            return "+" if v > 0 else ("-" if v < 0 else "0")

        print(f"\n[{label}] (실측 n={agg[label]['n']}, Provia n={len(provia_imgs)})")
        print(f"  채도  실측 {real_delta_sat:+6.1f} ({arrow(real_delta_sat)})  "
              f"프리셋 {preset_delta_sat:+6.1f} ({arrow(preset_delta_sat)})  "
              f"{'일치' if arrow(real_delta_sat) == arrow(preset_delta_sat) else '불일치'}")
        print(f"  블랙p2 실측 {real_delta_b2:+6.1f} ({arrow(real_delta_b2)})  "
              f"프리셋 {preset_delta_b2:+6.1f} ({arrow(preset_delta_b2)})  "
              f"{'일치' if arrow(real_delta_b2) == arrow(preset_delta_b2) else '불일치'}")
        print(f"  화이트p99.5 실측 {real_delta_w995:+6.1f} ({arrow(real_delta_w995)})  "
              f"프리셋 {preset_delta_w995:+6.1f} ({arrow(preset_delta_w995)})  "
              f"{'일치' if arrow(real_delta_w995) == arrow(preset_delta_w995) else '불일치'}")


# ============================================================
# 인물 서브셋 + 피부톤 hue 불변성 검증 (원래 portrait_skin_analysis.py)
# ============================================================
def run_portrait():
    from brands.hasselblad import apply_hncs

    detector = cv2.FaceDetectorYN_create("models/yunet.onnx", "", (320, 320), score_threshold=0.7)

    files = sorted(f for f in os.listdir(HASSELBLAD_CACHE_DIR) if f.lower().endswith(('.jpg', '.jpeg')))

    portraits = []
    hue_deltas = []
    for fname in files:
        path = os.path.join(HASSELBLAD_CACHE_DIR, fname)
        img = cv2.imread(path)
        if img is None:
            continue
        h, w = img.shape[:2]
        detector.setInputSize((w, h))
        _, faces = detector.detect(img)
        if faces is None or len(faces) == 0:
            continue

        # faces: [x, y, w, h, ...landmarks..., score] per row
        best = max(faces, key=lambda f: f[-1])
        face = tuple(int(v) for v in best[:4])
        st = image_stats(img)
        hue_before = region_hue(img, face)

        graded = apply_hncs(img)
        hue_after = region_hue(graded, face)

        portraits.append(dict(filename=fname, n_faces=len(faces), **st))
        if hue_before is not None and hue_after is not None:
            hue_deltas.append(dict(filename=fname, hue_before=hue_before, hue_after=hue_after,
                                    delta=hue_after - hue_before))

    print(f"=== 인물(얼굴 검출) 서브셋: {len(portraits)}/{len(files)}장 ===\n")

    if portraits:
        shadow_valid = [p for p in portraits if p['dark_pct'] > 5]
        b2_target = np.mean([p['b2'] for p in shadow_valid]) if shadow_valid else float('nan')
        w995_target = np.mean([p['w995'] for p in portraits])
        print(f"인물 블랙p2 타깃: {b2_target:.1f} (그림자유효 {len(shadow_valid)}장, "
              f"std={np.std([p['b2'] for p in shadow_valid]) if shadow_valid else 0:.1f})")
        print(f"인물 화이트p99.5 타깃: {w995_target:.1f} (std={np.std([p['w995'] for p in portraits]):.1f})")

    print(f"\n=== 피부톤 hue 불변성 검증 (apply_hncs 적용 전/후, {len(hue_deltas)}장) ===")
    for h in hue_deltas:
        print(f"  {h['filename']:40s} hue {h['hue_before']:5.1f} -> {h['hue_after']:5.1f}  (delta={h['delta']:+.1f})")
    if hue_deltas:
        deltas = [abs(h['delta']) for h in hue_deltas]
        print(f"\n  평균 |delta|={np.mean(deltas):.2f}, 최대={np.max(deltas):.2f}")

    with open("portrait_stats_result.csv", "w", newline='', encoding='utf-8-sig') as f:
        if portraits:
            writer = csv.DictWriter(f, fieldnames=list(portraits[0].keys()))
            writer.writeheader()
            writer.writerows(portraits)

    with open("skin_hue_result.csv", "w", newline='', encoding='utf-8-sig') as f:
        if hue_deltas:
            writer = csv.DictWriter(f, fieldnames=list(hue_deltas[0].keys()))
            writer.writeheader()
            writer.writerows(hue_deltas)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "hasselblad":
        run_hasselblad()
    elif mode in BRAND_CONFIGS:
        run_imaging_resource_brand(mode)
    elif mode == "fuji_film_modes":
        run_fuji_film_modes()
    elif mode == "portrait":
        run_portrait()
    else:
        print("usage: python3 -m tools.analyze [hasselblad|hasselblad_ir|leica|phaseone|pentax|ricoh_gr|fuji_film_modes|portrait]")
